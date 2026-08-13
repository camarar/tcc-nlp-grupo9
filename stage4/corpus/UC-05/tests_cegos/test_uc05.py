"""Suíte cega UC-05 — motor de split e liquidação de recebíveis."""

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_EVEN

import pytest

from solucao import ErroRecebivel, MotorRecebiveis

D = Decimal
CENT = D("0.01")
INICIO = date(2026, 1, 10)


def q(x):
    return D(x).quantize(CENT, rounding=ROUND_HALF_EVEN)


@pytest.fixture
def m():
    return MotorRecebiveis()


def transacao(motor, **kw):
    dados = {"valor": "1000.00", "parcelas": 3, "mdr": "0.04", "data": INICIO,
             "split": [{"participante": "lojista", "percentual": "0.80"},
                       {"participante": "plataforma", "percentual": "0.20"}]}
    dados.update(kw)
    return motor.registrar_transacao(dados)


def por(recs, participante=None, parcela=None):
    return [r for r in recs
            if (participante is None or r["participante"] == participante)
            and (parcela is None or r["parcela"] == parcela)]


# ------------------------------------------------------ G-01/G-02 parcelamento

def test_parcelas_somam_o_valor_com_residuo_na_primeira(m):
    recs = m.recebiveis(transacao(m))
    brutos = {p: sum(r["valor_bruto"] for r in por(recs, parcela=p)) for p in (1, 2, 3)}
    assert brutos == {1: D("333.34"), 2: D("333.33"), 3: D("333.33")}
    assert sum(brutos.values()) == D("1000.00")


def test_vencimentos_a_cada_trinta_dias_corridos(m):
    recs = m.recebiveis(transacao(m))
    for p in (1, 2, 3):
        assert por(recs, parcela=p)[0]["vencimento"] == INICIO + timedelta(days=30 * p)


def test_primeira_parcela_nao_vence_na_data_da_transacao(m):
    recs = m.recebiveis(transacao(m))
    assert all(r["vencimento"] > INICIO for r in recs)


# ----------------------------------------------------------------- G-03 MDR

def test_taxa_incide_sobre_o_bruto_de_cada_recebivel(m):
    for r in m.recebiveis(transacao(m)):
        assert r["taxa"] == q(r["valor_bruto"] * D("0.04"))
        assert r["valor_liquido"] == r["valor_bruto"] - r["taxa"]


def test_mdr_zero_nao_gera_taxa(m):
    for r in m.recebiveis(transacao(m, mdr="0")):
        assert r["taxa"] == D("0.00") and r["valor_liquido"] == r["valor_bruto"]


# ------------------------------------------------------------- G-04/G-05 split

def test_split_rateia_cada_parcela_entre_os_participantes(m):
    recs = m.recebiveis(transacao(m))
    p1 = {r["participante"]: r["valor_bruto"] for r in por(recs, parcela=1)}
    assert p1 == {"lojista": D("266.67"), "plataforma": D("66.67")}
    assert sum(p1.values()) == D("333.34")


def test_residuo_do_split_vai_para_o_maior_percentual(m):
    """100.01 em 50/50 arredonda para 50.00 + 50.00; o centavo sobra."""
    tid = transacao(m, valor="100.01", parcelas=1,
                    split=[{"participante": "b", "percentual": "0.50"},
                           {"participante": "a", "percentual": "0.50"}])
    v = {r["participante"]: r["valor_bruto"] for r in m.recebiveis(tid)}
    assert v == {"a": D("50.01"), "b": D("50.00")}


def test_soma_dos_recebiveis_e_o_valor_da_transacao(m):
    recs = m.recebiveis(transacao(m, valor="999.97", parcelas=7))
    assert sum(r["valor_bruto"] for r in recs) == D("999.97")


@pytest.mark.parametrize("split", [
    [{"participante": "a", "percentual": "0.5"}],
    [{"participante": "a", "percentual": "0.5"}, {"participante": "a", "percentual": "0.5"}],
    [{"participante": "a", "percentual": "0"}, {"participante": "b", "percentual": "1.0"}],
    [],
])
def test_split_invalido(m, split):
    with pytest.raises(ErroRecebivel) as e:
        transacao(m, split=split)
    assert e.value.code == "SPLIT_INVALIDO"


# ------------------------------------------------------- G-06 transação inválida

@pytest.mark.parametrize("kw", [
    {"valor": "0"}, {"valor": "-1"}, {"parcelas": 0}, {"parcelas": 13},
    {"mdr": "-0.01"}, {"mdr": "1"}, {"data": None},
])
def test_transacao_invalida(m, kw):
    with pytest.raises(ErroRecebivel) as e:
        transacao(m, **kw)
    assert e.value.code == "TRANSACAO_INVALIDA"


