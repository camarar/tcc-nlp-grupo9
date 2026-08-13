from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN


def _to_decimal(valor):
    try:
        if isinstance(valor, Decimal):
            return valor
        return Decimal(str(valor))
    except InvalidOperation:
        raise ValueError(f"Valor numerico invalido: {valor!r}")
    except Exception:
        raise ValueError(f"Valor numerico invalido: {valor!r}")


def calcular_juros_compostos(principal, taxa_anual, meses) -> Decimal:
    if not isinstance(meses, int) or isinstance(meses, bool):
        raise TypeError("meses deve ser um int nativo")
    if meses <= 0:
        raise ValueError("meses deve ser um inteiro positivo")

    principal_dec = _to_decimal(principal)
    taxa_dec = _to_decimal(taxa_anual)

    if principal_dec < 0:
        raise ValueError("principal nao pode ser negativo")
    if taxa_dec < 0:
        raise ValueError("taxa_anual nao pode ser negativa")

    taxa_mensal = taxa_dec / Decimal(12)
    valor_final = principal_dec * (1 + taxa_mensal) ** meses

    return valor_final.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
