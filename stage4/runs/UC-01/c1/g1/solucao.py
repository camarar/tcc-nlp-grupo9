"""UC-01 — Motor de amortização de empréstimo.

Regras de negócio adotadas (não especificadas literalmente no enunciado):

- `taxa` é a taxa de juros efetiva ao mês (fração, ex.: "0.02" = 2% a.m.).
- Durante a carência apenas juros são cobrados (amortização zero); a
  amortização do saldo começa na parcela seguinte à carência.
- PRICE usa parcela constante (fórmula francesa); SAC usa amortização
  constante. Em ambos, a última parcela amortizante absorve o resíduo de
  arredondamento para que o saldo termine exatamente em zero.
- Pagamentos em atraso sofrem multa de 2% e mora de 1% ao mês (pro-rata
  diário) sobre o saldo pendente (juros + amortização) da parcela.
- Pagamentos são aplicados na ordem encargos -> juros -> principal, e
  ficam limitados ao valor efetivamente devido da parcela informada.
- `renegociar` só é permitido quando o contrato está EM_ATRASO na data
  informada; o novo contrato nasce com o total pendente (principal, juros
  e encargos das parcelas já vencidas) como novo principal.
- Quitação/renegociação são estados terminais e definitivos a partir da
  data em que ocorreram.
"""

from __future__ import annotations

import calendar
import decimal
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Callable, Optional

CENT = Decimal("0.01")
TAXA_MULTA = Decimal("0.02")
TAXA_MORA_DIARIA = Decimal("0.01") / Decimal("30")

SISTEMAS_VALIDOS = {"PRICE", "SAC"}


