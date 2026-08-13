"""UC-21 — Orquestrador de estornos e chargebacks.

Implementação em biblioteca padrão apenas, com valores monetários em
``decimal.Decimal`` e datas/instantes em ``datetime`` timezone-aware.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Callable, Optional

CENTAVOS = Decimal("0.01")

ESTADO_AUTORIZADO = "AUTORIZADO"
ESTADO_CAPTURADO_PARCIAL = "CAPTURADO_PARCIAL"
ESTADO_CAPTURADO = "CAPTURADO"
ESTADO_ESTORNADO_PARCIAL = "ESTORNADO_PARCIAL"
ESTADO_ESTORNADO = "ESTORNADO"
ESTADO_CHARGEBACK_PARCIAL = "CHARGEBACK_PARCIAL"
ESTADO_CHARGEBACK = "CHARGEBACK"

TIPO_REGISTRO = "REGISTRO"
TIPO_CAPTURA = "CAPTURA"
TIPO_ESTORNO = "ESTORNO"
TIPO_CHARGEBACK = "CHARGEBACK"

_ESTADOS_CAPTURAVEIS = {ESTADO_AUTORIZADO, ESTADO_CAPTURADO_PARCIAL}
_ESTADOS_ESTORNAVEIS = {
    ESTADO_CAPTURADO_PARCIAL, ESTADO_CAPTURADO, ESTADO_ESTORNADO_PARCIAL,
}
_ESTADOS_CHARGEBACKAVEIS = {
    ESTADO_CAPTURADO_PARCIAL, ESTADO_CAPTURADO,
    ESTADO_ESTORNADO_PARCIAL, ESTADO_CHARGEBACK_PARCIAL,
}


class ErroPagamento(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


def _validar_pagamento_id(pagamento_id) -> str:
    if not isinstance(pagamento_id, str) or not pagamento_id.strip():
        raise ErroPagamento("PAGAMENTO_INVALIDO", "pagamento_id invalido")
    return pagamento_id


def _validar_operacao_id(operacao_id) -> str:
    if not isinstance(operacao_id, str) or not operacao_id.strip():
        raise ErroPagamento("PAGAMENTO_INVALIDO", "operacao_id invalido")
    return operacao_id


def _validar_moeda(moeda) -> str:
    if not isinstance(moeda, str):
        raise ErroPagamento("MOEDA_INVALIDA", "moeda invalida")
    m = moeda.strip().upper()
    if len(m) != 3 or not m.isalpha():
        raise ErroPagamento("MOEDA_INVALIDA", "moeda invalida")
    return m


def _validar_data(instante) -> datetime:
    if not isinstance(instante, datetime):
        raise ErroPagamento("DATA_INVALIDA", "data invalida")
    if instante.tzinfo is None or instante.tzinfo.utcoffset(instante) is None:
        raise ErroPagamento("DATA_INVALIDA", "data sem timezone")
    return instante


def _to_decimal(valor, permitir_zero: bool = False) -> Decimal:
    if isinstance(valor, bool) or valor is None:
        raise ErroPagamento("VALOR_INVALIDO", "valor invalido")
    if isinstance(valor, Decimal):
        d = valor
    elif isinstance(valor, int):
        d = Decimal(valor)
    elif isinstance(valor, float):
        if not math.isfinite(valor):
            raise ErroPagamento("VALOR_INVALIDO", "valor invalido")
        d = Decimal(str(valor))
    elif isinstance(valor, str):
        try:
            d = Decimal(valor.strip())
        except (InvalidOperation, ValueError):
            raise ErroPagamento("VALOR_INVALIDO", "valor invalido")
    else:
        raise ErroPagamento("VALOR_INVALIDO", "valor invalido")

    if not d.is_finite():
        raise ErroPagamento("VALOR_INVALIDO", "valor invalido")

    d = d.quantize(CENTAVOS, rounding=ROUND_HALF_UP)

    if permitir_zero:
        if d < 0:
            raise ErroPagamento("VALOR_INVALIDO", "valor invalido")
    elif d <= 0:
        raise ErroPagamento("VALOR_INVALIDO", "valor invalido")
    return d


class OrquestradorPagamentos:
    def __init__(self, agora: Optional[Callable[[], datetime]] = None) -> None:
        self._agora = agora or (lambda: datetime.now(timezone.utc))
        self._pagamentos: dict[str, dict] = {}

    def _obter(self, pagamento_id: str) -> dict:
        pid = _validar_pagamento_id(pagamento_id)
        registro = self._pagamentos.get(pid)
        if registro is None:
            raise ErroPagamento("PAGAMENTO_NAO_ENCONTRADO", f"pagamento {pid} nao encontrado")
        return registro

    def _saldo_disponivel(self, registro: dict) -> Decimal:
        return (
            registro["valor_capturado"]
            - registro["valor_estornado"]
            - registro["valor_chargeback"]
        )

    def _proxima_sequencia(self, registro: dict) -> int:
        return len(registro["historico"]) + 1

    def _registrar_historico(self, registro: dict, tipo: str,
                              operacao_id: Optional[str], valor: Decimal,
                              instante: datetime) -> None:
        registro["historico"].append({
            "sequencia": self._proxima_sequencia(registro),
            "tipo": tipo,
            "operacao_id": operacao_id,
            "valor": valor,
            "instante": instante,
        })

    def _checar_idempotencia(self, registro: dict, operacao_id: str,
                              tipo: str, chave_valor) -> Optional[dict]:
        anterior = registro["operacoes"].get(operacao_id)
        if anterior is None:
            return None
        if anterior["tipo"] != tipo or anterior["chave_valor"] != chave_valor:
            raise ErroPagamento(
                "IDEMPOTENCIA_CONFLITANTE",
                f"operacao_id {operacao_id} ja usado de forma incompativel",
            )
        resultado = dict(anterior["resultado"])
        resultado["duplicado"] = True
        return resultado

    def registrar(self, pagamento_id: str, valor, moeda: str,
                  criado_em: datetime) -> dict:
        pid = _validar_pagamento_id(pagamento_id)
        if pid in self._pagamentos:
            raise ErroPagamento("PAGAMENTO_INVALIDO", f"pagamento {pid} ja registrado")

        valor_d = _to_decimal(valor)
        moeda_v = _validar_moeda(moeda)
        criado_em_v = _validar_data(criado_em)

        registro = {
            "pagamento_id": pid,
            "moeda": moeda_v,
            "valor_autorizado": valor_d,
            "valor_capturado": Decimal("0.00"),
            "valor_estornado": Decimal("0.00"),
            "valor_chargeback": Decimal("0.00"),
            "estado": ESTADO_AUTORIZADO,
            "criado_em": criado_em_v,
            "historico": [],
            "operacoes": {},
        }
        self._registrar_historico(registro, TIPO_REGISTRO, None, valor_d, criado_em_v)
        self._pagamentos[pid] = registro

        return {"pagamento_id": pid, "estado": registro["estado"], "valor": valor_d}

    def capturar(self, pagamento_id: str, operacao_id: str, valor=None) -> dict:
        registro = self._obter(pagamento_id)
        op_id = _validar_operacao_id(operacao_id)

        chave_valor = _to_decimal(valor) if valor is not None else None
        duplicado = self._checar_idempotencia(registro, op_id, TIPO_CAPTURA, chave_valor)
        if duplicado is not None:
            return duplicado

        if registro["estado"] not in _ESTADOS_CAPTURAVEIS:
            raise ErroPagamento("ESTADO_INVALIDO", "pagamento nao pode ser capturado neste estado")

        restante = registro["valor_autorizado"] - registro["valor_capturado"]
        if chave_valor is None:
            valor_d = restante
        else:
            valor_d = chave_valor
            if valor_d > restante:
                raise ErroPagamento("VALOR_INVALIDO", "valor de captura excede o disponivel")

        registro["valor_capturado"] += valor_d
        registro["estado"] = (
            ESTADO_CAPTURADO if registro["valor_capturado"] == registro["valor_autorizado"]
            else ESTADO_CAPTURADO_PARCIAL
        )

        instante = self._agora()
        self._registrar_historico(registro, TIPO_CAPTURA, op_id, valor_d, instante)

        resultado = {
            "duplicado": False,
            "capturado": valor_d,
            "saldo_disponivel": self._saldo_disponivel(registro),
            "estado": registro["estado"],
        }
        registro["operacoes"][op_id] = {
            "tipo": TIPO_CAPTURA, "chave_valor": chave_valor, "resultado": resultado,
        }
        return resultado

    def estornar(self, pagamento_id: str, operacao_id: str, valor,
                 motivo: str = "") -> dict:
        registro = self._obter(pagamento_id)
        op_id = _validar_operacao_id(operacao_id)

        chave_valor = _to_decimal(valor)
        duplicado = self._checar_idempotencia(registro, op_id, TIPO_ESTORNO, chave_valor)
        if duplicado is not None:
            return duplicado

        if registro["estado"] not in _ESTADOS_ESTORNAVEIS:
            raise ErroPagamento("ESTADO_INVALIDO", "pagamento nao pode ser estornado neste estado")

        saldo = self._saldo_disponivel(registro)
        valor_d = chave_valor
        if valor_d > saldo:
            raise ErroPagamento("VALOR_INVALIDO", "valor de estorno excede o saldo disponivel")

        registro["valor_estornado"] += valor_d
        registro["estado"] = (
            ESTADO_ESTORNADO
            if registro["valor_estornado"] + registro["valor_chargeback"] == registro["valor_capturado"]
            else ESTADO_ESTORNADO_PARCIAL
        )

        instante = self._agora()
        self._registrar_historico(registro, TIPO_ESTORNO, op_id, valor_d, instante)

        resultado = {
            "duplicado": False,
            "estornado": valor_d,
            "saldo_disponivel": self._saldo_disponivel(registro),
            "estado": registro["estado"],
        }
        registro["operacoes"][op_id] = {
            "tipo": TIPO_ESTORNO, "chave_valor": chave_valor, "resultado": resultado,
        }
        return resultado

    def registrar_chargeback(self, pagamento_id: str, operacao_id: str,
                             valor, ocorrido_em: datetime) -> dict:
        registro = self._obter(pagamento_id)
        op_id = _validar_operacao_id(operacao_id)

        chave_valor = _to_decimal(valor)
        duplicado = self._checar_idempotencia(registro, op_id, TIPO_CHARGEBACK, chave_valor)
        if duplicado is not None:
            return duplicado

        if registro["estado"] not in _ESTADOS_CHARGEBACKAVEIS:
            raise ErroPagamento("ESTADO_INVALIDO", "pagamento nao aceita chargeback neste estado")

        ocorrido_em_v = _validar_data(ocorrido_em)
        if ocorrido_em_v < registro["criado_em"]:
            raise ErroPagamento("DATA_INVALIDA", "chargeback ocorrido antes do pagamento")

        saldo = self._saldo_disponivel(registro)
        valor_d = chave_valor
        if valor_d > saldo:
            raise ErroPagamento("VALOR_INVALIDO", "valor de chargeback excede o saldo disponivel")

        registro["valor_chargeback"] += valor_d
        registro["estado"] = (
            ESTADO_CHARGEBACK
            if registro["valor_estornado"] + registro["valor_chargeback"] == registro["valor_capturado"]
            else ESTADO_CHARGEBACK_PARCIAL
        )

        self._registrar_historico(registro, TIPO_CHARGEBACK, op_id, valor_d, ocorrido_em_v)

        resultado = {
            "duplicado": False,
            "chargeback": valor_d,
            "saldo_disponivel": self._saldo_disponivel(registro),
            "estado": registro["estado"],
        }
        registro["operacoes"][op_id] = {
            "tipo": TIPO_CHARGEBACK, "chave_valor": chave_valor, "resultado": resultado,
        }
        return resultado

    def consultar(self, pagamento_id: str) -> dict:
        registro = self._obter(pagamento_id)
        return {
            "pagamento_id": registro["pagamento_id"],
            "moeda": registro["moeda"],
            "valor_autorizado": registro["valor_autorizado"],
            "valor_capturado": registro["valor_capturado"],
            "valor_estornado": registro["valor_estornado"],
            "valor_chargeback": registro["valor_chargeback"],
            "saldo_disponivel": self._saldo_disponivel(registro),
            "estado": registro["estado"],
        }

    def historico(self, pagamento_id: str) -> list[dict]:
        registro = self._obter(pagamento_id)
        return [dict(item) for item in registro["historico"]]
