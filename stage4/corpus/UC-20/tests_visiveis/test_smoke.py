"""Smoke tests visíveis do UC-20 — cobrem só o contrato sintático."""

from datetime import datetime, timezone

import pytest

from solucao import ErroCredencial, GestorCredenciais

T0 = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
BOA = "Xk7#mQ2$wLp9"


def montar():
    g = GestorCredenciais(relogio=lambda: T0)
    g.definir_politica("padrao", {})
    g.criar_usuario("ana", "padrao")
    return g


def test_avaliar_devolve_lista():
    g = montar()
    v = g.avaliar("password", "padrao")
    assert isinstance(v, list) and all(isinstance(x, str) for x in v)
    assert set(v) <= {"COMPRIMENTO", "CLASSES", "COMUM", "REPETICAO", "SEQUENCIA"}


def test_definir_autenticar_e_situacao_respeitam_o_contrato():
    g = montar()
    d = g.definir_senha("ana", BOA)
    assert set(d) == {"expira_em", "trocas"}
    assert isinstance(d["expira_em"], datetime) and isinstance(d["trocas"], int)
    a = g.autenticar("ana", BOA)
    assert set(a) == {"autenticado", "expirada", "em_tolerancia", "dias_para_expirar"}
    assert isinstance(a["autenticado"], bool)
    assert set(g.situacao("ana")) == {"perfil", "definida_em", "expira_em",
                                      "trocas", "expirada", "em_tolerancia"}


def test_erro_expoe_code_do_vocabulario():
    with pytest.raises(ErroCredencial) as e:
        montar().situacao("inexistente")
    assert e.value.code in {"SENHA_FRACA", "SENHA_REUTILIZADA", "USUARIO_INVALIDO",
                            "POLITICA_INVALIDA", "ESTADO_INVALIDO"}
