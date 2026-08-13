"""UC-11 — Pipeline de anonimização para uso analítico (LGPD)."""

from __future__ import annotations

import copy
import datetime
import hashlib
import re

_ESTRATEGIAS_VALIDAS = {
    "MASCARA", "HASH", "INICIAIS", "DOMINIO", "GENERALIZAR", "REMOVER", "MANTER",
}

_CAMPOS_SENSIVEIS_DENYLIST = {
    "cpf", "cnpj", "email", "telefone", "nome", "endereco", "cep", "rg",
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
        self._salt = salt
        self._politicas: dict[str, dict] = {}

    def registrar_politica(self, finalidade: str, regras: dict) -> None:
        if not finalidade:
            raise ErroAnonimizacao("POLITICA_INVALIDA", "finalidade vazia")
        if not regras:
            raise ErroAnonimizacao("POLITICA_INVALIDA", "regras vazias")
        for nome_campo, estrategia in regras.items():
            if not nome_campo:
                raise ErroAnonimizacao("POLITICA_INVALIDA", "nome de campo vazio")
            if estrategia not in _ESTRATEGIAS_VALIDAS:
                raise ErroAnonimizacao("POLITICA_INVALIDA", "estrategia invalida")
        self._politicas[finalidade] = dict(regras)

    def anonimizar(self, registro: dict, finalidade: str) -> dict:
        if not isinstance(registro, dict):
            raise ErroAnonimizacao("REGISTRO_INVALIDO", "registro nao e dict")
        if finalidade not in self._politicas:
            raise ErroAnonimizacao("FINALIDADE_INVALIDA", "finalidade nao registrada")
        regras = self._politicas[finalidade]
        return self._processar_dict(registro, regras)

    def anonimizar_lote(self, registros: list[dict], finalidade: str) -> list[dict]:
        return [self.anonimizar(r, finalidade) for r in registros]

    def chave_juncao(self, registro: dict) -> str:
        if not isinstance(registro, dict):
            raise ErroAnonimizacao("REGISTRO_INVALIDO", "registro nao e dict")
        cpf = registro.get("cpf")
        digitos = re.sub(r"\D", "", str(cpf)) if cpf is not None else ""
        if not digitos:
            raise ErroAnonimizacao("CHAVE_INVALIDA", "cpf ausente ou sem digitos")
        return hashlib.sha256((self._salt + digitos).encode()).hexdigest()

    def campos_sensiveis(self, registro: dict) -> list[str]:
        if not isinstance(registro, dict):
            raise ErroAnonimizacao("REGISTRO_INVALIDO", "registro nao e dict")
        encontrados: set[str] = set()
        self._coletar_sensiveis(registro, encontrados)
        return sorted(encontrados)

    def _coletar_sensiveis(self, valor, encontrados: set[str]) -> None:
        if isinstance(valor, dict):
            for chave, sub in valor.items():
                if chave in _CAMPOS_SENSIVEIS_DENYLIST:
                    encontrados.add(chave)
                self._coletar_sensiveis(sub, encontrados)
        elif isinstance(valor, list):
            for item in valor:
                self._coletar_sensiveis(item, encontrados)

    def _processar_dict(self, dados: dict, regras: dict) -> dict:
        resultado: dict = {}
        for chave, valor in dados.items():
            if isinstance(valor, dict):
                resultado[chave] = self._processar_dict(valor, regras)
            elif isinstance(valor, list) and self._e_lista_de_dicts(valor):
                resultado[chave] = [self._processar_dict(item, regras) for item in valor]
            else:
                if chave not in regras:
                    continue
                estrategia = regras[chave]
                if estrategia == "REMOVER":
                    continue
                resultado[chave] = self._aplicar_estrategia(estrategia, valor)
        return resultado

    @staticmethod
    def _e_lista_de_dicts(valor: list) -> bool:
        return len(valor) > 0 and all(isinstance(item, dict) for item in valor)

    def _aplicar_estrategia(self, estrategia: str, valor):
        if estrategia == "MANTER":
            return copy.deepcopy(valor)
        if valor is None and estrategia in {"MASCARA", "HASH", "INICIAIS", "DOMINIO", "GENERALIZAR"}:
            return None
        if estrategia == "MASCARA":
            return self._mascara(valor)
        if estrategia == "HASH":
            return hashlib.sha256((self._salt + str(valor)).encode()).hexdigest()
        if estrategia == "INICIAIS":
            return self._iniciais(valor)
        if estrategia == "DOMINIO":
            return self._dominio(valor)
        if estrategia == "GENERALIZAR":
            return self._generalizar(valor)
        raise ErroAnonimizacao("POLITICA_INVALIDA", "estrategia invalida")

    @staticmethod
    def _mascara(valor) -> str:
        texto = str(valor)
        if len(texto) <= 2:
            return texto
        return "*" * (len(texto) - 2) + texto[-2:]

    @staticmethod
    def _iniciais(valor) -> str:
        texto = str(valor)
        palavras = texto.split()
        return "".join(p[0].upper() + "." for p in palavras)

    @staticmethod
    def _dominio(valor) -> str:
        texto = str(valor)
        if "@" not in texto:
            raise ErroAnonimizacao("REGISTRO_INVALIDO", "email sem @")
        dominio = texto.split("@", 1)[1]
        return "*@" + dominio

    @staticmethod
    def _generalizar(valor):
        if isinstance(valor, datetime.date):
            return valor.year
        if isinstance(valor, int):
            piso = (valor // 10) * 10
            return f"{piso}-{piso + 9}"
        raise ErroAnonimizacao("REGISTRO_INVALIDO", "tipo invalido para GENERALIZAR")
