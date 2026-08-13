"""UC-01 - Motor de amortizacao de emprestimo.

Implementacao em Python 3.12, apenas biblioteca padrao.
"""

from __future__ import annotations

import calendar
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Callable, Optional

TWO_PLACES = Decimal("0.01")

CODES = {
    "CONTRATO_INVALIDO",
    "CONTRATO_NAO_ENCONTRADO",
    "ESTADO_INVALIDO",
    "VALOR_INVALIDO",
    "PARCELA_INVALIDA",
    "RENEGOCIACAO_NAO_PERMITIDA",
}

SISTEMAS = {"PRICE", "SAC"}


class ErroEmprestimo(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        self.code = code
        super().__init__(mensagem or code)


def _q(valor: Decimal) -> Decimal:
    return valor.quantize(TWO_PLACES, rounding=ROUND_HALF_EVEN)


def _to_decimal(valor) -> Decimal:
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, bool):
        raise ValueError("tipo invalido")
    if isinstance(valor, int):
        return Decimal(valor)
    if isinstance(valor, float):
        return Decimal(str(valor))
    if isinstance(valor, str):
        return Decimal(valor)
    raise ValueError("tipo invalido")


def _add_months(d: date, months: int) -> date:
    total = d.month - 1 + months
    ano = d.year + total // 12
    mes = total % 12 + 1
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    dia = min(d.day, ultimo_dia)
    return date(ano, mes, dia)


@dataclass
class _Parcela:
    numero: int
    vencimento: date
    juros: Decimal
    amortizacao: Decimal
    valor: Decimal
    saldo_apos: Decimal
    pago_juros: Decimal = Decimal("0.00")
    pago_principal: Decimal = Decimal("0.00")
    pago_encargos: Decimal = Decimal("0.00")
    quitada: bool = False


@dataclass
class _Contrato:
    id: str
    principal_financiado: Decimal
    taxa: Decimal
    prazo_meses: int
    sistema: str
    carencia_meses: int
    data_inicio: date
    parcelas: list = field(default_factory=list)
    renegociado: bool = False
    pagamentos: dict = field(default_factory=dict)


