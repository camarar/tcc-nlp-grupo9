"""Suíte cega UC-01 — motor de amortização de empréstimo.

Cada teste evidencia uma lacuna plantada (ver lacunas.json). Os valores esperados são
recalculados aqui a partir das regras do gabarito, nunca lidos da implementação.
"""

from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN

import pytest

from solucao import ErroEmprestimo, MotorEmprestimo

CENT = Decimal("0.01")


def q(x) -> Decimal:
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_EVEN)


def pmt_price(principal: Decimal, i: Decimal, n: int) -> Decimal:
    return q(principal * i / (1 - (1 + i) ** -n))


def novo(motor, **kw) -> str:
    dados = {
        "principal": "10000.00",
        "taxa": "0.02",
        "prazo_meses": 12,
        "sistema": "PRICE",
        "data_inicio": date(2026, 1, 15),
    }
    dados.update(kw)
    return motor.criar_contrato(dados)


@pytest.fixture
def m():
    return MotorEmprestimo()


# ---------------------------------------------------------------- G-01 sistema

def test_sistema_ausente_invalida_contrato(m):
    with pytest.raises(ErroEmprestimo) as e:
        m.criar_contrato({"principal": "1000", "taxa": "0.02", "prazo_meses": 6,
                          "data_inicio": date(2026, 1, 15)})
    assert e.value.code == "CONTRATO_INVALIDO"


def test_sistema_desconhecido_invalida_contrato(m):
    with pytest.raises(ErroEmprestimo) as e:
        novo(m, sistema="FRANCES")
    assert e.value.code == "CONTRATO_INVALIDO"


# ------------------------------------------------- G-01/G-02/G-03 cronogramas

def test_price_parcela_constante_e_juros_da_taxa_mensal(m):
    cid = novo(m)
    cr = m.cronograma(cid)
    esperado = pmt_price(Decimal("10000.00"), Decimal("0.02"), 12)
    assert len(cr) == 12
    assert [p["valor"] for p in cr[:-1]] == [esperado] * 11
    # taxa é MENSAL efetiva: juros da 1ª parcela = 2% do principal
    assert cr[0]["juros"] == q(Decimal("10000.00") * Decimal("0.02"))


def test_price_juros_decrescem_e_amortizacao_cresce(m):
    cr = m.cronograma(novo(m))
    juros = [p["juros"] for p in cr]
    amort = [p["amortizacao"] for p in cr]
    assert all(juros[i] > juros[i + 1] for i in range(len(juros) - 1))
    assert all(amort[i] < amort[i + 1] for i in range(len(amort) - 1))


def test_sac_amortizacao_constante_e_parcela_decrescente(m):
    cr = m.cronograma(novo(m, sistema="SAC"))
    amort = [p["amortizacao"] for p in cr]
    assert amort[:-1] == [q(Decimal("10000.00") / 12)] * 11
    valores = [p["valor"] for p in cr]
    assert all(valores[i] > valores[i + 1] for i in range(len(valores) - 1))


@pytest.mark.parametrize("sistema", ["PRICE", "SAC"])
def test_conservacao_soma_das_amortizacoes_igual_ao_principal(m, sistema):
    """Resíduo de arredondamento absorvido na última parcela — invariante forte."""
    cr = m.cronograma(novo(m, sistema=sistema, principal="10000.07", prazo_meses=7))
    assert sum(p["amortizacao"] for p in cr) == Decimal("10000.07")
    assert cr[-1]["saldo_apos"] == Decimal("0.00")


@pytest.mark.parametrize("sistema", ["PRICE", "SAC"])
def test_valor_da_parcela_e_soma_de_juros_e_amortizacao(m, sistema):
    for p in m.cronograma(novo(m, sistema=sistema)):
        assert p["valor"] == p["juros"] + p["amortizacao"]


def test_valores_monetarios_sao_decimal_com_duas_casas(m):
    for p in m.cronograma(novo(m)):
        for campo in ("juros", "amortizacao", "valor", "saldo_apos"):
            assert isinstance(p[campo], Decimal)
            assert -p[campo].as_tuple().exponent == 2


# ------------------------------------------------------------------ G-04 carência

def test_carencia_capitaliza_juros_no_principal(m):
    cr = m.cronograma(novo(m, carencia_meses=3))
    financiado = q(Decimal("10000.00") * Decimal("1.02") ** 3)
    assert sum(p["amortizacao"] for p in cr) == financiado


