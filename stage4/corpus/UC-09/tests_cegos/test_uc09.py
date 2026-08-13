"""Suíte cega UC-09 — central de chamados com SLA."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from solucao import CentralChamados, ErroChamado

TZ = ZoneInfo("America/Sao_Paulo")
# 2026-06-15 é segunda; 2026-06-19 sexta; 2026-06-20 sábado


def t(dia, h, mi=0, mes=6):
    return datetime(2026, mes, dia, h, mi, tzinfo=TZ)


@pytest.fixture
def c():
    cc = CentralChamados()
    cc.configurar_sla("CRITICA", 120, True)
    cc.configurar_sla("ALTA", 480, True)
    cc.configurar_sla("MEDIA", 600, True)
    cc.configurar_sla("BAIXA", 240, False)
    return cc


def abrir(cc, sev="CRITICA", em=None, cliente="cli", assunto="a"):
    return cc.abrir({"cliente": cliente, "severidade": sev, "assunto": assunto,
                     "aberto_em": em or t(15, 10)})


# ---------------------------------------------------- G-01/G-02 prazo útil

def test_prazo_dentro_do_mesmo_dia(c):
    assert c.prazo(abrir(c, em=t(15, 10))) == t(15, 12)


def test_prazo_atravessa_o_fim_do_expediente(c):
    # MEDIA = 600 min úteis: seg 10:00 -> 18:00 (480) + 120 na terça
    assert c.prazo(abrir(c, "MEDIA", t(15, 10))) == t(16, 11)


def test_prazo_atravessa_o_fim_de_semana(c):
    # sexta 17:00 + 120 úteis: 60 até 18:00, 60 na segunda
    assert c.prazo(abrir(c, em=t(19, 17))) == t(22, 10)


def test_abertura_fora_do_expediente_comeca_no_proximo_util(c):
    assert c.prazo(abrir(c, em=t(20, 10))) == t(22, 11)   # sábado -> segunda 09:00 + 120


def test_abertura_antes_da_abertura_do_dia(c):
    assert c.prazo(abrir(c, em=t(15, 7))) == t(15, 11)


def test_sla_corrido_ignora_o_expediente(c):
    assert c.prazo(abrir(c, "BAIXA", t(19, 17))) == t(19, 21)


# ------------------------------------------------------------- G-03 Regra de Ouro

def test_severidade_sem_sla_configurado():
    cc = CentralChamados()
    cc.configurar_sla("CRITICA", 120, True)
    with pytest.raises(ErroChamado) as e:
        abrir(cc, "ALTA")
    assert e.value.code == "DADOS_INVALIDOS"


# --------------------------------------------------------- G-04/G-05 fila

def test_severidade_ordena_a_fila(c):
    b = abrir(c, "BAIXA", t(15, 9))
    a = abrir(c, "ALTA", t(15, 9))
    x = abrir(c, "CRITICA", t(15, 9))
    ids = [i["chamado_id"] for i in c.fila(t(15, 10))]
    assert ids == [x, a, b]


def test_estourado_sobe_dentro_da_severidade(c):
    novo = abrir(c, "CRITICA", t(15, 14))          # prazo 16:00
    velho = abrir(c, "CRITICA", t(15, 9))          # prazo 11:00 -> estourado
    ids = [i["chamado_id"] for i in c.fila(t(15, 15))]
    assert ids == [velho, novo]


def test_estourado_nao_ultrapassa_severidade_maior(c):
    velho = abrir(c, "ALTA", t(15, 9))
    nova = abrir(c, "CRITICA", t(17, 9))
    ids = [i["chamado_id"] for i in c.fila(t(17, 10))]
    assert ids == [nova, velho]


def test_fifo_desempata_prazos_iguais(c):
    p = abrir(c, "CRITICA", t(15, 10))
    s = abrir(c, "CRITICA", t(15, 10))
    ids = [i["chamado_id"] for i in c.fila(t(15, 11))]
    assert ids == [p, s]


def test_estourado_no_instante_exato_do_prazo(c):
    cid = abrir(c, em=t(15, 10))                   # prazo 12:00
    assert c.fila(t(15, 12))[0]["estourado"] is False
    assert c.fila(t(15, 12, 1))[0]["estourado"] is True


def test_fila_expoe_as_chaves_do_contrato(c):
    abrir(c)
    item = c.fila(t(15, 11))[0]
    assert set(item) == {"chamado_id", "severidade", "situacao", "prazo", "estourado"}


# ---------------------------------------------------------- G-06/G-07 escopo

def test_pausado_e_resolvido_ficam_fora_da_fila(c):
    p = abrir(c, em=t(15, 10))
    r = abrir(c, em=t(15, 10))
    fica = abrir(c, em=t(15, 10))
    c.pausar(p, "aguardando cliente", t(15, 11))
    c.resolver(r, t(15, 11))
    assert [i["chamado_id"] for i in c.fila(t(15, 12))] == [fica]


def test_proximo_devolve_o_topo(c):
    abrir(c, "BAIXA", t(15, 9))
    x = abrir(c, "CRITICA", t(15, 9))
    assert c.proximo(t(15, 10)) == x


def test_proximo_com_fila_vazia(c):
    with pytest.raises(ErroChamado) as e:
        c.proximo(t(15, 10))
    assert e.value.code == "FILA_VAZIA"


def test_fila_vazia_nao_e_erro(c):
    assert c.fila(t(15, 10)) == []


# --------------------------------------------------------- G-08/G-09 pausa

def test_pausa_empurra_o_prazo(c):
    cid = abrir(c, em=t(15, 10))                   # prazo 12:00
    c.pausar(cid, "cliente", t(15, 11))
    c.retomar(cid, t(15, 15))                      # 4 h úteis pausado
    assert c.prazo(cid) == t(15, 16)


def test_pausa_atravessando_a_noite_conta_so_tempo_util(c):
    cid = abrir(c, "MEDIA", t(15, 10))             # prazo terça 11:00
    c.pausar(cid, "cliente", t(15, 17))            # 1 h útil na segunda
    c.retomar(cid, t(16, 10))                      # + 1 h útil na terça = 2 h
    assert c.prazo(cid) == t(16, 13)


def test_pausar_duas_vezes(c):
    cid = abrir(c, em=t(15, 10))
    c.pausar(cid, "cliente", t(15, 11))
    with pytest.raises(ErroChamado) as e:
        c.pausar(cid, "cliente", t(15, 12))
    assert e.value.code == "ESTADO_INVALIDO"


def test_pausa_sem_motivo(c):
    cid = abrir(c, em=t(15, 10))
    with pytest.raises(ErroChamado) as e:
        c.pausar(cid, "", t(15, 11))
    assert e.value.code == "DADOS_INVALIDOS"


def test_retomar_devolve_a_situacao_anterior(c):
    cid = abrir(c, em=t(15, 10))
    c.atribuir(cid, "joana", t(15, 10, 30))
    c.pausar(cid, "cliente", t(15, 11))
    c.retomar(cid, t(15, 12))
    assert c.fila(t(15, 12))[0]["situacao"] == "ATRIBUIDO"


def test_retomar_sem_estar_pausado(c):
    cid = abrir(c, em=t(15, 10))
    with pytest.raises(ErroChamado) as e:
        c.retomar(cid, t(15, 11))
    assert e.value.code == "ESTADO_INVALIDO"


# ------------------------------------------------------------ G-10 atribuição

def test_atribuicao_muda_a_situacao(c):
    cid = abrir(c, em=t(15, 10))
    c.atribuir(cid, "joana", t(15, 11))
    assert c.fila(t(15, 11))[0]["situacao"] == "ATRIBUIDO"


def test_reatribuicao_e_permitida(c):
    cid = abrir(c, em=t(15, 10))
    c.atribuir(cid, "joana", t(15, 11))
    c.atribuir(cid, "pedro", t(15, 11, 30))
    assert c.fila(t(15, 12))[0]["situacao"] == "ATRIBUIDO"


def test_atendente_vazio(c):
    cid = abrir(c, em=t(15, 10))
    with pytest.raises(ErroChamado) as e:
        c.atribuir(cid, "", t(15, 11))
    assert e.value.code == "ATRIBUICAO_INVALIDA"


def test_atribuir_chamado_pausado(c):
    cid = abrir(c, em=t(15, 10))
    c.pausar(cid, "cliente", t(15, 11))
    with pytest.raises(ErroChamado) as e:
        c.atribuir(cid, "joana", t(15, 12))
    assert e.value.code == "ESTADO_INVALIDO"


# -------------------------------------------------------- G-11/G-13 resolução

def test_tempo_util_e_cumprimento_do_sla(c):
    cid = abrir(c, em=t(15, 10))
    r = c.resolver(cid, t(15, 11, 30))
    assert r == {"cumpriu_sla": True, "tempo_util_min": 90}


def test_tempo_util_desconta_a_pausa(c):
    cid = abrir(c, em=t(15, 10))
    c.pausar(cid, "cliente", t(15, 10, 30))
    c.retomar(cid, t(15, 15))
    r = c.resolver(cid, t(15, 15, 30))
    assert r["tempo_util_min"] == 60
    assert r["cumpriu_sla"] is True


def test_tempo_util_ignora_a_madrugada(c):
    cid = abrir(c, "MEDIA", t(15, 17))
    r = c.resolver(cid, t(16, 10))
    assert r["tempo_util_min"] == 120          # 1 h na segunda + 1 h na terça


def test_sla_descumprido(c):
    cid = abrir(c, em=t(15, 10))
    assert c.resolver(cid, t(15, 14))["cumpriu_sla"] is False


def test_sla_corrido_conta_tempo_corrido(c):
    cid = abrir(c, "BAIXA", t(19, 17))
    assert c.resolver(cid, t(19, 19))["tempo_util_min"] == 120


def test_resolver_duas_vezes(c):
    cid = abrir(c, em=t(15, 10))
    c.resolver(cid, t(15, 11))
    with pytest.raises(ErroChamado) as e:
        c.resolver(cid, t(15, 12))
    assert e.value.code == "ESTADO_INVALIDO"


def test_resolver_pausado(c):
    cid = abrir(c, em=t(15, 10))
    c.pausar(cid, "cliente", t(15, 11))
    with pytest.raises(ErroChamado) as e:
        c.resolver(cid, t(15, 12))
    assert e.value.code == "ESTADO_INVALIDO"


# ------------------------------------------------------------ G-12 reabertura

def test_reabertura_preserva_o_tempo_consumido(c):
    cid = abrir(c, "MEDIA", t(15, 10))
    c.resolver(cid, t(15, 12))                 # 120 min consumidos
    c.reabrir(cid, t(15, 15))
    assert c.resolver(cid, t(15, 16))["tempo_util_min"] == 180


def test_reabertura_empurra_o_prazo_pelo_tempo_resolvido(c):
    cid = abrir(c, "MEDIA", t(15, 10))         # prazo terça 11:00
    c.resolver(cid, t(15, 12))
    c.reabrir(cid, t(15, 15))                  # 3 h úteis resolvido
    assert c.prazo(cid) == t(16, 14)


def test_reabertura_volta_para_a_fila(c):
    cid = abrir(c, em=t(15, 10))
    c.resolver(cid, t(15, 11))
    c.reabrir(cid, t(15, 12))
    assert [i["situacao"] for i in c.fila(t(15, 12))] == ["REABERTO"]


def test_reabrir_chamado_nao_resolvido(c):
    cid = abrir(c, em=t(15, 10))
    with pytest.raises(ErroChamado) as e:
        c.reabrir(cid, t(15, 11))
    assert e.value.code == "ESTADO_INVALIDO"


# ------------------------------------------------ G-14/G-15/G-16 dados e refs

@pytest.mark.parametrize("kw", [
    {"cliente": ""}, {"assunto": ""}, {"sev": "URGENTE"},
])
def test_dados_invalidos(c, kw):
    with pytest.raises(ErroChamado) as e:
        abrir(c, **kw)
    assert e.value.code == "DADOS_INVALIDOS"


def test_aberto_em_naive(c):
    with pytest.raises(ErroChamado) as e:
        c.abrir({"cliente": "x", "severidade": "CRITICA", "assunto": "a",
                 "aberto_em": datetime(2026, 6, 15, 10, 0)})
    assert e.value.code == "DADOS_INVALIDOS"


@pytest.mark.parametrize("sev,minutos", [("CRITICA", 0), ("CRITICA", -1), ("URGENTE", 60)])
def test_politica_invalida(c, sev, minutos):
    with pytest.raises(ErroChamado) as e:
        c.configurar_sla(sev, minutos, True)
    assert e.value.code == "POLITICA_INVALIDA"


def test_reconfiguracao_nao_afeta_chamados_existentes(c):
    cid = abrir(c, em=t(15, 10))
    c.configurar_sla("CRITICA", 600, True)
    assert c.prazo(cid) == t(15, 12)
    novo = abrir(c, em=t(15, 10))
    assert c.prazo(novo) == t(16, 11)


def test_chamado_inexistente(c):
    with pytest.raises(ErroChamado) as e:
        c.prazo("fantasma")
    assert e.value.code == "CHAMADO_NAO_ENCONTRADO"


def test_inexistente_precede_estado(c):
    with pytest.raises(ErroChamado) as e:
        c.retomar("fantasma", t(15, 11))
    assert e.value.code == "CHAMADO_NAO_ENCONTRADO"
