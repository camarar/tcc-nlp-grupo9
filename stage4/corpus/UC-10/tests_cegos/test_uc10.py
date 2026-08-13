"""Suíte cega UC-10 — motor de conciliação de pagamentos."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from solucao import ErroConciliacao, MotorConciliacao

D = Decimal
DIA = date(2026, 6, 15)
CORTE = date(2026, 6, 30)


def interna(tid="T1", valor="100.00", data=DIA, status="APROVADA"):
    return {"transacao_id": tid, "valor": valor, "data": data, "status": status}


def extrato(tid="T1", bruto="100.00", taxa="2.00", data=DIA, tipo="VENDA"):
    return {"transacao_id": tid, "valor_bruto": bruto, "taxa": taxa,
            "data": data, "tipo": tipo}


@pytest.fixture
def m():
    return MotorConciliacao()


def montar(m, internas, extratos, corte=CORTE):
    m.carregar_internas(internas)
    m.carregar_extrato(extratos)
    return m.conciliar(corte)


def cat(m, categoria):
    return [i["transacao_id"] for i in m.itens(categoria)]


# ------------------------------------------------------ G-01/G-02 casamento

def test_par_perfeito_concilia(m):
    r = montar(m, [interna()], [extrato()])
    assert r["conciliadas"] == 1 and r["divergentes"] == 0
    assert cat(m, "CONCILIADA") == ["T1"]


def test_sem_par_no_extrato(m):
    r = montar(m, [interna()], [])
    assert r["somente_interna"] == 1 and cat(m, "SOMENTE_INTERNA") == ["T1"]


def test_sem_par_interno(m):
    r = montar(m, [], [extrato()])
    assert r["somente_extrato"] == 1 and cat(m, "SOMENTE_EXTRATO") == ["T1"]


def test_cancelada_e_ignorada(m):
    r = montar(m, [interna(status="CANCELADA")], [])
    assert r["somente_interna"] == 0
    assert m.itens("SOMENTE_INTERNA") == []


def test_valor_igual_nao_basta_sem_id_igual(m):
    montar(m, [interna("A")], [extrato("B")])
    assert cat(m, "SOMENTE_INTERNA") == ["A"]
    assert cat(m, "SOMENTE_EXTRATO") == ["B"]


# ---------------------------------------------------- G-03..G-06 divergências

def test_estornada_casa_com_estorno(m):
    r = montar(m, [interna(status="ESTORNADA")], [extrato(tipo="ESTORNO")])
    assert r["conciliadas"] == 1


def test_tipo_trocado_e_divergente(m):
    montar(m, [interna(status="ESTORNADA")], [extrato(tipo="VENDA")])
    assert m.itens("DIVERGENTE")[0]["motivo"] == "TIPO_DIVERGENTE"


def test_um_centavo_de_diferenca_e_divergente(m):
    montar(m, [interna(valor="100.00")], [extrato(bruto="100.01")])
    it = m.itens("DIVERGENTE")[0]
    assert it["motivo"] == "VALOR_DIVERGENTE"
    assert it["valor_interno"] == D("100.00") and it["valor_extrato"] == D("100.01")


def test_janela_de_dois_dias_e_inclusiva(m):
    r = montar(m, [interna()], [extrato(data=DIA + timedelta(days=2))])
    assert r["conciliadas"] == 1


def test_terceiro_dia_sai_da_janela(m):
    montar(m, [interna()], [extrato(data=DIA + timedelta(days=3))])
    assert m.itens("DIVERGENTE")[0]["motivo"] == "FORA_DA_JANELA"


def test_extrato_anterior_a_interna_sai_da_janela(m):
    montar(m, [interna()], [extrato(data=DIA - timedelta(days=1))])
    assert m.itens("DIVERGENTE")[0]["motivo"] == "FORA_DA_JANELA"


def test_tipo_tem_precedencia_sobre_valor(m):
    montar(m, [interna(status="ESTORNADA", valor="100.00")],
           [extrato(tipo="VENDA", bruto="999.00")])
    assert m.itens("DIVERGENTE")[0]["motivo"] == "TIPO_DIVERGENTE"


def test_valor_tem_precedencia_sobre_janela(m):
    montar(m, [interna(valor="100.00")],
           [extrato(bruto="999.00", data=DIA + timedelta(days=9))])
    assert m.itens("DIVERGENTE")[0]["motivo"] == "VALOR_DIVERGENTE"


# ----------------------------------------------------------- G-07 duplicatas

def test_duplicata_gera_um_item_e_nao_concilia(m):
    r = montar(m, [interna()], [extrato(), extrato()])
    assert r["duplicadas"] == 1 and r["conciliadas"] == 0
    assert r["somente_interna"] == 0
    assert cat(m, "DUPLICADA") == ["T1"]


def test_duplicata_sem_interna(m):
    r = montar(m, [], [extrato(), extrato()])
    assert r["duplicadas"] == 1 and r["somente_extrato"] == 0


def test_triplicata_ainda_e_um_item(m):
    r = montar(m, [interna()], [extrato(), extrato(), extrato()])
    assert r["duplicadas"] == 1


def test_duplicata_usa_o_valor_da_primeira_ocorrencia(m):
    montar(m, [interna()], [extrato(bruto="100.00"), extrato(bruto="500.00")])
    assert m.itens("DUPLICADA")[0]["valor_extrato"] == D("100.00")


# ------------------------------------------------------- G-08 data de corte

def test_interna_depois_do_corte_fica_de_fora(m):
    r = montar(m, [interna(data=date(2026, 7, 5))], [], corte=CORTE)
    assert r["somente_interna"] == 0


def test_extrato_dentro_da_folga_do_corte_entra(m):
    r = montar(m, [interna(data=CORTE)], [extrato(data=CORTE + timedelta(days=2))],
               corte=CORTE)
    assert r["conciliadas"] == 1


def test_extrato_alem_da_folga_do_corte_fica_de_fora(m):
    r = montar(m, [interna(data=CORTE)], [extrato(data=CORTE + timedelta(days=3))],
               corte=CORTE)
    assert r["somente_interna"] == 1 and r["somente_extrato"] == 0


# ------------------------------------------------------- G-09 total líquido

def test_total_liquido_desconta_a_taxa(m):
    r = montar(m, [interna()], [extrato(bruto="100.00", taxa="2.50")])
    assert r["total_liquido"] == D("97.50")


def test_estorno_subtrai_do_total(m):
    r = montar(m,
               [interna("V", "100.00"), interna("E", "40.00", status="ESTORNADA")],
               [extrato("V", "100.00", "2.00"),
                extrato("E", "40.00", "1.00", tipo="ESTORNO")])
    assert r["total_liquido"] == D("59.00")     # 98.00 - 39.00


def test_divergente_nao_entra_no_total(m):
    r = montar(m, [interna()], [extrato(bruto="100.01")])
    assert r["total_liquido"] == D("0.00")


# ---------------------------------------------------- G-10/G-11/G-12 resolução

def test_conciliar_e_idempotente(m):
    m.carregar_internas([interna()])
    m.carregar_extrato([extrato()])
    assert m.conciliar(CORTE) == m.conciliar(CORTE)


def test_resolucao_sobrevive_a_reconciliacao(m):
    montar(m, [interna()], [extrato(bruto="100.01")])
    m.resolver("T1", "ana", "ajuste manual")
    m.conciliar(CORTE)
    assert m.itens("DIVERGENTE")[0]["resolvida"] is True
    assert m.relatorio()["pendentes"] == 0


def test_resolvida_continua_listada_como_divergente(m):
    montar(m, [interna()], [extrato(bruto="100.01")])
    m.resolver("T1", "ana", "ok")
    assert cat(m, "DIVERGENTE") == ["T1"]
    assert m.relatorio()["resolvidas"] == 1


def test_resolver_conciliada(m):
    montar(m, [interna()], [extrato()])
    with pytest.raises(ErroConciliacao) as e:
        m.resolver("T1", "ana", "ok")
    assert e.value.code == "ESTADO_INVALIDO"


def test_resolver_duas_vezes(m):
    montar(m, [interna()], [extrato(bruto="100.01")])
    m.resolver("T1", "ana", "ok")
    with pytest.raises(ErroConciliacao) as e:
        m.resolver("T1", "ana", "ok")
    assert e.value.code == "ESTADO_INVALIDO"


def test_resolver_transacao_inexistente(m):
    montar(m, [interna()], [extrato()])
    with pytest.raises(ErroConciliacao) as e:
        m.resolver("ZZZ", "ana", "ok")
    assert e.value.code == "TRANSACAO_NAO_ENCONTRADA"


def test_inexistente_precede_estado(m):
    montar(m, [interna()], [extrato()])
    with pytest.raises(ErroConciliacao) as e:
        m.resolver("ZZZ", "", "")
    assert e.value.code == "TRANSACAO_NAO_ENCONTRADA"


@pytest.mark.parametrize("ator,obs", [("", "ok"), ("ana", "")])
def test_resolver_sem_ator_ou_observacao(m, ator, obs):
    montar(m, [interna()], [extrato(bruto="100.01")])
    with pytest.raises(ErroConciliacao) as e:
        m.resolver("T1", ator, obs)
    assert e.value.code == "REGISTRO_INVALIDO"


# ---------------------------------------------------------- G-13/G-14 carga

def test_carga_acumula_entre_chamadas(m):
    assert m.carregar_internas([interna("A")]) == 1
    assert m.carregar_internas([interna("B")]) == 1
    r = m.conciliar(CORTE)
    assert r["somente_interna"] == 2


def test_carga_e_atomica(m):
    m.carregar_internas([interna("A")])
    with pytest.raises(ErroConciliacao):
        m.carregar_internas([interna("B"), interna("C", valor="0")])
    r = m.conciliar(CORTE)
    assert r["somente_interna"] == 1


@pytest.mark.parametrize("kw", [
    {"tid": ""}, {"valor": "0"}, {"valor": "-1"}, {"data": None}, {"status": "PENDENTE"},
])
def test_registro_interno_invalido(m, kw):
    with pytest.raises(ErroConciliacao) as e:
        m.carregar_internas([interna(**kw)])
    assert e.value.code == "REGISTRO_INVALIDO"


@pytest.mark.parametrize("kw", [
    {"bruto": "0"}, {"taxa": "-1"}, {"taxa": "200.00"}, {"tipo": "AJUSTE"},
])
def test_registro_de_extrato_invalido(m, kw):
    with pytest.raises(ErroConciliacao) as e:
        m.carregar_extrato([extrato(**kw)])
    assert e.value.code == "REGISTRO_INVALIDO"


def test_id_interno_repetido(m):
    with pytest.raises(ErroConciliacao) as e:
        m.carregar_internas([interna("A"), interna("A")])
    assert e.value.code == "REGISTRO_INVALIDO"


def test_id_repetido_no_extrato_e_permitido(m):
    assert m.carregar_extrato([extrato("A"), extrato("A")]) == 2


# ------------------------------------------------- G-15/G-16/G-17 consultas

def test_itens_ordenados_por_id(m):
    montar(m, [interna("C"), interna("A"), interna("B")], [])
    assert cat(m, "SOMENTE_INTERNA") == ["A", "B", "C"]


def test_lado_ausente_vira_none(m):
    montar(m, [interna()], [])
    it = m.itens("SOMENTE_INTERNA")[0]
    assert it["valor_interno"] == D("100.00") and it["valor_extrato"] is None
    assert it["motivo"] is None


def test_categoria_invalida(m):
    montar(m, [interna()], [extrato()])
    with pytest.raises(ErroConciliacao) as e:
        m.itens("QUALQUER")
    assert e.value.code == "CATEGORIA_INVALIDA"


def test_consulta_antes_de_conciliar(m):
    m.carregar_internas([interna()])
    with pytest.raises(ErroConciliacao) as e:
        m.itens("CONCILIADA")
    assert e.value.code == "CONCILIACAO_NAO_EXECUTADA"


def test_relatorio_antes_de_conciliar(m):
    with pytest.raises(ErroConciliacao) as e:
        m.relatorio()
    assert e.value.code == "CONCILIACAO_NAO_EXECUTADA"


def test_relatorio_traz_as_cinco_categorias(m):
    montar(m, [interna()], [extrato()])
    rel = m.relatorio()
    assert set(rel["por_categoria"]) == {"CONCILIADA", "DIVERGENTE", "DUPLICADA",
                                         "SOMENTE_INTERNA", "SOMENTE_EXTRATO"}
    assert rel["por_categoria"]["DIVERGENTE"] == 0
    assert rel["total_liquido"] == D("98.00")


def test_itens_expoe_as_chaves_do_contrato(m):
    montar(m, [interna()], [extrato()])
    assert set(m.itens("CONCILIADA")[0]) == {
        "transacao_id", "categoria", "motivo", "valor_interno",
        "valor_extrato", "resolvida"}
