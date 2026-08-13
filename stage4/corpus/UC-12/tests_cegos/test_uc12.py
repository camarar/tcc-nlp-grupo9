"""Suíte cega UC-12 — serviço de conversão de moedas resiliente."""

from decimal import Decimal

import pytest

from solucao import ErroCambio, ServicoCambio

D = Decimal


class Provedor:
    def __init__(self, taxas=None):
        self.taxas = taxas or {"USD/BRL": D("5.00"), "USD/EUR": D("0.90"),
                               "USD/JPY": D("150.50")}
        self.falhar = False
        self.chamadas = []

    def __call__(self, par):
        self.chamadas.append(par)
        if self.falhar:
            raise RuntimeError("provedor fora do ar")
        if par not in self.taxas:
            raise KeyError(par)
        return self.taxas[par]


class Relogio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def avancar(self, s):
        self.t += s


def montar(config=None):
    p, r = Provedor(), Relogio()
    s = ServicoCambio(p, relogio=r, config=config)
    for cod, casas in (("USD", 2), ("BRL", 2), ("EUR", 2), ("JPY", 0)):
        s.registrar_moeda(cod, casas)
    return s, p, r


# --------------------------------------------------------- G-01/G-02 taxas

def test_conversao_direta_a_partir_do_dolar():
    s, p, _ = montar()
    r = s.converter("100", "USD", "BRL")
    assert r["valor_convertido"] == D("500.00")
    assert r["taxa"] == D("5.000000")
    assert p.chamadas == ["USD/BRL"]


def test_provedor_e_sempre_consultado_com_o_dolar_na_base():
    s, p, _ = montar()
    s.converter("100", "BRL", "EUR")
    assert sorted(p.chamadas) == ["USD/BRL", "USD/EUR"]


def test_taxa_cruzada_entre_duas_moedas():
    s, _, _ = montar()
    r = s.converter("100", "EUR", "BRL")
    assert r["taxa"] == D("5.555556")          # 5.00 / 0.90
    assert r["valor_convertido"] == D("555.56")


def test_dolar_nao_e_perguntado_ao_provedor():
    s, p, _ = montar()
    s.converter("100", "USD", "USD")
    s.converter("100", "BRL", "USD")
    assert "USD/USD" not in p.chamadas


# ----------------------------------------------------------- G-03 cache

def test_dentro_do_ttl_nao_chama_o_provedor():
    s, p, r = montar()
    s.converter("1", "USD", "BRL")
    r.avancar(599)
    s.converter("1", "USD", "BRL")
    assert p.chamadas == ["USD/BRL"]
    assert s.estatisticas()["acertos_cache"] == 1


def test_ttl_expira_na_fronteira():
    s, p, r = montar()
    s.converter("1", "USD", "BRL")
    r.avancar(600)
    s.converter("1", "USD", "BRL")
    assert p.chamadas == ["USD/BRL", "USD/BRL"]


def test_ttl_configuravel():
    s, p, r = montar({"ttl_s": 10})
    s.converter("1", "USD", "BRL")
    r.avancar(11)
    s.converter("1", "USD", "BRL")
    assert len(p.chamadas) == 2


# ------------------------------------------------------ G-04/G-05 fallback

def test_falha_usa_cotacao_obsoleta():
    s, p, r = montar()
    s.converter("1", "USD", "BRL")
    r.avancar(700)
    p.falhar = True
    res = s.converter("100", "USD", "BRL")
    assert res["stale"] is True
    assert res["valor_convertido"] == D("500.00")
    assert res["idade_s"] == 700.0
    assert s.estatisticas()["usos_stale"] == 1


def test_obsoleta_alem_do_limite():
    s, p, r = montar()
    s.converter("1", "USD", "BRL")
    r.avancar(86400)
    p.falhar = True
    with pytest.raises(ErroCambio) as e:
        s.converter("1", "USD", "BRL")
    assert e.value.code == "COTACAO_INDISPONIVEL"


