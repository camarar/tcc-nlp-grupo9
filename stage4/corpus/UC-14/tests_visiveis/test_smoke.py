"""Smoke tests visíveis do UC-14 — cobrem só o contrato sintático."""

from decimal import Decimal

import pytest

from solucao import ErroTributario, MotorTributario

CNPJ = "00000000000191"
NOTA = {"cnpj_emitente": CNPJ, "uf_destino": "SP", "frete": "0",
        "itens": [{"ncm": "12345678", "valor": "100.00",
                   "quantidade": 2, "desconto": "0"}]}


def montar():
    m = MotorTributario()
    m.registrar_regime(CNPJ, "NORMAL")
    m.registrar_aliquota("SP", "12345678", "0.18")
    return m


def test_calcular_retorna_as_chaves_do_contrato():
    r = montar().calcular(NOTA)
    assert set(r) == {"base_calculo", "icms", "icms_st",
                      "total_tributos", "total_nota"}
    assert all(isinstance(v, Decimal) for v in r.values())


def test_memoria_de_calculo_respeita_o_contrato():
    mem = montar().memoria_calculo(NOTA)
    assert isinstance(mem, list) and len(mem) == 1
    assert set(mem[0]) == {"ncm", "ncm_aplicado", "aliquota", "base",
                           "icms", "icms_st", "isento"}
    assert isinstance(mem[0]["isento"], bool)


def test_erro_expoe_code_do_vocabulario():
    m = montar()
    with pytest.raises(ErroTributario) as e:
        m.registrar_regime(CNPJ, "MEI")
    assert e.value.code in {"ALIQUOTA_NAO_CADASTRADA", "TABELA_INVALIDA",
                            "NOTA_INVALIDA", "ITEM_INVALIDO", "REGIME_DESCONHECIDO"}