def test_transacao_invalida_precede_split_invalido(m):
    with pytest.raises(ErroRecebivel) as e:
        transacao(m, valor="-1", split=[])
    assert e.value.code == "TRANSACAO_INVALIDA"


# ---------------------------------------------------------- G-07/G-08 antecipação

def test_desagio_pro_rata_die_por_recebivel(m):
    tid = transacao(m)
    liquidos = {r["parcela"]: r["valor_liquido"]
                for r in por(m.recebiveis(tid), participante="lojista")}
    esperado = sum(q(liquidos[p] * D("0.015") * (30 * p) / 30) for p in (1, 2, 3))
    r = m.antecipar(tid, "lojista", 3, INICIO)
    assert r["desagio"] == esperado
    assert r["valor_bruto"] == sum(
        x["valor_bruto"] for x in por(m.recebiveis(tid), participante="lojista"))
    assert r["valor_liquido"] == sum(liquidos.values()) - esperado
    assert r["parcelas"] == [1, 2, 3]


def test_antecipacao_respeita_o_limite_de_parcela(m):
    tid = transacao(m)
    r = m.antecipar(tid, "lojista", 2, INICIO)
    assert r["parcelas"] == [1, 2]
    sit = {(x["parcela"], x["participante"]): x["situacao"] for x in m.recebiveis(tid)}
    assert sit[(1, "lojista")] == "ANTECIPADO" and sit[(3, "lojista")] == "A_RECEBER"
    assert sit[(1, "plataforma")] == "A_RECEBER"


def test_sem_desagio_quando_o_vencimento_ja_passou(m):
    tid = transacao(m)
    r = m.antecipar(tid, "lojista", 1, INICIO + timedelta(days=45))
    assert r["desagio"] == D("0.00")


def test_reantecipar_sem_elegivel(m):
    tid = transacao(m)
    m.antecipar(tid, "lojista", 3, INICIO)
    with pytest.raises(ErroRecebivel) as e:
        m.antecipar(tid, "lojista", 3, INICIO)
    assert e.value.code == "ESTADO_INVALIDO"


# ------------------------------------------------------------ G-09/G-10 liquidação

def test_liquida_somente_o_vencido(m):
    tid = transacao(m)
    saida = m.liquidar(INICIO + timedelta(days=30))
    assert [(x["parcela"], x["participante"]) for x in saida] == \
        [(1, "lojista"), (1, "plataforma")]
    sit = {(x["parcela"], x["participante"]): x["situacao"] for x in m.recebiveis(tid)}
    assert sit[(1, "lojista")] == "LIQUIDADO" and sit[(2, "lojista")] == "A_RECEBER"


def test_liquidacao_e_idempotente(m):
    transacao(m)
    d = INICIO + timedelta(days=30)
    m.liquidar(d)
    assert m.liquidar(d) == []


def test_antecipado_nao_e_liquidado(m):
    tid = transacao(m)
    m.antecipar(tid, "lojista", 1, INICIO)
    saida = m.liquidar(INICIO + timedelta(days=30))
    assert [x["participante"] for x in saida] == ["plataforma"]


def test_liquidacao_ordenada(m):
    transacao(m)
    saida = m.liquidar(INICIO + timedelta(days=90))
    chaves = [(x["transacao_id"], x["parcela"], x["participante"]) for x in saida]
    assert chaves == sorted(chaves)


# ------------------------------------------------------------- G-11..G-13 estorno

def test_estorno_rateado_proporcionalmente(m):
    tid = transacao(m)
    r = m.estornar(tid, "300.00", INICIO)
    assert r["estornado"] == D("300.00")
    assert r["por_participante"] == {"lojista": D("240.00"), "plataforma": D("60.00")}


def test_soma_do_rateio_e_exatamente_o_valor_pedido(m):
    tid = transacao(m)
    r = m.estornar(tid, "100.00", INICIO)
    assert sum(r["por_participante"].values()) == r["estornado"] == D("100.00")


def test_estorno_reduz_o_bruto_e_recalcula_o_liquido(m):
    tid = transacao(m)
    m.estornar(tid, "300.00", INICIO)
    for r in m.recebiveis(tid):
        assert r["taxa"] == q(r["valor_bruto"] * D("0.04"))
        assert r["valor_liquido"] == r["valor_bruto"] - r["taxa"]
    assert sum(r["valor_bruto"] for r in m.recebiveis(tid)) == D("700.00")


def test_estorno_total_marca_todos_como_estornado(m):
    tid = transacao(m)
    m.estornar(tid, "1000.00", INICIO)
    recs = m.recebiveis(tid)
    assert all(r["situacao"] == "ESTORNADO" for r in recs)
    assert all(r["valor_bruto"] == D("0.00") for r in recs)


