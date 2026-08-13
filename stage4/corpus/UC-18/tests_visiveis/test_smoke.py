"""Smoke tests visíveis do UC-18 — cobrem só o contrato sintático."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from solucao import ErroPedido, Pedidos

T0 = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
DADOS = {"cliente": "ana",
         "itens": [{"item_id": "i1", "sku": "A", "preco_cheio": "100.00",
                    "combo": "C1"},
                   {"item_id": "i2", "sku": "B", "preco_cheio": "60.00",
                    "combo": "C1"},
                   {"item_id": "i3", "sku": "C", "preco_cheio": "40.00",
                    "combo": None}],
         "combos": [{"combo_id": "C1", "preco": "120.00"}]}


def test_resumo_expoe_as_chaves_do_contrato():
    p = Pedidos()
    pid = p.criar(dict(DADOS))
    r = p.resumo(pid)
    assert set(r) == {"situacao", "total", "pago", "estornado", "itens"}
    assert set(r["itens"][0]) == {"item_id", "preco", "situacao", "combo"}
    assert isinstance(r["total"], Decimal)
    assert r["situacao"] in {"CRIADO", "PAGO", "PARCIALMENTE_DESPACHADO",
                             "DESPACHADO", "CANCELADO", "CONCLUIDO"}


def test_pagar_despachar_e_cancelar_respeitam_o_contrato():
    p = Pedidos()
    pid = p.criar(dict(DADOS))
    pg = p.pagar(pid, p.resumo(pid)["total"], T0)
    assert set(pg) == {"situacao", "pago"}
    assert isinstance(p.despachar(pid, ["i3"], T0), str)
    c = p.cancelar_item(pid, "i2", T0)
    assert set(c) == {"estorno", "novo_total", "situacao"}
    h = p.historico(pid)
    assert all(set(x) == {"em", "evento", "item_id", "valor"} for x in h)


def test_erro_expoe_code_do_vocabulario():
    with pytest.raises(ErroPedido) as e:
        Pedidos().resumo("inexistente")
    assert e.value.code in {"PEDIDO_NAO_ENCONTRADO", "ITEM_INVALIDO", "ESTADO_INVALIDO",
                            "VALOR_INVALIDO", "COMBO_INVALIDO",
                            "OPERACAO_NAO_PERMITIDA"}
