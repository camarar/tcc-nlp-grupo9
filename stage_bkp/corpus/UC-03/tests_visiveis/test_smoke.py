from decimal import Decimal

import pytest

from solucao import ErroCupom, calcular_total


def test_sem_cupom():
    assert calcular_total("100.00", [], frete="10") == Decimal("110.00")


def test_percentual_simples():
    cupons = [{"tipo": "percentual", "valor": "0.10", "stackable": False, "expirado": False}]
    assert calcular_total("200.00", cupons, frete="0") == Decimal("180.00")
