from decimal import Decimal
import pytest
from solucao import calcular_juros_compostos

def test_valor_composto_12_meses():
    assert calcular_juros_compostos("1000", "0.12", 12) == Decimal("1126.83")

def test_taxa_zero_devolve_principal():
    assert calcular_juros_compostos("1000", "0", 12) == Decimal("1000.00")

def test_um_mes():
    assert calcular_juros_compostos("100", "0.06", 1) == Decimal("100.50")

def test_arredondamento_half_even():
    # 10 * (1 + 0.054/12) = 10.045 -> half-even 2 casas = 10.04 (half-up daria 10.05)
    assert calcular_juros_compostos("10", "0.054", 1) == Decimal("10.04")

def test_duas_casas_no_resultado():
    r = calcular_juros_compostos("1234.56", "0.1", 7)
    assert r == r.quantize(Decimal("0.01"))

def test_principal_negativo():
    with pytest.raises(ValueError):
        calcular_juros_compostos("-1", "0.1", 1)

def test_taxa_negativa():
    with pytest.raises(ValueError):
        calcular_juros_compostos("100", "-0.1", 1)

def test_periodo_zero():
    with pytest.raises(ValueError):
        calcular_juros_compostos("100", "0.1", 0)

def test_precisao_horizonte_longo():
    # horizonte longo com dizima na taxa mensal (0.1/12): precisao Decimal
    r = calcular_juros_compostos("30000", "0.1", 24)
    assert r == Decimal("36611.73")
