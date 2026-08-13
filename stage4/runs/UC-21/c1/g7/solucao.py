"""UC-21 - Orquestrador de estornos e chargebacks.

Implementacao de referencia usando apenas a biblioteca padrao.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Callable, Optional

CODIGOS_ERRO = frozenset({
    "PAGAMENTO_INVALIDO",
    "PAGAMENTO_NAO_ENCONTRADO",
    "ESTADO_INVALIDO",
    "VALOR_INVALIDO",
    "MOEDA_INVALIDA",
    "IDEMPOTENCIA_CONFLITANTE",
    "DATA_INVALIDA",
})

ESTADOS_CAPTURA_PERMITIDA = frozenset({"AUTORIZADO", "CAPTURADO_PARCIAL"})
ESTADOS_ESTORNO_PERMITIDO = frozenset({"CAPTURADO", "CAPTURADO_PARCIAL", "ESTORNADO_PARCIAL"})
ESTADOS_CHARGEBACK_PERMITIDO = frozenset({
    "CAPTURADO", "CAPTURADO_PARCIAL", "ESTORNADO_PARCIAL", "ESTORNADO", "CHARGEBACK_PARCIAL",
})


class ErroPagamento(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        assert code in CODIGOS_ERRO
        super().__init__(mensagem or code)
        self.code = code


@dataclass
class _Operacao:
    tipo: str
    valor: Decimal
    resultado: dict


@dataclass
class _Pagamento:
    pagamento_id: str
    moeda: str
    valor_autorizado: Decimal
    criado_em: datetime
    valor_capturado: Decimal = Decimal("0")
    valor_estornado: Decimal = Decimal("0")
    valor_chargeback: Decimal = Decimal("0")
    estado: str = "AUTORIZADO"
    historico: list = field(default_factory=list)
    operacoes: dict = field(default_factory=dict)


def _estado_atual(p: _Pagamento) -> str:
    if p.valor_chargeback > 0:
        return "CHARGEBACK" if p.valor_chargeback >= p.valor_capturado else "CHARGEBACK_PARCIAL"
    if p.valor_estornado > 0:
        return "ESTORNADO" if p.valor_estornado + p.valor_chargeback >= p.valor_capturado else "ESTORNADO_PARCIAL"
    if p.valor_capturado > 0:
        return "CAPTURADO" if p.valor_capturado >= p.valor_autorizado else "CAPTURADO_PARCIAL"
    return "AUTORIZADO"


def _saldo_disponivel(p: _Pagamento) -> Decimal:
    return p.valor_capturado - p.valor_estornado - p.valor_chargeback


class OrquestradorPagamentos:
    def __init__(self, agora: Optional[Callable[[], datetime]] = None) -> None:
        self._agora = agora or (lambda: datetime.now(timezone.utc))
        self._pagamentos: dict[str, _Pagamento] = {}

    def _validar_pagamento_id(self, pagamento_id: str) -> None:
        if not isinstance(pagamento_id, str) or not pagamento_id.strip():
            raise ErroPagamento("PAGAMENTO_INVALIDO", "pagamento_id invalido")

    def _validar_operacao_id(self, operacao_id: str) -> None:
        if not isinstance(operacao_id, str) or not operacao_id.strip():
            raise ErroPagamento("PAGAMENTO_INVALIDO", "operacao_id invalido")

    def _obter(self, pagamento_id: str) -> _Pagamento:
        self._validar_pagamento_id(pagamento_id)
        p = self._pagamentos.get(pagamento_id)
        if p is None:
            raise ErroPagamento("PAGAMENTO_NAO_ENCONTRADO", pagamento_id)
        return p

    def _validar_moeda(self, moeda: str) -> str:
        if not isinstance(moeda, str) or len(moeda) != 3 or not moeda.isalpha():
            raise ErroPagamento("MOEDA_INVALIDA", str(moeda))
        return moeda.upper()

    def _validar_data(self, data: datetime) -> None:
        if not isinstance(data, datetime) or data.tzinfo is None or data.utcoffset() is None:
            raise ErroPagamento("DATA_INVALIDA", "data deve ser timezone-aware")

    def _para_decimal(self, valor) -> Decimal:
        if isinstance(valor, Decimal):
            d = valor
        elif isinstance(valor, bool):
            raise ErroPagamento("VALOR_INVALIDO", str(valor))
        elif isinstance(valor, int):
            d = Decimal(valor)
        elif isinstance(valor, float):
            try:
                d = Decimal(str(valor))
            except InvalidOperation:
                raise ErroPagamento("VALOR_INVALIDO", str(valor)) from None
        elif isinstance(valor, str):
            try:
                d = Decimal(valor.strip())
            except (InvalidOperation, AttributeError):
                raise ErroPagamento("VALOR_INVALIDO", valor) from None
        else:
            raise ErroPagamento("VALOR_INVALIDO", str(valor))
        if not d.is_finite():
            raise ErroPagamento("VALOR_INVALIDO", str(valor))
        return d

    def _valor_positivo(self, valor) -> Decimal:
        d = self._para_decimal(valor)
        if d <= 0:
            raise ErroPagamento("VALOR_INVALIDO", str(valor))
        return d

    def _proxima_sequencia(self, p: _Pagamento) -> int:
        return len(p.historico) + 1

    def _registrar_evento(self, p: _Pagamento, tipo: str, operacao_id, valor: Decimal, instante: datetime) -> None:
        p.historico.append({
            "sequencia": self._proxima_sequencia(p),
            "tipo": tipo,
            "operacao_id": operacao_id,
            "valor": valor,
            "instante": instante,
        })

    def _checar_idempotencia(self, p: _Pagamento, operacao_id: str, tipo: str, valor: Decimal) -> Optional[dict]:
        anterior = p.operacoes.get(operacao_id)
        if anterior is None:
            return None
        if anterior.tipo != tipo or anterior.valor != valor:
            raise ErroPagamento("IDEMPOTENCIA_CONFLITANTE", operacao_id)
        resultado = dict(anterior.resultado)
        resultado["duplicado"] = True
        return resultado

    def registrar(self, pagamento_id: str, valor, moeda: str, criado_em: datetime) -> dict:
        self._validar_pagamento_id(pagamento_id)
        valor_d = self._valor_positivo(valor)
        moeda_norm = self._validar_moeda(moeda)
        self._validar_data(criado_em)

        existente = self._pagamentos.get(pagamento_id)
        if existente is not None:
            if (existente.valor_autorizado == valor_d and existente.moeda == moeda_norm
                    and existente.criado_em == criado_em):
                return {
                    "pagamento_id": existente.pagamento_id,
                    "estado": existente.estado,
                    "valor": existente.valor_autorizado,
                }
            raise ErroPagamento("IDEMPOTENCIA_CONFLITANTE", pagamento_id)

        p = _Pagamento(
            pagamento_id=pagamento_id,
            moeda=moeda_norm,
            valor_autorizado=valor_d,
            criado_em=criado_em,
        )
        self._registrar_evento(p, "REGISTRO", None, valor_d, criado_em)
        self._pagamentos[pagamento_id] = p
        return {"pagamento_id": p.pagamento_id, "estado": p.estado, "valor": p.valor_autorizado}

    def capturar(self, pagamento_id: str, operacao_id: str, valor=None) -> dict:
        p = self._obter(pagamento_id)
        self._validar_operacao_id(operacao_id)

        restante = p.valor_autorizado - p.valor_capturado
        valor_d = restante if valor is None else self._valor_positivo(valor)

        duplicado = self._checar_idempotencia(p, operacao_id, "CAPTURA", valor_d)
        if duplicado is not None:
            return duplicado

        if p.estado not in ESTADOS_CAPTURA_PERMITIDA:
            raise ErroPagamento("ESTADO_INVALIDO", p.estado)
        if valor_d <= 0 or valor_d > restante:
            raise ErroPagamento("VALOR_INVALIDO", str(valor))

        instante = self._agora()
        p.valor_capturado += valor_d
        p.estado = _estado_atual(p)
        self._registrar_evento(p, "CAPTURA", operacao_id, valor_d, instante)

        resultado = {
            "duplicado": False,
            "capturado": valor_d,
            "saldo_disponivel": _saldo_disponivel(p),
            "estado": p.estado,
        }
        p.operacoes[operacao_id] = _Operacao("CAPTURA", valor_d, resultado)
        return resultado

    def estornar(self, pagamento_id: str, operacao_id: str, valor, motivo: str = "") -> dict:
        p = self._obter(pagamento_id)
        self._validar_operacao_id(operacao_id)
        valor_d = self._valor_positivo(valor)

        duplicado = self._checar_idempotencia(p, operacao_id, "ESTORNO", valor_d)
        if duplicado is not None:
            return duplicado

        if p.estado not in ESTADOS_ESTORNO_PERMITIDO:
            raise ErroPagamento("ESTADO_INVALIDO", p.estado)
        disponivel = _saldo_disponivel(p)
        if valor_d > disponivel:
            raise ErroPagamento("VALOR_INVALIDO", str(valor))

        instante = self._agora()
        p.valor_estornado += valor_d
        p.estado = _estado_atual(p)
        self._registrar_evento(p, "ESTORNO", operacao_id, valor_d, instante)

        resultado = {
            "duplicado": False,
            "estornado": valor_d,
            "saldo_disponivel": _saldo_disponivel(p),
            "estado": p.estado,
        }
        p.operacoes[operacao_id] = _Operacao("ESTORNO", valor_d, resultado)
        return resultado

    def registrar_chargeback(self, pagamento_id: str, operacao_id: str, valor, ocorrido_em: datetime) -> dict:
        p = self._obter(pagamento_id)
        self._validar_operacao_id(operacao_id)
        self._validar_data(ocorrido_em)
        valor_d = self._valor_positivo(valor)

        duplicado = self._checar_idempotencia(p, operacao_id, "CHARGEBACK", valor_d)
        if duplicado is not None:
            return duplicado

        if p.estado not in ESTADOS_CHARGEBACK_PERMITIDO:
            raise ErroPagamento("ESTADO_INVALIDO", p.estado)
        disponivel = _saldo_disponivel(p)
        if valor_d > disponivel:
            raise ErroPagamento("VALOR_INVALIDO", str(valor))

        p.valor_chargeback += valor_d
        p.estado = _estado_atual(p)
        self._registrar_evento(p, "CHARGEBACK", operacao_id, valor_d, ocorrido_em)

        resultado = {
            "duplicado": False,
            "chargeback": valor_d,
            "saldo_disponivel": _saldo_disponivel(p),
            "estado": p.estado,
        }
        p.operacoes[operacao_id] = _Operacao("CHARGEBACK", valor_d, resultado)
        return resultado

    def consultar(self, pagamento_id: str) -> dict:
        p = self._obter(pagamento_id)
        return {
            "pagamento_id": p.pagamento_id,
            "moeda": p.moeda,
            "valor_autorizado": p.valor_autorizado,
            "valor_capturado": p.valor_capturado,
            "valor_estornado": p.valor_estornado,
            "valor_chargeback": p.valor_chargeback,
            "saldo_disponivel": _saldo_disponivel(p),
            "estado": p.estado,
        }

    def historico(self, pagamento_id: str) -> list:
        p = self._obter(pagamento_id)
        return [dict(evento) for evento in p.historico]
