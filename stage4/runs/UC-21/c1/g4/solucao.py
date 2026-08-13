"""UC-21 - Orquestrador de estornos e chargebacks.

Implementacao unica em stdlib. As regras de transicao de estado,
arredondamento, idempotencia, precedencia e composicao de saldos nao
estavam definidas no enunciado; as decisões tomadas estao documentadas
junto aos trechos de codigo que as aplicam.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

_MOEDA_RE = re.compile(r"^[A-Z]{3}$")


class ErroPagamento(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code
        self.mensagem = mensagem


@dataclass
class _Operacao:
    tipo: str
    valor_bruto: Decimal | None
    resultado: dict


@dataclass
class _Pagamento:
    pagamento_id: str
    moeda: str
    valor_autorizado: Decimal
    valor_capturado: Decimal = field(default_factory=lambda: Decimal(0))
    valor_estornado: Decimal = field(default_factory=lambda: Decimal(0))
    valor_chargeback: Decimal = field(default_factory=lambda: Decimal(0))
    historico: list = field(default_factory=list)
    operacoes: dict = field(default_factory=dict)

    @property
    def saldo_disponivel(self) -> Decimal:
        return self.valor_capturado - self.valor_estornado - self.valor_chargeback

    @property
    def estado(self) -> str:
        consumido = self.valor_estornado + self.valor_chargeback
        if self.valor_chargeback > 0:
            return "CHARGEBACK" if consumido == self.valor_capturado else "CHARGEBACK_PARCIAL"
        if self.valor_estornado > 0:
            return "ESTORNADO" if consumido == self.valor_capturado else "ESTORNADO_PARCIAL"
        if self.valor_capturado > 0:
            return "CAPTURADO" if self.valor_capturado == self.valor_autorizado else "CAPTURADO_PARCIAL"
        return "AUTORIZADO"


def _validar_pagamento_id(pagamento_id) -> None:
    if not isinstance(pagamento_id, str) or not pagamento_id.strip():
        raise ErroPagamento("PAGAMENTO_INVALIDO", "pagamento_id invalido")


def _validar_operacao_id(operacao_id) -> None:
    if not isinstance(operacao_id, str) or not operacao_id.strip():
        raise ErroPagamento("PAGAMENTO_INVALIDO", "operacao_id invalido")


def _validar_datetime(instante) -> None:
    if not isinstance(instante, datetime) or instante.tzinfo is None \
            or instante.tzinfo.utcoffset(instante) is None:
        raise ErroPagamento("DATA_INVALIDA", "instante precisa ser datetime timezone-aware")


def _to_decimal(valor) -> Decimal:
    if isinstance(valor, Decimal):
        d = valor
    elif isinstance(valor, bool):
        raise ErroPagamento("VALOR_INVALIDO", "tipo de valor nao suportado")
    elif isinstance(valor, int):
        d = Decimal(valor)
    elif isinstance(valor, str):
        try:
            d = Decimal(valor.strip())
        except (InvalidOperation, ValueError, AttributeError):
            raise ErroPagamento("VALOR_INVALIDO", "valor monetario invalido") from None
    elif isinstance(valor, float):
        if not math.isfinite(valor):
            raise ErroPagamento("VALOR_INVALIDO", "valor monetario invalido")
        d = Decimal(str(valor))
    else:
        raise ErroPagamento("VALOR_INVALIDO", "tipo de valor nao suportado")
    if not d.is_finite():
        raise ErroPagamento("VALOR_INVALIDO", "valor monetario invalido")
    return d


def _validar_valor_positivo(valor: Decimal) -> None:
    if valor <= 0:
        raise ErroPagamento("VALOR_INVALIDO", "valor monetario deve ser positivo")


class OrquestradorPagamentos:
    def __init__(self, agora: Callable[[], datetime] | None = None) -> None:
        self._agora = agora or (lambda: datetime.now(tz=timezone.utc))
        self._pagamentos: dict[str, _Pagamento] = {}

    def _obter(self, pagamento_id: str) -> _Pagamento:
        _validar_pagamento_id(pagamento_id)
        pagamento = self._pagamentos.get(pagamento_id)
        if pagamento is None:
            raise ErroPagamento("PAGAMENTO_NAO_ENCONTRADO", "pagamento nao encontrado")
        return pagamento

    def _proxima_sequencia(self, pagamento: _Pagamento) -> int:
        return len(pagamento.historico) + 1

    def _registrar_historico(self, pagamento: _Pagamento, tipo: str,
                              operacao_id: str | None, valor: Decimal,
                              instante: datetime) -> None:
        pagamento.historico.append({
            "sequencia": self._proxima_sequencia(pagamento),
            "tipo": tipo,
            "operacao_id": operacao_id,
            "valor": valor,
            "instante": instante,
        })

    def registrar(self, pagamento_id: str, valor, moeda: str,
                  criado_em: datetime) -> dict:
        _validar_pagamento_id(pagamento_id)
        if pagamento_id in self._pagamentos:
            raise ErroPagamento("PAGAMENTO_INVALIDO", "pagamento_id ja registrado")

        valor_decimal = _to_decimal(valor)
        _validar_valor_positivo(valor_decimal)

        if not isinstance(moeda, str) or not _MOEDA_RE.match(moeda):
            raise ErroPagamento("MOEDA_INVALIDA", "moeda deve ser um codigo de 3 letras maiusculas")

        _validar_datetime(criado_em)

        pagamento = _Pagamento(
            pagamento_id=pagamento_id,
            moeda=moeda,
            valor_autorizado=valor_decimal,
        )
        self._registrar_historico(pagamento, "REGISTRO", None, valor_decimal, criado_em)
        self._pagamentos[pagamento_id] = pagamento

        return {
            "pagamento_id": pagamento_id,
            "estado": pagamento.estado,
            "valor": valor_decimal,
        }

    def capturar(self, pagamento_id: str, operacao_id: str, valor=None) -> dict:
        pagamento = self._obter(pagamento_id)
        _validar_operacao_id(operacao_id)

        valor_bruto = None if valor is None else _to_decimal(valor)
        if valor_bruto is not None:
            _validar_valor_positivo(valor_bruto)

        existente = pagamento.operacoes.get(operacao_id)
        if existente is not None:
            if existente.tipo != "CAPTURA" or existente.valor_bruto != valor_bruto:
                raise ErroPagamento("IDEMPOTENCIA_CONFLITANTE",
                                     "operacao_id ja usado com parametros diferentes")
            return dict(existente.resultado, duplicado=True)

        restante = pagamento.valor_autorizado - pagamento.valor_capturado
        if restante <= 0:
            raise ErroPagamento("ESTADO_INVALIDO", "nao ha valor autorizado restante para captura")

        valor_captura = restante if valor_bruto is None else valor_bruto
        if valor_captura > restante:
            raise ErroPagamento("VALOR_INVALIDO", "valor de captura excede o saldo autorizado")

        pagamento.valor_capturado += valor_captura
        self._registrar_historico(pagamento, "CAPTURA", operacao_id, valor_captura, self._agora())

        resultado = {
            "duplicado": False,
            "capturado": valor_captura,
            "saldo_disponivel": pagamento.saldo_disponivel,
            "estado": pagamento.estado,
        }
        pagamento.operacoes[operacao_id] = _Operacao(
            tipo="CAPTURA", valor_bruto=valor_bruto, resultado=resultado,
        )
        return dict(resultado)

    def estornar(self, pagamento_id: str, operacao_id: str, valor,
                 motivo: str = "") -> dict:
        pagamento = self._obter(pagamento_id)
        _validar_operacao_id(operacao_id)

        valor_decimal = _to_decimal(valor)
        _validar_valor_positivo(valor_decimal)

        existente = pagamento.operacoes.get(operacao_id)
        if existente is not None:
            if existente.tipo != "ESTORNO" or existente.valor_bruto != valor_decimal:
                raise ErroPagamento("IDEMPOTENCIA_CONFLITANTE",
                                     "operacao_id ja usado com parametros diferentes")
            return dict(existente.resultado, duplicado=True)

        if pagamento.valor_capturado <= 0:
            raise ErroPagamento("ESTADO_INVALIDO", "nao ha valor capturado para estornar")

        saldo = pagamento.saldo_disponivel
        if valor_decimal > saldo:
            raise ErroPagamento("VALOR_INVALIDO", "valor de estorno excede o saldo disponivel")

        pagamento.valor_estornado += valor_decimal
        self._registrar_historico(pagamento, "ESTORNO", operacao_id, valor_decimal, self._agora())

        resultado = {
            "duplicado": False,
            "estornado": valor_decimal,
            "saldo_disponivel": pagamento.saldo_disponivel,
            "estado": pagamento.estado,
        }
        pagamento.operacoes[operacao_id] = _Operacao(
            tipo="ESTORNO", valor_bruto=valor_decimal, resultado=resultado,
        )
        return dict(resultado)

    def registrar_chargeback(self, pagamento_id: str, operacao_id: str,
                             valor, ocorrido_em: datetime) -> dict:
        pagamento = self._obter(pagamento_id)
        _validar_operacao_id(operacao_id)

        valor_decimal = _to_decimal(valor)
        _validar_valor_positivo(valor_decimal)
        _validar_datetime(ocorrido_em)

        existente = pagamento.operacoes.get(operacao_id)
        if existente is not None:
            if existente.tipo != "CHARGEBACK" or existente.valor_bruto != valor_decimal:
                raise ErroPagamento("IDEMPOTENCIA_CONFLITANTE",
                                     "operacao_id ja usado com parametros diferentes")
            return dict(existente.resultado, duplicado=True)

        if pagamento.valor_capturado <= 0:
            raise ErroPagamento("ESTADO_INVALIDO", "nao ha valor capturado para chargeback")

        saldo = pagamento.saldo_disponivel
        if valor_decimal > saldo:
            raise ErroPagamento("VALOR_INVALIDO", "valor de chargeback excede o saldo disponivel")

        pagamento.valor_chargeback += valor_decimal
        self._registrar_historico(pagamento, "CHARGEBACK", operacao_id, valor_decimal, ocorrido_em)

        resultado = {
            "duplicado": False,
            "chargeback": valor_decimal,
            "saldo_disponivel": pagamento.saldo_disponivel,
            "estado": pagamento.estado,
        }
        pagamento.operacoes[operacao_id] = _Operacao(
            tipo="CHARGEBACK", valor_bruto=valor_decimal, resultado=resultado,
        )
        return dict(resultado)

    def consultar(self, pagamento_id: str) -> dict:
        pagamento = self._obter(pagamento_id)
        return {
            "pagamento_id": pagamento.pagamento_id,
            "moeda": pagamento.moeda,
            "valor_autorizado": pagamento.valor_autorizado,
            "valor_capturado": pagamento.valor_capturado,
            "valor_estornado": pagamento.valor_estornado,
            "valor_chargeback": pagamento.valor_chargeback,
            "saldo_disponivel": pagamento.saldo_disponivel,
            "estado": pagamento.estado,
        }

    def historico(self, pagamento_id: str) -> list[dict]:
        pagamento = self._obter(pagamento_id)
        return [dict(item) for item in pagamento.historico]
