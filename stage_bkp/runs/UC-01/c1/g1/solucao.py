import decimal
from decimal import Decimal, ROUND_HALF_UP


def calcular_juros_compostos(principal, taxa_anual, meses):
    principal = Decimal(str(principal))
    taxa_anual = Decimal(str(taxa_anual))
    taxa_mensal = taxa_anual / Decimal(12)
    montante = principal * (Decimal(1) + taxa_mensal) ** meses
    return montante.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
