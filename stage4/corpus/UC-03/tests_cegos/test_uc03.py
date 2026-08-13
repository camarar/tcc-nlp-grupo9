"""Suíte cega UC-03 — motor de precificação e promoções."""

from datetime import date
from decimal import Decimal

import pytest

from solucao import ErroPrecificacao, MotorPrecificacao

HOJE = date(2026, 6, 15)
D = Decimal


@pytest.fixture
def m():
    return MotorPrecificacao()


def pedido(itens=None, frete="20.00"):
    if itens is None:
        itens = [{"sku": "A", "categoria": "livros", "preco_unitario": "100.00", "quantidade": 1},
                 {"sku": "B", "categoria": "eletro", "preco_unitario": "200.00", "quantidade": 1}]
    return {"itens": itens, "frete": frete}


def tres_iguais(cat="x"):
    return [{"sku": s, "categoria": cat, "preco_unitario": "100.00", "quantidade": 1}
            for s in ("A", "B", "C")]


def cupom(m, codigo="C1", tipo="PERCENTUAL", valor="0.10", acumulavel=True,
          validade=date(2026, 12, 31), pedido_minimo=None, categorias=None):
    return m.registrar_cupom({"codigo": codigo, "tipo": tipo, "valor": valor,
                              "acumulavel": acumulavel, "validade": validade,
                              "pedido_minimo": pedido_minimo, "categorias": categorias})


def campanha(m, nome="P1", categoria="livros", percentual="0.10",
             inicio=date(2026, 1, 1), fim=date(2026, 12, 31)):
    return m.registrar_campanha({"nome": nome, "categoria": categoria,
                                 "percentual": percentual, "inicio": inicio, "fim": fim})


# ------------------------------------------------------- G-01/G-02/G-03 ordem

def test_campanha_aplica_antes_do_cupom(m):
    campanha(m)                                    # livros 10% -> 10.00
    cupom(m)                                       # 10% sobre 290 -> 29.00
    r = m.cotar(pedido(), ["C1"], HOJE)
    assert r["desconto_campanhas"] == D("10.00")
    assert r["desconto_cupons"] == D("29.00")
    assert r["desconto_total"] == D("39.00")


def test_percentual_antes_de_fixo_independente_da_ordem_da_lista(m):
    cupom(m, "FIX", "FIXO", "5.00")
    cupom(m, "PCT", "PERCENTUAL", "0.10")
    r1 = m.cotar(pedido(), ["FIX", "PCT"], HOJE)
    r2 = m.cotar(pedido(), ["PCT", "FIX"], HOJE)
    assert r1["desconto_cupons"] == r2["desconto_cupons"] == D("35.00")  # 30 + 5


def test_frete_fora_da_base_de_desconto(m):
    cupom(m)
    r = m.cotar(pedido(frete="500.00"), ["C1"], HOJE)
    assert r["desconto_cupons"] == D("30.00")      # 10% de 300, não de 800
    assert r["frete"] == D("500.00")


def test_total_e_subtotal_menos_desconto_mais_frete(m):
    cupom(m)
    r = m.cotar(pedido(), ["C1"], HOJE)
    assert r["total"] == r["subtotal"] - r["desconto_total"] + r["frete"]


# -------------------------------------------------------------- G-04 acumulação

def test_nao_acumulavel_sozinho_funciona(m):
    cupom(m, "SO", acumulavel=False)
    assert m.cotar(pedido(), ["SO"], HOJE)["desconto_cupons"] == D("30.00")


def test_nao_acumulavel_com_outro_e_recusado(m):
    cupom(m, "SO", acumulavel=False)
    cupom(m, "AC")
    with pytest.raises(ErroPrecificacao) as e:
        m.cotar(pedido(), ["SO", "AC"], HOJE)
    assert e.value.code == "CUPOM_NAO_ACUMULAVEL"


def test_dois_acumulaveis_combinam(m):
    cupom(m, "A1")
    cupom(m, "A2")
    r = m.cotar(pedido(), ["A1", "A2"], HOJE)
    assert r["desconto_cupons"] == D("57.00")      # 30 + 27


# ---------------------------------------------------------------- G-05 teto

