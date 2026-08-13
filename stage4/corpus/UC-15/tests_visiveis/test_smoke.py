"""Smoke tests visíveis do UC-15 — cobrem só o contrato sintático."""

from datetime import datetime, timezone

import pytest

from solucao import ErroNotificacao, Orquestrador

AGORA = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
NOTIF = {"destinatario": "cli", "mensagem": "oi", "idempotency_key": "k1",
         "urgente": False, "quando": AGORA}


def montar():
    o = Orquestrador(relogio=lambda: AGORA, dormir=lambda s: None)
    o.registrar_canal("push", lambda d, m: None, 1)
    return o


def test_enviar_retorna_as_chaves_do_contrato():
    r = montar().enviar(dict(NOTIF))
    assert set(r) == {"status", "canal", "tentativas", "duplicado"}
    assert r["status"] in {"ENTREGUE", "ADIADA", "DEAD_LETTER"}
    assert isinstance(r["tentativas"], int) and isinstance(r["duplicado"], bool)


def test_historico_e_dead_letters_respeitam_o_contrato():
    o = montar()
    o.enviar(dict(NOTIF))
    h = o.historico("k1")
    assert all(set(x) == {"em", "canal", "tentativa", "resultado", "erro"} for x in h)
    assert all(x["resultado"] in {"SUCESSO", "FALHA"} for x in h)
    assert isinstance(o.dead_letters(), list)


def test_erro_expoe_code_do_vocabulario():
    with pytest.raises(ErroNotificacao) as e:
        montar().reprocessar("inexistente")
    assert e.value.code in {"CANAL_DESCONHECIDO", "DESTINATARIO_INVALIDO",
                            "MENSAGEM_INVALIDA", "CONFIGURACAO_INVALIDA",
                            "NOTIFICACAO_NAO_ENCONTRADA", "ESTADO_INVALIDO"}
