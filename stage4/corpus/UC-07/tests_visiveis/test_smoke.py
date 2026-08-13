"""Smoke tests visíveis do UC-07 — cobrem só o contrato sintático."""

from decimal import Decimal

import pytest

from solucao import ErroFrete, MotorFrete

CFG = {"faixas": [{"ate_kg": "1", "preco": "10.00", "prazo_dias": 1},
                  {"ate_kg": "30", "preco": "50.00", "prazo_dias": 3}],
       "regioes": ["SP"], "fator_cubagem": 6000,
       "peso_maximo_kg": "30", "ad_valorem": None}

PEDIDO = {"uf_destino": "SP", "cep_destino": "01001000",
          "itens": [{"peso_kg": "2", "altura_cm": "20", "largura_cm": "20",
                     "comprimento_cm": "20", "quantidade": 1, "valor": "100.00"}]}


def test_cotar_retorna_as_chaves_do_contrato():
    m = MotorFrete()
    m.registrar_transportadora("r", dict(CFG))
    c = m.cotar(PEDIDO)
    assert isinstance(c, list)
    assert set(c[0]) == {"transportadora", "peso_cobrado_kg", "frete",
                         "seguro", "prazo_dias", "total"}
    assert isinstance(c[0]["total"], Decimal) and isinstance(c[0]["prazo_dias"], int)


def test_melhor_cotacao_devolve_um_item_do_mesmo_formato():
    m = MotorFrete()
    m.registrar_transportadora("r", dict(CFG))
    b = m.melhor_cotacao(PEDIDO, "PRECO")
    assert set(b) == {"transportadora", "peso_cobrado_kg", "frete",
                      "seguro", "prazo_dias", "total"}


def test_erro_expoe_code_do_vocabulario():
    m = MotorFrete()
    m.registrar_transportadora("r", dict(CFG))
    with pytest.raises(ErroFrete) as e:
        m.registrar_restricao("inexistente", "010")
    assert e.value.code in {"REGIAO_NAO_ATENDIDA", "TRANSPORTADORA_DESCONHECIDA",
                            "DIMENSOES_INVALIDAS", "TABELA_INVALIDA",
                            "PEDIDO_INVALIDO", "SEM_COTACAO"}
