"""Smoke tests visíveis do UC-04 — cobrem só o contrato sintático."""

import pytest

from solucao import ErroLimite, Limitador


def montar():
    lim = Limitador(relogio=lambda: 0.0)
    lim.registrar_plano("p", {"limite": 3, "janela_s": 10.0, "burst": 5})
    lim.registrar_cliente("c1", "p")
    return lim


def test_permitir_retorna_as_chaves_do_contrato():
    r = montar().permitir("c1")
    assert set(r) == {"permitido", "restante", "retry_after", "limitante"}
    assert isinstance(r["permitido"], bool) and isinstance(r["restante"], int)
    assert isinstance(r["retry_after"], float)


def test_consumo_e_redefinir_respeitam_o_contrato():
    lim = montar()
    lim.permitir("c1")
    c = lim.consumo("c1")
    assert set(c) == {"cliente", "organizacao"}
    assert lim.redefinir("c1") is None


def test_erro_expoe_code_do_vocabulario():
    with pytest.raises(ErroLimite) as e:
        montar().permitir("fantasma")
    assert e.value.code in {"PLANO_DESCONHECIDO", "CLIENTE_DESCONHECIDO",
                            "ORGANIZACAO_DESCONHECIDA", "CONFIGURACAO_INVALIDA",
                            "CUSTO_INVALIDO"}
