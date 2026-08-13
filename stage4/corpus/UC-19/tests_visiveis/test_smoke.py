"""Smoke tests visíveis do UC-19 — cobrem só o contrato sintático."""

from datetime import datetime, timezone

import pytest

from solucao import ErroAuditoria, TrilhaAuditoria

T0 = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
EVENTO = {"actor_id": "u1", "action": "LOGIN", "resource": "sessao",
          "result": "SUCESSO", "payload": {"ip": "1.1.1.1"}}


def test_registrar_e_exportar_respeitam_o_contrato():
    t = TrilhaAuditoria(relogio=lambda: T0)
    h = t.registrar(dict(EVENTO))
    assert isinstance(h, str) and len(h) == 64
    reg = t.exportar()[0]
    assert set(reg) == {"indice", "timestamp_utc", "actor_id", "action",
                        "resource", "result", "payload", "hash_anterior", "hash"}
    assert reg["result"] in {"SUCESSO", "FALHA", "NEGADO"}


def test_consultar_verificar_e_expurgar_respeitam_o_contrato():
    t = TrilhaAuditoria(relogio=lambda: T0)
    t.registrar(dict(EVENTO))
    assert isinstance(t.consultar({}), list)
    v = t.verificar_integridade()
    assert set(v) == {"integra", "total", "primeiro_divergente"}
    assert isinstance(v["integra"], bool) and isinstance(v["total"], int)
    assert isinstance(t.expurgar(T0), int)


def test_erro_expoe_code_do_vocabulario():
    t = TrilhaAuditoria(relogio=lambda: T0)
    with pytest.raises(ErroAuditoria) as e:
        t.registrar({"actor_id": "u1"})
    assert e.value.code in {"REGISTRO_INVALIDO", "CONSULTA_INVALIDA",
                            "POLITICA_INVALIDA"}