class MotorEmprestimo:
    def __init__(self, agora: Optional[Callable[[], datetime]] = None) -> None:
        self._agora = agora or (lambda: datetime.now())
        self._contratos: dict[str, _Contrato] = {}

    # ------------------------------------------------------------------
    # Criacao / cronograma
    # ------------------------------------------------------------------
    def criar_contrato(self, dados: dict) -> str:
        if not isinstance(dados, dict):
            raise ErroEmprestimo("CONTRATO_INVALIDO")
        for chave in ("principal", "taxa", "prazo_meses", "sistema", "data_inicio"):
            if chave not in dados:
                raise ErroEmprestimo("CONTRATO_INVALIDO")

        sistema = dados.get("sistema")
        if sistema not in SISTEMAS:
            raise ErroEmprestimo("CONTRATO_INVALIDO")

        try:
            principal = _to_decimal(dados.get("principal"))
            taxa = _to_decimal(dados.get("taxa"))
        except Exception:
            raise ErroEmprestimo("CONTRATO_INVALIDO")

        if principal <= 0 or taxa < 0:
            raise ErroEmprestimo("CONTRATO_INVALIDO")

        prazo_meses = dados.get("prazo_meses")
        if not isinstance(prazo_meses, int) or isinstance(prazo_meses, bool):
            raise ErroEmprestimo("CONTRATO_INVALIDO")
        if prazo_meses < 1 or prazo_meses > 120:
            raise ErroEmprestimo("CONTRATO_INVALIDO")

        carencia_meses = dados.get("carencia_meses", 0)
        if carencia_meses is None:
            carencia_meses = 0
        if not isinstance(carencia_meses, int) or isinstance(carencia_meses, bool):
            raise ErroEmprestimo("CONTRATO_INVALIDO")
        if carencia_meses < 0:
            raise ErroEmprestimo("CONTRATO_INVALIDO")

        data_inicio = dados.get("data_inicio")
        if not isinstance(data_inicio, date):
            raise ErroEmprestimo("CONTRATO_INVALIDO")

        principal_financiado = _q(principal * (1 + taxa) ** carencia_meses)

        contrato_id = str(uuid.uuid4())
        contrato = _Contrato(
            id=contrato_id,
            principal_financiado=principal_financiado,
            taxa=taxa,
            prazo_meses=prazo_meses,
            sistema=sistema,
            carencia_meses=carencia_meses,
            data_inicio=data_inicio,
        )
        contrato.parcelas = self._gerar_parcelas(contrato)
        self._contratos[contrato_id] = contrato
        return contrato_id

    def _gerar_parcelas(self, contrato: _Contrato) -> list:
        parcelas = []
        n = contrato.prazo_meses
        taxa = contrato.taxa
        saldo = contrato.principal_financiado
        soma_amort = Decimal("0.00")

        valor_constante = None
        if contrato.sistema == "PRICE":
            if taxa == 0:
                valor_constante = _q(contrato.principal_financiado / n)
            else:
                fator = taxa / (1 - (1 + taxa) ** (-n))
                valor_constante = _q(contrato.principal_financiado * fator)
        else:  # SAC
            amort_base = _q(contrato.principal_financiado / n)

        for i in range(1, n + 1):
            juros_i = _q(saldo * taxa)
            ultima = i == n

            if contrato.sistema == "SAC":
                amort_i = (
                    contrato.principal_financiado - soma_amort
                    if ultima
                    else amort_base
                )
                valor_i = _q(juros_i + amort_i)
            else:  # PRICE
                if ultima:
                    amort_i = contrato.principal_financiado - soma_amort
                    valor_i = _q(juros_i + amort_i)
                else:
                    amort_i = _q(valor_constante - juros_i)
                    valor_i = valor_constante

            soma_amort += amort_i
            saldo_apos = Decimal("0.00") if ultima else _q(saldo - amort_i)

            vencimento = _add_months(contrato.data_inicio, contrato.carencia_meses + i)
            parcelas.append(
                _Parcela(
                    numero=i,
                    vencimento=vencimento,
                    juros=juros_i,
                    amortizacao=amort_i,
                    valor=valor_i,
                    saldo_apos=saldo_apos,
                )
            )
            saldo = saldo_apos
        return parcelas

    def cronograma(self, contrato_id: str) -> list:
        contrato = self._get_contrato(contrato_id)
        return [
            {
                "numero": p.numero,
                "vencimento": p.vencimento,
                "juros": p.juros,
                "amortizacao": p.amortizacao,
                "valor": p.valor,
                "saldo_apos": p.saldo_apos,
            }
            for p in contrato.parcelas
        ]

    # ------------------------------------------------------------------
    # Consultas de valores
    # ------------------------------------------------------------------
    def _componentes_restantes(self, parcela: _Parcela, data: date):
        if parcela.quitada:
            return Decimal("0.00"), Decimal("0.00"), Decimal("0.00")

        principal = parcela.amortizacao - parcela.pago_principal
        juros = parcela.juros - parcela.pago_juros

        if data > parcela.vencimento:
            dias_atraso = (data - parcela.vencimento).days
            encargos_total = _q(
                parcela.valor * Decimal("0.02")
                + parcela.valor * Decimal("0.01") * dias_atraso / Decimal(30)
            )
            encargos = encargos_total - parcela.pago_encargos
            if encargos < 0:
                encargos = Decimal("0.00")
        else:
            encargos = Decimal("0.00")

        return principal, juros, encargos

    def valor_devido(self, contrato_id: str, numero_parcela: int, data: date) -> dict:
        contrato = self._get_contrato(contrato_id)
        parcela = self._get_parcela(contrato, numero_parcela)
        principal, juros, encargos = self._componentes_restantes(parcela, data)
        total = _q(principal + juros + encargos)
        return {
            "principal": principal,
            "juros": juros,
            "encargos": encargos,
            "total": total,
        }

    def saldo_devedor(self, contrato_id: str, data: date) -> Decimal:
        contrato = self._get_contrato(contrato_id)
        total = Decimal("0.00")
        for parcela in contrato.parcelas:
            principal, juros, encargos = self._componentes_restantes(parcela, data)
            total += principal
            if parcela.vencimento < data:
                total += juros + encargos
        return _q(total)

    def situacao(self, contrato_id: str, data: date) -> str:
        contrato = self._get_contrato(contrato_id)
        if contrato.renegociado:
            return "RENEGOCIADO"
        if self.saldo_devedor(contrato_id, data) == Decimal("0.00"):
            return "QUITADO"
        for parcela in contrato.parcelas:
            if parcela.vencimento < data and not parcela.quitada:
                return "EM_ATRASO"
        return "ATIVO"

    # ------------------------------------------------------------------
    # Pagamento
    # ------------------------------------------------------------------
    def registrar_pagamento(
        self,
        contrato_id: str,
        pagamento_id: str,
        numero_parcela: int,
        valor,
        data: date,
    ) -> dict:
        contrato = self._get_contrato(contrato_id)

        if pagamento_id in contrato.pagamentos:
            numero_original = contrato.pagamentos[pagamento_id]
            parcela = self._get_parcela(contrato, numero_original)
            return {
                "duplicado": True,
                "aplicado_encargos": Decimal("0.00"),
                "aplicado_juros": Decimal("0.00"),
                "aplicado_principal": Decimal("0.00"),
                "parcela_quitada": parcela.quitada,
            }

        estado_atual = self.situacao(contrato_id, data)
        if estado_atual in ("QUITADO", "RENEGOCIADO"):
            raise ErroEmprestimo("ESTADO_INVALIDO")

        parcela = self._get_parcela(contrato, numero_parcela)

        try:
            valor_dec = _q(_to_decimal(valor))
        except Exception:
            raise ErroEmprestimo("VALOR_INVALIDO")

        if valor_dec <= 0:
            raise ErroEmprestimo("VALOR_INVALIDO")

        devido = self.valor_devido(contrato_id, numero_parcela, data)
        if valor_dec > devido["total"]:
            raise ErroEmprestimo("VALOR_INVALIDO")

        restante = valor_dec
        aplicado_encargos = min(restante, devido["encargos"])
        restante -= aplicado_encargos
        aplicado_juros = min(restante, devido["juros"])
        restante -= aplicado_juros
        aplicado_principal = min(restante, devido["principal"])
        restante -= aplicado_principal

        parcela.pago_encargos += aplicado_encargos
        parcela.pago_juros += aplicado_juros
        parcela.pago_principal += aplicado_principal

        quitada = (
            devido["encargos"] - aplicado_encargos == 0
            and devido["juros"] - aplicado_juros == 0
            and devido["principal"] - aplicado_principal == 0
        )
        if quitada:
            parcela.quitada = True

        contrato.pagamentos[pagamento_id] = numero_parcela

        return {
            "duplicado": False,
            "aplicado_encargos": aplicado_encargos,
            "aplicado_juros": aplicado_juros,
            "aplicado_principal": aplicado_principal,
            "parcela_quitada": parcela.quitada,
        }

    # ------------------------------------------------------------------
    # Quitacao antecipada / renegociacao
    # ------------------------------------------------------------------
    def quitar_antecipado(self, contrato_id: str, data: date) -> dict:
        contrato = self._get_contrato(contrato_id)
        estado_atual = self.situacao(contrato_id, data)
        if estado_atual in ("QUITADO", "RENEGOCIADO"):
            raise ErroEmprestimo("ESTADO_INVALIDO")

        principal_remanescente = Decimal("0.00")
        encargos_vencidas = Decimal("0.00")
        desconto_juros_futuros = Decimal("0.00")

        for parcela in contrato.parcelas:
            principal, juros, encargos = self._componentes_restantes(parcela, data)
            principal_remanescente += principal
            if parcela.vencimento < data:
                encargos_vencidas += encargos
            else:
                desconto_juros_futuros += juros

            if not parcela.quitada:
                parcela.pago_principal = parcela.amortizacao
                parcela.pago_juros = parcela.juros
                if parcela.vencimento < data:
                    dias_atraso = (data - parcela.vencimento).days
                    encargos_total = _q(
                        parcela.valor * Decimal("0.02")
                        + parcela.valor * Decimal("0.01") * dias_atraso / Decimal(30)
                    )
                    parcela.pago_encargos = encargos_total
                parcela.quitada = True

        return {
            "valor_quitacao": _q(principal_remanescente + encargos_vencidas),
            "desconto_juros_futuros": _q(desconto_juros_futuros),
        }

    def renegociar(
        self, contrato_id: str, novo_prazo_meses: int, nova_taxa, data: date
    ) -> str:
        contrato = self._get_contrato(contrato_id)
        estado_atual = self.situacao(contrato_id, data)
        if estado_atual in ("QUITADO", "RENEGOCIADO"):
            raise ErroEmprestimo("ESTADO_INVALIDO")

        elegivel = any(
            parcela.vencimento < data
            and not parcela.quitada
            and (data - parcela.vencimento).days >= 30
            for parcela in contrato.parcelas
        )
        if not elegivel:
            raise ErroEmprestimo("RENEGOCIACAO_NAO_PERMITIDA")

        saldo = self.saldo_devedor(contrato_id, data)
        novo_id = self.criar_contrato(
            {
                "principal": saldo,
                "taxa": nova_taxa,
                "prazo_meses": novo_prazo_meses,
                "sistema": contrato.sistema,
                "carencia_meses": 0,
                "data_inicio": data,
            }
        )
        contrato.renegociado = True
        return novo_id

    # ------------------------------------------------------------------
    # Auxiliares
    # ------------------------------------------------------------------
    def _get_contrato(self, contrato_id: str) -> _Contrato:
        contrato = self._contratos.get(contrato_id)
        if contrato is None:
            raise ErroEmprestimo("CONTRATO_NAO_ENCONTRADO")
        return contrato

    def _get_parcela(self, contrato: _Contrato, numero_parcela: int) -> _Parcela:
        if (
            not isinstance(numero_parcela, int)
            or isinstance(numero_parcela, bool)
            or numero_parcela < 1
            or numero_parcela > len(contrato.parcelas)
        ):
            raise ErroEmprestimo("PARCELA_INVALIDA")
        return contrato.parcelas[numero_parcela - 1]
