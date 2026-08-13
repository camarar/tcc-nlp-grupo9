"""UC-21 - Orquestrador de estornos e chargebacks."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Callable, Optional

_MOEDA_RE = re.compile(r"^[A-Za-z]{3}$")
_CENTAVOS = Decimal("0.01")


class ErroPagamento(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


class OrquestradorPagamentos:
    def __init__(self, agora: Optional[Callable[[], datetime]] = None) -> None:
        self._agora = agora or (lambda: datetime.now(timezone.utc))
        self._pagamentos: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # validacoes
    # ------------------------------------------------------------------
    def _validar_id(self, valor, code: str = "PAGAMENTO_INVALIDO") -> str:
        if not isinstance(valor, str) or not valor.strip():
            raise ErroPagamento(code, "identificador invalido")
        return valor

    def _to_decimal(self, valor) -> Decimal:
        if isinstance(valor, bool):
            raise ErroPagamento("VALOR_INVALIDO", "valor invalido")
        if isinstance(valor, Decimal):
            d = valor
        elif isinstance(valor, int):
            d = Decimal(valor)
        elif isinstance(valor, str):
            try:
                d = Decimal(valor.strip())
            except (InvalidOperation, ValueError):
                raise ErroPagamento("VALOR_INVALIDO", "valor invalido")
        elif isinstance(valor, float):
            if valor != valor or valor in (float("inf"), float("-inf")):
                raise ErroPagamento("VALOR_INVALIDO", "valor invalido")
            d = Decimal(str(valor))
        else:
            raise ErroPagamento("VALOR_INVALIDO", "valor invalido")

        if not d.is_finite():
            raise ErroPagamento("VALOR_INVALIDO", "valor invalido")

        d = d.quantize(_CENTAVOS, rounding=ROUND_HALF_UP)
        if d <= 0:
            raise ErroPagamento("VALOR_INVALIDO", "valor deve ser positivo")
        return d

    def _validar_moeda(self, moeda) -> str:
        if not isinstance(moeda, str) or not _MOEDA_RE.match(moeda):
            raise ErroPagamento("MOEDA_INVALIDA", "moeda invalida")
        return moeda.upper()

    def _validar_data(self, dt) -> datetime:
        if not isinstance(dt, datetime) or dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            raise ErroPagamento("DATA_INVALIDA", "data deve ser timezone-aware")
        return dt

    def _buscar(self, pagamento_id: str) -> dict:
        self._validar_id(pagamento_id)
        pagamento = self._pagamentos.get(pagamento_id)
        if pagamento is None:
            raise ErroPagamento("PAGAMENTO_NAO_ENCONTRADO", "pagamento nao encontrado")
        return pagamento

    def _saldo_disponivel(self, pagamento: dict) -> Decimal:
        return (
            pagamento["valor_capturado"]
            - pagamento["valor_estornado"]
            - pagamento["valor_chargeback"]
        )

    def _registrar_historico(self, pagamento: dict, tipo: str,
                              operacao_id: Optional[str], valor: Decimal,
                              instante: datetime) -> None:
        pagamento["sequencia"] += 1
        pagamento["historico"].append({
            "sequencia": pagamento["sequencia"],
            "tipo": tipo,
            "operacao_id": operacao_id,
            "valor": valor,
            "instante": instante,
        })

    def _checar_idempotencia(self, pagamento: dict, operacao_id: str,
                              tipo: str, valor: Decimal) -> Optional[dict]:
        registrada = pagamento["operacoes"].get(operacao_id)
        if registrada is None:
            return None
        if registrada["tipo"] != tipo or registrada["valor"] != valor:
            raise ErroPagamento("IDEMPOTENCIA_CONFLITANTE",
                                 "operacao_id ja usado com dados diferentes")
        return registrada

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------
    def registrar(self, pagamento_id: str, valor, moeda: str,
                  criado_em: datetime) -> dict:
        self._validar_id(pagamento_id)
        if pagamento_id in self._pagamentos:
            raise ErroPagamento("IDEMPOTENCIA_CONFLITANTE",
                                 "pagamento ja registrado")
        valor_dec = self._to_decimal(valor)
        moeda_norm = self._validar_moeda(moeda)
        criado_em_norm = self._validar_data(criado_em)

        pagamento = {
            "pagamento_id": pagamento_id,
            "moeda": moeda_norm,
            "valor_autorizado": valor_dec,
            "valor_capturado": Decimal("0.00"),
            "valor_estornado": Decimal("0.00"),
            "valor_chargeback": Decimal("0.00"),
            "estado": "AUTORIZADO",
            "criado_em": criado_em_norm,
            "sequencia": 0,
            "historico": [],
            "operacoes": {},
        }
        self._pagamentos[pagamento_id] = pagamento
        self._registrar_historico(pagamento, "REGISTRO", None, valor_dec, criado_em_norm)

        return {
            "pagamento_id": pagamento_id,
            "estado": pagamento["estado"],
            "valor": valor_dec,
        }

    def capturar(self, pagamento_id: str, operacao_id: str, valor=None) -> dict:
        pagamento = self._buscar(pagamento_id)
        self._validar_id(operacao_id)

        disponivel_para_captura = pagamento["valor_autorizado"] - pagamento["valor_capturado"]
        valor_dec = self._to_decimal(valor) if valor is not None else disponivel_para_captura
        if valor_dec <= 0:
            raise ErroPagamento("VALOR_INVALIDO", "nao ha valor disponivel para captura")

        duplicada = self._checar_idempotencia(pagamento, operacao_id, "CAPTURA", valor_dec)
        if duplicada is not None:
            return {
                "duplicado": True,
                "capturado": duplicada["valor"],
                "saldo_disponivel": self._saldo_disponivel(pagamento),
                "estado": pagamento["estado"],
            }

        if pagamento["estado"] not in ("AUTORIZADO", "CAPTURADO_PARCIAL"):
            raise ErroPagamento("ESTADO_INVALIDO",
                                 "pagamento nao pode ser capturado neste estado")
        if valor_dec > disponivel_para_captura:
            raise ErroPagamento("VALOR_INVALIDO", "valor excede o saldo autorizado")

        pagamento["valor_capturado"] += valor_dec
        pagamento["estado"] = (
            "CAPTURADO"
            if pagamento["valor_capturado"] == pagamento["valor_autorizado"]
            else "CAPTURADO_PARCIAL"
        )

        instante = self._agora()
        self._registrar_historico(pagamento, "CAPTURA", operacao_id, valor_dec, instante)
        pagamento["operacoes"][operacao_id] = {"tipo": "CAPTURA", "valor": valor_dec}

        return {
            "duplicado": False,
            "capturado": valor_dec,
            "saldo_disponivel": self._saldo_disponivel(pagamento),
            "estado": pagamento["estado"],
        }

    def estornar(self, pagamento_id: str, operacao_id: str, valor,
                 motivo: str = "") -> dict:
        pagamento = self._buscar(pagamento_id)
        self._validar_id(operacao_id)
        valor_dec = self._to_decimal(valor)

        duplicada = self._checar_idempotencia(pagamento, operacao_id, "ESTORNO", valor_dec)
        if duplicada is not None:
            return {
                "duplicado": True,
                "estornado": duplicada["valor"],
                "saldo_disponivel": self._saldo_disponivel(pagamento),
                "estado": pagamento["estado"],
            }

        if pagamento["estado"] not in ("CAPTURADO", "CAPTURADO_PARCIAL", "ESTORNADO_PARCIAL"):
            raise ErroPagamento("ESTADO_INVALIDO",
                                 "pagamento nao pode ser estornado neste estado")

        estornavel = pagamento["valor_capturado"] - pagamento["valor_estornado"] - pagamento["valor_chargeback"]
        if valor_dec > estornavel:
            raise ErroPagamento("VALOR_INVALIDO", "valor excede o saldo capturado disponivel")

        pagamento["valor_estornado"] += valor_dec
        pagamento["estado"] = (
            "ESTORNADO"
            if pagamento["valor_estornado"] + pagamento["valor_chargeback"] == pagamento["valor_capturado"]
            else "ESTORNADO_PARCIAL"
        )

        instante = self._agora()
        self._registrar_historico(pagamento, "ESTORNO", operacao_id, valor_dec, instante)
        pagamento["operacoes"][operacao_id] = {"tipo": "ESTORNO", "valor": valor_dec}

        return {
            "duplicado": False,
            "estornado": valor_dec,
            "saldo_disponivel": self._saldo_disponivel(pagamento),
            "estado": pagamento["estado"],
        }

    def registrar_chargeback(self, pagamento_id: str, operacao_id: str,
                             valor, ocorrido_em: datetime) -> dict:
        pagamento = self._buscar(pagamento_id)
        self._validar_id(operacao_id)
        valor_dec = self._to_decimal(valor)
        ocorrido_em_norm = self._validar_data(ocorrido_em)
        if ocorrido_em_norm < pagamento["criado_em"]:
            raise ErroPagamento("DATA_INVALIDA",
                                 "chargeback nao pode ocorrer antes do registro")

        duplicada = self._checar_idempotencia(pagamento, operacao_id, "CHARGEBACK", valor_dec)
        if duplicada is not None:
            return {
                "duplicado": True,
                "chargeback": duplicada["valor"],
                "saldo_disponivel": self._saldo_disponivel(pagamento),
                "estado": pagamento["estado"],
            }

        if pagamento["estado"] not in ("CAPTURADO", "CAPTURADO_PARCIAL"):
            raise ErroPagamento("ESTADO_INVALIDO",
                                 "pagamento nao pode sofrer chargeback neste estado")

        contestavel = pagamento["valor_capturado"] - pagamento["valor_estornado"] - pagamento["valor_chargeback"]
        if valor_dec > contestavel:
            raise ErroPagamento("VALOR_INVALIDO", "valor excede o saldo capturado disponivel")

        pagamento["valor_chargeback"] += valor_dec
        pagamento["estado"] = (
            "CHARGEBACK"
            if pagamento["valor_chargeback"] + pagamento["valor_estornado"] == pagamento["valor_capturado"]
            else "CHARGEBACK_PARCIAL"
        )

        self._registrar_historico(pagamento, "CHARGEBACK", operacao_id, valor_dec, ocorrido_em_norm)
        pagamento["operacoes"][operacao_id] = {"tipo": "CHARGEBACK", "valor": valor_dec}

        return {
            "duplicado": False,
            "chargeback": valor_dec,
            "saldo_disponivel": self._saldo_disponivel(pagamento),
            "estado": pagamento["estado"],
        }

    def consultar(self, pagamento_id: str) -> dict:
        pagamento = self._buscar(pagamento_id)
        return {
            "pagamento_id": pagamento["pagamento_id"],
            "moeda": pagamento["moeda"],
            "valor_autorizado": pagamento["valor_autorizado"],
            "valor_capturado": pagamento["valor_capturado"],
            "valor_estornado": pagamento["valor_estornado"],
            "valor_chargeback": pagamento["valor_chargeback"],
            "saldo_disponivel": self._saldo_disponivel(pagamento),
            "estado": pagamento["estado"],
        }

    def historico(self, pagamento_id: str) -> list[dict]:
        pagamento = self._buscar(pagamento_id)
        return [dict(item) for item in pagamento["historico"]]