def test_obsoleta_no_limite_ainda_serve():
    s, p, r = montar()
    s.converter("1", "USD", "BRL")
    r.avancar(86399)
    p.falhar = True
    assert s.converter("1", "USD", "BRL")["stale"] is True


def test_sem_cache_e_provedor_fora():
    s, p, _ = montar()
    p.falhar = True
    with pytest.raises(ErroCambio) as e:
        s.converter("1", "USD", "BRL")
    assert e.value.code == "PROVEDOR_INDISPONIVEL"


# ------------------------------------------------------ G-06..G-08 disjuntor

def test_circuito_comeca_fechado():
    s, _, _ = montar()
    assert s.estado_circuito() == "FECHADO"


def test_cinco_falhas_consecutivas_abrem_o_circuito():
    s, p, _ = montar()
    p.falhar = True
    for _ in range(5):
        with pytest.raises(ErroCambio):
            s.converter("1", "USD", "BRL")
    assert s.estado_circuito() == "ABERTO"


def test_circuito_aberto_nao_chama_o_provedor():
    s, p, _ = montar()
    p.falhar = True
    for _ in range(5):
        with pytest.raises(ErroCambio):
            s.converter("1", "USD", "BRL")
    antes = len(p.chamadas)
    with pytest.raises(ErroCambio):
        s.converter("1", "USD", "BRL")
    assert len(p.chamadas) == antes


def test_meio_aberto_apos_o_tempo_de_espera():
    s, p, r = montar()
    p.falhar = True
    for _ in range(5):
        with pytest.raises(ErroCambio):
            s.converter("1", "USD", "BRL")
    r.avancar(60)
    assert s.estado_circuito() == "MEIO_ABERTO"


def test_sucesso_em_meio_aberto_fecha_o_circuito():
    s, p, r = montar()
    p.falhar = True
    for _ in range(5):
        with pytest.raises(ErroCambio):
            s.converter("1", "USD", "BRL")
    r.avancar(61)
    p.falhar = False
    s.converter("1", "USD", "BRL")
    assert s.estado_circuito() == "FECHADO"
    # Anomalia G-08: subtrai 1, então fica 4
    assert s.estatisticas()["falhas_consecutivas"] == 4


def test_falha_em_meio_aberto_reabre():
    s, p, r = montar()
    p.falhar = True
    for _ in range(5):
        with pytest.raises(ErroCambio):
            s.converter("1", "USD", "BRL")
    r.avancar(61)
    with pytest.raises(ErroCambio):
        s.converter("1", "USD", "BRL")
    assert s.estado_circuito() == "ABERTO"


def test_sucesso_subtrai_um_do_contador_de_falhas():
    s, p, _ = montar()
    p.falhar = True
    for _ in range(3):
        with pytest.raises(ErroCambio):
            s.converter("1", "USD", "BRL")
    p.falhar = False
    s.converter("1", "USD", "BRL")
    # Subtrai 1, então 3 vira 2
    assert s.estatisticas()["falhas_consecutivas"] == 2
    assert s.estado_circuito() == "FECHADO"


def test_limiar_configuravel():
    s, p, _ = montar({"falhas_para_abrir": 2})
    p.falhar = True
    for _ in range(2):
        with pytest.raises(ErroCambio):
            s.converter("1", "USD", "BRL")
    assert s.estado_circuito() == "ABERTO"


# ------------------------------------------------------- G-09/G-10 precisão

def test_casas_decimais_da_moeda_de_destino():
    s, _, _ = montar()
    r = s.converter("10", "USD", "JPY")
    assert r["valor_convertido"] == D("1505")
    assert -r["valor_convertido"].as_tuple().exponent == 0


def test_taxa_sempre_com_seis_casas():
    s, _, _ = montar()
    assert -s.converter("1", "USD", "BRL")["taxa"].as_tuple().exponent == 6


