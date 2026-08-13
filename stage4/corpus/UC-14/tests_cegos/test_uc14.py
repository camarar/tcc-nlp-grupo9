"""Suíte cega UC-14 — motor de cálculo tributário por UF e NCM."""

from decimal import Decimal

import pytest

from solucao import ErroTributario, MotorTributario

D = Decimal
CNPJ = "00000000000191"


@pytest.fixture
def m():
    mt = MotorTributario()
    mt.registrar_regime(CNPJ, "NORMAL")
    mt.registrar_aliquota("SP", "12345678", "0.18")
    return mt


def item(ncm="12345678", valor="100.00", quantidade=2, desconto="0"):
    return {"ncm": ncm, "valor": valor, "quantidade": quantidade, "desconto": desconto}


def nota(itens=None, uf="SP", frete="0", cnpj=CNPJ):
    return {"cnpj_emitente": cnpj, "uf_destino": uf, "frete": frete,
            "itens": itens if itens is not None else [item()]}


# ------------------------------------------------------- G-01 Regra de Ouro

def test_par_uf_ncm_sem_cadastro(m):
    with pytest.raises(ErroTributario) as e:
        m.calcular(nota([item(ncm="99999999")]))
    assert e.value.code == "ALIQUOTA_NAO_CADASTRADA"


def test_nao_usa_a_aliquota_de_outra_uf(m):
    with pytest.raises(ErroTributario) as e:
        m.calcular(nota(uf="RJ"))
    assert e.value.code == "ALIQUOTA_NAO_CADASTRADA"


def test_omissao_nao_vira_isencao(m):
    with pytest.raises(ErroTributario):
        m.calcular(nota([item(ncm="99999999")]))


# ------------------------------------------------------- G-02 busca por prefixo

def test_ncm_exato_tem_precedencia(m):
    m.registrar_aliquota("SP", "1234", "0.12")
    assert m.calcular(nota())["icms"] == D("36.00")      # 200 x 0.18


def test_fallback_para_o_prefixo(m):
    m.registrar_aliquota("SP", "1234", "0.12")
    r = m.calcular(nota([item(ncm="12349999")]))
    assert r["icms"] == D("24.00")                        # 200 x 0.12


def test_vale_o_prefixo_mais_longo(m):
    m.registrar_aliquota("SP", "1234", "0.12")
    m.registrar_aliquota("SP", "123456", "0.15")
    r = m.calcular(nota([item(ncm="12345699")]))
    assert r["icms"] == D("30.00")                        # 200 x 0.15


def test_prefixo_de_outra_uf_nao_serve(m):
    m.registrar_aliquota("RJ", "1234", "0.12")
    with pytest.raises(ErroTributario) as e:
        m.calcular(nota([item(ncm="12349999")]))
    assert e.value.code == "ALIQUOTA_NAO_CADASTRADA"


def test_memoria_expoe_o_prefixo_aplicado(m):
    m.registrar_aliquota("SP", "1234", "0.12")
    mem = m.memoria_calculo(nota([item(ncm="12349999")]))
    assert mem[0]["ncm_aplicado"] == "1234"
    assert mem[0]["aliquota"] == D("0.12")


# ------------------------------------------------------------ G-03 base

def test_base_desconta_o_desconto(m):
    r = m.calcular(nota([item(desconto="50.00")]))
    assert r["base_calculo"] == D("150.00")
    assert r["icms"] == D("27.00")


def test_frete_fora_da_base(m):
    r = m.calcular(nota(frete="80.00"))
    assert r["base_calculo"] == D("200.00")
    assert r["icms"] == D("36.00")


def test_base_soma_os_itens(m):
    r = m.calcular(nota([item(), item(valor="50.00", quantidade=1)]))
    assert r["base_calculo"] == D("250.00")


# ---------------------------------------------------------- G-04 isenção

def test_item_isento_sai_da_base(m):
    m.registrar_isencao("SP", "12345678")
    r = m.calcular(nota())
    assert r["base_calculo"] == D("0.00") and r["icms"] == D("0.00")