def test_carencia_desloca_o_primeiro_vencimento(m):
    cr = m.cronograma(novo(m, carencia_meses=3))
    assert cr[0]["vencimento"] == date(2026, 5, 15)


# ------------------------------------------------------------- G-05 vencimentos

def test_vencimento_usa_ultimo_dia_quando_o_dia_nao_existe(m):
    cr = m.cronograma(novo(m, data_inicio=date(2026, 1, 31), prazo_meses=3))
    assert [p["vencimento"] for p in cr] == [
        date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]


# ------------------------------------------------------ G-07 encargos de atraso

def test_encargos_multa_mais_mora_pro_rata_die(m):
    cid = novo(m)
    v = m.cronograma(cid)[0]["valor"]
    dev = m.valor_devido(cid, 1, date(2026, 2, 25))  # 10 dias de atraso
    esperado = q(v * Decimal("0.02") + v * Decimal("0.01") * 10 / 30)
    assert dev["encargos"] == esperado


def test_sem_atraso_nao_ha_encargos(m):
    cid = novo(m)
    dev = m.valor_devido(cid, 1, date(2026, 2, 15))
    assert dev["encargos"] == Decimal("0.00")
    assert dev["total"] == dev["principal"] + dev["juros"]


# ------------------------------------------------------------- G-06 imputação

def test_pagamento_parcial_quita_encargos_e_juros_antes_do_principal(m):
    cid = novo(m)
    d = date(2026, 2, 25)
    dev = m.valor_devido(cid, 1, d)
    r = m.registrar_pagamento(cid, "p1", 1, dev["encargos"] + dev["juros"], d)
    assert r["aplicado_encargos"] == dev["encargos"]
    assert r["aplicado_juros"] == dev["juros"]
    assert r["aplicado_principal"] == Decimal("0.00")
    assert r["parcela_quitada"] is False


def test_pagamento_parcial_menor_que_encargos_so_abate_encargos(m):
    cid = novo(m)
    d = date(2026, 2, 25)
    dev = m.valor_devido(cid, 1, d)
    parcial = q(dev["encargos"] / 2)
    r = m.registrar_pagamento(cid, "p1", 1, parcial, d)
    assert r["aplicado_encargos"] == parcial
    assert r["aplicado_juros"] == Decimal("0.00")
    assert r["aplicado_principal"] == Decimal("0.00")


def test_pagamento_integral_quita_a_parcela(m):
    cid = novo(m)
    d = date(2026, 2, 15)
    dev = m.valor_devido(cid, 1, d)
    r = m.registrar_pagamento(cid, "p1", 1, dev["total"], d)
    assert r["parcela_quitada"] is True
    assert r["aplicado_principal"] == dev["principal"]


# ------------------------------------------------------------- G-08 excedente

def test_pagamento_acima_do_devido_e_recusado(m):
    cid = novo(m)
    d = date(2026, 2, 15)
    total = m.valor_devido(cid, 1, d)["total"]
    with pytest.raises(ErroEmprestimo) as e:
        m.registrar_pagamento(cid, "p1", 1, total + CENT, d)
    assert e.value.code == "VALOR_INVALIDO"


@pytest.mark.parametrize("valor", ["0", "-10.00"])
def test_pagamento_nao_positivo_e_recusado(m, valor):
    cid = novo(m)
    with pytest.raises(ErroEmprestimo) as e:
        m.registrar_pagamento(cid, "p1", 1, valor, date(2026, 2, 15))
    assert e.value.code == "VALOR_INVALIDO"


# ---------------------------------------------------------- G-09 idempotência

def test_pagamento_repetido_e_idempotente(m):
    cid = novo(m)
    d = date(2026, 2, 15)
    total = m.valor_devido(cid, 1, d)["total"]
    m.registrar_pagamento(cid, "p1", 1, total, d)
    saldo = m.saldo_devedor(cid, d)
    r = m.registrar_pagamento(cid, "p1", 1, total, d)
    assert r["duplicado"] is True
    assert r["aplicado_principal"] == Decimal("0.00")
    assert m.saldo_devedor(cid, d) == saldo


# ------------------------------------------------------------ G-10 saldo devedor

def test_saldo_antes_do_primeiro_vencimento_e_o_principal(m):
    cid = novo(m)
    assert m.saldo_devedor(cid, date(2026, 2, 1)) == Decimal("10000.00")