def test_teto_de_cinquenta_por_cento_do_subtotal_original(m):
    campanha(m, categoria="x", percentual="0.40")
    cupom(m, valor="0.40")
    r = m.cotar(pedido(itens=tres_iguais()), ["C1"], HOJE)
    assert r["desconto_total"] == D("150.00")
    assert r["total"] == D("170.00")


def test_teto_gera_entrada_final_na_trilha(m):
    campanha(m, categoria="x", percentual="0.40")
    cupom(m, valor="0.40")
    t = m.explicar(pedido(itens=tres_iguais()), ["C1"], HOJE)
    assert t[-1]["origem"] == "TETO"


# ------------------------------------------------------------- G-06 validade

def test_validade_e_inclusiva(m):
    cupom(m, validade=HOJE)
    assert m.cotar(pedido(), ["C1"], HOJE)["desconto_cupons"] == D("30.00")


def test_cupom_expirado(m):
    cupom(m, validade=date(2026, 6, 14))
    with pytest.raises(ErroPrecificacao) as e:
        m.cotar(pedido(), ["C1"], HOJE)
    assert e.value.code == "CUPOM_EXPIRADO"


# -------------------------------------------------------- G-07 pedido mínimo

def test_pedido_minimo_igual_ao_subtotal_e_aceito(m):
    cupom(m, pedido_minimo="300.00")
    assert m.cotar(pedido(), ["C1"], HOJE)["desconto_cupons"] == D("30.00")


def test_pedido_minimo_avaliado_no_subtotal_original(m):
    """Campanha de 10% derruba o valor para 290, mas o mínimo olha os 300 originais."""
    campanha(m, categoria="livros", percentual="0.10")
    cupom(m, pedido_minimo="295.00")
    assert m.cotar(pedido(), ["C1"], HOJE)["desconto_cupons"] > D("0")


def test_pedido_minimo_nao_atingido(m):
    cupom(m, pedido_minimo="300.01")
    with pytest.raises(ErroPrecificacao) as e:
        m.cotar(pedido(), ["C1"], HOJE)
    assert e.value.code == "PEDIDO_MINIMO"


# ------------------------------------------------------------- G-08 campanhas

def test_campanha_so_atinge_a_categoria(m):
    campanha(m, categoria="livros", percentual="0.50")
    r = m.cotar(pedido(), [], HOJE)
    assert r["desconto_campanhas"] == D("50.00")


def test_periodo_inclusivo_nas_duas_pontas(m):
    campanha(m, nome="P1", categoria="livros", inicio=HOJE, fim=HOJE)
    assert m.cotar(pedido(), [], HOJE)["desconto_campanhas"] == D("10.00")


def test_campanha_fora_do_periodo_nao_aplica(m):
    campanha(m, inicio=date(2026, 1, 1), fim=date(2026, 6, 14))
    assert m.cotar(pedido(), [], HOJE)["desconto_campanhas"] == D("0.00")


def test_campanhas_de_categorias_diferentes_acumulam(m):
    campanha(m, nome="P1", categoria="livros", percentual="0.10")
    campanha(m, nome="P2", categoria="eletro", percentual="0.10")
    assert m.cotar(pedido(), [], HOJE)["desconto_campanhas"] == D("30.00")


def test_mesma_categoria_aplica_apenas_o_maior_percentual(m):
    campanha(m, nome="P1", categoria="livros", percentual="0.10")
    campanha(m, nome="P2", categoria="livros", percentual="0.25")
    assert m.cotar(pedido(), [], HOJE)["desconto_campanhas"] == D("25.00")


# --------------------------------------------------------------- G-09 rateio

def test_rateio_proporcional_ao_preco_bruto(m):
    cupom(m, "FIX", "FIXO", "44.00")
    r = m.cotar(pedido(), ["FIX"], HOJE)
    por_sku = {i["sku"]: i for i in r["itens"]}
    assert por_sku["A"]["desconto_rateado"] == D("14.67")
    assert por_sku["B"]["desconto_rateado"] == D("29.33")