def test_mesma_moeda_cobra_taxa_de_identidade():
    s, p, _ = montar()
    r = s.converter("100", "BRL", "BRL")
    # 100 * 0.99 = 99.00
    assert r == {"valor_convertido": D("99.00"), "taxa": D("0.990000"),
                 "stale": False, "idade_s": 0.0}
    assert p.chamadas == []
    assert s.estatisticas()["acertos_cache"] == 0


# ------------------------------------------------- G-11/G-12 entradas inválidas

@pytest.mark.parametrize("de,para", [("XXX", "BRL"), ("USD", "XXX")])
def test_moeda_nao_registrada(de, para):
    s, p, _ = montar()
    with pytest.raises(ErroCambio) as e:
        s.converter("1", de, para)
    assert e.value.code == "MOEDA_NAO_SUPORTADA"
    assert p.chamadas == []


def test_valor_negativo():
    s, _, _ = montar()
    with pytest.raises(ErroCambio) as e:
        s.converter("-1", "USD", "BRL")
    assert e.value.code == "VALOR_INVALIDO"


def test_valor_zero_e_valido():
    s, _, _ = montar()
    assert s.converter("0", "USD", "BRL")["valor_convertido"] == D("0.00")


# ------------------------------------------------------------- G-13 idade

def test_idade_zero_em_cotacao_recem_buscada():
    s, _, _ = montar()
    assert s.cotacao("USD", "BRL")["idade_s"] == 0.0


def test_idade_reflete_o_tempo_em_cache():
    s, _, r = montar()
    s.cotacao("USD", "BRL")
    r.avancar(120.5)
    assert s.cotacao("USD", "BRL")["idade_s"] == 120.5


def test_cruzada_usa_a_idade_da_mais_antiga():
    s, p, r = montar()
    s.cotacao("USD", "EUR")
    r.avancar(100)
    s.cotacao("USD", "BRL")
    r.avancar(50)
    assert s.cotacao("EUR", "BRL")["idade_s"] == 150.0


def test_cruzada_fica_obsoleta_se_qualquer_lado_estiver():
    s, p, r = montar()
    s.cotacao("USD", "EUR")
    s.cotacao("USD", "BRL")
    r.avancar(700)
    p.falhar = True
    assert s.cotacao("EUR", "BRL")["stale"] is True


# ------------------------------------------------- G-14..G-17 configuração

@pytest.mark.parametrize("cfg", [
    {"ttl_s": 0}, {"stale_max_s": -1}, {"falhas_para_abrir": 0}, {"tempo_aberto_s": 0},
])
def test_configuracao_invalida(cfg):
    with pytest.raises(ErroCambio) as e:
        ServicoCambio(Provedor(), relogio=Relogio(), config=cfg)
    assert e.value.code == "CONFIGURACAO_INVALIDA"


@pytest.mark.parametrize("cod,casas", [("BRL", -1), ("BRL", 9), ("", 2)])
def test_registro_de_moeda_invalido(cod, casas):
    s, _, _ = montar()
    with pytest.raises(ErroCambio) as e:
        s.registrar_moeda(cod, casas)
    assert e.value.code == "CONFIGURACAO_INVALIDA"


def test_reregistro_nao_invalida_o_cache():
    s, p, _ = montar()
    s.converter("1", "USD", "BRL")
    s.registrar_moeda("BRL", 4)
    r = s.converter("1", "USD", "BRL")
    assert len(p.chamadas) == 1
    assert -r["valor_convertido"].as_tuple().exponent == 4


def test_estatisticas_expoem_as_chaves_do_contrato():
    s, _, _ = montar()
    s.converter("1", "USD", "BRL")
    e = s.estatisticas()
    assert set(e) == {"chamadas_provedor", "acertos_cache",
                      "falhas_consecutivas", "usos_stale"}
    assert e["chamadas_provedor"] == 1


def test_cada_moeda_e_resolvida_uma_vez_por_chamada():
    s, p, _ = montar()
    s.converter("1", "EUR", "BRL")
    assert len(p.chamadas) == len(set(p.chamadas)) == 2
