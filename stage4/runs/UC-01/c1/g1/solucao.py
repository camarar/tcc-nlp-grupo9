"""UC-01 — Motor de amortização de empréstimo.

Implementação de referência usando apenas a biblioteca padrão.
"""

from __future__ import annotations

import calendar
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext
from typing import Callable, Optional

getcontext().prec = 50

CENTAVO = Decimal("0.01")
MULTA_PCT = Decimal("0.02")       # multa fixa de 2% sobre o saldo em atraso
MORA_AO_MES_PCT = Decimal("0.01")  # juros de mora de 1% ao mês, pro-rata dia

SITUACOES = ("ATIVO", "EM_ATRASO", "QUITADO", "RENEGOCIADO")
SISTEMAS = ("PRICE", "SAC")


class ErroEmprestimo(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code
        self.mensagem = mensagem


def _money(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _to_decimal(valor) -> Decimal:
    if isinstance(valor, bool):
        raise ErroEmprestimo("VALOR_INVALIDO", "valor booleano não é aceito")
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, int):
        return Decimal(valor)
    if isinstance(valor, float):
        return Decimal(str(valor))
    if isinstance(valor, str):
        try:
            return Decimal(valor.strip())
        except InvalidOperation:
            raise ErroEmprestimo("VALOR_INVALIDO", f"valor monetário inválido: {valor!r}")
    raise ErroEmprestimo("VALOR_INVALIDO", f"tipo inválido para valor monetário: {type(valor)!r}")


def _add_months(base: date, meses: int) -> date:
    indice = base.month - 1 + meses
    ano = base.year + indice // 12
    mes = indice % 12 + 1
    dia = min(base.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def _is_int(valor) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


@dataclass
class Aplicacao:
    data: date
    principal: Decimal
    juros: Decimal
    encargos: Decimal


@dataclass
class Parcela:
    numero: int
    vencimento: date
    juros: Decimal
    amortizacao: Decimal
    valor: Decimal
    saldo_apos: Decimal
    aplicacoes: list = field(default_factory=list)


@dataclass
class Contrato:
    id: str
    principal: Decimal
    taxa: Decimal
    prazo_meses: int
    sistema: str
    carencia_meses: int
    data_inicio: date
    parcelas: list
    pagamentos: dict = field(default_factory=dict)
    criado_em: Optional[datetime] = None
    encerrado_em: Optional[date] = None
    encerrado_tipo: Optional[str] = None
    renegociado_para: Optional[str] = None


def _gerar_parcelas(principal: Decimal, taxa: Decimal, prazo_meses: int,
                     sistema: str, carencia_meses: int, data_inicio: date) -> list:
    parcelas = []
    numero = 0
    saldo = principal

    for _ in range(carencia_meses):
        numero += 1
        vencimento = _add_months(data_inicio, numero)
        juros = _money(saldo * taxa)
        amortizacao = Decimal("0.00")
        valor = juros
        parcelas.append(Parcela(numero, vencimento, juros, amortizacao, valor, _money(saldo)))

    if sistema == "PRICE":
        if taxa == 0:
            parcela_fixa = _money(saldo / prazo_meses)
        else:
            fator = 1 - (1 + taxa) ** (-prazo_meses)
            parcela_fixa = _money(saldo * taxa / fator)
        for i in range(1, prazo_meses + 1):
            numero += 1
            vencimento = _add_months(data_inicio, numero)
            juros = _money(saldo * taxa)
            if i == prazo_meses:
                amortizacao = saldo
                valor = _money(amortizacao + juros)
            else:
                amortizacao = _money(parcela_fixa - juros)
                valor = parcela_fixa
            saldo = _money(saldo - amortizacao)
            parcelas.append(Parcela(numero, vencimento, juros, amortizacao, valor, saldo))
    else:  # SAC
        amortizacao_fixa = _money(principal / prazo_meses)
        for i in range(1, prazo_meses + 1):
            numero += 1
            vencimento = _add_months(data_inicio, numero)
            juros = _money(saldo * taxa)
            amortizacao = saldo if i == prazo_meses else amortizacao_fixa
            valor = _money(amortizacao + juros)
            saldo = _money(saldo - amortizacao)
            parcelas.append(Parcela(numero, vencimento, juros, amortizacao, valor, saldo))

    return parcelas


class MotorEmprestimo:
    def __init__(self, agora: Optional[Callable[[], datetime]] = None) -> None:
        self._agora = agora or (lambda: datetime.now())
        self._contratos: dict = {}

    # ------------------------------------------------------------------
    # Auxiliares internos
    # ------------------------------------------------------------------
    def _get_contrato(self, contrato_id: str) -> Contrato:
        contrato = self._contratos.get(contrato_id)
        if contrato is None:
            raise ErroEmprestimo("CONTRATO_NAO_ENCONTRADO",
                                  f"contrato não encontrado: {contrato_id!r}")
        return contrato

    def _get_parcela(self, contrato: Contrato, numero_parcela: int) -> Parcela:
        if not _is_int(numero_parcela) or not (1 <= numero_parcela <= len(contrato.parcelas)):
            raise ErroEmprestimo("PARCELA_INVALIDA",
                                  f"número de parcela inválido: {numero_parcela!r}")
        return contrato.parcelas[numero_parcela - 1]

    @staticmethod
    def _pago_ate(parcela: Parcela, data: date):
        principal = Decimal("0.00")
        juros = Decimal("0.00")
        encargos = Decimal("0.00")
        for ap in parcela.aplicacoes:
            if ap.data <= data:
                principal += ap.principal
                juros += ap.juros
                encargos += ap.encargos
        return principal, juros, encargos

    @staticmethod
    def _encargos(parcela: Parcela, data: date, pago_principal: Decimal,
                  pago_juros: Decimal, pago_encargos: Decimal) -> Decimal:
        if data <= parcela.vencimento:
            return Decimal("0.00")
        dias_atraso = (data - parcela.vencimento).days
        saldo_parcela = (parcela.amortizacao + parcela.juros) - pago_principal - pago_juros
        if saldo_parcela <= 0:
            return Decimal("0.00")
        multa = saldo_parcela * MULTA_PCT
        mora = saldo_parcela * MORA_AO_MES_PCT * Decimal(dias_atraso) / Decimal("30")
        pendente = multa + mora - pago_encargos
        return _money(pendente) if pendente > 0 else Decimal("0.00")

    def _valor_liquidacao(self, contrato: Contrato, data: date):
        total = Decimal("0.00")
        desconto = Decimal("0.00")
        for p in contrato.parcelas:
            pago_principal, pago_juros, pago_encargos = self._pago_ate(p, data)
            principal_restante = max(p.amortizacao - pago_principal, Decimal("0"))
            if p.vencimento <= data:
                juros_restante = max(p.juros - pago_juros, Decimal("0"))
                encargos_restante = self._encargos(p, data, pago_principal, pago_juros, pago_encargos)
                total += principal_restante + juros_restante + encargos_restante
            else:
                juros_futuro = max(p.juros - pago_juros, Decimal("0"))
                desconto += juros_futuro
                total += principal_restante
        return _money(total), _money(desconto)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def criar_contrato(self, dados: dict) -> str:
        if not isinstance(dados, dict):
            raise ErroEmprestimo("CONTRATO_INVALIDO", "dados deve ser um dicionário")

        for campo in ("principal", "taxa", "prazo_meses", "sistema", "data_inicio"):
            if campo not in dados:
                raise ErroEmprestimo("CONTRATO_INVALIDO", f"campo obrigatório ausente: {campo}")

        principal = _to_decimal(dados["principal"])
        if principal <= 0:
            raise ErroEmprestimo("VALOR_INVALIDO", "principal deve ser positivo")

        taxa = _to_decimal(dados["taxa"])
        if taxa < 0:
            raise ErroEmprestimo("VALOR_INVALIDO", "taxa não pode ser negativa")

        prazo_meses = dados["prazo_meses"]
        if not _is_int(prazo_meses) or prazo_meses <= 0:
            raise ErroEmprestimo("CONTRATO_INVALIDO", "prazo_meses deve ser inteiro positivo")

        sistema = dados["sistema"]
        if sistema not in SISTEMAS:
            raise ErroEmprestimo("CONTRATO_INVALIDO", "sistema deve ser PRICE ou SAC")

        data_inicio = dados["data_inicio"]
        if not isinstance(data_inicio, date):
            raise ErroEmprestimo("CONTRATO_INVALIDO", "data_inicio deve ser datetime.date")

        carencia_meses = dados.get("carencia_meses", 0)
        if not _is_int(carencia_meses) or carencia_meses < 0:
            raise ErroEmprestimo("CONTRATO_INVALIDO", "carencia_meses deve ser inteiro não-negativo")

        contrato_id = f"ct-{uuid.uuid4().hex}"
        parcelas = _gerar_parcelas(principal, taxa, prazo_meses, sistema, carencia_meses, data_inicio)
        contrato = Contrato(
            id=contrato_id,
            principal=principal,
            taxa=taxa,
            prazo_meses=prazo_meses,
            sistema=sistema,
            carencia_meses=carencia_meses,
            data_inicio=data_inicio,
            parcelas=parcelas,
            criado_em=self._agora(),
        )
        self._contratos[contrato_id] = contrato
        return contrato_id

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

    def valor_devido(self, contrato_id: str, numero_parcela: int, data: date) -> dict:
        contrato = self._get_contrato(contrato_id)
        parcela = self._get_parcela(contrato, numero_parcela)
        pago_principal, pago_juros, pago_encargos = self._pago_ate(parcela, data)
        principal = _money(max(parcela.amortizacao - pago_principal, Decimal("0")))
        juros = _money(max(parcela.juros - pago_juros, Decimal("0")))
        encargos = self._encargos(parcela, data, pago_principal, pago_juros, pago_encargos)
        total = _money(principal + juros + encargos)
        return {"principal": principal, "juros": juros, "encargos": encargos, "total": total}

    def registrar_pagamento(self, contrato_id: str, pagamento_id: str,
                             numero_parcela: int, valor, data: date) -> dict:
        contrato = self._get_contrato(contrato_id)
        situacao_atual = self.situacao(contrato_id, data)
        if situacao_atual in ("QUITADO", "RENEGOCIADO"):
            raise ErroEmprestimo("ESTADO_INVALIDO", "contrato encerrado não aceita pagamentos")

        parcela = self._get_parcela(contrato, numero_parcela)
        valor_decimal = _to_decimal(valor)
        if valor_decimal <= 0:
            raise ErroEmprestimo("VALOR_INVALIDO", "valor do pagamento deve ser positivo")

        if pagamento_id in contrato.pagamentos:
            pago_principal, pago_juros, _ = self._pago_ate(parcela, data)
            quitada_atual = pago_principal >= parcela.amortizacao and pago_juros >= parcela.juros
            return {
                "duplicado": True,
                "aplicado_encargos": Decimal("0.00"),
                "aplicado_juros": Decimal("0.00"),
                "aplicado_principal": Decimal("0.00"),
                "parcela_quitada": quitada_atual,
            }

        devido = self.valor_devido(contrato_id, numero_parcela, data)
        restante = valor_decimal

        aplicado_encargos = min(restante, devido["encargos"])
        restante -= aplicado_encargos
        aplicado_juros = min(restante, devido["juros"])
        restante -= aplicado_juros
        aplicado_principal = min(restante, devido["principal"])

        aplicado_encargos = _money(aplicado_encargos)
        aplicado_juros = _money(aplicado_juros)
        aplicado_principal = _money(aplicado_principal)

        parcela.aplicacoes.append(Aplicacao(data, aplicado_principal, aplicado_juros, aplicado_encargos))
        contrato.pagamentos[pagamento_id] = True

        pago_principal, pago_juros, _ = self._pago_ate(parcela, data)
        parcela_quitada = pago_principal >= parcela.amortizacao and pago_juros >= parcela.juros

        return {
            "duplicado": False,
            "aplicado_encargos": aplicado_encargos,
            "aplicado_juros": aplicado_juros,
            "aplicado_principal": aplicado_principal,
            "parcela_quitada": parcela_quitada,
        }

    def saldo_devedor(self, contrato_id: str, data: date) -> Decimal:
        contrato = self._get_contrato(contrato_id)
        if contrato.encerrado_em is not None and data >= contrato.encerrado_em:
            return Decimal("0.00")
        total = Decimal("0.00")
        for p in contrato.parcelas:
            pago_principal, _, _ = self._pago_ate(p, data)
            total += max(p.amortizacao - pago_principal, Decimal("0.00"))
        return _money(total)

    def quitar_antecipado(self, contrato_id: str, data: date) -> dict:
        contrato = self._get_contrato(contrato_id)
        situacao_atual = self.situacao(contrato_id, data)
        if situacao_atual in ("QUITADO", "RENEGOCIADO"):
            raise ErroEmprestimo("ESTADO_INVALIDO", "contrato já encerrado")

        valor_quitacao, desconto = self._valor_liquidacao(contrato, data)
        contrato.encerrado_em = data
        contrato.encerrado_tipo = "QUITADO"
        return {"valor_quitacao": valor_quitacao, "desconto_juros_futuros": desconto}

    def renegociar(self, contrato_id: str, novo_prazo_meses: int, nova_taxa, data: date) -> str:
        contrato = self._get_contrato(contrato_id)
        situacao_atual = self.situacao(contrato_id, data)
        if situacao_atual != "EM_ATRASO":
            raise ErroEmprestimo("RENEGOCIACAO_NAO_PERMITIDA",
                                  "somente contratos em atraso podem ser renegociados")

        if not _is_int(novo_prazo_meses) or novo_prazo_meses <= 0:
            raise ErroEmprestimo("CONTRATO_INVALIDO", "novo_prazo_meses deve ser inteiro positivo")

        nova_taxa_decimal = _to_decimal(nova_taxa)
        if nova_taxa_decimal < 0:
            raise ErroEmprestimo("VALOR_INVALIDO", "nova_taxa não pode ser negativa")

        novo_principal, _ = self._valor_liquidacao(contrato, data)
        novo_id = self.criar_contrato({
            "principal": novo_principal,
            "taxa": nova_taxa_decimal,
            "prazo_meses": novo_prazo_meses,
            "sistema": contrato.sistema,
            "data_inicio": data,
        })

        contrato.encerrado_em = data
        contrato.encerrado_tipo = "RENEGOCIADO"
        contrato.renegociado_para = novo_id
        return novo_id

    def situacao(self, contrato_id: str, data: date) -> str:
        contrato = self._get_contrato(contrato_id)
        if contrato.encerrado_em is not None and data >= contrato.encerrado_em:
            return contrato.encerrado_tipo

        for p in contrato.parcelas:
            if p.vencimento < data:
                pago_principal, pago_juros, _ = self._pago_ate(p, data)
                if pago_principal < p.amortizacao or pago_juros < p.juros:
                    return "EM_ATRASO"

        return "ATIVO"
