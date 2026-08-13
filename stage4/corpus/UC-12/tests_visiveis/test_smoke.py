"""Smoke tests visíveis do UC-12 — cobrem só o contrato sintático."""

from decimal import Decimal

import pytest

from solucao import ErroCambio, ServicoCambio

TAXAS = {"USD/BRL": Decimal("5.00")}


def montar():
    s = ServicoCambio(lambda par: TAXAS[par], relogio=lambda: 1000.0)
    s.registrar_moeda("USD", 2)
    s.registrar_moeda("BRL", 2)
    return s


def test_converter_retorna_as_chaves_do_contrato():
    r = montar().converter("100", "USD", "BRL")
    assert set(r) == {"valor_convertido", "taxa", "stale", "idade_s"}
    assert isinstance(r["valor_convertido"], Decimal) and isinstance(r["taxa"], Decimal)
    assert isinstance(r["stale"], bool) and isinstance(r["idade_s"], float)


def test_cotacao_estado_e_estatisticas_respeitam_o_contrato():
    s = montar()
    c = s.cotacao("USD", "BRL")
    assert set(c) == {"taxa", "stale", "idade_s"}
    assert s.estado_circuito() in {"FECHADO", "ABERTO", "MEIO_ABERTO"}
    assert set(s.estatisticas()) == {"chamadas_provedor", "acertos_cache",
                                     "falhas_consecutivas", "usos_stale"}


def test_erro_expoe_code_do_vocabulario():
    with pytest.raises(ErroCambio) as e:
        montar().converter("1", "USD", "XYZ")
    assert e.value.code in {"MOEDA_NAO_SUPORTADA", "COTACAO_INDISPONIVEL",
                            "PROVEDOR_INDISPONIVEL", "VALOR_INVALIDO",
                            "CONFIGURACAO_INVALIDA"}
