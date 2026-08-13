"""Smoke tests visíveis do UC-01 — entregues ao gerador nas duas condições.

Cobrem apenas o contrato sintático; nenhuma decisão de negócio do gabarito.
"""

from datetime import date
from decimal import Decimal

import pytest

from solucao import ErroEmprestimo, MotorEmprestimo

BASE = {
    "principal": "10000.00",
    "taxa": "0.02",
    "prazo_meses": 12,
    "sistema": "PRICE",
    "data_inicio": date(2026, 1, 15),
}


def test_cria_contrato_e_gera_cronograma_com_as_chaves_do_contrato():
    m = MotorEmprestimo()
    cid = m.criar_contrato(dict(BASE))
    cr = m.cronograma(cid)
    assert len(cr) == 12
    assert set(cr[0]) == {"numero", "vencimento", "juros",
                          "amortizacao", "valor", "saldo_apos"}
    assert isinstance(cr[0]["valor"], Decimal)


def test_valor_devido_e_pagamento_retornam_o_dicionario_do_contrato():
    m = MotorEmprestimo()
    cid = m.criar_contrato(dict(BASE))
    dev = m.valor_devido(cid, 1, date(2026, 2, 15))
    assert set(dev) == {"principal", "juros", "encargos", "total"}
    r = m.registrar_pagamento(cid, "pag-1", 1, dev["total"], date(2026, 2, 15))
    assert set(r) == {"duplicado", "aplicado_encargos", "aplicado_juros",
                      "aplicado_principal", "parcela_quitada"}


def test_erro_expoe_code_do_vocabulario():
    m = MotorEmprestimo()
    with pytest.raises(ErroEmprestimo) as e:
        m.saldo_devedor("inexistente", date(2026, 2, 1))
    assert e.value.code in {
        "CONTRATO_INVALIDO", "CONTRATO_NAO_ENCONTRADO", "ESTADO_INVALIDO",
        "VALOR_INVALIDO", "PARCELA_INVALIDA", "RENEGOCIACAO_NAO_PERMITIDA"}
