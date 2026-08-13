"""UC-21 — Orquestrador de estornos e chargebacks.

Regras de negócio adotadas (não fixadas pelo enunciado, apenas o vocabulário):

- Valores monetários são normalizados para 2 casas decimais (ROUND_HALF_UP).
- `capturar` só é permitida em AUTORIZADO/CAPTURADO_PARCIAL; `valor=None`
  captura o restante autorizado.
- `estornar`/`registrar_chargeback` consomem o mesmo saldo capturado
  (capturado - estornado - chargeback) e só são permitidas quando esse saldo
  é positivo.
- `operacao_id` é idempotente por pagamento: repetir o mesmo par
  (tipo, valor) devolve o resultado original com `duplicado=True`; um par
  (tipo, valor) divergente para o mesmo `operacao_id` é IDEMPOTENCIA_CONFLITANTE.
- `criado_em`/`ocorrido_em` precisam ser timezone-aware; `ocorrido_em` não
  pode ser anterior a `criado_em`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Callable, Optional

_CENTS = Decimal("0.01")
_MOEDA_RE = re.compile(r"^[A-Za-z]{3}$")

_ESTADOS_CAPTURAVEIS = {"AUTORIZADO", "CAPTURADO_PARCIAL"}
_ESTADOS_COM_SALDO = {
    "CAPTURADO",
    "CAPTURADO_PARCIAL",
    "ESTORNADO_PARCIAL",
    "CHARGEBACK_PARCIAL",
}


class ErroPagamento(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code
        self.mensagem = mensagem


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
    estado: str = "AUTORIZADO"
    valor_capturado: Decimal = Decimal("0.00")
    valor_estornado: Decimal = Decimal("0.00")
    valor_chargeback: Decimal = Decimal("0.00")
    historico: list = field(default_factory=list)
    operacoes: dict = field(default_factory=dict)

    @property
    def saldo_disponivel(self) -> Decimal:
        return self.valor_capturado - self.valor_estornado - self.valor_chargeback


class OrquestradorPagamentos:
    def __init__(self, agora: Optional[Callable[[], datetime]] = None) -> None:
        self._agora = agora or (lambda: datetime.now(timezone.utc))
        self._pagamentos: dict[str, _Pagamento] = {}

    # ---------- validação ----------

    @staticmethod
    def _validar_id(valor, nome: str = "identificador") -> str:
        if not isinstance(valor, str) or not valor.strip():
            raise ErroPagamento("PAGAMENTO_INVALIDO", f"{nome} inválido")
        return valor

    @staticmethod
    def _to_decimal(valor) -> Decimal:
        if isinstance(valor, bool):
            raise ErroPagamento("VALOR_INVALIDO", "valor booleano não é aceito")
        if isinstance(valor, Decimal):
            d = valor
        elif isinstance(valor, int):
            d = Decimal(valor)
        elif isinstance(valor, float):
            if valor != valor or valor in (float("inf"), float("-inf")):
                raise ErroPagamento("VALOR_INVALIDO", "valor não finito")
            d = Decimal(str(valor))
        elif isinstance(valor, str):
            try:
                d = Decimal(valor.strip())
            except (InvalidOperation, ValueError):
                raise ErroPagamento("VALOR_INVALIDO", "valor não numérico")
        else:
            raise ErroPagamento("VALOR_INVALIDO", "tipo de valor não suportado")

        if not d.is_finite():
            raise ErroPagamento("VALOR_INVALIDO", "valor não finito")
        d = d.quantize(_CENTS, rounding=ROUND_HALF_UP)
        if d <= 0:
            raise ErroPagamento("VALOR_INVALIDO", "valor deve ser positivo")
        return d

    @staticmethod
    def _validar_moeda(moeda) -> str:
        if not isinstance(moeda, str) or not _MOEDA_RE.match(moeda):
            raise ErroPagamento("MOEDA_INVALIDA", "moeda deve ter 3 letras")
        return moeda.upper()

    @staticmethod
    def _validar_data(instante, referencia: Optional[datetime] = None) -> datetime:
        if not isinstance(instante, datetime) or instante.tzinfo is None:
            raise ErroPagamento(
                "DATA_INVALIDA", "instante deve ser datetime timezone-aware"
            )
        if referencia is not None and instante < referencia:
            raise ErroPagamento(
                "DATA_INVALIDA", "instante anterior ao registro do pagamento"
            )
        return instante

    def _clock(self) -> datetime:
        return self._validar_data(self._agora())

    def _obter(self, pagamento_id: str) -> _Pagamento:
        self._validar_id(pagamento_id, "pagamento_id")
        pagamento = self._pagamentos.get(pagamento_id)
        if pagamento is None:
            raise ErroPagamento("PAGAMENTO_NAO_ENCONTRADO", pagamento_id)
        return pagamento

    def _registrar_evento(
        self, pagamento: _Pagamento, tipo: str, operacao_id, valor: Decimal, instante: datetime
    ) -> None:
        pagamento.historico.append(
            {
                "sequencia": len(pagamento.historico) + 1,
                "tipo": tipo,
                "operacao_id": operacao_id,
                "valor": valor,
                "instante": instante,
            }
        )

    def _duplicado_ou_none(
        self,
        pagamento: _Pagamento,
        operacao_id: str,
        tipo: str,
        valor_dec: Optional[Decimal],
    ) -> Optional[dict]:
        self._validar_id(operacao_id, "operacao_id")
        existente = pagamento.operacoes.get(operacao_id)
        if existente is None:
            return None
        if existente.tipo != tipo or (
            valor_dec is not None and existente.valor != valor_dec
        ):
            raise ErroPagamento("IDEMPOTENCIA_CONFLITANTE", operacao_id)
        resultado = dict(existente.resultado)
        resultado["duplicado"] = True
        return resultado

    # ---------- API pública ----------

    def registrar(
        self, pagamento_id: str, valor, moeda: str, criado_em: datetime
    ) -> dict:
        self._validar_id(pagamento_id, "pagamento_id")
        if pagamento_id in self._pagamentos:
            raise ErroPagamento("PAGAMENTO_INVALIDO", "pagamento já registrado")

        valor_dec = self._to_decimal(valor)
        moeda_norm = self._validar_moeda(moeda)
        instante = self._validar_data(criado_em)

        pagamento = _Pagamento(
            pagamento_id=pagamento_id,
            moeda=moeda_norm,
            valor_autorizado=valor_dec,
            criado_em=instante,
        )
        self._pagamentos[pagamento_id] = pagamento
        self._registrar_evento(pagamento, "REGISTRO", None, valor_dec, instante)
        return {"pagamento_id": pagamento_id, "estado": pagamento.estado, "valor": valor_dec}

    def capturar(self, pagamento_id: str, operacao_id: str, valor=None) -> dict:
        pagamento = self._obter(pagamento_id)
        valor_informado = self._to_decimal(valor) if valor is not None else None

        duplicado = self._duplicado_ou_none(pagamento, operacao_id, "CAPTURA", valor_informado)
        if duplicado is not None:
            return duplicado

        if pagamento.estado not in _ESTADOS_CAPTURAVEIS:
            raise ErroPagamento("ESTADO_INVALIDO", pagamento.estado)

        restante = pagamento.valor_autorizado - pagamento.valor_capturado
        valor_dec = valor_informado if valor_informado is not None else restante
        if valor_dec <= 0:
            raise ErroPagamento("VALOR_INVALIDO", "nada a capturar")
        if valor_dec > restante:
            raise ErroPagamento("VALOR_INVALIDO", "captura excede valor autorizado")

        instante = self._clock()
        pagamento.valor_capturado += valor_dec
        pagamento.estado = (
            "CAPTURADO"
            if pagamento.valor_capturado == pagamento.valor_autorizado
            else "CAPTURADO_PARCIAL"
        )

        resultado = {
            "duplicado": False,
            "capturado": valor_dec,
            "saldo_disponivel": pagamento.saldo_disponivel,
            "estado": pagamento.estado,
        }
        pagamento.operacoes[operacao_id] = _Operacao("CAPTURA", valor_dec, resultado)
        self._registrar_evento(pagamento, "CAPTURA", operacao_id, valor_dec, instante)
        return resultado

    def estornar(
        self, pagamento_id: str, operacao_id: str, valor, motivo: str = ""
    ) -> dict:
        pagamento = self._obter(pagamento_id)
        valor_dec = self._to_decimal(valor)

        duplicado = self._duplicado_ou_none(pagamento, operacao_id, "ESTORNO", valor_dec)
        if duplicado is not None:
            return duplicado

        if pagamento.estado not in _ESTADOS_COM_SALDO:
            raise ErroPagamento("ESTADO_INVALIDO", pagamento.estado)
        if valor_dec > pagamento.saldo_disponivel:
            raise ErroPagamento("VALOR_INVALIDO", "estorno excede saldo disponível")

        instante = self._clock()
        pagamento.valor_estornado += valor_dec
        pagamento.estado = (
            "ESTORNADO"
            if pagamento.valor_estornado + pagamento.valor_chargeback == pagamento.valor_capturado
            else "ESTORNADO_PARCIAL"
        )

        resultado = {
            "duplicado": False,
            "estornado": valor_dec,
            "saldo_disponivel": pagamento.saldo_disponivel,
            "estado": pagamento.estado,
        }
        pagamento.operacoes[operacao_id] = _Operacao("ESTORNO", valor_dec, resultado)
        self._registrar_evento(pagamento, "ESTORNO", operacao_id, valor_dec, instante)
        return resultado

    def registrar_chargeback(
        self, pagamento_id: str, operacao_id: str, valor, ocorrido_em: datetime
    ) -> dict:
        pagamento = self._obter(pagamento_id)
        valor_dec = self._to_decimal(valor)
        instante = self._validar_data(ocorrido_em, referencia=pagamento.criado_em)

        duplicado = self._duplicado_ou_none(pagamento, operacao_id, "CHARGEBACK", valor_dec)
        if duplicado is not None:
            return duplicado

        if pagamento.estado not in _ESTADOS_COM_SALDO:
            raise ErroPagamento("ESTADO_INVALIDO", pagamento.estado)
        if valor_dec > pagamento.saldo_disponivel:
            raise ErroPagamento("VALOR_INVALIDO", "chargeback excede saldo disponível")

        pagamento.valor_chargeback += valor_dec
        pagamento.estado = (
            "CHARGEBACK"
            if pagamento.valor_chargeback + pagamento.valor_estornado == pagamento.valor_capturado
            else "CHARGEBACK_PARCIAL"
        )

        resultado = {
            "duplicado": False,
            "chargeback": valor_dec,
            "saldo_disponivel": pagamento.saldo_disponivel,
            "estado": pagamento.estado,
        }
        pagamento.operacoes[operacao_id] = _Operacao("CHARGEBACK", valor_dec, resultado)
        self._registrar_evento(pagamento, "CHARGEBACK", operacao_id, valor_dec, instante)
        return resultado

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

    def historico(self, pagamento_id: str) -> list:
        pagamento = self._obter(pagamento_id)
        return [dict(item) for item in pagamento.historico]
