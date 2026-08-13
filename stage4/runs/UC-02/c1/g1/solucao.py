"""UC-02 — Motor de cadastro e deduplicação de clientes."""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable


class ErroCadastro(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code
        self.mensagem = mensagem


def _vazio(valor: Any) -> bool:
    return valor is None or (isinstance(valor, str) and valor.strip() == "")


def _norm_nome(valor: Any) -> str:
    s = valor or ""
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    s = s.upper()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s


def _norm_email(valor: Any) -> str | None:
    if valor is None:
        return None
    return valor.strip().lower()


def _norm_telefone(valor: Any) -> str | None:
    if valor is None:
        return None
    return re.sub(r"\D", "", valor)


def _digito_verificador(digitos: list[int], pesos: range) -> int:
    soma = sum(d * p for d, p in zip(digitos, pesos))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def _validar_cpf(documento: str) -> bool:
    nums = [int(c) for c in documento]
    base = nums[:9]
    d10 = _digito_verificador(base, range(10, 1, -1))
    d11 = _digito_verificador(base + [d10], range(11, 1, -1))
    return nums[9] == d10 and nums[10] == d11


def _validar_cnpj(documento: str) -> bool:
    nums = [int(c) for c in documento]
    base = nums[:12]
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma1 = sum(d * p for d, p in zip(base, pesos1))
    resto1 = soma1 % 11
    d13 = 0 if resto1 < 2 else 11 - resto1
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma2 = sum(d * p for d, p in zip(base + [d13], pesos2))
    resto2 = soma2 % 11
    d14 = 0 if resto2 < 2 else 11 - resto2
    return nums[12] == d13 and nums[13] == d14


class MotorCadastro:
    def __init__(self, agora: Callable[[], datetime] | None = None) -> None:
        self._agora = agora or datetime.now
        self._registros: dict[str, dict[str, Any]] = {}
        self._historico: dict[str, list[dict[str, Any]]] = {}

    def _get_registro(self, cadastro_id: str) -> dict[str, Any]:
        rec = self._registros.get(cadastro_id)
        if rec is None:
            raise ErroCadastro("CADASTRO_NAO_ENCONTRADO")
        return rec

    def _add_historico(self, cadastro_id: str, ator: str, acao: str,
                        campo: str | None = None, de: Any = None, para: Any = None) -> None:
        self._historico[cadastro_id].append({
            "em": self._agora(),
            "ator": ator,
            "acao": acao,
            "campo": campo,
            "de": de,
            "para": para,
        })

    @staticmethod
    def _score(a: dict[str, Any], b: dict[str, Any]) -> tuple[Decimal, list[str]]:
        criterios: list[str] = []
        total = Decimal("0.00")
        if a["documento"] and b["documento"] and a["documento"] == b["documento"]:
            total += Decimal("1.00")
            criterios.append("DOCUMENTO")
        if a["email"] and b["email"] and a["email"] == b["email"]:
            total += Decimal("0.50")
            criterios.append("EMAIL")
        if a["telefone"] and b["telefone"] and a["telefone"] == b["telefone"]:
            total += Decimal("0.30")
            criterios.append("TELEFONE")
        if a["nome"] and b["nome"] and a["nome"] == b["nome"]:
            total += Decimal("0.20")
            criterios.append("NOME")
        return total, criterios

    def registrar(self, dados: dict) -> str:
        documento_raw = dados.get("documento")
        nome_raw = dados.get("nome")
        tipo_raw = dados.get("tipo")
        email_raw = dados.get("email")
        telefone_raw = dados.get("telefone")

        if _vazio(documento_raw) or _vazio(nome_raw) or _vazio(tipo_raw):
            raise ErroCadastro("CAMPO_OBRIGATORIO")
        if tipo_raw not in ("PF", "PJ"):
            raise ErroCadastro("CAMPO_OBRIGATORIO")

        documento = re.sub(r"\D", "", documento_raw)
        tamanho_esperado = 11 if tipo_raw == "PF" else 14
        if len(documento) != tamanho_esperado:
            raise ErroCadastro("DOCUMENTO_INVALIDO")
        if len(set(documento)) == 1:
            raise ErroCadastro("DOCUMENTO_INVALIDO")
        valido = _validar_cpf(documento) if tipo_raw == "PF" else _validar_cnpj(documento)
        if not valido:
            raise ErroCadastro("DOCUMENTO_INVALIDO")

        nome = _norm_nome(nome_raw)
        email = _norm_email(email_raw)
        telefone = _norm_telefone(telefone_raw)

        for rec in self._registros.values():
            if rec["documento"] == documento and rec["situacao"] == "ATIVO":
                raise ErroCadastro("DUPLICADO")

        cadastro_id = uuid.uuid4().hex
        self._registros[cadastro_id] = {
            "cadastro_id": cadastro_id,
            "documento": documento,
            "nome": nome,
            "email": email,
            "telefone": telefone,
            "tipo": tipo_raw,
            "situacao": "ATIVO",
            "mesclado_em": None,
        }
        self._historico[cadastro_id] = []
        self._add_historico(cadastro_id, ator="SISTEMA", acao="REGISTRO")
        return cadastro_id

    def obter(self, cadastro_id: str) -> dict:
        return dict(self._get_registro(cadastro_id))

    def atualizar(self, cadastro_id: str, campos: dict, ator: str) -> dict:
        rec = self._get_registro(cadastro_id)
        if rec["situacao"] != "ATIVO":
            raise ErroCadastro("ESTADO_INVALIDO")

        permitido = {"nome", "email", "telefone"}
        for chave in campos:
            if chave not in permitido:
                raise ErroCadastro("CAMPO_OBRIGATORIO")

        novos: dict[str, Any] = {}
        for chave, valor in campos.items():
            if chave == "nome":
                novo = _norm_nome(valor)
                if novo == "":
                    raise ErroCadastro("CAMPO_OBRIGATORIO")
            elif chave == "email":
                novo = _norm_email(valor)
            else:
                novo = _norm_telefone(valor)
            novos[chave] = novo

        for chave, novo in novos.items():
            antigo = rec[chave]
            if antigo != novo:
                rec[chave] = novo
                self._add_historico(cadastro_id, ator=ator, acao="ALTERACAO",
                                     campo=chave, de=antigo, para=novo)

        return dict(rec)

    def buscar_duplicados(self, cadastro_id: str) -> list[dict]:
        alvo = self._get_registro(cadastro_id)
        if alvo["situacao"] == "MESCLADO":
            raise ErroCadastro("ESTADO_INVALIDO")

        resultados = []
        for oid, rec in self._registros.items():
            if oid == cadastro_id:
                continue
            if rec["situacao"] not in ("ATIVO", "INATIVO"):
                continue
            score, criterios = self._score(alvo, rec)
            if score >= Decimal("0.50"):
                resultados.append({"cadastro_id": oid, "score": score, "criterios": criterios})

        resultados.sort(key=lambda d: (-d["score"], d["cadastro_id"]))
        return resultados

    def mesclar(self, principal_id: str, secundario_id: str, ator: str) -> str:
        principal = self._get_registro(principal_id)
        secundario = self._get_registro(secundario_id)

        if principal["situacao"] != "ATIVO" or secundario["situacao"] != "ATIVO":
            raise ErroCadastro("ESTADO_INVALIDO")

        if principal_id == secundario_id:
            raise ErroCadastro("CONFLITO_MERGE")

        score, _criterios = self._score(principal, secundario)
        if score < Decimal("0.50"):
            raise ErroCadastro("CONFLITO_MERGE")

        for campo in ("email", "telefone"):
            if _vazio(principal[campo]) and not _vazio(secundario[campo]):
                principal[campo] = secundario[campo]

        secundario["situacao"] = "MESCLADO"
        secundario["mesclado_em"] = self._agora()

        self._add_historico(principal_id, ator=ator, acao="MERGE_DESTINO")
        self._add_historico(secundario_id, ator=ator, acao="MERGE_ORIGEM")

        return principal_id

    def inativar(self, cadastro_id: str, ator: str) -> None:
        rec = self._get_registro(cadastro_id)
        if rec["situacao"] != "ATIVO":
            raise ErroCadastro("ESTADO_INVALIDO")
        rec["situacao"] = "INATIVO"
        self._add_historico(cadastro_id, ator=ator, acao="INATIVACAO")

    def historico(self, cadastro_id: str) -> list[dict]:
        self._get_registro(cadastro_id)
        return list(self._historico[cadastro_id])

    def situacao(self, cadastro_id: str) -> str:
        return self._get_registro(cadastro_id)["situacao"]
