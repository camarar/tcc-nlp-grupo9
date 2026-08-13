"""UC-21 — Orquestrador de estornos e chargebacks.

Regras de negócio adotadas (o enunciado define apenas o vocabulário):

- Valores monetários são normalizados para `Decimal` com 2 casas decimais
  (arredondamento ROUND_HALF_UP) e devem ser estritamente positivos.
- `moeda` deve ser um código de 3 letras maiúsculas (ex.: "BRL", "USD").
- Datas (`criado_em`, `ocorrido_em`) devem ser `datetime` timezone-aware.
- Idempotência: cada `operacao_id` só pode ser usado uma vez por pagamento.
  Reenviar o mesmo `operacao_id` com os mesmos parâmetros devolve o mesmo
  resultado com `duplicado=True`; com parâmetros diferentes, é conflito
  (`IDEMPOTENCIA_CONFLITANTE`).
- Captura: só é permitida em AUTORIZADO/CAPTURADO_PARCIAL e nunca excede o
  valor autorizado restante. `valor=None` captura o restante integral.
- Estorno/chargeback: só são permitidos enquanto houver saldo capturado
  ainda não devolvido (nem por estorno, nem por chargeback), e nunca
  excedem esse saldo.
- `saldo_disponivel` é sempre `capturado - estornado - chargeback`
  (fundos retidos ainda não devolvidos).
- Estado é derivado dos totais acumulados, com chargeback tendo
  precedência sobre estorno, que tem precedência sobre captura.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Callable, Optional

_CODIGO_MOEDA = re.compile(r"^[A-Z]{3}$")
_CENTAVO = Decimal("0.01")

_CODES = {
    "PAGAMENTO_INVALIDO", "PAGAMENTO_NAO_ENCONTRADO", "ESTADO_INVALIDO",
    "VALOR_INVALIDO", "MOEDA_INVALIDA", "IDEMPOTENCIA_CONFLITANTE",
    "DATA_INVALIDA",
}


class ErroPagamento(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        assert code in _CODES
        super().__init__(mensagem or code)
        self.code = code
        self.mensagem = mensagem


class _Operacao:
    __slots__ = ("tipo", "parametros", "resultado")

    def __init__(self, tipo: str, parametros: tuple, resultado: dict) -> None:
        self.tipo = tipo
        self.parametros = parametros
        self.resultado = resultado


class _Pagamento:
    __slots__ = (
        "pagamento_id", "moeda", "valor_autorizado", "criado_em",
        "valor_capturado", "valor_estornado", "valor_chargeback",
        "historico", "operacoes",
    )

    def __init__(self, pagamento_id: str, moeda: str, valor_autorizado: Decimal,
                 criado_em: datetime) -> None:
        self.pagamento_id = pagamento_id
        self.moeda = moeda
        self.valor_autorizado = valor_autorizado
        self.criado_em = criado_em
        self.valor_capturado = Decimal("0.00")
        self.valor_estornado = Decimal("0.00")
        self.valor_chargeback = Decimal("0.00")
        self.historico: list[dict] = []
        self.operacoes: dict[str, _Operacao] = {}

    @property
    def saldo_disponivel(self) -> Decimal:
        return self.valor_capturado - self.valor_estornado - self.valor_chargeback

    @property
    def estado(self) -> str:
        devolvido = self.valor_estornado + self.valor_chargeback
        if self.valor_chargeback > 0:
            if self.valor_capturado > 0 and devolvido >= self.valor_capturado:
                return "CHARGEBACK"
            return "CHARGEBACK_PARCIAL"
        if self.valor_estornado > 0:
            if self.valor_capturado > 0 and devolvido >= self.valor_capturado:
                return "ESTORNADO"
            return "ESTORNADO_PARCIAL"
        if self.valor_capturado > 0:
            if self.valor_capturado >= self.valor_autorizado:
                return "CAPTURADO"
            return "CAPTURADO_PARCIAL"
        return "AUTORIZADO"


def _quantizar(valor: Decimal) -> Decimal:
    return valor.quantize(_CENTAVO, rounding=ROUND_HALF_UP)


def _to_decimal(valor) -> Decimal:
    if isinstance(valor, bool):
        raise ErroPagamento("VALOR_INVALIDO", "valor não pode ser booleano")
    if isinstance(valor, Decimal):
        d = valor
    elif isinstance(valor, int):
        d = Decimal(valor)
    elif isinstance(valor, str):
        try:
            d = Decimal(valor.strip())
        except (InvalidOperation, AttributeError):
            raise ErroPagamento("VALOR_INVALIDO", "valor textual inválido")
    elif isinstance(valor, float):
        try:
            d = Decimal(str(valor))
        except InvalidOperation:
            raise ErroPagamento("VALOR_INVALIDO", "valor float inválido")
    else:
        raise ErroPagamento("VALOR_INVALIDO", "tipo de valor não suportado")
    if not d.is_finite():
        raise ErroPagamento("VALOR_INVALIDO", "valor não finito")
    return d


def _validar_valor_positivo(valor) -> Decimal:
    d = _quantizar(_to_decimal(valor))
    if d <= 0:
        raise ErroPagamento("VALOR_INVALIDO", "valor deve ser positivo")
    return d


def _validar_identificador(valor, code: str, rotulo: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ErroPagamento(code, f"{rotulo} inválido")
    return valor


def _validar_moeda(moeda) -> str:
    if not isinstance(moeda, str) or not _CODIGO_MOEDA.fullmatch(moeda):
        raise ErroPagamento("MOEDA_INVALIDA", "moeda deve ter 3 letras maiúsculas")
    return moeda


def _validar_data(valor, rotulo: str) -> datetime:
    if not isinstance(valor, datetime) or valor.tzinfo is None:
        raise ErroPagamento("DATA_INVALIDA", f"{rotulo} deve ser datetime timezone-aware")
    return valor


def _normalizar_parametro_valor(valor) -> Optional[Decimal]:
    if valor is None:
        return None
    return _validar_valor_positivo(valor)


class OrquestradorPagamentos:
    def __init__(self, agora: Callable[[], datetime] | None = None) -> None:
        self._agora = agora or (lambda: datetime.now(timezone.utc))
        self._pagamentos: dict[str, _Pagamento] = {}

    def _obter(self, pagamento_id: str) -> _Pagamento:
        _validar_identificador(pagamento_id, "PAGAMENTO_INVALIDO", "pagamento_id")
        pagamento = self._pagamentos.get(pagamento_id)
        if pagamento is None:
            raise ErroPagamento("PAGAMENTO_NAO_ENCONTRADO", pagamento_id)
        return pagamento

    def _registrar_historico(self, pagamento: _Pagamento, tipo: str,
                              operacao_id: Optional[str], valor: Decimal,
                              instante: datetime) -> None:
        pagamento.historico.append({
            "sequencia": len(pagamento.historico) + 1,
            "tipo": tipo,
            "operacao_id": operacao_id,
            "valor": valor,
            "instante": instante,
        })

    def _checar_idempotencia(self, pagamento: _Pagamento, operacao_id: str,
                              tipo: str, parametros: tuple) -> Optional[dict]:
        existente = pagamento.operacoes.get(operacao_id)
        if existente is None:
            return None
        if existente.tipo != tipo or existente.parametros != parametros:
            raise ErroPagamento(
                "IDEMPOTENCIA_CONFLITANTE",
                f"operacao_id {operacao_id!r} já usado com parâmetros diferentes",
            )
        return dict(existente.resultado, duplicado=True)

    def registrar(self, pagamento_id: str, valor, moeda: str,
                  criado_em: datetime) -> dict:
        _validar_identificador(pagamento_id, "PAGAMENTO_INVALIDO", "pagamento_id")
        if pagamento_id in self._pagamentos:
            raise ErroPagamento("PAGAMENTO_INVALIDO", "pagamento já registrado")
        valor_autorizado = _validar_valor_positivo(valor)
        moeda_valida = _validar_moeda(moeda)
        data_valida = _validar_data(criado_em, "criado_em")

        pagamento = _Pagamento(pagamento_id, moeda_valida, valor_autorizado, data_valida)
        self._pagamentos[pagamento_id] = pagamento
        self._registrar_historico(pagamento, "REGISTRO", None, valor_autorizado, data_valida)

        return {
            "pagamento_id": pagamento_id,
            "estado": pagamento.estado,
            "valor": valor_autorizado,
        }

    def capturar(self, pagamento_id: str, operacao_id: str, valor=None) -> dict:
        pagamento = self._obter(pagamento_id)
        _validar_identificador(operacao_id, "PAGAMENTO_INVALIDO", "operacao_id")

        parametro = _normalizar_parametro_valor(valor)
        cache = self._checar_idempotencia(pagamento, operacao_id, "CAPTURA", (parametro,))
        if cache is not None:
            return cache

        if pagamento.estado not in ("AUTORIZADO", "CAPTURADO_PARCIAL"):
            raise ErroPagamento("ESTADO_INVALIDO", "pagamento não pode ser capturado")

        restante = pagamento.valor_autorizado - pagamento.valor_capturado
        valor_captura = restante if parametro is None else parametro
        if valor_captura <= 0 or valor_captura > restante:
            raise ErroPagamento("VALOR_INVALIDO", "valor de captura excede o restante autorizado")

        pagamento.valor_capturado += valor_captura
        instante = self._agora()
        self._registrar_historico(pagamento, "CAPTURA", operacao_id, valor_captura, instante)

        resultado = {
            "duplicado": False,
            "capturado": valor_captura,
            "saldo_disponivel": pagamento.saldo_disponivel,
            "estado": pagamento.estado,
        }
        pagamento.operacoes[operacao_id] = _Operacao("CAPTURA", (parametro,), resultado)
        return resultado

    def estornar(self, pagamento_id: str, operacao_id: str, valor,
                 motivo: str = "") -> dict:
        pagamento = self._obter(pagamento_id)
        _validar_identificador(operacao_id, "PAGAMENTO_INVALIDO", "operacao_id")

        parametro = _validar_valor_positivo(valor)
        cache = self._checar_idempotencia(pagamento, operacao_id, "ESTORNO", (parametro,))
        if cache is not None:
            return cache

        if pagamento.saldo_disponivel <= 0:
            raise ErroPagamento("ESTADO_INVALIDO", "pagamento sem saldo capturado para estornar")
        if parametro > pagamento.saldo_disponivel:
            raise ErroPagamento("VALOR_INVALIDO", "valor de estorno excede o saldo disponível")

        pagamento.valor_estornado += parametro
        instante = self._agora()
        self._registrar_historico(pagamento, "ESTORNO", operacao_id, parametro, instante)

        resultado = {
            "duplicado": False,
            "estornado": parametro,
            "saldo_disponivel": pagamento.saldo_disponivel,
            "estado": pagamento.estado,
        }
        pagamento.operacoes[operacao_id] = _Operacao("ESTORNO", (parametro,), resultado)
        return resultado

    def registrar_chargeback(self, pagamento_id: str, operacao_id: str,
                             valor, ocorrido_em: datetime) -> dict:
        pagamento = self._obter(pagamento_id)
        _validar_identificador(operacao_id, "PAGAMENTO_INVALIDO", "operacao_id")

        parametro = _validar_valor_positivo(valor)
        data_valida = _validar_data(ocorrido_em, "ocorrido_em")
        cache = self._checar_idempotencia(pagamento, operacao_id, "CHARGEBACK", (parametro,))
        if cache is not None:
            return cache

        if pagamento.saldo_disponivel <= 0:
            raise ErroPagamento("ESTADO_INVALIDO", "pagamento sem saldo capturado para chargeback")
        if parametro > pagamento.saldo_disponivel:
            raise ErroPagamento("VALOR_INVALIDO", "valor de chargeback excede o saldo disponível")

        pagamento.valor_chargeback += parametro
        self._registrar_historico(pagamento, "CHARGEBACK", operacao_id, parametro, data_valida)

        resultado = {
            "duplicado": False,
            "chargeback": parametro,
            "saldo_disponivel": pagamento.saldo_disponivel,
            "estado": pagamento.estado,
        }
        pagamento.operacoes[operacao_id] = _Operacao("CHARGEBACK", (parametro,), resultado)
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

    def historico(self, pagamento_id: str) -> list[dict]:
        pagamento = self._obter(pagamento_id)
        return [dict(item) for item in pagamento.historico]