def test_estorno_nao_atinge_antecipado(m):
    tid = transacao(m)
    m.antecipar(tid, "lojista", 3, INICIO)
    r = m.estornar(tid, "200.00", INICIO)
    assert set(r["por_participante"]) == {"plataforma"}


def test_estorno_acima_do_disponivel(m):
    tid = transacao(m)
    m.antecipar(tid, "lojista", 3, INICIO)
    # sobram só os 3 recebíveis da plataforma: 66.67 x 3 = 200.01
    assert m.estornar(tid, "200.01", INICIO)["estornado"] == D("200.01")
    tid2 = transacao(m)
    m.antecipar(tid2, "lojista", 3, INICIO)
    with pytest.raises(ErroRecebivel) as e:
        m.estornar(tid2, "200.02", INICIO)
    assert e.value.code == "VALOR_INVALIDO"


@pytest.mark.parametrize("valor", ["0", "-1"])
def test_estorno_de_valor_nao_positivo(m, valor):
    tid = transacao(m)
    with pytest.raises(ErroRecebivel) as e:
        m.estornar(tid, valor, INICIO)
    assert e.value.code == "VALOR_INVALIDO"


def test_estado_invalido_precede_valor_invalido_no_estorno(m):
    tid = transacao(m)
    m.estornar(tid, "1000.00", INICIO)
    with pytest.raises(ErroRecebivel) as e:
        m.estornar(tid, "-5", INICIO)
    assert e.value.code == "ESTADO_INVALIDO"


# ------------------------------------------------------------- G-14 posição

def test_posicao_e_retrato_temporal(m):
    tid = transacao(m)
    m.liquidar(INICIO + timedelta(days=30))
    liquido_p1 = [r for r in m.recebiveis(tid)
                  if r["parcela"] == 1 and r["participante"] == "lojista"][0]["valor_liquido"]

    antes = m.posicao("lojista", INICIO)
    assert antes["liquidado"] == D("0.00")

    depois = m.posicao("lojista", INICIO + timedelta(days=30))
    assert depois["liquidado"] == liquido_p1
    assert depois["a_receber"] < antes["a_receber"]


def test_posicao_separa_antecipado_de_a_receber(m):
    tid = transacao(m)
    r = m.antecipar(tid, "lojista", 3, INICIO)
    p = m.posicao("lojista", INICIO)
    assert p["a_receber"] == D("0.00")
    assert p["antecipado"] == r["valor_bruto"] - sum(
        x["taxa"] for x in m.recebiveis(tid) if x["participante"] == "lojista")


def test_posicao_de_participante_sem_recebivel(m):
    transacao(m)
    assert m.posicao("ninguem", INICIO) == {
        "a_receber": D("0.00"), "antecipado": D("0.00"),
        "liquidado": D("0.00"), "estornado": D("0.00")}


def test_posicao_contabiliza_o_estorno_pelo_bruto(m):
    tid = transacao(m)
    m.estornar(tid, "300.00", INICIO)
    assert m.posicao("lojista", INICIO)["estornado"] == D("240.00")


# ------------------------------------------------------- G-15/G-16 ordem e refs

def test_recebiveis_ordenados_por_parcela_e_participante(m):
    recs = m.recebiveis(transacao(m))
    assert [(r["parcela"], r["participante"]) for r in recs] == \
        sorted((r["parcela"], r["participante"]) for r in recs)
    assert len(recs) == 6


def test_transacao_inexistente(m):
    with pytest.raises(ErroRecebivel) as e:
        m.recebiveis("nao-existe")
    assert e.value.code == "TRANSACAO_NAO_ENCONTRADA"


def test_participante_fora_do_split(m):
    tid = transacao(m)
    with pytest.raises(ErroRecebivel) as e:
        m.antecipar(tid, "estranho", 1, INICIO)
    assert e.value.code == "PARTICIPANTE_INVALIDO"


@pytest.mark.parametrize("ate", [0, 4])
def test_ate_parcela_fora_do_intervalo(m, ate):
    tid = transacao(m)
    with pytest.raises(ErroRecebivel) as e:
        m.antecipar(tid, "lojista", ate, INICIO)
    assert e.value.code == "PARCELA_INVALIDA"


def test_participante_invalido_precede_parcela_invalida(m):
    tid = transacao(m)
    with pytest.raises(ErroRecebivel) as e:
        m.antecipar(tid, "estranho", 99, INICIO)
    assert e.value.code == "PARTICIPANTE_INVALIDO"


def test_transacao_inexistente_precede_participante(m):
    with pytest.raises(ErroRecebivel) as e:
        m.antecipar("nao-existe", "estranho", 1, INICIO)
    assert e.value.code == "TRANSACAO_NAO_ENCONTRADA"
