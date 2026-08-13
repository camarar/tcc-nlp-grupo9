"""UC-21 — Orquestrador de estornos e chargebacks.

Implementação em biblioteca padrão apenas. Valores monetários trafegam como
``decimal.Decimal``; datas/instantes usam ``datetime`` timezone-aware.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Callable, Optional

_MOEDA_RE = re.compile(r"^[A-Z]{3}$")

_ESTADOS_CAPTURAVEIS = {"AUTORIZADO", "CAPTURADO_PARCIAL"}
_ESTADOS_ESTORNAVEIS = {"CAPTURADO", "CAPTURADO_PARCIAL", "ESTORNADO_PARCIAL"}
_ESTADOS_CHARGEBACKAVEIS = {
    "CAPTURADO", "CAPTURADO_PARCIAL", "ESTORNADO_PARCIAL", "CHARGEBACK_PARCIAL",
}


class ErroPagamento(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


def _to_decimal(valor) -> Decimal:
    if isinstance(valor, bool):
        raise ErroPagamento("VALOR_INVALIDO", "valor booleano nao e aceito")
    if isinstance(valor, Decimal):
        d = valor
    elif isinstance(valor, int):
        d = Decimal(valor)
    elif isinstance(valor, float):
        try:
            d = Decimal(str(valor))
        except InvalidOperation as exc:
            raise ErroPagamento("VALOR_INVALIDO", "valor float invalido") from exc
    elif isinstance(valor, str):
        try:
            d = Decimal(valor.strip())
        except InvalidOperation as exc:
            raise ErroPagamento("VALOR_INVALIDO", "valor string invalido") from exc
    else:
        raise ErroPagamento("VALOR_INVALIDO", "tipo de valor nao suportado")
    if not d.is_finite():
        raise ErroPagamento("VALOR_INVALIDO", "valor nao finito")
    return d


def _to_decimal_positivo(valor) -> Decimal:
    d = _to_decimal(valor)
    if d <= 0:
        raise ErroPagamento("VALOR_INVALIDO", "valor deve ser maior que zero")
    return d


def _validar_id(valor, code: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ErroPagamento(code, "identificador invalido")
    return valor


def _validar_data(valor, mensagem: str = "data invalida") -> datetime:
    if not isinstance(valor, datetime) or valor.tzinfo is None:
        raise ErroPagamento("DATA_INVALIDA", mensagem)
    return valor


def _compute_estado(autorizado: Decimal, capturado: Decimal, estornado: Decimal,
                     chargeback: Decimal) -> str:
    if chargeback > 0:
        if chargeback + estornado >= capturado:
            return "CHARGEBACK"
        return "CHARGEBACK_PARCIAL"
    if estornado > 0:
        if estornado >= capturado:
            return "ESTORNADO"
        return "ESTORNADO_PARCIAL"
    if capturado > 0:
        if capturado >= autorizado:
            return "CAPTURADO"
        return "CAPTURADO_PARCIAL"
    return "AUTORIZADO"


class _Pagamento:
    __slots__ = (
        "pagamento_id", "moeda", "valor_autorizado", "valor_capturado",
        "valor_estornado", "valor_chargeback", "estado", "criado_em",
        "historico", "operacoes", "_seq",
    )

    def __init__(self, pagamento_id: str, valor_autorizado: Decimal, moeda: str,
                 criado_em: datetime) -> None:
        self.pagamento_id = pagamento_id
        self.moeda = moeda
        self.valor_autorizado = valor_autorizado
        self.valor_capturado = Decimal(0)
        self.valor_estornado = Decimal(0)
        self.valor_chargeback = Decimal(0)
        self.estado = "AUTORIZADO"
        self.criado_em = criado_em
        self.historico: list[dict] = []
        self.operacoes: dict[str, dict] = {}
        self._seq = 0

    def registrar_historico(self, tipo: str, operacao_id: Optional[str],
                             valor: Decimal, instante: datetime) -> None:
        self._seq += 1
        self.historico.append({
            "sequencia": self._seq,
            "tipo": tipo,
            "operacao_id": operacao_id,
            "valor": valor,
            "instante": instante,
        })

    def saldo_disponivel(self) -> Decimal:
        return self.valor_capturado - self.valor_estornado - self.valor_chargeback

    def snapshot(self) -> dict:
        return {
            "pagamento_id": self.pagamento_id,
            "moeda": self.moeda,
            "valor_autorizado": self.valor_autorizado,
            "valor_capturado": self.valor_capturado,
            "valor_estornado": self.valor_estornado,
            "valor_chargeback": self.valor_chargeback,
            "saldo_disponivel": self.saldo_disponivel(),
            "estado": self.estado,
        }


class OrquestradorPagamentos:
    def __init__(self, agora: Optional[Callable[[], datetime]] = None) -> None:
        self._agora = agora or (lambda: datetime.now(timezone.utc))
        self._pagamentos: dict[str, _Pagamento] = {}

    def _obter(self, pagamento_id: str) -> _Pagamento:
        _validar_id(pagamento_id, "PAGAMENTO_INVALIDO")
        pagamento = self._pagamentos.get(pagamento_id)
        if pagamento is None:
            raise ErroPagamento("PAGAMENTO_NAO_ENCONTRADO", pagamento_id)
        return pagamento

    def registrar(self, pagamento_id: str, valor, moeda: str,
                  criado_em: datetime) -> dict:
        _validar_id(pagamento_id, "PAGAMENTO_INVALIDO")
        if pagamento_id in self._pagamentos:
            raise ErroPagamento("IDEMPOTENCIA_CONFLITANTE",
                                 "pagamento ja registrado")
        if not isinstance(moeda, str) or not _MOEDA_RE.fullmatch(moeda):
            raise ErroPagamento("MOEDA_INVALIDA", str(moeda))
        valor_dec = _to_decimal_positivo(valor)
        _validar_data(criado_em, "criado_em invalido")

        pagamento = _Pagamento(pagamento_id, valor_dec, moeda, criado_em)
        pagamento.registrar_historico("REGISTRO", None, valor_dec, criado_em)
        self._pagamentos[pagamento_id] = pagamento
        return {
            "pagamento_id": pagamento_id,
            "estado": pagamento.estado,
            "valor": valor_dec,
        }

    def _operacao(self, pagamento: _Pagamento, operacao_id: str, tipo: str,
                  valor_resolvido: Decimal) -> Optional[dict]:
        """Trata idempotencia. Retorna resposta de duplicata ou None."""
        existente = pagamento.operacoes.get(operacao_id)
        if existente is None:
            return None
        if existente["tipo"] != tipo or existente["valor"] != valor_resolvido:
            raise ErroPagamento("IDEMPOTENCIA_CONFLITANTE", operacao_id)
        resultado = dict(existente["resultado"])
        resultado["duplicado"] = True
        return resultado

    def capturar(self, pagamento_id: str, operacao_id: str, valor=None) -> dict:
        pagamento = self._obter(pagamento_id)
        _validar_id(operacao_id, "VALOR_INVALIDO")

        restante = pagamento.valor_autorizado - pagamento.valor_capturado
        valor_resolvido = restante if valor is None else _to_decimal_positivo(valor)

        duplicado = self._operacao(pagamento, operacao_id, "CAPTURA", valor_resolvido)
        if duplicado is not None:
            return duplicado

        if pagamento.estado not in _ESTADOS_CAPTURAVEIS:
            raise ErroPagamento("ESTADO_INVALIDO", pagamento.estado)
        if valor_resolvido <= 0 or valor_resolvido > restante:
            raise ErroPagamento("VALOR_INVALIDO", "valor excede saldo capturavel")

        pagamento.valor_capturado += valor_resolvido
        pagamento.estado = _compute_estado(
            pagamento.valor_autorizado, pagamento.valor_capturado,
            pagamento.valor_estornado, pagamento.valor_chargeback,
        )
        instante = self._agora()
        pagamento.registrar_historico("CAPTURA", operacao_id, valor_resolvido, instante)

        resultado = {
            "duplicado": False,
            "capturado": valor_resolvido,
            "saldo_disponivel": pagamento.saldo_disponivel(),
            "estado": pagamento.estado,
        }
        pagamento.operacoes[operacao_id] = {
            "tipo": "CAPTURA", "valor": valor_resolvido, "resultado": resultado,
        }
        return resultado

    def estornar(self, pagamento_id: str, operacao_id: str, valor,
                 motivo: str = "") -> dict:
        pagamento = self._obter(pagamento_id)
        _validar_id(operacao_id, "VALOR_INVALIDO")
        valor_resolvido = _to_decimal_positivo(valor)

        duplicado = self._operacao(pagamento, operacao_id, "ESTORNO", valor_resolvido)
        if duplicado is not None:
            return duplicado

        if pagamento.estado not in _ESTADOS_ESTORNAVEIS:
            raise ErroPagamento("ESTADO_INVALIDO", pagamento.estado)
        restante = pagamento.saldo_disponivel()
        if valor_resolvido > restante:
            raise ErroPagamento("VALOR_INVALIDO", "valor excede saldo estornavel")

        pagamento.valor_estornado += valor_resolvido
        pagamento.estado = _compute_estado(
            pagamento.valor_autorizado, pagamento.valor_capturado,
            pagamento.valor_estornado, pagamento.valor_chargeback,
        )
        instante = self._agora()
        pagamento.registrar_historico("ESTORNO", operacao_id, valor_resolvido, instante)

        resultado = {
            "duplicado": False,
            "estornado": valor_resolvido,
            "saldo_disponivel": pagamento.saldo_disponivel(),
            "estado": pagamento.estado,
        }
        pagamento.operacoes[operacao_id] = {
            "tipo": "ESTORNO", "valor": valor_resolvido, "resultado": resultado,
        }
        return resultado

    def registrar_chargeback(self, pagamento_id: str, operacao_id: str,
                             valor, ocorrido_em: datetime) -> dict:
        pagamento = self._obter(pagamento_id)
        _validar_id(operacao_id, "VALOR_INVALIDO")
        _validar_data(ocorrido_em, "ocorrido_em invalido")
        if ocorrido_em < pagamento.criado_em:
            raise ErroPagamento("DATA_INVALIDA", "ocorrido_em anterior ao registro")
        valor_resolvido = _to_decimal_positivo(valor)

        duplicado = self._operacao(pagamento, operacao_id, "CHARGEBACK", valor_resolvido)
        if duplicado is not None:
            return duplicado

        if pagamento.estado not in _ESTADOS_CHARGEBACKAVEIS:
            raise ErroPagamento("ESTADO_INVALIDO", pagamento.estado)
        restante = pagamento.saldo_disponivel()
        if valor_resolvido > restante:
            raise ErroPagamento("VALOR_INVALIDO", "valor excede saldo disponivel")

        pagamento.valor_chargeback += valor_resolvido
        pagamento.estado = _compute_estado(
            pagamento.valor_autorizado, pagamento.valor_capturado,
            pagamento.valor_estornado, pagamento.valor_chargeback,
        )
        pagamento.registrar_historico("CHARGEBACK", operacao_id, valor_resolvido, ocorrido_em)

        resultado = {
            "duplicado": False,
            "chargeback": valor_resolvido,
            "saldo_disponivel": pagamento.saldo_disponivel(),
            "estado": pagamento.estado,
        }
        pagamento.operacoes[operacao_id] = {
            "tipo": "CHARGEBACK", "valor": valor_resolvido, "resultado": resultado,
        }
        return resultado

    def consultar(self, pagamento_id: str) -> dict:
        pagamento = self._obter(pagamento_id)
        return pagamento.snapshot()

    def historico(self, pagamento_id: str) -> list[dict]:
        pagamento = self._obter(pagamento_id)
        return [dict(item) for item in pagamento.historico]
