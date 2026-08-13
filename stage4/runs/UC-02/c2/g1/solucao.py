"""UC-02 - Motor de cadastro e deduplicacao de clientes."""

from __future__ import annotations

import unicodedata
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable


class ErroCadastro(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


_CAMPOS_ATUALIZAVEIS = {"nome", "email", "telefone"}

_PESOS = {
    "DOCUMENTO": Decimal("1.00"),
    "EMAIL": Decimal("0.50"),
    "TELEFONE": Decimal("0.30"),
    "NOME": Decimal("0.20"),
}

_LIMIAR = Decimal("0.50")


def _normalizar_nome(nome: str) -> str:
    nome = nome.strip()
    nome = " ".join(nome.split())
    nome = unicodedata.normalize("NFKD", nome)
    nome = "".join(ch for ch in nome if not unicodedata.combining(ch))
    return nome.upper()


def _normalizar_email(email: str | None) -> str | None:
    if email is None:
        return None
    email = email.strip().lower()
    return email or None


def _normalizar_telefone(telefone: str | None) -> str | None:
    if telefone is None:
        return None
    digitos = "".join(ch for ch in telefone if ch.isdigit())
    return digitos or None


def _somente_digitos(documento: str) -> str:
    return "".join(ch for ch in documento if ch.isdigit())


def _digito_verificador_modulo11(base: str, pesos_iniciais: int) -> int:
    peso = pesos_iniciais
    soma = 0
    for ch in base:
        soma += int(ch) * peso
        peso -= 1
        if peso < 2:
            peso = 11
    resto = soma % 11
    dv = 0 if resto < 2 else 11 - resto
    return dv


def _cpf_valido(doc: str) -> bool:
    if len(doc) != 11:
        return False
    if doc == doc[0] * 11:
        return False
    dv1 = _digito_verificador_modulo11(doc[:9], 10)
    dv2 = _digito_verificador_modulo11(doc[:9] + str(dv1), 11)
    return doc[9] == str(dv1) and doc[10] == str(dv2)


def _cnpj_valido(doc: str) -> bool:
    if len(doc) != 14:
        return False
    if doc == doc[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    def calc(base: str, pesos: list[int]) -> int:
        soma = sum(int(d) * p for d, p in zip(base, pesos))
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto

    dv1 = calc(doc[:12], pesos1)
    dv2 = calc(doc[:12] + str(dv1), pesos2)
    return doc[12] == str(dv1) and doc[13] == str(dv2)


def _validar_documento(documento: str, tipo: str) -> str:
    limpo = _somente_digitos(documento)
    if tipo == "PF":
        if not _cpf_valido(limpo):
            raise ErroCadastro("DOCUMENTO_INVALIDO", "CPF invalido")
    else:
        if not _cnpj_valido(limpo):
            raise ErroCadastro("DOCUMENTO_INVALIDO", "CNPJ invalido")
    return limpo


class MotorCadastro:
    def __init__(self, agora: Callable[[], datetime] | None = None) -> None:
        self._agora = agora or datetime.now
        self._cadastros: dict[str, dict[str, Any]] = {}
        self._historicos: dict[str, list[dict[str, Any]]] = {}

    def _novo_id(self) -> str:
        return uuid.uuid4().hex

    def _exigir_cadastro(self, cadastro_id: str) -> dict[str, Any]:
        cadastro = self._cadastros.get(cadastro_id)
        if cadastro is None:
            raise ErroCadastro("CADASTRO_NAO_ENCONTRADO", cadastro_id)
        return cadastro

    def _registrar_evento(self, cadastro_id: str, acao: str, campo: str | None,
                           de: Any, para: Any, ator: str) -> None:
        self._historicos[cadastro_id].append({
            "em": self._agora(),
            "ator": ator,
            "acao": acao,
            "campo": campo,
            "de": de,
            "para": para,
        })

    def registrar(self, dados: dict) -> str:
        documento = dados.get("documento")
        nome = dados.get("nome")
        tipo = dados.get("tipo")
        email = dados.get("email")
        telefone = dados.get("telefone")

        if documento is None or not str(documento).strip():
            raise ErroCadastro("CAMPO_OBRIGATORIO", "documento")
        if nome is None or not str(nome).strip():
            raise ErroCadastro("CAMPO_OBRIGATORIO", "nome")
        if tipo is None or not str(tipo).strip():
            raise ErroCadastro("CAMPO_OBRIGATORIO", "tipo")

        doc_normalizado = _validar_documento(str(documento), tipo)

        for outro in self._cadastros.values():
            if outro["documento"] == doc_normalizado and outro["situacao"] == "ATIVO":
                raise ErroCadastro("DUPLICADO", doc_normalizado)

        cadastro_id = self._novo_id()
        cadastro = {
            "cadastro_id": cadastro_id,
            "documento": doc_normalizado,
            "nome": _normalizar_nome(str(nome)),
            "email": _normalizar_email(email),
            "telefone": _normalizar_telefone(telefone),
            "tipo": tipo,
            "situacao": "ATIVO",
            "mesclado_em": None,
        }
        self._cadastros[cadastro_id] = cadastro
        self._historicos[cadastro_id] = []
        self._registrar_evento(cadastro_id, "REGISTRO", None, None, None, "sistema")
        return cadastro_id

    def obter(self, cadastro_id: str) -> dict:
        cadastro = self._exigir_cadastro(cadastro_id)
        return dict(cadastro)

    def atualizar(self, cadastro_id: str, campos: dict, ator: str) -> dict:
        cadastro = self._exigir_cadastro(cadastro_id)
        if cadastro["situacao"] != "ATIVO":
            raise ErroCadastro("ESTADO_INVALIDO", cadastro["situacao"])

        for chave in campos:
            if chave not in _CAMPOS_ATUALIZAVEIS:
                raise ErroCadastro("CAMPO_OBRIGATORIO", chave)
        if "nome" in campos:
            novo_nome = campos["nome"]
            if novo_nome is None or not str(novo_nome).strip():
                raise ErroCadastro("CAMPO_OBRIGATORIO", "nome")

        mudancas: list[tuple[str, Any, Any]] = []
        if "nome" in campos:
            novo = _normalizar_nome(str(campos["nome"]))
            if novo != cadastro["nome"]:
                mudancas.append(("nome", cadastro["nome"], novo))
        if "email" in campos:
            novo = _normalizar_email(campos["email"])
            if novo != cadastro["email"]:
                mudancas.append(("email", cadastro["email"], novo))
        if "telefone" in campos:
            novo = _normalizar_telefone(campos["telefone"])
            if novo != cadastro["telefone"]:
                mudancas.append(("telefone", cadastro["telefone"], novo))

        for campo, de, para in mudancas:
            cadastro[campo] = para
            self._registrar_evento(cadastro_id, "ALTERACAO", campo, de, para, ator)

        return dict(cadastro)

    def _score(self, a: dict, b: dict) -> tuple[Decimal, list[str]]:
        score = Decimal("0.00")
        criterios: list[str] = []
        if a["documento"] and b["documento"] and a["documento"] == b["documento"]:
            score += _PESOS["DOCUMENTO"]
            criterios.append("DOCUMENTO")
        if a["email"] and b["email"] and a["email"] == b["email"]:
            score += _PESOS["EMAIL"]
            criterios.append("EMAIL")
        if a["telefone"] and b["telefone"] and a["telefone"] == b["telefone"]:
            score += _PESOS["TELEFONE"]
            criterios.append("TELEFONE")
        if a["nome"] and b["nome"] and a["nome"] == b["nome"]:
            score += _PESOS["NOME"]
            criterios.append("NOME")
        return score, criterios

    def buscar_duplicados(self, cadastro_id: str) -> list[dict]:
        cadastro = self._exigir_cadastro(cadastro_id)
        if cadastro["situacao"] == "MESCLADO":
            raise ErroCadastro("ESTADO_INVALIDO", cadastro["situacao"])

        resultados = []
        for outro_id, outro in self._cadastros.items():
            if outro_id == cadastro_id:
                continue
            if outro["situacao"] not in ("ATIVO", "INATIVO"):
                continue
            score, criterios = self._score(cadastro, outro)
            if score >= _LIMIAR:
                resultados.append({"cadastro_id": outro_id, "score": score, "criterios": criterios})

        resultados.sort(key=lambda r: (-r["score"], r["cadastro_id"]))
        return resultados

    def mesclar(self, principal_id: str, secundario_id: str, ator: str) -> str:
        principal = self._exigir_cadastro(principal_id)
        secundario = self._exigir_cadastro(secundario_id)

        if principal["situacao"] != "ATIVO" or secundario["situacao"] != "ATIVO":
            raise ErroCadastro("ESTADO_INVALIDO")

        if principal_id == secundario_id:
            raise ErroCadastro("CONFLITO_MERGE")

        score, _ = self._score(principal, secundario)
        if score < _LIMIAR:
            raise ErroCadastro("CONFLITO_MERGE")

        if not principal["email"] and secundario["email"]:
            de = principal["email"]
            principal["email"] = secundario["email"]
            self._registrar_evento(principal_id, "ALTERACAO", "email", de, principal["email"], ator)
        if not principal["telefone"] and secundario["telefone"]:
            de = principal["telefone"]
            principal["telefone"] = secundario["telefone"]
            self._registrar_evento(principal_id, "ALTERACAO", "telefone", de, principal["telefone"], ator)

        secundario["situacao"] = "MESCLADO"
        secundario["mesclado_em"] = self._agora()

        self._registrar_evento(principal_id, "MERGE_DESTINO", None, None, None, ator)
        self._registrar_evento(secundario_id, "MERGE_ORIGEM", None, None, None, ator)

        return principal_id

    def inativar(self, cadastro_id: str, ator: str) -> None:
        cadastro = self._exigir_cadastro(cadastro_id)
        if cadastro["situacao"] != "ATIVO":
            raise ErroCadastro("ESTADO_INVALIDO", cadastro["situacao"])
        cadastro["situacao"] = "INATIVO"
        self._registrar_evento(cadastro_id, "INATIVACAO", None, None, None, ator)

    def historico(self, cadastro_id: str) -> list[dict]:
        self._exigir_cadastro(cadastro_id)
        return [dict(evento) for evento in self._historicos[cadastro_id]]

    def situacao(self, cadastro_id: str) -> str:
        cadastro = self._exigir_cadastro(cadastro_id)
        return cadastro["situacao"]