def test_residuo_do_rateio_vai_para_o_maior_preco_com_desempate_por_sku(m):
    cupom(m, "FIX", "FIXO", "10.00")
    r = m.cotar(pedido(itens=tres_iguais()), ["FIX"], HOJE)
    por_sku = {i["sku"]: i["desconto_rateado"] for i in r["itens"]}
    assert por_sku == {"A": D("3.34"), "B": D("3.33"), "C": D("3.33")}


def test_soma_do_rateio_e_exatamente_o_desconto_total(m):
    cupom(m, "FIX", "FIXO", "10.00")
    r = m.cotar(pedido(itens=tres_iguais()), ["FIX"], HOJE)
    assert sum(i["desconto_rateado"] for i in r["itens"]) == r["desconto_total"]


def test_preco_liquido_e_bruto_menos_rateio(m):
    cupom(m, "FIX", "FIXO", "10.00")
    for i in m.cotar(pedido(itens=tres_iguais()), ["FIX"], HOJE)["itens"]:
        assert i["preco_liquido"] == i["preco_bruto"] - i["desconto_rateado"]


def test_preco_bruto_considera_a_quantidade(m):
    itens = [{"sku": "A", "categoria": "x", "preco_unitario": "50.00", "quantidade": 3}]
    r = m.cotar({"itens": itens, "frete": "0"}, [], HOJE)
    assert r["subtotal"] == D("150.00")
    assert r["itens"][0]["preco_bruto"] == D("150.00")


# --------------------------------------------------------------- G-10 precisão

def test_valores_sao_decimal_com_duas_casas(m):
    r = m.cotar(pedido(), [], HOJE)
    for campo in ("subtotal", "desconto_campanhas", "desconto_cupons",
                  "desconto_total", "frete", "total"):
        assert isinstance(r[campo], Decimal)
        assert -r[campo].as_tuple().exponent == 2


# --------------------------------------------------------- G-11 itens inválidos

@pytest.mark.parametrize("itens", [
    [],
    [{"sku": "A", "categoria": "x", "preco_unitario": "10.00", "quantidade": 0}],
    [{"sku": "A", "categoria": "x", "preco_unitario": "-1.00", "quantidade": 1}],
    [{"sku": "", "categoria": "x", "preco_unitario": "10.00", "quantidade": 1}],
    [{"sku": "A", "categoria": "x", "preco_unitario": "10.00", "quantidade": 1},
     {"sku": "A", "categoria": "x", "preco_unitario": "20.00", "quantidade": 1}],
])
def test_item_invalido(m, itens):
    with pytest.raises(ErroPrecificacao) as e:
        m.cotar({"itens": itens, "frete": "0"}, [], HOJE)
    assert e.value.code == "ITEM_INVALIDO"


def test_frete_negativo(m):
    with pytest.raises(ErroPrecificacao) as e:
        m.cotar(pedido(frete="-1.00"), [], HOJE)
    assert e.value.code == "ITEM_INVALIDO"


# -------------------------------------------------------- G-12/G-13 registros

def test_cupom_desconhecido(m):
    with pytest.raises(ErroPrecificacao) as e:
        m.cotar(pedido(), ["NAO-EXISTE"], HOJE)
    assert e.value.code == "CUPOM_INVALIDO"


def test_cupom_repetido_na_mesma_cotacao(m):
    cupom(m)
    with pytest.raises(ErroPrecificacao) as e:
        m.cotar(pedido(), ["C1", "C1"], HOJE)
    assert e.value.code == "CUPOM_INVALIDO"


def test_registro_de_codigo_duplicado(m):
    cupom(m)
    with pytest.raises(ErroPrecificacao) as e:
        cupom(m)
    assert e.value.code == "CUPOM_INVALIDO"


@pytest.mark.parametrize("kw", [
    {"tipo": "BRINDE"}, {"valor": "-1"}, {"tipo": "PERCENTUAL", "valor": "1.5"},
])
def test_cupom_invalido_no_registro(m, kw):
    with pytest.raises(ErroPrecificacao) as e:
        cupom(m, **kw)
    assert e.value.code == "CUPOM_INVALIDO"


