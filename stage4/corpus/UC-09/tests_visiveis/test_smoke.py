"""Smoke tests visíveis do UC-09 — cobrem só o contrato sintático."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from solucao import CentralChamados, ErroChamado

TZ = ZoneInfo("America/Sao_Paulo")


def montar():
    c = CentralChamados()
    c.configurar_sla("CRITICA", 120, True)
    return c


def test_abrir_e_consultar_a_fila_respeitam_o_contrato():
    c = montar()
    cid = c.abrir({"cliente": "cli", "severidade": "CRITICA", "assunto": "a",
                   "aberto_em": datetime(2026, 6, 15, 10, 0, tzinfo=TZ)})
    item = c.fila(datetime(2026, 6, 15, 11, 0, tzinfo=TZ))[0]
    assert set(item) == {"chamado_id", "severidade", "situacao", "prazo", "estourado"}
    assert item["chamado_id"] == cid
    assert item["situacao"] in {"ABERTO", "ATRIBUIDO", "PAUSADO", "RESOLVIDO", "REABERTO"}
    assert isinstance(item["estourado"], bool)
    assert isinstance(c.prazo(cid), datetime)
    assert c.proximo(datetime(2026, 6, 15, 11, 0, tzinfo=TZ)) == cid


def test_resolver_retorna_o_dicionario_do_contrato():
    c = montar()
    cid = c.abrir({"cliente": "cli", "severidade": "CRITICA", "assunto": "a",
                   "aberto_em": datetime(2026, 6, 15, 10, 0, tzinfo=TZ)})
    c.atribuir(cid, "joana", datetime(2026, 6, 15, 10, 30, tzinfo=TZ))
    r = c.resolver(cid, datetime(2026, 6, 15, 11, 0, tzinfo=TZ))
    assert set(r) == {"cumpriu_sla", "tempo_util_min"}
    assert isinstance(r["cumpriu_sla"], bool) and isinstance(r["tempo_util_min"], int)


def test_erro_expoe_code_do_vocabulario():
    with pytest.raises(ErroChamado) as e:
        montar().prazo("inexistente")
    assert e.value.code in {"CHAMADO_NAO_ENCONTRADO", "ESTADO_INVALIDO",
                            "DADOS_INVALIDOS", "POLITICA_INVALIDA",
                            "FILA_VAZIA", "ATRIBUICAO_INVALIDA"}