def test_isencao_nao_usa_prefixo(m):
    m.registrar_isencao("SP", "1234")
    r = m.calcular(nota())                                # NCM 12345678 não é isento
    assert r["icms"] == D("36.00")


def test_isencao_dispensa_aliquota_cadastrada(m):
    m.registrar_isencao("SP", "99999999")
    r = m.calcular(nota([item(ncm="99999999")]))
    assert r["icms"] == D("0.00")


def test_memoria_marca_o_item_isento(m):
    m.registrar_isencao("SP", "12345678")
    mem = m.memoria_calculo(nota())[0]
    assert mem["isento"] is True
    assert mem["aliquota"] is None and mem["ncm_aplicado"] is None


def test_isencao_prevalece_sobre_a_aliquota(m):
    m.registrar_isencao("SP", "12345678")
    assert m.calcular(nota())["icms"] == D("0.00")


def test_nota_mista_isento_e_tributado(m):
    m.registrar_aliquota("SP", "5555", "0.10")
    m.registrar_isencao("SP", "12345678")
    r = m.calcular(nota([item(), item(ncm="55550000", valor="100.00", quantidade=1)]))
    assert r["base_calculo"] == D("100.00") and r["icms"] == D("10.00")


# -------------------------------------------------------------- G-06 ST

def test_substituicao_tributaria(m):
    m.registrar_aliquota("SP", "12345678", "0.18", mva="0.40")
    r = m.calcular(nota())
    assert r["icms"] == D("36.00")
    assert r["icms_st"] == D("14.40")                     # 200x1.4x0.18 - 36
    assert r["total_tributos"] == D("50.40")


def test_sem_mva_nao_ha_st(m):
    assert m.calcular(nota())["icms_st"] == D("0.00")


def test_st_nunca_negativo(m):
    m.registrar_aliquota("SP", "12345678", "0.18", mva="0")
    assert m.calcular(nota())["icms_st"] == D("0.00")


# --------------------------------------------------------- G-07/G-08 regime

def test_simples_reduz_o_icms_pela_metade(m):
    m.registrar_regime(CNPJ, "SIMPLES")
    assert m.calcular(nota())["icms"] == D("18.00")


def test_simples_zera_a_substituicao(m):
    m.registrar_aliquota("SP", "12345678", "0.18", mva="0.40")
    m.registrar_regime(CNPJ, "SIMPLES")
    r = m.calcular(nota())
    assert r["icms_st"] == D("0.00") and r["total_tributos"] == D("18.00")


def test_regime_nao_cadastrado(m):
    with pytest.raises(ErroTributario) as e:
        m.calcular(nota(cnpj="99999999999999"))
    assert e.value.code == "REGIME_DESCONHECIDO"


def test_reregistro_substitui_o_regime(m):
    m.registrar_regime(CNPJ, "SIMPLES")
    m.registrar_regime(CNPJ, "NORMAL")
    assert m.calcular(nota())["icms"] == D("36.00")


# --------------------------------------------------------------- G-09 totais

def test_total_da_nota_soma_frete_e_st(m):
    m.registrar_aliquota("SP", "12345678", "0.18", mva="0.40")
    r = m.calcular(nota(frete="30.00"))
    assert r["total_nota"] == D("244.40")                 # 200 + 30 + 14.40


def test_icms_nao_soma_ao_total(m):
    r = m.calcular(nota(frete="30.00"))
    assert r["total_nota"] == D("230.00")


def test_isento_entra_no_total_da_nota(m):
    m.registrar_isencao("SP", "12345678")
    assert m.calcular(nota(frete="10.00"))["total_nota"] == D("210.00")


# ------------------------------------------------------- G-10..G-13 validação

