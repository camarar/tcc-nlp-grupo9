"""UC-19 — Trilha de auditoria à prova de adulteração."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Callable

GENESIS = "0" * 64

DENYLIST_PADRAO = ["cpf", "cnpj", "senha", "password", "email", "telefone", "cartao"]
RETENCAO_DIAS_PADRAO = 365

RESULTADOS_VALIDOS = {"SUCESSO", "FALHA", "NEGADO"}
FILTROS_VALIDOS = {"actor_id", "action", "resource", "result", "desde", "ate"}


class ErroAuditoria(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


def _filtrar_payload(valor, denylist_lower: set[str]):
    if isinstance(valor, dict):
        novo = {}
        for chave, sub in valor.items():
            if isinstance(chave, str) and chave.lower() in denylist_lower:
                continue
            novo[chave] = _filtrar_payload(sub, denylist_lower)
        return novo
    if isinstance(valor, list):
        return [_filtrar_payload(item, denylist_lower) for item in valor]
    return valor


def _serializar(registro: dict) -> str:
    dados = {k: v for k, v in registro.items() if k not in ("hash", "hash_anterior")}
    return json.dumps(dados, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


class TrilhaAuditoria:
    def __init__(self, relogio: Callable[[], datetime] | None = None) -> None:
        self._relogio = relogio or (lambda: datetime.now(tz=None))
        self._registros: list[dict] = []
        self._denylist: set[str] = set(DENYLIST_PADRAO)
        self._retencao_dias: int = RETENCAO_DIAS_PADRAO

    def configurar(self, config: dict) -> None:
        retencao_dias = config.get("retencao_dias", self._retencao_dias)
        denylist = config.get("denylist", None)

        if not isinstance(retencao_dias, int) or isinstance(retencao_dias, bool) or retencao_dias < 1:
            raise ErroAuditoria("POLITICA_INVALIDA", "retencao_dias deve ser inteiro >= 1")

        if denylist is not None:
            if not isinstance(denylist, list) or not all(isinstance(item, str) for item in denylist):
                raise ErroAuditoria("POLITICA_INVALIDA", "denylist deve ser lista de strings")
            self._denylist = {item.lower() for item in denylist}

        self._retencao_dias = retencao_dias

    def registrar(self, evento: dict) -> str:
        actor_id = evento.get("actor_id")
        action = evento.get("action")
        resource = evento.get("resource")
        result = evento.get("result")
        payload = evento.get("payload", {})

        if not isinstance(actor_id, str) or not actor_id:
            raise ErroAuditoria("REGISTRO_INVALIDO", "actor_id obrigatorio")
        if not isinstance(action, str) or not action:
            raise ErroAuditoria("REGISTRO_INVALIDO", "action obrigatorio")
        if not isinstance(resource, str) or not resource:
            raise ErroAuditoria("REGISTRO_INVALIDO", "resource obrigatorio")
        if not isinstance(result, str) or result not in RESULTADOS_VALIDOS:
            raise ErroAuditoria("REGISTRO_INVALIDO", "result invalido")
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            raise ErroAuditoria("REGISTRO_INVALIDO", "payload deve ser dict")

        payload_filtrado = _filtrar_payload(payload, self._denylist)

        timestamp_utc = self._relogio()
        indice = len(self._registros)
        hash_anterior = self._registros[-1]["hash"] if self._registros else GENESIS

        registro = {
            "indice": indice,
            "timestamp_utc": timestamp_utc,
            "actor_id": actor_id,
            "action": action,
            "resource": resource,
            "result": result,
            "payload": payload_filtrado,
            "hash_anterior": hash_anterior,
        }
        digest = hashlib.sha256((hash_anterior + _serializar(registro)).encode("utf-8")).hexdigest()
        registro["hash"] = digest

        self._registros.append(registro)
        return digest

    def consultar(self, filtros: dict) -> list[dict]:
        chaves_invalidas = set(filtros) - FILTROS_VALIDOS
        if chaves_invalidas:
            raise ErroAuditoria("CONSULTA_INVALIDA", f"filtros invalidos: {chaves_invalidas}")

        desde = filtros.get("desde")
        ate = filtros.get("ate")
        if desde is not None and ate is not None and desde > ate:
            raise ErroAuditoria("CONSULTA_INVALIDA", "desde > ate")

        resultado = []
        for registro in self._registros:
            if "actor_id" in filtros and registro["actor_id"] != filtros["actor_id"]:
                continue
            if "action" in filtros and registro["action"] != filtros["action"]:
                continue
            if "resource" in filtros and registro["resource"] != filtros["resource"]:
                continue
            if "result" in filtros and registro["result"] != filtros["result"]:
                continue
            if desde is not None and registro["timestamp_utc"] < desde:
                continue
            if ate is not None and registro["timestamp_utc"] > ate:
                continue
            resultado.append(deepcopy(registro))

        resultado.sort(key=lambda r: r["timestamp_utc"])
        return resultado

    def verificar_integridade(self) -> dict:
        total = len(self._registros)
        hash_anterior_esperado = GENESIS

        for registro in self._registros:
            if registro["hash_anterior"] != hash_anterior_esperado:
                return {"integra": False, "total": total, "primeiro_divergente": registro["indice"]}
            digest_esperado = hashlib.sha256(
                (registro["hash_anterior"] + _serializar(registro)).encode("utf-8")
            ).hexdigest()
            if registro["hash"] != digest_esperado:
                return {"integra": False, "total": total, "primeiro_divergente": registro["indice"]}
            hash_anterior_esperado = registro["hash"]

        return {"integra": True, "total": total, "primeiro_divergente": None}

    def expurgar(self, quando: datetime) -> int:
        limite = quando - timedelta(days=self._retencao_dias)
        remanescentes = [r for r in self._registros if r["timestamp_utc"] >= limite]
        descartados = len(self._registros) - len(remanescentes)

        if descartados == 0:
            return 0

        hash_anterior = GENESIS
        for novo_indice, registro in enumerate(remanescentes):
            registro["indice"] = novo_indice
            registro["hash_anterior"] = hash_anterior
            digest = hashlib.sha256(
                (hash_anterior + _serializar(registro)).encode("utf-8")
            ).hexdigest()
            registro["hash"] = digest
            hash_anterior = digest

        self._registros = remanescentes
        return descartados

    def exportar(self) -> list[dict]:
        return [deepcopy(registro) for registro in self._registros]
