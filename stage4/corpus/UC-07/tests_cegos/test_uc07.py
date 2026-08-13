"""Suíte cega UC-07 — motor de cotação de frete multi-transportadora."""

from decimal import Decimal

import pytest

from solucao import ErroFrete, MotorFrete

D = Decimal

FAIXAS_R = [{"ate_kg": "1", "preco": "10.00", "prazo_dias": 1},
            {"ate_kg": "5", "preco": "20.00", "prazo_dias": 2},
            {"ate_kg": "30", "preco": "50.00", "prazo_dias": 3}]
FAIXAS_E = [{"ate_kg": "1", "preco": "5.00", "prazo_dias": 5},
            {"ate_kg": "5", "preco": "12.00", "prazo_dias": 6},
            {"ate_kg": "30", "preco": "30.00", "prazo_dias": 8}]


@pytest.fixture
def m():
    mf = MotorFrete()
    mf.registrar_transportadora("rapida", {
        "faixas": FAIXAS_R, "regioes": ["SP"], "fator_cubagem": 6000,
        "peso_maximo_kg": "30", "ad_valorem": None})
    mf.registrar_transportadora("economica", {
        "faixas": FAIXAS_E, "regioes": ["SP", "RJ"], "fator_cubagem": 6000,
        "peso_maximo_kg": "30", "ad_valorem": None})
    return mf


def item(**kw):
    it = {"peso_kg": "2", "altura_cm": "20", "largura_cm": "20",
          "comprimento_cm": "20", "quantidade": 1, "valor": "100.00"}
    it.update(kw)
    return it


def pedido(itens=None, uf="SP", cep="01001000"):
    return {"uf_destino": uf, "cep_destino": cep,
            "itens": itens if itens is not None else [item()]}


# --------------------------------------------------------- G-01/G-02 peso

def test_peso_real_prevalece_sobre_o_cubado():
    # 20x20x20 / 6000 = 1.333 kg cubado contra 2 kg reais
    mf = MotorFrete()
    mf.registrar_transportadora("r", {"faixas": FAIXAS_R, "regioes": ["SP"],
                                      "fator_cubagem": 6000, "peso_maximo_kg": "30",
                                      "ad_valorem": None})
    assert mf.cotar(pedido())[0]["peso_cobrado_kg"] == D("2.000")


def test_peso_cubado_prevalece_quando_maior(m):
    # 40x40x40 / 6000 = 10.667 -> teto de 0,5 -> 11.0
    it = item(altura_cm="40", largura_cm="40", comprimento_cm="40")
    assert m.cotar(pedido([it]))[0]["peso_cobrado_kg"] == D("11.000")


def test_cubagem_multiplica_pela_quantidade(m):
    it = item(peso_kg="0.1", quantidade=3)     # cubado 1.333 x 3 = 4.0
    assert m.cotar(pedido([it]))[0]["peso_cobrado_kg"] == D("4.000")


def test_peso_real_soma_a_quantidade(m):
    it = item(peso_kg="2", altura_cm="1", largura_cm="1",
              comprimento_cm="1", quantidade=4)
    assert m.cotar(pedido([it]))[0]["peso_cobrado_kg"] == D("8.000")


def test_arredonda_para_cima_ate_o_proximo_meio_quilo(m):
    it = item(peso_kg="1.2", altura_cm="1", largura_cm="1", comprimento_cm="1")
    assert m.cotar(pedido([it]))[0]["peso_cobrado_kg"] == D("1.500")


def test_peso_ja_multiplo_de_meio_quilo_permanece(m):
    it = item(peso_kg="1.5", altura_cm="1", largura_cm="1", comprimento_cm="1")
    assert m.cotar(pedido([it]))[0]["peso_cobrado_kg"] == D("1.500")


def test_soma_de_itens_diferentes(m):
    itens = [item(peso_kg="1", altura_cm="1", largura_cm="1", comprimento_cm="1"),
             item(peso_kg="2", altura_cm="1", largura_cm="1", comprimento_cm="1")]
    assert m.cotar(pedido(itens))[0]["peso_cobrado_kg"] == D("3.000")


# ------------------------------------------------------------- G-03 faixas

def test_limite_da_faixa_e_inclusivo(m):
    it = item(peso_kg="1", altura_cm="1", largura_cm="1", comprimento_cm="1")
    por_nome = {c["transportadora"]: c for c in m.cotar(pedido([it]))}
    assert por_nome["rapida"]["frete"] == D("10.00")
    assert por_nome["rapida"]["prazo_dias"] == 1


def test_um_grama_acima_muda_de_faixa(m):
    it = item(peso_kg="1.001", altura_cm="1", largura_cm="1", comprimento_cm="1")
    por_nome = {c["transportadora"]: c for c in m.cotar(pedido([it]))}
    assert por_nome["rapida"]["frete"] == D("20.00")


