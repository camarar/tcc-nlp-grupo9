"""Smoke tests visíveis do UC-03 — cobrem só o contrato sintático."""

from datetime import date
from decimal import Decimal

import pytest

from solucao import ErroPrecificacao, MotorPrecificacao

PEDIDO = {"itens": [{"sku": "A", "categoria": "livros",
                     "preco_unitario": "100.00", "quantidade": 1}],
          "frete": "20.00"}


def test_cotar_retorna_as_chaves_do_contrato():
    r = MotorPrecificacao().cotar(PEDIDO, [], date(2026, 6, 15))
    assert set(r) == {"subtotal", "desconto_campanhas", "desconto_cupons",
                      "desconto_total", "frete", "total", "itens"}
    assert set(r["itens"][0]) == {"sku", "preco_bruto", "desconto_rateado", "preco_liquido"}
    assert isinstance(r["total"], Decimal)


def test_registros_e_trilha_respeitam_o_contrato():
    m = MotorPrecificacao()
    m.registrar_campanha({"nome": "P1", "categoria": "livros", "percentual": "0.10",
                          "inicio": date(2026, 1, 1), "fim": date(2026, 12, 31)})
    m.registrar_cupom({"codigo": "C1", "tipo": "PERCENTUAL", "valor": "0.10",
                       "acumulavel": True, "validade": date(2026, 12, 31),
                       "pedido_minimo": None, "categorias": None})
    t = m.explicar(PEDIDO, ["C1"], date(2026, 6, 15))
    assert isinstance(t, list)
    assert all(set(x) == {"origem", "referencia", "base", "valor"} for x in t)


def test_erro_expoe_code_do_vocabulario():
    with pytest.raises(ErroPrecificacao) as e:
        MotorPrecificacao().cotar(PEDIDO, ["INEXISTENTE"], date(2026, 6, 15))
    assert e.value.code in {"CUPOM_INVALIDO", "CUPOM_EXPIRADO", "PEDIDO_MINIMO",
                            "CUPOM_NAO_ACUMULAVEL", "ITEM_INVALIDO", "CAMPANHA_INVALIDA"}
