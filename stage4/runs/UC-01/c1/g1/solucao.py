"""UC-01 - Motor de amortizacao de emprestimo."""

from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Callable

_Q2 = Decimal("0.01")


def _q2(valor: Decimal) -> Decimal:
    return valor.quantize(_Q2, rounding=ROUND_HALF_EVEN)


def _to_decimal(valor) -> Decimal:
    if isinstance(valor, bool):
        raise ValueError("bool nao suportado")
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, int):
        return Decimal(valor)
    if isinstance(valor, float):
        return Decimal(str(valor))
    if isinstance(valor, str):
        return Decimal(valor)
    raise ValueError("tipo nao suportado")


def _add_months(d: date, months: int) -> date:
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def _dias_atraso(vencimento: date, data: date) -> int:
    delta = (data - vencimento).days
    return delta if delta > 0 else 0


def _calc_encargos(valor: Decimal, atraso: int) -> Decimal:
    if atraso <= 0:
        return Decimal("0.00")
    multa = valor * Decimal("0.02")
    mora = valor * Decimal("0.01") * Decimal(atraso) / Decimal(30)
    return _q2(multa + mora)


class ErroEmprestimo(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code
        self.mensagem = mensagem


class _Parcela:
    def __init__(self, numero: int, vencimento: date, juros_original: Decimal,
                 amortizacao_original: Decimal, valor_nominal: Decimal,
                 saldo_apos_original: Decimal) -> None:
        self.numero = numero
        self.vencimento = vencimento
        self.juros_original = juros_original
        self.amortizacao_original = amortizacao_original
        self.valor_nominal = valor_nominal
        self.saldo_apos_original = saldo_apos_original
        self.juros_pago = Decimal("0.00")
        self.principal_pago = Decimal("0.00")
        self.encargos_pago = Decimal("0.00")

    def juros_devido(self) -> Decimal:
        restante = self.juros_original - self.juros_pago
        return restante if restante > 0 else Decimal("0.00")

    def principal_devido(self) -> Decimal:
        restante = self.amortizacao_original - self.principal_pago
        return restante if restante > 0 else Decimal("0.00")

    def encargos_devido(self, data: date) -> Decimal:
        total = _calc_encargos(self.valor_nominal, _dias_atraso(self.vencimento, data))
        restante = total - self.encargos_pago
        return restante if restante > 0 else Decimal("0.00")


class _Contrato:
    def __init__(self, id_: str, principal_original: Decimal, taxa: Decimal,
                 prazo_meses: int, sistema: str, carencia_meses: int,
                 data_inicio: date, principal_financiado: Decimal,
                 parcelas: list[_Parcela]) -> None:
        self.id = id_
        self.principal_original = principal_original
        self.taxa = taxa
        self.prazo_meses = prazo_meses
        self.sistema = sistema
        self.carencia_meses = carencia_meses
        self.data_inicio = data_inicio
        self.principal_financiado = principal_financiado
        self.parcelas = parcelas
        self.pagamentos: dict[str, dict] = {}
        self.renegociado = False
        self.quitado_forcado = False


class MotorEmprestimo:
    def __init__(self, agora: Callable[[], datetime] | None = None) -> None:
        self._agora = agora or datetime.now
        self._contratos: dict[str, _Contrato] = {}

    # ------------------------------------------------------------------ #
    # helpers internos
    # ------------------------------------------------------------------ #
    def _get_contrato(self, contrato_id: str) -> _Contrato:
        contrato = self._contratos.get(contrato_id)
        if contrato is None:
            raise ErroEmprestimo("CONTRATO_NAO_ENCONTRADO")
        return contrato

    def _checar_parcela(self, contrato: _Contrato, numero_parcela) -> None:
        if not isinstance(numero_parcela, int) or isinstance(numero_parcela, bool):
            raise ErroEmprestimo("PARCELA_INVALIDA")
        if numero_parcela < 1 or numero_parcela > contrato.prazo_meses:
            raise ErroEmprestimo("PARCELA_INVALIDA")

    def _calc_devido(self, parcela: _Parcela, data: date) -> dict:
        principal = parcela.principal_devido()
        juros = parcela.juros_devido()
        encargos = parcela.encargos_devido(data)
        total = _q2(principal + juros + encargos)
        return {"principal": _q2(principal), "juros": _q2(juros),
                "encargos": _q2(encargos), "total": total}

    def _gerar_parcelas(self, principal: Decimal, taxa: Decimal, prazo_meses: int,
                         sistema: str, data_inicio: date,
                         carencia_meses: int) -> list[_Parcela]:
        parcelas: list[_Parcela] = []
        saldo = principal
        soma_amort = Decimal("0.00")
        i = taxa
        n = prazo_meses

        if sistema == "PRICE":
            if i == 0:
                valor_parcela = _q2(principal / n)
            else:
                fator = (Decimal(1) + i) ** n
                pmt = principal * i * fator / (fator - Decimal(1))
                valor_parcela = _q2(pmt)
        else:
            amort_base = _q2(principal / n)

        for k in range(1, n + 1):
            juros_k = _q2(saldo * i)
            if sistema == "PRICE":
                if k < n:
                    amort_k = _q2(valor_parcela - juros_k)
                    valor_k = valor_parcela
                else:
                    amort_k = _q2(principal - soma_amort)
                    valor_k = _q2(juros_k + amort_k)
            else:
                if k < n:
                    amort_k = amort_base
                else:
                    amort_k = _q2(principal - soma_amort)
                valor_k = _q2(juros_k + amort_k)

            saldo_apos = _q2(saldo - amort_k)
            if k == n:
                saldo_apos = Decimal("0.00")

            vencimento = _add_months(data_inicio, carencia_meses + k)
            parcelas.append(_Parcela(
                numero=k, vencimento=vencimento, juros_original=juros_k,
                amortizacao_original=amort_k, valor_nominal=valor_k,
                saldo_apos_original=saldo_apos,
            ))
            soma_amort += amort_k
            saldo = saldo_apos

        return parcelas

    # ------------------------------------------------------------------ #
    # API pública
    # ------------------------------------------------------------------ #
    def criar_contrato(self, dados: dict) -> str:
        if not isinstance(dados, dict):
            raise ErroEmprestimo("CONTRATO_INVALIDO")

        for chave in ("principal", "taxa", "prazo_meses", "sistema", "data_inicio"):
            if chave not in dados:
                raise ErroEmprestimo("CONTRATO_INVALIDO")

        sistema = dados.get("sistema")
        if sistema not in ("PRICE", "SAC"):
            raise ErroEmprestimo("CONTRATO_INVALIDO")

        try:
            principal = _to_decimal(dados["principal"])
        except Exception:
            raise ErroEmprestimo("CONTRATO_INVALIDO")
        if principal <= 0:
            raise ErroEmprestimo("CONTRATO_INVALIDO")

        try:
            taxa = _to_decimal(dados["taxa"])
        except Exception:
            raise ErroEmprestimo("CONTRATO_INVALIDO")
        if taxa < 0:
            raise ErroEmprestimo("CONTRATO_INVALIDO")

        prazo_meses = dados["prazo_meses"]
        if not isinstance(prazo_meses, int) or isinstance(prazo_meses, bool):
            raise ErroEmprestimo("CONTRATO_INVALIDO")
        if prazo_meses < 1 or prazo_meses > 120:
            raise ErroEmprestimo("CONTRATO_INVALIDO")

        carencia_meses = dados.get("carencia_meses", 0)
        if not isinstance(carencia_meses, int) or isinstance(carencia_meses, bool):
            raise ErroEmprestimo("CONTRATO_INVALIDO")
        if carencia_meses < 0:
            raise ErroEmprestimo("CONTRATO_INVALIDO")

        data_inicio = dados["data_inicio"]
        if not isinstance(data_inicio, date):
            raise ErroEmprestimo("CONTRATO_INVALIDO")

        principal = _q2(principal)
        principal_financiado = _q2(principal * (Decimal(1) + taxa) ** carencia_meses)

        parcelas = self._gerar_parcelas(principal_financiado, taxa, prazo_meses,
                                         sistema, data_inicio, carencia_meses)

        contrato_id = uuid.uuid4().hex
        contrato = _Contrato(contrato_id, principal, taxa, prazo_meses, sistema,
                              carencia_meses, data_inicio, principal_financiado, parcelas)
        self._contratos[contrato_id] = contrato
        return contrato_id

    def cronograma(self, contrato_id: str) -> list[dict]:
        contrato = self._get_contrato(contrato_id)
        return [
            {
                "numero": p.numero,
                "vencimento": p.vencimento,
                "juros": p.juros_original,
                "amortizacao": p.amortizacao_original,
                "valor": p.valor_nominal,
                "saldo_apos": p.saldo_apos_original,
            }
            for p in contrato.parcelas
        ]

    def valor_devido(self, contrato_id: str, numero_parcela: int, data: date) -> dict:
        contrato = self._get_contrato(contrato_id)
        self._checar_parcela(contrato, numero_parcela)
        parcela = contrato.parcelas[numero_parcela - 1]
        return self._calc_devido(parcela, data)

    def registrar_pagamento(self, contrato_id: str, pagamento_id: str,
                             numero_parcela: int, valor, data: date) -> dict:
        contrato = self._get_contrato(contrato_id)

        if pagamento_id in contrato.pagamentos:
            registro = contrato.pagamentos[pagamento_id]
            parcela = contrato.parcelas[registro["numero_parcela"] - 1]
            devido = self._calc_devido(parcela, data)
            return {
                "duplicado": True,
                "aplicado_encargos": Decimal("0.00"),
                "aplicado_juros": Decimal("0.00"),
                "aplicado_principal": Decimal("0.00"),
                "parcela_quitada": devido["total"] == Decimal("0.00"),
            }

        if self.situacao(contrato_id, data) in ("QUITADO", "RENEGOCIADO"):
            raise ErroEmprestimo("ESTADO_INVALIDO")

        self._checar_parcela(contrato, numero_parcela)

        try:
            valor_dec = _to_decimal(valor)
        except Exception:
            raise ErroEmprestimo("VALOR_INVALIDO")
        if valor_dec <= 0:
            raise ErroEmprestimo("VALOR_INVALIDO")

        parcela = contrato.parcelas[numero_parcela - 1]
        devido = self._calc_devido(parcela, data)
        if valor_dec > devido["total"]:
            raise ErroEmprestimo("VALOR_INVALIDO")

        restante = valor_dec
        aplicado_encargos = min(restante, devido["encargos"])
        restante -= aplicado_encargos
        aplicado_juros = min(restante, devido["juros"])
        restante -= aplicado_juros
        aplicado_principal = min(restante, devido["principal"])
        restante -= aplicado_principal

        parcela.encargos_pago += aplicado_encargos
        parcela.juros_pago += aplicado_juros
        parcela.principal_pago += aplicado_principal

        contrato.pagamentos[pagamento_id] = {"numero_parcela": numero_parcela}

        novo_devido = self._calc_devido(parcela, data)
        return {
            "duplicado": False,
            "aplicado_encargos": _q2(aplicado_encargos),
            "aplicado_juros": _q2(aplicado_juros),
            "aplicado_principal": _q2(aplicado_principal),
            "parcela_quitada": novo_devido["total"] == Decimal("0.00"),
        }

    def saldo_devedor(self, contrato_id: str, data: date) -> Decimal:
        contrato = self._get_contrato(contrato_id)
        if contrato.quitado_forcado:
            return Decimal("0.00")

        principal = Decimal("0.00")
        juros = Decimal("0.00")
        encargos = Decimal("0.00")
        for parcela in contrato.parcelas:
            principal += parcela.principal_devido()
            if parcela.vencimento <= data:
                juros += parcela.juros_devido()
            encargos += parcela.encargos_devido(data)

        return _q2(principal + juros + encargos)

    def quitar_antecipado(self, contrato_id: str, data: date) -> dict:
        contrato = self._get_contrato(contrato_id)
        if self.situacao(contrato_id, data) in ("QUITADO", "RENEGOCIADO"):
            raise ErroEmprestimo("ESTADO_INVALIDO")

        principal_remanescente = Decimal("0.00")
        encargos_vencidas = Decimal("0.00")
        desconto_juros_futuros = Decimal("0.00")
        for parcela in contrato.parcelas:
            principal_remanescente += parcela.principal_devido()
            if parcela.vencimento <= data:
                encargos_vencidas += parcela.encargos_devido(data)
            else:
                desconto_juros_futuros += parcela.juros_devido()

        valor_quitacao = _q2(principal_remanescente + encargos_vencidas)
        desconto_juros_futuros = _q2(desconto_juros_futuros)

        for parcela in contrato.parcelas:
            parcela.principal_pago = parcela.amortizacao_original
            parcela.juros_pago = parcela.juros_original
            if parcela.vencimento <= data:
                parcela.encargos_pago = _calc_encargos(
                    parcela.valor_nominal, _dias_atraso(parcela.vencimento, data))
            else:
                parcela.encargos_pago = Decimal("0.00")

        contrato.quitado_forcado = True

        return {"valor_quitacao": valor_quitacao,
                "desconto_juros_futuros": desconto_juros_futuros}

    def renegociar(self, contrato_id: str, novo_prazo_meses: int, nova_taxa,
                   data: date) -> str:
        contrato = self._get_contrato(contrato_id)
        if self.situacao(contrato_id, data) in ("QUITADO", "RENEGOCIADO"):
            raise ErroEmprestimo("ESTADO_INVALIDO")

        elegivel = any(
            parcela.vencimento <= data
            and (data - parcela.vencimento).days >= 30
            and self._calc_devido(parcela, data)["total"] > 0
            for parcela in contrato.parcelas
        )
        if not elegivel:
            raise ErroEmprestimo("RENEGOCIACAO_NAO_PERMITIDA")

        saldo = self.saldo_devedor(contrato_id, data)
        novo_id = self.criar_contrato({
            "principal": saldo,
            "taxa": nova_taxa,
            "prazo_meses": novo_prazo_meses,
            "sistema": contrato.sistema,
            "carencia_meses": 0,
            "data_inicio": data,
        })

        contrato.renegociado = True
        return novo_id

    def situacao(self, contrato_id: str, data: date) -> str:
        contrato = self._get_contrato(contrato_id)
        if contrato.renegociado:
            return "RENEGOCIADO"
        if contrato.quitado_forcado or self.saldo_devedor(contrato_id, data) == Decimal("0.00"):
            return "QUITADO"
        for parcela in contrato.parcelas:
            if parcela.vencimento <= data:
                devido = self._calc_devido(parcela, data)
                if devido["total"] > 0:
                    return "EM_ATRASO"
        return "ATIVO"