@pytest.mark.parametrize("kw", [
    {"aliquota": "0"}, {"aliquota": "1.5"}, {"aliquota": "0.18", "mva": "-0.1"},
    {"ncm": "123"}, {"ncm": ""}, {"ncm": "12ab5678"}, {"uf": "SPX"},
])
def test_tabela_invalida(m, kw):
    args = {"uf": "SP", "ncm": "12345678", "aliquota": "0.18", "mva": None}
    args.update(kw)
    with pytest.raises(ErroTributario) as e:
        m.registrar_aliquota(args["uf"], args["ncm"], args["aliquota"], args["mva"])
    assert e.value.code == "TABELA_INVALIDA"


def test_isencao_com_ncm_curto(m):
    with pytest.raises(ErroTributario) as e:
        m.registrar_isencao("SP", "123")
    assert e.value.code == "TABELA_INVALIDA"


def test_regime_fora_do_vocabulario(m):
    with pytest.raises(ErroTributario) as e:
        m.registrar_regime(CNPJ, "MEI")
    assert e.value.code == "TABELA_INVALIDA"


@pytest.mark.parametrize("kw", [
    {"valor": "-1"}, {"quantidade": 0}, {"desconto": "-1"},
    {"desconto": "201.00"}, {"ncm": ""}, {"ncm": "abcd"},
])
def test_item_invalido(m, kw):
    with pytest.raises(ErroTributario) as e:
        m.calcular(nota([item(**kw)]))
    assert e.value.code == "ITEM_INVALIDO"


@pytest.mark.parametrize("kw", [
    {"itens": []}, {"frete": "-1"}, {"uf": "S"}, {"cnpj": ""},
])
def test_nota_invalida(m, kw):
    with pytest.raises(ErroTributario) as e:
        m.calcular(nota(**kw))
    assert e.value.code == "NOTA_INVALIDA"


def test_nota_precede_item(m):
    with pytest.raises(ErroTributario) as e:
        m.calcular(nota([item(valor="-1")], frete="-1"))
    assert e.value.code == "NOTA_INVALIDA"


def test_item_precede_regime(m):
    with pytest.raises(ErroTributario) as e:
        m.calcular(nota([item(valor="-1")], cnpj="99999999999999"))
    assert e.value.code == "ITEM_INVALIDO"


def test_regime_precede_aliquota(m):
    with pytest.raises(ErroTributario) as e:
        m.calcular(nota([item(ncm="99999999")], cnpj="99999999999999"))
    assert e.value.code == "REGIME_DESCONHECIDO"


# ------------------------------------------------------ G-14/G-15/G-16 saída

def test_memoria_tem_uma_entrada_por_item_na_ordem(m):
    m.registrar_aliquota("SP", "5555", "0.10")
    mem = m.memoria_calculo(nota([item(), item(ncm="55550000")]))
    assert [x["ncm"] for x in mem] == ["12345678", "55550000"]
    assert set(mem[0]) == {"ncm", "ncm_aplicado", "aliquota", "base",
                           "icms", "icms_st", "isento"}


def test_memoria_propaga_os_mesmos_erros(m):
    with pytest.raises(ErroTributario) as e:
        m.memoria_calculo(nota([item(ncm="99999999")]))
    assert e.value.code == "ALIQUOTA_NAO_CADASTRADA"


def test_valores_com_duas_casas(m):
    r = m.calcular(nota())
    for campo in ("base_calculo", "icms", "icms_st", "total_tributos", "total_nota"):
        assert isinstance(r[campo], Decimal)
        assert -r[campo].as_tuple().exponent == 2


def test_icms_soma_valores_ja_quantizados(m):
    m.registrar_aliquota("SP", "7777", "0.07")
    itens = [item(ncm="77770000", valor="10.07", quantidade=1),
             item(ncm="77770001", valor="10.07", quantidade=1)]
    # 10.07 x 0.07 = 0.7049 -> 0.70 por item; soma = 1.40
    assert m.calcular(nota(itens))["icms"] == D("1.40")


def test_reregistro_substitui_a_aliquota(m):
    m.registrar_aliquota("SP", "12345678", "0.10")
    assert m.calcular(nota())["icms"] == D("20.00")
