"""Smoke tests visíveis do UC-06 — cobrem só o contrato sintático."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from solucao import Agenda, ErroAgenda

TZ = ZoneInfo("America/Sao_Paulo")
SEG = date(2026, 6, 15)
JANELA = {"inicio": time(8, 0), "fim": time(18, 0), "dias": [0, 1, 2, 3, 4]}


def montar():
    a = Agenda()
    a.registrar_recurso("dr", "PROFISSIONAL", JANELA)
    a.registrar_recurso("s1", "SALA", JANELA)
    return a


def test_agendar_e_consultar_respeitam_o_contrato():
    a = montar()
    aid = a.agendar({"paciente": "p", "profissional": "dr", "sala": "s1",
                     "equipamento": None,
                     "inicio": datetime(2026, 6, 15, 9, 0, tzinfo=TZ),
                     "duracao_min": None})
    itens = a.agenda_do_dia("dr", SEG)
    assert set(itens[0]) == {"agendamento_id", "inicio", "fim", "paciente", "situacao"}
    assert itens[0]["agendamento_id"] == aid
    assert itens[0]["situacao"] in {"AGENDADO", "CANCELADO", "REMARCADO",
                                    "REALIZADO", "FALTA"}
    livres = a.disponibilidade("dr", SEG)
    assert all(set(b) == {"inicio", "fim"} for b in livres)


def test_cancelar_retorna_o_dicionario_do_contrato():
    a = montar()
    aid = a.agendar({"paciente": "p", "profissional": "dr", "sala": "s1",
                     "equipamento": None,
                     "inicio": datetime(2026, 6, 15, 9, 0, tzinfo=TZ),
                     "duracao_min": None})
    r = a.cancelar(aid, datetime(2026, 6, 14, 9, 0, tzinfo=TZ))
    assert set(r) == {"multa", "situacao"} and isinstance(r["multa"], bool)


def test_erro_expoe_code_do_vocabulario():
    with pytest.raises(ErroAgenda) as e:
        montar().cancelar("inexistente", datetime(2026, 6, 15, 9, 0, tzinfo=TZ))
    assert e.value.code in {"HORARIO_INDISPONIVEL", "FORA_DA_JANELA",
                            "RECURSO_DESCONHECIDO", "AGENDAMENTO_NAO_ENCONTRADO",
                            "ESTADO_INVALIDO", "DADOS_INVALIDOS"}
