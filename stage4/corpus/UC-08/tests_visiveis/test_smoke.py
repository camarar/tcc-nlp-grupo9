"""Smoke tests visíveis do UC-08 — cobrem só o contrato sintático."""

from datetime import datetime, timezone

import pytest

from solucao import ControleAcesso, ErroAcesso

AGORA = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)


def test_autenticar_retorna_as_chaves_do_contrato():
    c = ControleAcesso(relogio=lambda: AGORA)
    c.registrar_usuario("ana", "hash")
    r = c.autenticar("ana", "hash", "1.1.1.1", "d1")
    assert set(r) == {"status", "sessao_id", "desafio_id", "expira_em"}
    assert r["status"] in {"AUTENTICADO", "MFA_REQUERIDO"}


def test_situacao_sessao_e_eventos_respeitam_o_contrato():
    c = ControleAcesso(relogio=lambda: AGORA)
    c.registrar_usuario("ana", "hash")
    s = c.autenticar("ana", "hash", "1.1.1.1", "d1")["sessao_id"]
    assert set(c.validar_sessao(s)) == {"login", "expira_em"}
    assert set(c.situacao("ana")) == {"bloqueado", "falhas",
                                      "bloqueado_ate", "sessoes_ativas"}
    evs = c.eventos("ana")
    assert isinstance(evs, list)
    assert all(set(e) == {"em", "tipo", "ip", "dispositivo"} for e in evs)
    assert isinstance(c.revogar_todas("ana"), int)


def test_erro_expoe_code_do_vocabulario():
    c = ControleAcesso(relogio=lambda: AGORA)
    with pytest.raises(ErroAcesso) as e:
        c.validar_sessao("inexistente")
    assert e.value.code in {"CREDENCIAL_INVALIDA", "CONTA_BLOQUEADA", "SESSAO_INVALIDA",
                            "MFA_INVALIDO", "USUARIO_INVALIDO", "POLITICA_INVALIDA"}
