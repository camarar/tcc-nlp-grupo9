"""UC-11 -- Pipeline de anonimizacao para uso analitico (LGPD).

Arquivo unico, Python 3.12, apenas biblioteca padrao.
"""

from __future__ import annotations

import copy
import datetime
import hashlib

CODES_VALIDOS = {
    "POLITICA_INVALIDA",
    "FINALIDADE_INVALIDA",
    "REGISTRO_INVALIDO",
    "CHAVE_INVALIDA",
}

ESTRATEGIAS_VALIDAS = {
    "MASCARA",
    "HASH",
    "INICIAIS",
    "DOMINIO",
    "GENERALIZAR",
    "REMOVER",
    "MANTER",
}

CAMPOS_SENSIVEIS_DENYLIST = {
    "cpf",
    "cnpj",
    "email",
    "telefone",
    "nome",
    "endereco",
    "cep",
    "rg",
    "data_nascimento",
}


class ErroAnonimizacao(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


class Anonimizador:
    def __init__(self, salt: str) -> None:
        if not salt:
            raise ErroAnonimizacao("POLITICA_INVALIDA", "salt vazio")
        self.salt = salt
        self._politicas: dict[str, dict[str, str]] = {}

    # ------------------------------------------------------------------
    # RF-01
    def registrar_politica(self, finalidade: str, regras: dict) -> None:
        if not finalidade:
            raise ErroAnonimizacao("POLITICA_INVALIDA", "finalidade vazia")
        if not regras:
            raise ErroAnonimizacao("POLITICA_INVALIDA", "regras vazias ou ausentes")
        for campo, estrategia in regras.items():
            if not campo:
                raise ErroAnonimizacao("POLITICA_INVALIDA", "nome de campo vazio")
            if estrategia not in ESTRATEGIAS_VALIDAS:
                raise ErroAnonimizacao(
                    "POLITICA_INVALIDA", f"estrategia fora do vocabulario: {estrategia!r}"
                )
        # substitui integralmente as regras anteriores da mesma finalidade
        self._politicas[finalidade] = dict(regras)

    # ------------------------------------------------------------------
    # RF-11 / RF-12
    def anonimizar(self, registro: dict, finalidade: str) -> dict:
        if finalidade not in self._politicas:
            raise ErroAnonimizacao(
                "FINALIDADE_INVALIDA", f"finalidade nao registrada: {finalidade!r}"
            )
        if not isinstance(registro, dict):
            raise ErroAnonimizacao("REGISTRO_INVALIDO", "registro nao e um dict")
        regras = self._politicas[finalidade]
        return self._processar_dict(registro, regras)

    def anonimizar_lote(self, registros: list, finalidade: str) -> list:
        # Atomico "de graca": uma list comprehension so retorna a lista completa
        # se todos os itens forem processados sem excecao; qualquer erro em
        # qualquer item propaga imediatamente e nenhum resultado parcial e
        # devolvido (all-or-nothing).
        return [self.anonimizar(registro, finalidade) for registro in registros]

    # ------------------------------------------------------------------
    # RF-13
    def chave_juncao(self, registro: dict) -> str:
        if not isinstance(registro, dict):
            raise ErroAnonimizacao("REGISTRO_INVALIDO", "registro nao e um dict")
        cpf = registro.get("cpf")
        if not cpf:
            raise ErroAnonimizacao("CHAVE_INVALIDA", "cpf ausente ou vazio")
        digitos = "".join(c for c in str(cpf) if c.isdigit())
        if not digitos:
            raise ErroAnonimizacao("CHAVE_INVALIDA", "cpf sem nenhum digito")
        return hashlib.sha256((self.salt + digitos).encode()).hexdigest()

    # ------------------------------------------------------------------
    # RF-14
    def campos_sensiveis(self, registro: dict) -> list[str]:
        if not isinstance(registro, dict):
            raise ErroAnonimizacao("REGISTRO_INVALIDO", "registro nao e um dict")
        encontrados: set[str] = set()
        self._coletar_sensiveis(registro, encontrados)
        return sorted(encontrados)

    # ------------------------------------------------------------------
    # Internos

    @staticmethod
    def _eh_lista_de_dicts(valor) -> bool:
        return isinstance(valor, list) and len(valor) > 0 and all(
            isinstance(item, dict) for item in valor
        )

    def _processar_dict(self, registro: dict, regras: dict) -> dict:
        resultado: dict = {}
        for campo, valor in registro.items():
            if isinstance(valor, dict):
                # containers (dict) sao sempre percorridos recursivamente,
                # declarados ou nao na politica -- e mantidos mesmo vazios.
                resultado[campo] = self._processar_dict(valor, regras)
            elif self._eh_lista_de_dicts(valor):
                resultado[campo] = [self._processar_dict(item, regras) for item in valor]
            else:
                # RF-11 (risco aceito): quando um campo esta declarado na
                # politica mas sua chave esta ausente do dict de entrada, nao
                # ha decisao de produto registrada. Adotamos aqui, como
                # decisao de engenharia provisoria (nao regra de negocio
                # confirmada), a remocao silenciosa: como so iteramos as
                # chaves presentes em `registro`, uma chave declarada porem
                # ausente simplesmente nunca aparece no resultado.
                if campo not in regras:
                    continue
                estrategia = regras[campo]
                if estrategia == "REMOVER":
                    continue
                resultado[campo] = self._aplicar_estrategia(estrategia, valor)
        return resultado

    def _aplicar_estrategia(self, estrategia: str, valor):
        # RF-09: None atravessa qualquer estrategia sem erro e sem alteracao.
        if valor is None:
            return None

        if estrategia == "MASCARA":
            texto = str(valor)
            n = len(texto)
            if n <= 2:
                return texto
            return "*" * (n - 2) + texto[-2:]

        if estrategia == "HASH":
            return hashlib.sha256((self.salt + str(valor)).encode()).hexdigest()

        if estrategia == "INICIAIS":
            palavras = str(valor).split()
            return "".join(palavra[0].upper() + "." for palavra in palavras)

        if estrategia == "DOMINIO":
            if not isinstance(valor, str) or "@" not in valor:
                raise ErroAnonimizacao("REGISTRO_INVALIDO", f"valor sem '@': {valor!r}")
            dominio = valor.split("@", 1)[1]
            return "*@" + dominio

        if estrategia == "GENERALIZAR":
            if isinstance(valor, bool):
                raise ErroAnonimizacao(
                    "REGISTRO_INVALIDO", "bool nao suportado por GENERALIZAR"
                )
            if isinstance(valor, datetime.date):
                return valor.year
            if isinstance(valor, int):
                base = (valor // 10) * 10
                return f"{base}-{base + 9}"
            raise ErroAnonimizacao(
                "REGISTRO_INVALIDO",
                f"tipo nao suportado por GENERALIZAR: {type(valor).__name__}",
            )

        # MANTER: unica estrategia que preserva o valor original; copia para
        # respeitar a propriedade "nao destrutivo" (RF-16).
        return copy.deepcopy(valor)

    def _coletar_sensiveis(self, obj, encontrados: set) -> None:
        if isinstance(obj, dict):
            for campo, valor in obj.items():
                if isinstance(valor, dict):
                    self._coletar_sensiveis(valor, encontrados)
                elif self._eh_lista_de_dicts(valor):
                    for item in valor:
                        self._coletar_sensiveis(item, encontrados)
                else:
                    # Coerente com RF-10: a denylist so se aplica a valores
                    # escalares (folhas); campos-container sao apenas
                    # percorridos, nunca marcados como sensiveis por si so.
                    if campo in CAMPOS_SENSIVEIS_DENYLIST:
                        encontrados.add(campo)