@pytest.mark.parametrize("kw", [
    {"percentual": "0"}, {"percentual": "1.5"}, {"categoria": ""},
    {"inicio": date(2026, 12, 31), "fim": date(2026, 1, 1)},
])
def test_campanha_invalida_no_registro(m, kw):
    with pytest.raises(ErroPrecificacao) as e:
        campanha(m, **kw)
    assert e.value.code == "CAMPANHA_INVALIDA"


# ------------------------------------------------ G-14 restrição de categoria

def test_cupom_restrito_incide_so_na_categoria(m):
    cupom(m, categorias=["livros"])
    assert m.cotar(pedido(), ["C1"], HOJE)["desconto_cupons"] == D("10.00")


def test_cupom_restrito_apos_a_campanha_da_mesma_categoria(m):
    campanha(m, categoria="livros", percentual="0.10")   # livros: 100 -> 90
    cupom(m, categorias=["livros"])                       # 10% de 90
    assert m.cotar(pedido(), ["C1"], HOJE)["desconto_cupons"] == D("9.00")


def test_cupom_restrito_sem_item_elegivel_nao_e_erro(m):
    cupom(m, categorias=["moveis"])
    assert m.cotar(pedido(), ["C1"], HOJE)["desconto_cupons"] == D("0.00")


# ------------------------------------------------------- G-15/G-16 trilha e frete

def test_trilha_ordena_campanha_antes_de_cupom(m):
    campanha(m)
    cupom(m)
    t = m.explicar(pedido(), ["C1"], HOJE)
    assert [x["origem"] for x in t] == ["CAMPANHA", "CUPOM"]
    assert t[0]["referencia"] == "P1" and t[1]["referencia"] == "C1"
    assert t[1]["base"] == D("290.00") and t[1]["valor"] == D("29.00")


def test_desconto_zero_nao_gera_entrada(m):
    cupom(m, categorias=["moveis"])
    assert m.explicar(pedido(), ["C1"], HOJE) == []


def test_frete_gratis_zera_o_frete_sem_entrar_no_desconto(m):
    cupom(m, "FG", "FRETE_GRATIS", "0")
    r = m.cotar(pedido(), ["FG"], HOJE)
    assert r["frete"] == D("0.00")
    assert r["desconto_cupons"] == D("0.00")
    assert r["desconto_total"] == D("0.00")
    assert r["total"] == D("300.00")


def test_frete_gratis_gera_entrada_de_origem_frete(m):
    cupom(m, "FG", "FRETE_GRATIS", "0")
    t = m.explicar(pedido(), ["FG"], HOJE)
    assert t[-1]["origem"] == "FRETE" and t[-1]["valor"] == D("20.00")


def test_dois_frete_gratis_nao_sao_erro(m):
    cupom(m, "F1", "FRETE_GRATIS", "0")
    cupom(m, "F2", "FRETE_GRATIS", "0")
    r = m.cotar(pedido(), ["F1", "F2"], HOJE)
    assert r["frete"] == D("0.00")


# --------------------------------------------------- G-17 ordem de validação

def test_item_invalido_precede_cupom_desconhecido(m):
    with pytest.raises(ErroPrecificacao) as e:
        m.cotar({"itens": [], "frete": "0"}, ["NAO-EXISTE"], HOJE)
    assert e.value.code == "ITEM_INVALIDO"


def test_cupom_desconhecido_precede_expirado(m):
    cupom(m, "EXP", validade=date(2026, 1, 1))
    with pytest.raises(ErroPrecificacao) as e:
        m.cotar(pedido(), ["EXP", "NAO-EXISTE"], HOJE)
    assert e.value.code == "CUPOM_INVALIDO"


def test_acumulacao_precede_validade(m):
    cupom(m, "SO", acumulavel=False, validade=date(2026, 1, 1))
    cupom(m, "AC")
    with pytest.raises(ErroPrecificacao) as e:
        m.cotar(pedido(), ["SO", "AC"], HOJE)
    assert e.value.code == "CUPOM_NAO_ACUMULAVEL"


def test_validade_precede_pedido_minimo(m):
    cupom(m, validade=date(2026, 1, 1), pedido_minimo="9999.00")
    with pytest.raises(ErroPrecificacao) as e:
        m.cotar(pedido(), ["C1"], HOJE)
    assert e.value.code == "CUPOM_EXPIRADO"