def test_saldo_cai_pela_amortizacao_e_ignora_juros_futuros(m):
    cid = novo(m)
    d = date(2026, 2, 15)
    dev = m.valor_devido(cid, 1, d)
    m.registrar_pagamento(cid, "p1", 1, dev["total"], d)
    assert m.saldo_devedor(cid, d) == Decimal("10000.00") - dev["principal"]


# ------------------------------------------------------- G-11 quitação antecipada

def test_quitacao_dispensa_todos_os_juros_futuros(m):
    cid = novo(m)
    cr = m.cronograma(cid)
    r = m.quitar_antecipado(cid, date(2026, 2, 1))
    assert r["valor_quitacao"] == Decimal("10000.00")
    assert r["desconto_juros_futuros"] == sum(p["juros"] for p in cr)
    assert m.situacao(cid, date(2026, 2, 1)) == "QUITADO"


# --------------------------------------------------------- G-12 renegociação

def test_renegociacao_antes_de_trinta_dias_e_bloqueada(m):
    cid = novo(m)
    with pytest.raises(ErroEmprestimo) as e:
        m.renegociar(cid, 24, "0.02", date(2026, 3, 16))  # 29 dias de atraso
    assert e.value.code == "RENEGOCIACAO_NAO_PERMITIDA"


def test_renegociacao_migra_o_saldo_para_o_novo_contrato(m):
    cid = novo(m)
    d = date(2026, 3, 17)  # 30 dias de atraso na parcela 1
    saldo = m.saldo_devedor(cid, d)
    novo_id = m.renegociar(cid, 24, "0.02", d)
    assert novo_id != cid
    cr = m.cronograma(novo_id)
    assert len(cr) == 24
    assert sum(p["amortizacao"] for p in cr) == saldo
    assert m.situacao(cid, d) == "RENEGOCIADO"


# ------------------------------------------------------- G-13 estados terminais

def test_contrato_quitado_recusa_pagamento(m):
    cid = novo(m)
    m.quitar_antecipado(cid, date(2026, 2, 1))
    with pytest.raises(ErroEmprestimo) as e:
        m.registrar_pagamento(cid, "p9", 1, "100.00", date(2026, 2, 15))
    assert e.value.code == "ESTADO_INVALIDO"


def test_contrato_renegociado_recusa_quitacao(m):
    cid = novo(m)
    d = date(2026, 3, 17)
    m.renegociar(cid, 24, "0.02", d)
    with pytest.raises(ErroEmprestimo) as e:
        m.quitar_antecipado(cid, d)
    assert e.value.code == "ESTADO_INVALIDO"


# ------------------------------------------------------------- G-14 situação

def test_situacao_ativo_antes_do_vencimento(m):
    assert m.situacao(novo(m), date(2026, 2, 1)) == "ATIVO"


def test_situacao_em_atraso_com_parcela_vencida(m):
    assert m.situacao(novo(m), date(2026, 2, 16)) == "EM_ATRASO"


# ------------------------------------------------- G-15/G-16 validação e refs

@pytest.mark.parametrize("campo,valor", [
    ("principal", "0"), ("principal", "-1"), ("prazo_meses", 0),
    ("prazo_meses", 121), ("taxa", "-0.01"), ("carencia_meses", -1),
])
def test_criacao_invalida(m, campo, valor):
    with pytest.raises(ErroEmprestimo) as e:
        novo(m, **{campo: valor})
    assert e.value.code == "CONTRATO_INVALIDO"


def test_contrato_inexistente(m):
    with pytest.raises(ErroEmprestimo) as e:
        m.saldo_devedor("nao-existe", date(2026, 2, 1))
    assert e.value.code == "CONTRATO_NAO_ENCONTRADO"


@pytest.mark.parametrize("numero", [0, 13])
def test_parcela_fora_do_intervalo(m, numero):
    cid = novo(m)
    with pytest.raises(ErroEmprestimo) as e:
        m.valor_devido(cid, numero, date(2026, 2, 15))
    assert e.value.code == "PARCELA_INVALIDA"


def test_contrato_inexistente_precede_parcela_invalida(m):
    with pytest.raises(ErroEmprestimo) as e:
        m.valor_devido("nao-existe", 99, date(2026, 2, 15))
    assert e.value.code == "CONTRATO_NAO_ENCONTRADO"
