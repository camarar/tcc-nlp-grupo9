from decimal import Decimal
from solucao import calcular_juros_compostos

def test_caso_basico():
    # 12% a.a., capitalizacao mensal, 12 meses
    assert calcular_juros_compostos("1000", "0.12", 12) == Decimal("1126.83")

def test_retorna_decimal():
    assert isinstance(calcular_juros_compostos("100", "0.06", 1), Decimal)