class ErroEmprestimo(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code
        self.mensagem = mensagem


def _to_decimal(valor, code: str = "VALOR_INVALIDO") -> Decimal:
    if isinstance(valor, Decimal):
        d = valor
    elif isinstance(valor, bool):
        raise ErroEmprestimo(code, "valor booleano nao e um valor monetario valido")
    elif isinstance(valor, int):
        d = Decimal(valor)
    elif isinstance(valor, float):
        d = Decimal(str(valor))
    elif isinstance(valor, str):
        try:
            d = Decimal(valor.strip())
        except InvalidOperation:
            raise ErroEmprestimo(code, f"valor monetario invalido: {valor!r}")
    else:
        raise ErroEmprestimo(code, f"tipo de valor invalido: {type(valor)!r}")
    if not d.is_finite():
        raise ErroEmprestimo(code, "valor nao finito")
    return d


def _money(d: Decimal) -> Decimal:
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def _add_months(d: date, n: int) -> date:
    total = d.month - 1 + n
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _is_date(v) -> bool:
    return isinstance(v, date) and not isinstance(v, datetime)


@dataclass
class _Parcela:
    numero: int
    vencimento: date
    juros: Decimal
    amortizacao: Decimal
    valor: Decimal
    saldo_apos: Decimal
    juros_pago: Decimal = field(default_factory=lambda: Decimal("0.00"))
    principal_pago: Decimal = field(default_factory=lambda: Decimal("0.00"))
    encargos_pago: Decimal = field(default_factory=lambda: Decimal("0.00"))


@dataclass
class _Contrato:
    id: str
    principal: Decimal
    taxa: Decimal
    prazo_meses: int
    sistema: str
    carencia_meses: int
    data_inicio: date
    parcelas: list = field(default_factory=list)
    estado: str = "ATIVO"  # ATIVO | QUITADO | RENEGOCIADO
    quitado_em: Optional[date] = None
    renegociado_para: Optional[str] = None
    pagamentos: dict = field(default_factory=dict)  # pagamento_id -> resultado


class MotorEmprestimo:
    def __init__(self, agora: Optional[Callable[[], datetime]] = None) -> None:
        self._agora = agora or datetime.now
        self._contratos: dict[str, _Contrato] = {}

    # ------------------------------------------------------------------ #
    # criação e consulta de cronograma
    # ------------------------------------------------------------------ #

    def criar_contrato(self, dados: dict) -> str:
        if not isinstance(dados, dict):
            raise ErroEmprestimo("CONTRATO_INVALIDO", "dados deve ser um dicionario")

        sistema = dados.get("sistema")
        prazo_meses = dados.get("prazo_meses")
        carencia_meses = dados.get("carencia_meses", 0)
        data_inicio = dados.get("data_inicio")

        if sistema not in SISTEMAS_VALIDOS:
            raise ErroEmprestimo("CONTRATO_INVALIDO", "sistema deve ser PRICE ou SAC")
        if not isinstance(prazo_meses, int) or isinstance(prazo_meses, bool) or prazo_meses <= 0:
            raise ErroEmprestimo("CONTRATO_INVALIDO", "prazo_meses deve ser inteiro positivo")
        if not isinstance(carencia_meses, int) or isinstance(carencia_meses, bool) or carencia_meses < 0:
            raise ErroEmprestimo("CONTRATO_INVALIDO", "carencia_meses deve ser inteiro nao negativo")
        if carencia_meses >= prazo_meses:
            raise ErroEmprestimo("CONTRATO_INVALIDO", "carencia_meses deve ser menor que prazo_meses")
        if not _is_date(data_inicio):
            raise ErroEmprestimo("CONTRATO_INVALIDO", "data_inicio deve ser datetime.date")

        principal = _to_decimal(dados.get("principal"))
        taxa = _to_decimal(dados.get("taxa"))
        if principal <= 0:
            raise ErroEmprestimo("VALOR_INVALIDO", "principal deve ser positivo")
        if taxa < 0:
            raise ErroEmprestimo("VALOR_INVALIDO", "taxa nao pode ser negativa")

        contrato_id = str(uuid.uuid4())
        parcelas = self._gerar_cronograma(principal, taxa, prazo_meses, sistema, carencia_meses, data_inicio)
        self._contratos[contrato_id] = _Contrato(
            id=contrato_id,
            principal=principal,
            taxa=taxa,
            prazo_meses=prazo_meses,
            sistema=sistema,
            carencia_meses=carencia_meses,
            data_inicio=data_inicio,
            parcelas=parcelas,
        )
        return contrato_id

    def _gerar_cronograma(self, principal, taxa, prazo_meses, sistema, carencia_meses, data_inicio):
        n_amort = prazo_meses - carencia_meses

        with decimal.localcontext() as ctx:
            ctx.prec = 50
            valor_parcela = None
            amortizacao_constante = None
            if sistema == "PRICE":
                if taxa == 0:
                    valor_parcela = principal / n_amort
                else:
                    fator = (1 + taxa) ** n_amort
                    valor_parcela = principal * taxa * fator / (fator - 1)
            else:
                amortizacao_constante = principal / n_amort

        parcelas: list[_Parcela] = []
        saldo = principal
        for i in range(1, prazo_meses + 1):
            vencimento = _add_months(data_inicio, i)
            juros = _money(saldo * taxa)
            ultima = i == prazo_meses
            if i <= carencia_meses:
                amortizacao = Decimal("0.00")
            elif ultima:
                amortizacao = saldo
            elif sistema == "PRICE":
                amortizacao = valor_parcela - juros
            else:
                amortizacao = amortizacao_constante
            amortizacao = _money(amortizacao)
            valor = juros + amortizacao
            saldo = saldo - amortizacao
            if ultima:
                saldo = Decimal("0.00")
            parcelas.append(_Parcela(
                numero=i, vencimento=vencimento, juros=juros,
                amortizacao=amortizacao, valor=valor, saldo_apos=_money(saldo),
            ))
        return parcelas

    def cronograma(self, contrato_id: str) -> list:
        c = self._obter_contrato(contrato_id)
        return [
            {"numero": p.numero, "vencimento": p.vencimento, "juros": p.juros,
             "amortizacao": p.amortizacao, "valor": p.valor, "saldo_apos": p.saldo_apos}
            for p in c.parcelas
        ]

    # ------------------------------------------------------------------ #
    # helpers internos
    # ------------------------------------------------------------------ #

    def _obter_contrato(self, contrato_id) -> _Contrato:
        if not isinstance(contrato_id, str):
            raise ErroEmprestimo("CONTRATO_NAO_ENCONTRADO", "identificador invalido")
        c = self._contratos.get(contrato_id)
        if c is None:
            raise ErroEmprestimo("CONTRATO_NAO_ENCONTRADO", f"contrato {contrato_id!r} nao encontrado")
        return c

    def _obter_parcela(self, c: _Contrato, numero_parcela) -> _Parcela:
        if (not isinstance(numero_parcela, int) or isinstance(numero_parcela, bool)
                or numero_parcela < 1 or numero_parcela > len(c.parcelas)):
            raise ErroEmprestimo("PARCELA_INVALIDA", f"parcela {numero_parcela!r} invalida")
        return c.parcelas[numero_parcela - 1]

    def _calcular_encargos(self, p: _Parcela, data: date) -> Decimal:
        pendente = (p.amortizacao - p.principal_pago) + (p.juros - p.juros_pago)
        if pendente < 0:
            pendente = Decimal("0.00")
        if data <= p.vencimento or pendente == 0:
            calculado = Decimal("0.00")
        else:
            dias = (data - p.vencimento).days
            multa = pendente * TAXA_MULTA
            mora = pendente * TAXA_MORA_DIARIA * dias
            calculado = multa + mora
        pendente_encargos = calculado - p.encargos_pago
        if pendente_encargos < 0:
            pendente_encargos = Decimal("0.00")
        return pendente_encargos

    def _parcela_paga(self, p: _Parcela, data: date) -> bool:
        if p.principal_pago < p.amortizacao or p.juros_pago < p.juros:
            return False
        return self._calcular_encargos(p, data) == 0

    # ------------------------------------------------------------------ #
    # operações de cobrança
    # ------------------------------------------------------------------ #

    def valor_devido(self, contrato_id: str, numero_parcela: int, data: date) -> dict:
        c = self._obter_contrato(contrato_id)
        p = self._obter_parcela(c, numero_parcela)
        if not _is_date(data):
            raise ErroEmprestimo("VALOR_INVALIDO", "data deve ser datetime.date")

        principal_pendente = max(p.amortizacao - p.principal_pago, Decimal("0.00"))
        juros_pendente = max(p.juros - p.juros_pago, Decimal("0.00"))
        encargos_pendente = self._calcular_encargos(p, data)
        total = principal_pendente + juros_pendente + encargos_pendente
        return {
            "principal": _money(principal_pendente),
            "juros": _money(juros_pendente),
            "encargos": _money(encargos_pendente),
            "total": _money(total),
        }

    def registrar_pagamento(self, contrato_id: str, pagamento_id: str,
                             numero_parcela: int, valor, data: date) -> dict:
        c = self._obter_contrato(contrato_id)

        if not isinstance(pagamento_id, str) or not pagamento_id:
            raise ErroEmprestimo("VALOR_INVALIDO", "pagamento_id invalido")
        if pagamento_id in c.pagamentos:
            resultado = dict(c.pagamentos[pagamento_id])
            resultado["duplicado"] = True
            return resultado

        if c.estado != "ATIVO":
            raise ErroEmprestimo("ESTADO_INVALIDO", f"contrato em estado {c.estado}")

        p = self._obter_parcela(c, numero_parcela)

        if not _is_date(data):
            raise ErroEmprestimo("VALOR_INVALIDO", "data deve ser datetime.date")

        valor_dec = _to_decimal(valor)
        if valor_dec <= 0:
            raise ErroEmprestimo("VALOR_INVALIDO", "valor do pagamento deve ser positivo")

        devido = self.valor_devido(contrato_id, numero_parcela, data)

        restante = valor_dec
        aplicado_encargos = min(restante, devido["encargos"])
        restante -= aplicado_encargos
        aplicado_juros = min(restante, devido["juros"])
        restante -= aplicado_juros
        aplicado_principal = min(restante, devido["principal"])

        p.encargos_pago += aplicado_encargos
        p.juros_pago += aplicado_juros
        p.principal_pago += aplicado_principal

        resultado = {
            "duplicado": False,
            "aplicado_encargos": _money(aplicado_encargos),
            "aplicado_juros": _money(aplicado_juros),
            "aplicado_principal": _money(aplicado_principal),
            "parcela_quitada": self._parcela_paga(p, data),
        }
        c.pagamentos[pagamento_id] = dict(resultado)

        if all(self._parcela_paga(pp, data) for pp in c.parcelas):
            c.estado = "QUITADO"
            c.quitado_em = data

        return resultado

    def saldo_devedor(self, contrato_id: str, data: date) -> Decimal:
        c = self._obter_contrato(contrato_id)
        if not _is_date(data):
            raise ErroEmprestimo("VALOR_INVALIDO", "data deve ser datetime.date")
        if c.quitado_em is not None and data >= c.quitado_em:
            return Decimal("0.00")
        pago = sum((p.principal_pago for p in c.parcelas), Decimal("0.00"))
        return _money(c.principal - pago)

    def quitar_antecipado(self, contrato_id: str, data: date) -> dict:
        c = self._obter_contrato(contrato_id)
        if not _is_date(data):
            raise ErroEmprestimo("VALOR_INVALIDO", "data deve ser datetime.date")
        if c.estado != "ATIVO":
            raise ErroEmprestimo("ESTADO_INVALIDO", f"contrato em estado {c.estado}")

        saldo_principal = self.saldo_devedor(contrato_id, data)
        vencidos = Decimal("0.00")
        desconto_juros_futuros = Decimal("0.00")
        for p in c.parcelas:
            dev = self.valor_devido(contrato_id, p.numero, data)
            if p.vencimento <= data:
                vencidos += dev["juros"] + dev["encargos"]
            else:
                desconto_juros_futuros += dev["juros"]

        valor_quitacao = _money(saldo_principal + vencidos)

        c.estado = "QUITADO"
        c.quitado_em = data
        return {
            "valor_quitacao": valor_quitacao,
            "desconto_juros_futuros": _money(desconto_juros_futuros),
        }

    def renegociar(self, contrato_id: str, novo_prazo_meses: int, nova_taxa, data: date) -> str:
        c = self._obter_contrato(contrato_id)
        if not _is_date(data):
            raise ErroEmprestimo("VALOR_INVALIDO", "data deve ser datetime.date")

        if self.situacao(contrato_id, data) != "EM_ATRASO":
            raise ErroEmprestimo("RENEGOCIACAO_NAO_PERMITIDA",
                                  "somente contratos em atraso podem ser renegociados")

        if (not isinstance(novo_prazo_meses, int) or isinstance(novo_prazo_meses, bool)
                or novo_prazo_meses <= 0):
            raise ErroEmprestimo("CONTRATO_INVALIDO", "novo_prazo_meses deve ser inteiro positivo")

        nova_taxa_dec = _to_decimal(nova_taxa)
        if nova_taxa_dec < 0:
            raise ErroEmprestimo("VALOR_INVALIDO", "nova_taxa nao pode ser negativa")

        novo_principal = Decimal("0.00")
        for p in c.parcelas:
            dev = self.valor_devido(contrato_id, p.numero, data)
            novo_principal += dev["principal"] + dev["juros"] + dev["encargos"]
        novo_principal = _money(novo_principal)
        if novo_principal <= 0:
            raise ErroEmprestimo("RENEGOCIACAO_NAO_PERMITIDA", "nao ha saldo pendente para renegociar")

        novo_id = self.criar_contrato({
            "principal": novo_principal,
            "taxa": nova_taxa_dec,
            "prazo_meses": novo_prazo_meses,
            "sistema": c.sistema,
            "carencia_meses": 0,
            "data_inicio": data,
        })
        c.estado = "RENEGOCIADO"
        c.renegociado_para = novo_id
        return novo_id

    def situacao(self, contrato_id: str, data: date) -> str:
        c = self._obter_contrato(contrato_id)
        if not _is_date(data):
            raise ErroEmprestimo("VALOR_INVALIDO", "data deve ser datetime.date")

        if c.estado == "RENEGOCIADO":
            return "RENEGOCIADO"
        if c.estado == "QUITADO" and (c.quitado_em is None or data >= c.quitado_em):
            return "QUITADO"

        for p in c.parcelas:
            if data > p.vencimento and not self._parcela_paga(p, data):
                return "EM_ATRASO"
        return "ATIVO"
