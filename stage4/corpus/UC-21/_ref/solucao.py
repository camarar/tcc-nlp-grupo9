"""Implementação de referência do UC-21 — instrumento, não dado experimental."""

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from threading import RLock
from typing import Callable

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


class ErroPagamento(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


def _dinheiro(valor) -> Decimal:
    try:
        resultado = Decimal(str(valor)).quantize(CENT, rounding=ROUND_HALF_EVEN)
    except (InvalidOperation, ValueError, TypeError):
        raise ErroPagamento("VALOR_INVALIDO") from None
    if not resultado.is_finite() or resultado <= ZERO:
        raise ErroPagamento("VALOR_INVALIDO")
    return resultado


def _aware(valor) -> bool:
    return (isinstance(valor, datetime) and valor.tzinfo is not None
            and valor.utcoffset() is not None)


class OrquestradorPagamentos:
    def __init__(self, agora: Callable[[], datetime] | None = None) -> None:
        self._agora = agora or (lambda: datetime.now(timezone.utc))
        self._pagamentos = {}
        self._lock = RLock()

    def registrar(self, pagamento_id: str, valor, moeda: str,
                  criado_em: datetime) -> dict:
        with self._lock:
            if not isinstance(pagamento_id, str) or not pagamento_id:
                raise ErroPagamento("PAGAMENTO_INVALIDO")
            if pagamento_id in self._pagamentos:
                raise ErroPagamento("PAGAMENTO_INVALIDO")
            montante = _dinheiro(valor)
            if not isinstance(moeda, str) or moeda.upper() not in {"BRL", "USD", "EUR"}:
                raise ErroPagamento("MOEDA_INVALIDA")
            if not _aware(criado_em):
                raise ErroPagamento("DATA_INVALIDA")
            p = {"id": pagamento_id, "moeda": moeda.upper(), "autorizado": montante,
                 "capturado": ZERO, "estornado": ZERO, "chargeback": ZERO,
                 "estado": "AUTORIZADO", "criado_em": criado_em,
                 "historico": [], "operacoes": {}}
            self._evento(p, "REGISTRO", None, montante, criado_em)
            self._pagamentos[pagamento_id] = p
            return {"pagamento_id": pagamento_id, "estado": "AUTORIZADO",
                    "valor": montante}

    def _obter(self, pagamento_id):
        try:
            return self._pagamentos[pagamento_id]
        except (KeyError, TypeError):
            raise ErroPagamento("PAGAMENTO_NAO_ENCONTRADO") from None

    @staticmethod
    def _op_id(operacao_id):
        if not isinstance(operacao_id, str) or not operacao_id:
            raise ErroPagamento("PAGAMENTO_INVALIDO")

    @staticmethod
    def _saldo(p):
        return (p["capturado"] - p["estornado"] - p["chargeback"]).quantize(CENT)

    def _replay(self, p, operacao_id, assinatura):
        anterior = p["operacoes"].get(operacao_id)
        if anterior is None:
            return None
        if anterior["assinatura"] != assinatura:
            raise ErroPagamento("IDEMPOTENCIA_CONFLITANTE")
        retorno = dict(anterior["retorno"])
        retorno["duplicado"] = True
        return retorno

    @staticmethod
    def _guardar(p, operacao_id, assinatura, retorno):
        p["operacoes"][operacao_id] = {
            "assinatura": assinatura, "retorno": dict(retorno)}

    @staticmethod
    def _evento(p, tipo, operacao_id, valor, instante):
        p["historico"].append({"sequencia": len(p["historico"]) + 1,
                               "tipo": tipo, "operacao_id": operacao_id,
                               "valor": valor, "instante": instante})

    def capturar(self, pagamento_id: str, operacao_id: str, valor=None) -> dict:
        with self._lock:
            p = self._obter(pagamento_id)
            self._op_id(operacao_id)
            restante = p["autorizado"] - p["capturado"]
            anterior = p["operacoes"].get(operacao_id)
            if (valor is None and anterior is not None
                    and anterior["assinatura"][0] == "CAPTURA"):
                montante = anterior["assinatura"][1]
            else:
                montante = restante if valor is None else _dinheiro(valor)
            assinatura = ("CAPTURA", montante)
            replay = self._replay(p, operacao_id, assinatura)
            if replay is not None:
                return replay
            if montante <= ZERO or montante > restante or self._saldo(p) == ZERO and p["capturado"]:
                raise ErroPagamento("VALOR_INVALIDO")
            p["capturado"] += montante
            p["estado"] = ("CAPTURADO" if p["capturado"] == p["autorizado"]
                           else "CAPTURADO_PARCIAL")
            self._evento(p, "CAPTURA", operacao_id, montante, self._agora())
            retorno = {"duplicado": False, "capturado": montante,
                       "saldo_disponivel": self._saldo(p), "estado": p["estado"]}
            self._guardar(p, operacao_id, assinatura, retorno)
            return dict(retorno)

    def estornar(self, pagamento_id: str, operacao_id: str, valor,
                 motivo: str = "") -> dict:
        with self._lock:
            p = self._obter(pagamento_id)
            self._op_id(operacao_id)
            montante = _dinheiro(valor)
            assinatura = ("ESTORNO", montante, motivo)
            replay = self._replay(p, operacao_id, assinatura)
            if replay is not None:
                return replay
            if montante > self._saldo(p):
                raise ErroPagamento("VALOR_INVALIDO")
            p["estornado"] += montante
            p["estado"] = "ESTORNADO" if self._saldo(p) == ZERO else "ESTORNADO_PARCIAL"
            self._evento(p, "ESTORNO", operacao_id, montante, self._agora())
            retorno = {"duplicado": False, "estornado": montante,
                       "saldo_disponivel": self._saldo(p), "estado": p["estado"]}
            self._guardar(p, operacao_id, assinatura, retorno)
            return dict(retorno)

    def registrar_chargeback(self, pagamento_id: str, operacao_id: str,
                             valor, ocorrido_em: datetime) -> dict:
        with self._lock:
            p = self._obter(pagamento_id)
            self._op_id(operacao_id)
            montante = _dinheiro(valor)
            assinatura = ("CHARGEBACK", montante, ocorrido_em)
            replay = self._replay(p, operacao_id, assinatura)
            if replay is not None:
                return replay
            if (not _aware(ocorrido_em) or ocorrido_em < p["criado_em"]
                    or ocorrido_em > self._agora()):
                raise ErroPagamento("DATA_INVALIDA")
            if montante > self._saldo(p):
                raise ErroPagamento("VALOR_INVALIDO")
            p["chargeback"] += montante
            p["estado"] = "CHARGEBACK" if self._saldo(p) == ZERO else "CHARGEBACK_PARCIAL"
            self._evento(p, "CHARGEBACK", operacao_id, montante, ocorrido_em)
            retorno = {"duplicado": False, "chargeback": montante,
                       "saldo_disponivel": self._saldo(p), "estado": p["estado"]}
            self._guardar(p, operacao_id, assinatura, retorno)
            return dict(retorno)

    def consultar(self, pagamento_id: str) -> dict:
        with self._lock:
            p = self._obter(pagamento_id)
            return {"pagamento_id": p["id"], "moeda": p["moeda"],
                    "valor_autorizado": p["autorizado"],
                    "valor_capturado": p["capturado"],
                    "valor_estornado": p["estornado"],
                    "valor_chargeback": p["chargeback"],
                    "saldo_disponivel": self._saldo(p), "estado": p["estado"]}

    def historico(self, pagamento_id: str) -> list[dict]:
        with self._lock:
            return deepcopy(self._obter(pagamento_id)["historico"])
