"""Smoke tests visíveis do UC-10 — cobrem só o contrato sintático."""

from datetime import date
from decimal import Decimal

import pytest

from solucao import ErroConciliacao, MotorConciliacao

DIA = date(2026, 6, 15)
INTERNA = {"transacao_id": "T1", "valor": "100.00", "data": DIA, "status": "APROVADA"}
EXTRATO = {"transacao_id": "T1", "valor_bruto": "100.00", "taxa": "2.00",
           "data": DIA, "tipo": "VENDA"}


def test_conciliar_retorna_as_chaves_do_contrato():
    m = MotorConciliacao()
    assert m.carregar_internas([dict(INTERNA)]) == 1
    assert m.carregar_extrato([dict(EXTRATO)]) == 1
    r = m.conciliar(date(2026, 6, 30))
    assert set(r) == {"conciliadas", "divergentes", "duplicadas",
                      "somente_interna", "somente_extrato", "total_liquido"}
    assert isinstance(r["total_liquido"], Decimal)


def test_itens_e_relatorio_respeitam_o_contrato():
    m = MotorConciliacao()
    m.carregar_internas([dict(INTERNA)])
    m.carregar_extrato([dict(EXTRATO)])
    m.conciliar(date(2026, 6, 30))
    itens = m.itens("CONCILIADA")
    assert all(set(i) == {"transacao_id", "categoria", "motivo", "valor_interno",
                          "valor_extrato", "resolvida"} for i in itens)
    rel = m.relatorio()
    assert set(rel) == {"por_categoria", "pendentes", "resolvidas", "total_liquido"}


def test_erro_expoe_code_do_vocabulario():
    with pytest.raises(ErroConciliacao) as e:
        MotorConciliacao().relatorio()
    assert e.value.code in {"REGISTRO_INVALIDO", "TRANSACAO_NAO_ENCONTRADA",
                            "ESTADO_INVALIDO", "CONCILIACAO_NAO_EXECUTADA",
                            "CATEGORIA_INVALIDA"}
