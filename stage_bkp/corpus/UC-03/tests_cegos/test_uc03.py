from decimal import Decimal

import pytest

from solucao import ErroCupom, calcular_total


def test_fixo_simples():
    cupons = [{"tipo": "fixo", "valor": "15.50", "stackable": False, "expirado": False}]
    assert calcular_total("100.00", cupons) == Decimal("84.50")


def test_percentual_antes_de_fixo():
    cupons = [
        {"tipo": "percentual", "valor": "0.10", "stackable": True, "expirado": False},
        {"tipo": "fixo", "valor": "5.00", "stackable": True, "expirado": False},
    ]
    # 100 - 10% = 90; 90 - 5 = 85
    assert calcular_total("100.00", cupons) == Decimal("85.00")


def test_teto_cinquenta_porcento():
    cupons = [
        {"tipo": "percentual", "valor": "0.40", "stackable": True, "expirado": False},
        {"tipo": "fixo", "valor": "30.00", "stackable": True, "expirado": False},
    ]
    # bruto > 50% de 100; teto desconto = 50 -> total 50
    assert calcular_total("100.00", cupons) == Decimal("50.00")


def test_frete_nao_entra_na_base():
    cupons = [{"tipo": "percentual", "valor": "0.10", "stackable": False, "expirado": False}]
    assert calcular_total("100.00", cupons, frete="20.00") == Decimal("110.00")


def test_cupom_expirado():
    cupons = [{"tipo": "fixo", "valor": "10", "stackable": False, "expirado": True}]
    with pytest.raises(ErroCupom) as exc:
        calcular_total("100.00", cupons)
    assert exc.value.code == "CUPOM_EXPIRADO"


def test_pedido_minimo():
    cupons = [
        {
            "tipo": "percentual",
            "valor": "0.10",
            "stackable": False,
            "pedido_minimo": "150.00",
            "expirado": False,
        }
    ]
    with pytest.raises(ErroCupom) as exc:
        calcular_total("100.00", cupons)
    assert exc.value.code == "PEDIDO_MINIMO"


def test_nao_stackable_duplicado():
    cupons = [
        {"tipo": "fixo", "valor": "5", "stackable": False, "expirado": False},
        {"tipo": "fixo", "valor": "3", "stackable": False, "expirado": False},
    ]
    with pytest.raises(ValueError):
        calcular_total("100.00", cupons)


def test_stackable_permitido():
    cupons = [
        {"tipo": "percentual", "valor": "0.10", "stackable": True, "expirado": False},
        {"tipo": "percentual", "valor": "0.10", "stackable": True, "expirado": False},
    ]
    # 100 -> 90 -> 81
    assert calcular_total("100.00", cupons) == Decimal("81.00")


def test_retorno_decimal_duas_casas():
    cupons = [{"tipo": "percentual", "valor": "0.333", "stackable": False, "expirado": False}]
    r = calcular_total("10.00", cupons)
    assert isinstance(r, Decimal)
    assert r == r.quantize(Decimal("0.01"))