# --------------------------------------------------- G-04/G-05/G-06 exclusões

def test_peso_acima_do_maximo_exclui_a_transportadora(m):
    m.registrar_transportadora("pesada", {
        "faixas": [{"ate_kg": "100", "preco": "90.00", "prazo_dias": 9}],
        "regioes": ["SP"], "fator_cubagem": 6000,
        "peso_maximo_kg": "100", "ad_valorem": None})
    it = item(peso_kg="40", altura_cm="1", largura_cm="1", comprimento_cm="1")
    nomes = [c["transportadora"] for c in m.cotar(pedido([it]))]
    assert nomes == ["pesada"]


def test_uf_nao_atendida_exclui_sem_erro(m):
    nomes = [c["transportadora"] for c in m.cotar(pedido(uf="RJ"))]
    assert nomes == ["economica"]


def test_nenhuma_transportadora_atende_a_uf(m):
    with pytest.raises(ErroFrete) as e:
        m.cotar(pedido(uf="AM"))
    assert e.value.code == "REGIAO_NAO_ATENDIDA"


def test_restricao_por_prefixo_de_cep(m):
    m.registrar_restricao("rapida", "010")
    nomes = [c["transportadora"] for c in m.cotar(pedido(cep="01001000"))]
    assert nomes == ["economica"]


def test_restricao_nao_atinge_cep_de_outro_prefixo(m):
    m.registrar_restricao("rapida", "010")
    nomes = sorted(c["transportadora"] for c in m.cotar(pedido(cep="20040002")))
    assert nomes == ["economica", "rapida"]


def test_mascara_do_cep_e_ignorada(m):
    m.registrar_restricao("rapida", "010")
    nomes = [c["transportadora"] for c in m.cotar(pedido(cep="01001-000"))]
    assert nomes == ["economica"]


def test_todas_excluidas_com_uf_atendida(m):
    it = item(peso_kg="40", altura_cm="1", largura_cm="1", comprimento_cm="1")
    with pytest.raises(ErroFrete) as e:
        m.cotar(pedido([it]))
    assert e.value.code == "SEM_COTACAO"


# --------------------------------------------------------- G-07/G-08 seguro

def test_seguro_ad_valorem_sobre_o_valor_declarado(m):
    m.registrar_transportadora("segurada", {
        "faixas": FAIXAS_R, "regioes": ["SP"], "fator_cubagem": 6000,
        "peso_maximo_kg": "30", "ad_valorem": "0.01"})
    c = [x for x in m.cotar(pedido([item(valor="250.00", quantidade=2)]))
         if x["transportadora"] == "segurada"][0]
    assert c["seguro"] == D("5.00")
    assert c["total"] == c["frete"] + c["seguro"]


def test_sem_ad_valorem_nao_ha_seguro(m):
    c = m.cotar(pedido())[0]
    assert c["seguro"] == D("0.00") and c["total"] == c["frete"]


# ----------------------------------------------------- G-09/G-10 ordenação

def test_cotacoes_ordenadas_por_total(m):
    cot = m.cotar(pedido())
    assert [c["transportadora"] for c in cot] == ["economica", "rapida"]
    assert [c["total"] for c in cot] == sorted(c["total"] for c in cot)


def test_empate_de_total_desempata_por_prazo(m):
    m.registrar_transportadora("gemea", {
        "faixas": FAIXAS_E, "regioes": ["SP"], "fator_cubagem": 6000,
        "peso_maximo_kg": "30", "ad_valorem": None})
    m.registrar_transportadora("veloz", {
        "faixas": [{"ate_kg": "30", "preco": "12.00", "prazo_dias": 1}],
        "regioes": ["SP"], "fator_cubagem": 6000,
        "peso_maximo_kg": "30", "ad_valorem": None})
    cot = [c["transportadora"] for c in m.cotar(pedido())]
    assert cot[0] == "veloz"          # mesmo total de 12.00, prazo menor


def test_melhor_cotacao_por_preco(m):
    assert m.melhor_cotacao(pedido(), "PRECO")["transportadora"] == "economica"


def test_melhor_cotacao_por_prazo(m):
    assert m.melhor_cotacao(pedido(), "PRAZO")["transportadora"] == "rapida"


def test_criterio_invalido(m):
    with pytest.raises(ErroFrete) as e:
        m.melhor_cotacao(pedido(), "PESO")
    assert e.value.code == "PEDIDO_INVALIDO"


# ---------------------------------------------------- G-12/G-13 entradas

