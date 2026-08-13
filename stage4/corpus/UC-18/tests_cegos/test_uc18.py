"""Suíte cega UC-18 — ciclo de vida de pedido com combos promocionais."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from solucao import ErroPedido, Pedidos

D = Decimal
T0 = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)


def item(item_id, preco, combo=None, sku=None):
    return {"item_id": item_id, "sku": sku or item_id,
            "preco_cheio": preco, "combo": combo}


BASE_ITENS = [item("i1", "100.00", "C1"), item("i2", "60.00", "C1"),
              item("i3", "40.00")]
BASE_COMBOS = [{"combo_id": "C1", "preco": "120.00"}]


@pytest.fixture
def p():
    return Pedidos(relogio=lambda: T0)


def criar(pd, itens=None, combos=None, cliente="ana"):
    itens = BASE_ITENS if itens is None else itens
    combos = BASE_COMBOS if combos is None else combos
    return pd.criar({"cliente": cliente,
                     "itens": [dict(i) for i in itens],
                     "combos": [dict(c) for c in combos]})


def precos(pd, pid):
    return {i["item_id"]: i["preco"] for i in pd.resumo(pid)["itens"]}


def sits(pd, pid):
    return {i["item_id"]: i["situacao"] for i in pd.resumo(pid)["itens"]}


# ------------------------------------------------------- G-01/G-02 preços

def test_combo_rateado_proporcionalmente(p):
    pid = criar(p)
    assert precos(p, pid) == {"i1": D("75.00"), "i2": D("45.00"), "i3": D("40.00")}


def test_total_inicial(p):
    assert p.resumo(criar(p))["total"] == D("160.00")


def test_residuo_do_rateio_vai_para_o_maior_preco(p):
    itens = [item("a", "10.00", "C1"), item("b", "10.00", "C1"),
             item("c", "10.00", "C1")]
    pid = criar(p, itens, [{"combo_id": "C1", "preco": "10.00"}])
    assert precos(p, pid) == {"a": D("3.34"), "b": D("3.33"), "c": D("3.33")}


def test_soma_dos_itens_do_combo_e_o_preco_do_combo(p):
    pid = criar(p)
    pr = precos(p, pid)
    assert pr["i1"] + pr["i2"] == D("120.00")


# --------------------------------------------------- G-03/G-04 quebra do combo

def test_cancelar_item_de_combo_reprecifica_os_restantes(p):
    pid = criar(p)
    p.pagar(pid, "160.00", T0)
    r = p.cancelar_item(pid, "i2", T0)
    assert precos(p, pid)["i1"] == D("100.00")
    assert r["novo_total"] == D("140.00")


def test_estorno_e_o_pago_menos_o_novo_total(p):
    pid = criar(p)
    p.pagar(pid, "160.00", T0)
    r = p.cancelar_item(pid, "i2", T0)
    assert r["estorno"] == D("20.00")          # 160 - 140, não os 45 do item
    assert p.resumo(pid)["estornado"] == D("20.00")


def test_item_avulso_nao_e_reprecificado(p):
    pid = criar(p)
    p.pagar(pid, "160.00", T0)
    p.cancelar_item(pid, "i2", T0)
    assert precos(p, pid)["i3"] == D("40.00")


def test_combo_desfeito_nao_se_refaz(p):
    itens = [item("i1", "100.00", "C1"), item("i2", "60.00", "C1"),
             item("i4", "50.00", "C1")]
    pid = criar(p, itens, [{"combo_id": "C1", "preco": "180.00"}])
    p.pagar(pid, p.resumo(pid)["total"], T0)
    p.cancelar_item(pid, "i2", T0)
    p.cancelar_item(pid, "i4", T0)
    assert precos(p, pid)["i1"] == D("100.00")


def test_estorno_nunca_negativo(p):
    """A reprecificação eleva o total acima do pago: estorno vai a zero."""
    itens = [item("i1", "100.00", "C1"), item("i2", "20.00", "C1")]
    pid = criar(p, itens, [{"combo_id": "C1", "preco": "60.00"}])
    p.pagar(pid, "60.00", T0)
    r = p.cancelar_item(pid, "i2", T0)
    assert r["novo_total"] == D("100.00")
    assert r["estorno"] == D("0.00")


def test_pedido_nao_pago_estorna_zero(p):
    pid = criar(p)
    assert p.cancelar_item(pid, "i2", T0)["estorno"] == D("0.00")


def test_reprecificacao_registrada_no_historico(p):
    pid = criar(p)
    p.pagar(pid, "160.00", T0)
    p.cancelar_item(pid, "i2", T0)
    reps = [h for h in p.historico(pid) if h["evento"] == "REPRECIFICACAO"]
    assert len(reps) == 1
    assert reps[0]["item_id"] == "i1" and reps[0]["valor"] == D("100.00")


# ------------------------------------------------------- G-06/G-07 devolução

def test_item_despachado_nao_e_cancelavel(p):
    pid = criar(p)
    p.pagar(pid, "160.00", T0)
    p.despachar(pid, ["i3"], T0)
    with pytest.raises(ErroPedido) as e:
        p.cancelar_item(pid, "i3", T0)
    assert e.value.code == "OPERACAO_NAO_PERMITIDA"


def test_devolucao_no_setimo_dia_e_permitida(p):
    pid = criar(p)
    p.pagar(pid, "160.00", T0)
    p.despachar(pid, ["i3"], T0)
    r = p.devolver(pid, "i3", T0 + timedelta(days=7))
    assert r["novo_total"] == D("120.00")
    assert sits(p, pid)["i3"] == "DEVOLVIDO"


def test_devolucao_apos_o_prazo(p):
    pid = criar(p)
    p.pagar(pid, "160.00", T0)
    p.despachar(pid, ["i3"], T0)
    with pytest.raises(ErroPedido) as e:
        p.devolver(pid, "i3", T0 + timedelta(days=8))
    assert e.value.code == "OPERACAO_NAO_PERMITIDA"


def test_devolver_item_ativo(p):
    pid = criar(p)
    p.pagar(pid, "160.00", T0)
    with pytest.raises(ErroPedido) as e:
        p.devolver(pid, "i3", T0)
    assert e.value.code == "OPERACAO_NAO_PERMITIDA"


def test_devolucao_tambem_quebra_o_combo(p):
    pid = criar(p)
    p.pagar(pid, "160.00", T0)
    p.despachar(pid, ["i2"], T0)
    p.devolver(pid, "i2", T0 + timedelta(days=1))
    assert precos(p, pid)["i1"] == D("100.00")


def test_cancelar_item_ja_cancelado(p):
    pid = criar(p)
    p.cancelar_item(pid, "i2", T0)
    with pytest.raises(ErroPedido) as e:
        p.cancelar_item(pid, "i2", T0)
    assert e.value.code == "OPERACAO_NAO_PERMITIDA"


# ---------------------------------------------------------- G-08 pagamento

def test_pagamento_exato(p):
    pid = criar(p)
    assert p.pagar(pid, "160.00", T0) == {"situacao": "PAGO", "pago": D("160.00")}


@pytest.mark.parametrize("valor", ["159.99", "160.01"])
def test_pagamento_divergente(p, valor):
    pid = criar(p)
    with pytest.raises(ErroPedido) as e:
        p.pagar(pid, valor, T0)
    assert e.value.code == "VALOR_INVALIDO"


def test_pagar_duas_vezes(p):
    pid = criar(p)
    p.pagar(pid, "160.00", T0)
    with pytest.raises(ErroPedido) as e:
        p.pagar(pid, "160.00", T0)
    assert e.value.code == "ESTADO_INVALIDO"


# ------------------------------------------------------ G-09/G-10 despacho

def test_despacho_parcial(p):
    pid = criar(p)
    p.pagar(pid, "160.00", T0)
    assert p.despachar(pid, ["i3"], T0) == "PARCIALMENTE_DESPACHADO"


def test_despacho_total(p):
    pid = criar(p)
    p.pagar(pid, "160.00", T0)
    assert p.despachar(pid, ["i1", "i2", "i3"], T0) == "DESPACHADO"


def test_despachar_sem_pagar(p):
    pid = criar(p)
    with pytest.raises(ErroPedido) as e:
        p.despachar(pid, ["i3"], T0)
    assert e.value.code == "ESTADO_INVALIDO"


def test_despacho_e_atomico(p):
    pid = criar(p)
    p.pagar(pid, "160.00", T0)
    p.despachar(pid, ["i3"], T0)
    with pytest.raises(ErroPedido) as e:
        p.despachar(pid, ["i1", "i3"], T0)
    assert e.value.code == "ITEM_INVALIDO"
    assert sits(p, pid)["i1"] == "ATIVO"


def test_despachar_lista_vazia(p):
    pid = criar(p)
    p.pagar(pid, "160.00", T0)
    with pytest.raises(ErroPedido) as e:
        p.despachar(pid, [], T0)
    assert e.value.code == "ITEM_INVALIDO"


def test_despacho_gera_uma_entrada_por_item(p):
    pid = criar(p)
    p.pagar(pid, "160.00", T0)
    p.despachar(pid, ["i1", "i3"], T0)
    assert len([h for h in p.historico(pid) if h["evento"] == "DESPACHO"]) == 2


def test_pedido_vira_cancelado_quando_nao_resta_item(p):
    pid = criar(p)
    for i in ("i1", "i2", "i3"):
        p.cancelar_item(pid, i, T0)
    assert p.resumo(pid)["situacao"] == "CANCELADO"
    assert any(h["evento"] == "CANCELAMENTO_PEDIDO" for h in p.historico(pid))


def test_pedido_concluido_com_cancelamento_e_despacho(p):
    pid = criar(p)
    p.pagar(pid, "160.00", T0)
    p.cancelar_item(pid, "i2", T0)
    p.despachar(pid, ["i1", "i3"], T0)
    assert p.resumo(pid)["situacao"] == "CONCLUIDO"


def test_despachado_sem_cancelamento_nao_e_concluido(p):
    pid = criar(p)
    p.pagar(pid, "160.00", T0)
    p.despachar(pid, ["i1", "i2", "i3"], T0)
    assert p.resumo(pid)["situacao"] == "DESPACHADO"


# ------------------------------------------------------ G-11 estado terminal

@pytest.mark.parametrize("op", ["pagar", "despachar", "cancelar_item"])
def test_pedido_cancelado_recusa_operacoes(p, op):
    pid = criar(p)
    for i in ("i1", "i2", "i3"):
        p.cancelar_item(pid, i, T0)
    with pytest.raises(ErroPedido) as e:
        if op == "pagar":
            p.pagar(pid, "1", T0)
        elif op == "despachar":
            p.despachar(pid, ["i1"], T0)
        else:
            p.cancelar_item(pid, "i1", T0)
    assert e.value.code == "ESTADO_INVALIDO"


def test_pedido_cancelado_continua_consultavel(p):
    pid = criar(p)
    for i in ("i1", "i2", "i3"):
        p.cancelar_item(pid, i, T0)
    assert p.resumo(pid)["total"] == D("0.00")
    assert len(p.historico(pid)) > 0


# ----------------------------------------------------------- G-12 histórico

def test_historico_cronologico_com_as_chaves_do_contrato(p):
    pid = criar(p)
    p.pagar(pid, "160.00", T0)
    h = p.historico(pid)
    assert [x["evento"] for x in h][:2] == ["CRIACAO", "PAGAMENTO"]
    assert set(h[0]) == {"em", "evento", "item_id", "valor"}
    assert h[0]["item_id"] is None and h[0]["valor"] is None
    assert h[1]["valor"] == D("160.00")
    assert [x["em"] for x in h] == sorted(x["em"] for x in h)


def test_cancelamento_registra_o_estorno(p):
    pid = criar(p)
    p.pagar(pid, "160.00", T0)
    p.cancelar_item(pid, "i2", T0)
    ev = [h for h in p.historico(pid) if h["evento"] == "CANCELAMENTO_ITEM"][0]
    assert ev["item_id"] == "i2" and ev["valor"] == D("20.00")


# --------------------------------------------------- G-13/G-14 validação

@pytest.mark.parametrize("itens", [
    [], [item("i1", "0")], [item("i1", "-1")],
    [item("i1", "10"), item("i1", "20")], [item("", "10")],
])
def test_criacao_com_item_invalido(p, itens):
    with pytest.raises(ErroPedido) as e:
        criar(p, itens, [])
    assert e.value.code == "ITEM_INVALIDO"


def test_cliente_vazio(p):
    with pytest.raises(ErroPedido) as e:
        criar(p, cliente="")
    assert e.value.code == "ITEM_INVALIDO"


@pytest.mark.parametrize("itens,combos", [
    ([item("i1", "10", "CX")], []),
    ([item("i1", "10")], [{"combo_id": "C1", "preco": "5"}]),
    ([item("i1", "10", "C1")], [{"combo_id": "C1", "preco": "0"}]),
    ([item("i1", "10", "C1")], [{"combo_id": "C1", "preco": "10"}]),
    ([item("i1", "10", "C1")], [{"combo_id": "C1", "preco": "20"}]),
    ([item("i1", "10", "C1")], [{"combo_id": "C1", "preco": "5"},
                                {"combo_id": "C1", "preco": "6"}]),
])
def test_criacao_com_combo_invalido(p, itens, combos):
    with pytest.raises(ErroPedido) as e:
        criar(p, itens, combos)
    assert e.value.code == "COMBO_INVALIDO"


def test_item_invalido_precede_combo_invalido(p):
    with pytest.raises(ErroPedido) as e:
        criar(p, [item("i1", "0", "CX")], [])
    assert e.value.code == "ITEM_INVALIDO"


def test_pedido_inexistente(p):
    with pytest.raises(ErroPedido) as e:
        p.resumo("fantasma")
    assert e.value.code == "PEDIDO_NAO_ENCONTRADO"


def test_item_inexistente(p):
    pid = criar(p)
    with pytest.raises(ErroPedido) as e:
        p.cancelar_item(pid, "zz", T0)
    assert e.value.code == "ITEM_INVALIDO"


def test_pedido_precede_item(p):
    with pytest.raises(ErroPedido) as e:
        p.cancelar_item("fantasma", "zz", T0)
    assert e.value.code == "PEDIDO_NAO_ENCONTRADO"


def test_valores_com_duas_casas(p):
    r = p.resumo(criar(p))
    for campo in ("total", "pago", "estornado"):
        assert isinstance(r[campo], Decimal) and -r[campo].as_tuple().exponent == 2
