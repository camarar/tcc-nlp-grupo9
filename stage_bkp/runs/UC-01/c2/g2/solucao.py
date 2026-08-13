import decimal
from decimal import Decimal, ROUND_HALF_EVEN


def _to_decimal(valor):
    try:
        if isinstance(valor, Decimal):
            return valor
        return Decimal(str(valor))
    except decimal.InvalidOperation:
        raise ValueError(f"Valor numerico invalido: {valor!r}")
    except (TypeError, AttributeError, ValueError):
        raise ValueError(f"Valor numerico invalido: {valor!r}")


def calcular_juros_compostos(principal, taxa_anual, meses):
    if not isinstance(meses, int):
        raise TypeError("meses deve ser int")
    if meses <= 0:
        raise ValueError("meses deve ser positivo")

    principal_dec = _to_decimal(principal)
    taxa_dec = _to_decimal(taxa_anual)

    if principal_dec < 0:
        raise ValueError("principal nao pode ser negativo")
    if taxa_dec < 0:
        raise ValueError("taxa_anual nao pode ser negativa")

    taxa_mensal = taxa_dec / Decimal(12)
    valor_final = principal_dec * (1 + taxa_mensal) ** meses

    return valor_final.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
