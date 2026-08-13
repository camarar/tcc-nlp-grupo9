"""Suíte cega UC-06 — agenda clínica com múltiplos recursos."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from solucao import Agenda, ErroAgenda

TZ = ZoneInfo("America/Sao_Paulo")
# 2026-06-15 é uma segunda-feira
SEG = date(2026, 6, 15)
SAB = date(2026, 6, 20)


def dt(h, mi=0, dia=SEG):
    return datetime(dia.year, dia.month, dia.day, h, mi, tzinfo=TZ)


@pytest.fixture
def a():
    ag = Agenda()
    janela = {"inicio": time(8, 0), "fim": time(18, 0), "dias": [0, 1, 2, 3, 4]}
    ag.registrar_recurso("dr", "PROFISSIONAL", janela)
    ag.registrar_recurso("dr2", "PROFISSIONAL", janela)
    ag.registrar_recurso("s1", "SALA", janela)
    ag.registrar_recurso("s2", "SALA", janela)
    ag.registrar_recurso("eq", "EQUIPAMENTO", janela)
    return ag


def agendar(ag, **kw):
    dados = {"paciente": "p", "profissional": "dr", "sala": "s1",
             "equipamento": None, "inicio": dt(9), "duracao_min": None}
    dados.update(kw)
    return ag.agendar(dados)


# ------------------------------------------------------- G-01/G-02 intervalos

def test_adjacente_nao_conflita(a):
    agendar(a, inicio=dt(9))                     # 09:00-09:30
    assert agendar(a, inicio=dt(9, 30))          # 09:30-10:00


def test_sobreposicao_parcial_conflita(a):
    agendar(a, inicio=dt(9))
    with pytest.raises(ErroAgenda) as e:
        agendar(a, inicio=dt(9, 15))
    assert e.value.code == "HORARIO_INDISPONIVEL"


def test_duracao_padrao_de_trinta_minutos(a):
    aid = agendar(a, inicio=dt(9))
    item = a.agenda_do_dia("dr", SEG)[0]
    assert item["fim"] - item["inicio"] == timedelta(minutes=30)
    assert item["agendamento_id"] == aid


def test_duracao_customizada_respeitada(a):
    agendar(a, inicio=dt(9), duracao_min=45)
    item = a.agenda_do_dia("dr", SEG)[0]
    assert item["fim"] - item["inicio"] == timedelta(minutes=45)


@pytest.mark.parametrize("d", [0, -30, 17])
def test_duracao_invalida(a, d):
    with pytest.raises(ErroAgenda) as e:
        agendar(a, duracao_min=d)
    assert e.value.code == "DADOS_INVALIDOS"


# ------------------------------------------------------------ G-03 fuso horário

def test_datetime_naive_recusado(a):
    with pytest.raises(ErroAgenda) as e:
        agendar(a, inicio=datetime(2026, 6, 15, 9, 0))
    assert e.value.code == "DADOS_INVALIDOS"


def test_mesmo_instante_em_outro_fuso_conflita(a):
    agendar(a, inicio=dt(9))
    equivalente = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)  # 09:00 em SP
    with pytest.raises(ErroAgenda) as e:
        agendar(a, inicio=equivalente)
    assert e.value.code == "HORARIO_INDISPONIVEL"


def test_saida_no_fuso_da_clinica(a):
    agendar(a, inicio=datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc))
    item = a.agenda_do_dia("dr", SEG)[0]
    assert item["inicio"].utcoffset() == timedelta(hours=-3)
    assert item["inicio"].hour == 9


# -------------------------------------------------- G-04 conflito multi-recurso

def test_sala_ocupada_por_outro_profissional(a):
    agendar(a, inicio=dt(9))
    with pytest.raises(ErroAgenda) as e:
        agendar(a, profissional="dr2", sala="s1", inicio=dt(9))
    assert e.value.code == "HORARIO_INDISPONIVEL"


def test_troca_de_sala_libera_o_horario(a):
    agendar(a, inicio=dt(9))
    assert agendar(a, profissional="dr2", sala="s2", inicio=dt(9))


def test_equipamento_compartilhado_conflita(a):
    agendar(a, inicio=dt(9), equipamento="eq")
    with pytest.raises(ErroAgenda) as e:
        agendar(a, profissional="dr2", sala="s2", inicio=dt(9), equipamento="eq")
    assert e.value.code == "HORARIO_INDISPONIVEL"


def test_cancelado_libera_o_recurso(a):
    aid = agendar(a, inicio=dt(9))
    a.cancelar(aid, dt(8))
    assert agendar(a, inicio=dt(9))


def test_falta_libera_o_recurso(a):
    aid = agendar(a, inicio=dt(9))
    a.registrar_comparecimento(aid, False, dt(9, 5))
    assert agendar(a, inicio=dt(9))


def test_realizado_continua_ocupando(a):
    aid = agendar(a, inicio=dt(9))
    a.registrar_comparecimento(aid, True, dt(9, 5))
    with pytest.raises(ErroAgenda) as e:
        agendar(a, inicio=dt(9))
    assert e.value.code == "HORARIO_INDISPONIVEL"


# ------------------------------------------------------------ G-05 janela

def test_fim_exatamente_no_limite_da_janela(a):
    assert agendar(a, inicio=dt(17, 30))         # 17:30-18:00


def test_ultrapassar_o_fim_da_janela(a):
    with pytest.raises(ErroAgenda) as e:
        agendar(a, inicio=dt(17, 45))            # 17:45-18:15
    assert e.value.code == "FORA_DA_JANELA"


def test_antes_do_inicio_da_janela(a):
    with pytest.raises(ErroAgenda) as e:
        agendar(a, inicio=dt(7, 30))
    assert e.value.code == "FORA_DA_JANELA"


def test_dia_nao_atendido(a):
    with pytest.raises(ErroAgenda) as e:
        agendar(a, inicio=dt(9, 0, SAB))
    assert e.value.code == "FORA_DA_JANELA"


def test_janela_mais_estreita_de_um_recurso_prevalece(a):
    a.registrar_recurso("s3", "SALA",
                        {"inicio": time(8, 0), "fim": time(10, 0), "dias": [0]})
    assert agendar(a, sala="s3", inicio=dt(9, 30))
    with pytest.raises(ErroAgenda) as e:
        agendar(a, sala="s3", inicio=dt(10, 0))
    assert e.value.code == "FORA_DA_JANELA"


# ------------------------------------------------- G-06/G-07 recursos e ordem

@pytest.mark.parametrize("kw", [
    {"profissional": "fantasma"}, {"sala": "fantasma"}, {"equipamento": "fantasma"},
])
def test_recurso_desconhecido(a, kw):
    with pytest.raises(ErroAgenda) as e:
        agendar(a, **kw)
    assert e.value.code == "RECURSO_DESCONHECIDO"


def test_papel_trocado_e_recurso_desconhecido(a):
    with pytest.raises(ErroAgenda) as e:
        agendar(a, profissional="s1")
    assert e.value.code == "RECURSO_DESCONHECIDO"


def test_dados_precedem_recurso(a):
    with pytest.raises(ErroAgenda) as e:
        agendar(a, profissional="fantasma", duracao_min=0)
    assert e.value.code == "DADOS_INVALIDOS"


def test_recurso_precede_janela(a):
    with pytest.raises(ErroAgenda) as e:
        agendar(a, profissional="fantasma", inicio=dt(3))
    assert e.value.code == "RECURSO_DESCONHECIDO"


def test_janela_precede_conflito(a):
    agendar(a, inicio=dt(17, 30))
    with pytest.raises(ErroAgenda) as e:
        agendar(a, inicio=dt(17, 45))
    assert e.value.code == "FORA_DA_JANELA"


# -------------------------------------------------------- G-08 cancelamento

def test_cancelamento_com_mais_de_24h_nao_gera_multa(a):
    aid = agendar(a, inicio=dt(9))
    r = a.cancelar(aid, dt(9) - timedelta(hours=25))
    assert r == {"multa": False, "situacao": "CANCELADO"}


def test_exatamente_24h_antes_nao_gera_multa(a):
    aid = agendar(a, inicio=dt(9))
    assert a.cancelar(aid, dt(9) - timedelta(hours=24))["multa"] is False


def test_menos_de_24h_gera_multa(a):
    aid = agendar(a, inicio=dt(9))
    assert a.cancelar(aid, dt(9) - timedelta(hours=23, minutes=59))["multa"] is True


def test_cancelamento_apos_o_inicio_gera_multa(a):
    aid = agendar(a, inicio=dt(9))
    assert a.cancelar(aid, dt(10))["multa"] is True


# --------------------------------------------------------- G-09 estados

@pytest.mark.parametrize("op", ["cancelar", "remarcar", "comparecimento"])
def test_estado_terminal_recusa_operacoes(a, op):
    aid = agendar(a, inicio=dt(9))
    a.cancelar(aid, dt(8))
    with pytest.raises(ErroAgenda) as e:
        if op == "cancelar":
            a.cancelar(aid, dt(8))
        elif op == "remarcar":
            a.remarcar(aid, dt(11))
        else:
            a.registrar_comparecimento(aid, True, dt(9, 5))
    assert e.value.code == "ESTADO_INVALIDO"


# ------------------------------------------------------- G-10 remarcação

def test_remarcacao_cria_novo_agendamento(a):
    aid = agendar(a, inicio=dt(9))
    novo = a.remarcar(aid, dt(11))
    assert novo != aid
    sit = {x["agendamento_id"]: x["situacao"] for x in a.agenda_do_dia("dr", SEG)}
    assert sit[aid] == "REMARCADO" and sit[novo] == "AGENDADO"


def test_remarcacao_preserva_paciente_e_recursos(a):
    aid = agendar(a, paciente="ana", equipamento="eq", inicio=dt(9))
    novo = a.remarcar(aid, dt(11))
    item = [x for x in a.agenda_do_dia("dr", SEG) if x["agendamento_id"] == novo][0]
    assert item["paciente"] == "ana"
    with pytest.raises(ErroAgenda):        # o equipamento continua ocupado às 11h
        agendar(a, profissional="dr2", sala="s2", inicio=dt(11), equipamento="eq")


def test_remarcacao_para_horario_sobreposto_ao_proprio(a):
    aid = agendar(a, inicio=dt(9))
    assert a.remarcar(aid, dt(9, 15))


def test_remarcacao_invalida_nao_altera_o_original(a):
    aid = agendar(a, inicio=dt(9))
    with pytest.raises(ErroAgenda):
        a.remarcar(aid, dt(3))
    assert a.agenda_do_dia("dr", SEG)[0]["situacao"] == "AGENDADO"
    with pytest.raises(ErroAgenda) as e:
        agendar(a, inicio=dt(9))
    assert e.value.code == "HORARIO_INDISPONIVEL"


# ---------------------------------------------------- G-11 comparecimento

def test_comparecimento_define_a_situacao(a):
    aid = agendar(a, inicio=dt(9))
    assert a.registrar_comparecimento(aid, True, dt(9)) == "REALIZADO"


def test_falta_define_a_situacao(a):
    aid = agendar(a, inicio=dt(9))
    assert a.registrar_comparecimento(aid, False, dt(9, 30)) == "FALTA"


def test_comparecimento_antes_do_inicio_e_recusado(a):
    aid = agendar(a, inicio=dt(9))
    with pytest.raises(ErroAgenda) as e:
        a.registrar_comparecimento(aid, True, dt(8, 59))
    assert e.value.code == "ESTADO_INVALIDO"


# ------------------------------------------------------ G-12 disponibilidade

def test_disponibilidade_da_agenda_vazia_e_a_janela_inteira(a):
    livres = a.disponibilidade("dr", SEG)
    assert len(livres) == 1
    assert livres[0]["inicio"] == dt(8) and livres[0]["fim"] == dt(18)


def test_disponibilidade_desconta_o_agendamento(a):
    agendar(a, inicio=dt(9))
    livres = a.disponibilidade("dr", SEG)
    assert [(b["inicio"], b["fim"]) for b in livres] == [
        (dt(8), dt(9)), (dt(9, 30), dt(18))]


def test_blocos_contiguos_sao_mesclados(a):
    agendar(a, inicio=dt(9))
    agendar(a, inicio=dt(9, 30))
    livres = a.disponibilidade("dr", SEG)
    assert [(b["inicio"], b["fim"]) for b in livres] == [
        (dt(8), dt(9)), (dt(10), dt(18))]


def test_bloco_de_duracao_zero_nao_aparece(a):
    agendar(a, inicio=dt(8))
    livres = a.disponibilidade("dr", SEG)
    assert [(b["inicio"], b["fim"]) for b in livres] == [(dt(8, 30), dt(18))]


def test_cancelado_devolve_o_bloco(a):
    aid = agendar(a, inicio=dt(9))
    a.cancelar(aid, dt(8))
    assert len(a.disponibilidade("dr", SEG)) == 1


def test_dia_sem_janela_nao_tem_disponibilidade(a):
    assert a.disponibilidade("dr", SAB) == []


# --------------------------------------------------------- G-13 agenda do dia

def test_agenda_do_dia_inclui_encerrados_e_ordena(a):
    a2 = agendar(a, inicio=dt(11))
    a1 = agendar(a, inicio=dt(9))
    a.cancelar(a2, dt(8))
    itens = a.agenda_do_dia("dr", SEG)
    assert [x["agendamento_id"] for x in itens] == [a1, a2]
    assert set(itens[0]) == {"agendamento_id", "inicio", "fim", "paciente", "situacao"}


def test_agenda_do_dia_filtra_pelo_dia_no_fuso_da_clinica(a):
    agendar(a, inicio=dt(9))
    assert a.agenda_do_dia("dr", date(2026, 6, 16)) == []


# --------------------------------------------- G-14/G-15/G-16 dados e refs

@pytest.mark.parametrize("campo", ["paciente", "profissional", "sala", "inicio"])
def test_campo_obrigatorio_ausente(a, campo):
    dados = {"paciente": "p", "profissional": "dr", "sala": "s1",
             "equipamento": None, "inicio": dt(9), "duracao_min": None}
    del dados[campo]
    with pytest.raises(ErroAgenda) as e:
        a.agendar(dados)
    assert e.value.code == "DADOS_INVALIDOS"


@pytest.mark.parametrize("tipo,janela", [
    ("MEDICO", {"inicio": time(8), "fim": time(18), "dias": [0]}),
    ("SALA", {"inicio": time(18), "fim": time(8), "dias": [0]}),
    ("SALA", {"inicio": time(8), "fim": time(18), "dias": []}),
    ("SALA", {"inicio": time(8), "fim": time(18), "dias": [7]}),
])
def test_registro_de_recurso_invalido(a, tipo, janela):
    with pytest.raises(ErroAgenda) as e:
        a.registrar_recurso("novo", tipo, janela)
    assert e.value.code == "DADOS_INVALIDOS"


def test_reregistro_substitui_a_janela_e_mantem_agendamentos(a):
    aid = agendar(a, inicio=dt(9))
    a.registrar_recurso("dr", "PROFISSIONAL",
                        {"inicio": time(9, 0), "fim": time(12, 0), "dias": [0]})
    assert a.agenda_do_dia("dr", SEG)[0]["agendamento_id"] == aid
    assert a.disponibilidade("dr", SEG)[0]["inicio"] == dt(9, 30)


def test_agendamento_inexistente(a):
    with pytest.raises(ErroAgenda) as e:
        a.cancelar("fantasma", dt(9))
    assert e.value.code == "AGENDAMENTO_NAO_ENCONTRADO"


def test_profissional_desconhecido_na_consulta(a):
    with pytest.raises(ErroAgenda) as e:
        a.disponibilidade("fantasma", SEG)
    assert e.value.code == "RECURSO_DESCONHECIDO"
