from decimal import Decimal, ROUND_HALF_UP


def _to_decimal(valor):
    if isinstance(valor, Decimal):
        return valor
    return Decimal(str(valor))


def calcular_juros_compostos(principal, taxa_anual, meses):
    principal = _to_decimal(principal)
    taxa_anual = _to_decimal(taxa_anual)
    taxa_mensal = taxa_anual / Decimal(12)
    montante = principal * (Decimal(1) + taxa_mensal) ** int(meses)
    return montante.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