@pytest.mark.parametrize("kw", [
    {"peso_kg": "0"}, {"peso_kg": "-1"}, {"altura_cm": "0"}, {"largura_cm": "-2"},
    {"comprimento_cm": "0"}, {"quantidade": 0}, {"valor": "-1"},
])
def test_dimensoes_invalidas(m, kw):
    with pytest.raises(ErroFrete) as e:
        m.cotar(pedido([item(**kw)]))
    assert e.value.code == "DIMENSOES_INVALIDAS"


@pytest.mark.parametrize("ped", [
    {"uf_destino": "SP", "cep_destino": "01001000", "itens": []},
    {"uf_destino": "", "cep_destino": "01001000", "itens": [item()]},
    {"uf_destino": "SP", "cep_destino": "", "itens": [item()]},
    {"uf_destino": "SP", "cep_destino": "01001000"},
])
def test_pedido_invalido(m, ped):
    with pytest.raises(ErroFrete) as e:
        m.cotar(ped)
    assert e.value.code == "PEDIDO_INVALIDO"


# ------------------------------------------------------- G-14/G-15 registros

@pytest.mark.parametrize("cfg", [
    {"faixas": [], "regioes": ["SP"], "fator_cubagem": 6000,
     "peso_maximo_kg": "30", "ad_valorem": None},
    {"faixas": [{"ate_kg": "5", "preco": "1", "prazo_dias": 1},
                {"ate_kg": "5", "preco": "2", "prazo_dias": 1}],
     "regioes": ["SP"], "fator_cubagem": 6000, "peso_maximo_kg": "30",
     "ad_valorem": None},
    {"faixas": [{"ate_kg": "5", "preco": "-1", "prazo_dias": 1}],
     "regioes": ["SP"], "fator_cubagem": 6000, "peso_maximo_kg": "30",
     "ad_valorem": None},
    {"faixas": [{"ate_kg": "5", "preco": "1", "prazo_dias": 0}],
     "regioes": ["SP"], "fator_cubagem": 6000, "peso_maximo_kg": "30",
     "ad_valorem": None},
    {"faixas": FAIXAS_R, "regioes": ["SP"], "fator_cubagem": 0,
     "peso_maximo_kg": "30", "ad_valorem": None},
    {"faixas": FAIXAS_R, "regioes": ["SP"], "fator_cubagem": 6000,
     "peso_maximo_kg": "0", "ad_valorem": None},
    {"faixas": FAIXAS_R, "regioes": [], "fator_cubagem": 6000,
     "peso_maximo_kg": "30", "ad_valorem": None},
    {"faixas": FAIXAS_R, "regioes": ["SP"], "fator_cubagem": 6000,
     "peso_maximo_kg": "30", "ad_valorem": "-0.01"},
])
def test_tabela_invalida(m, cfg):
    with pytest.raises(ErroFrete) as e:
        m.registrar_transportadora("nova", cfg)
    assert e.value.code == "TABELA_INVALIDA"


def test_restricao_para_transportadora_inexistente(m):
    with pytest.raises(ErroFrete) as e:
        m.registrar_restricao("fantasma", "010")
    assert e.value.code == "TRANSPORTADORA_DESCONHECIDA"


def test_reregistro_mantem_as_restricoes(m):
    m.registrar_restricao("rapida", "010")
    m.registrar_transportadora("rapida", {
        "faixas": FAIXAS_R, "regioes": ["SP"], "fator_cubagem": 6000,
        "peso_maximo_kg": "30", "ad_valorem": None})
    assert [c["transportadora"] for c in m.cotar(pedido())] == ["economica"]


# ------------------------------------------------- G-16/G-17 precisão e ordem

def test_precisao_dos_campos(m):
    c = m.cotar(pedido())[0]
    for campo in ("frete", "seguro", "total"):
        assert isinstance(c[campo], Decimal) and -c[campo].as_tuple().exponent == 2
    assert -c["peso_cobrado_kg"].as_tuple().exponent == 3


def test_pedido_invalido_precede_dimensoes(m):
    with pytest.raises(ErroFrete) as e:
        m.cotar({"uf_destino": "", "cep_destino": "01001000",
                 "itens": [item(peso_kg="0")]})
    assert e.value.code == "PEDIDO_INVALIDO"


def test_dimensoes_precedem_regiao(m):
    with pytest.raises(ErroFrete) as e:
        m.cotar(pedido([item(peso_kg="0")], uf="AM"))
    assert e.value.code == "DIMENSOES_INVALIDAS"


def test_regiao_precede_sem_cotacao(m):
    it = item(peso_kg="40", altura_cm="1", largura_cm="1", comprimento_cm="1")
    with pytest.raises(ErroFrete) as e:
        m.cotar(pedido([it], uf="AM"))
    assert e.value.code == "REGIAO_NAO_ATENDIDA"
