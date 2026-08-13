import decimal
from decimal import Decimal


def calcular_juros_compostos(principal, taxa_anual, meses) -> Decimal:
    principal = Decimal(str(principal))
    taxa_anual = Decimal(str(taxa_anual))
    meses = int(meses)

    taxa_mensal = taxa_anual / Decimal(12)
    montante = principal * (Decimal(1) + taxa_mensal) ** meses

    return montante.quantize(Decimal("0.01"), rounding=decimal.ROUND_HALF_UP)
