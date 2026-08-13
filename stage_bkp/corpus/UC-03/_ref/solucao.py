from decimal import Decimal, ROUND_HALF_EVEN


class ErroCupom(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


def _money(value) -> Decimal:
    return Decimal(str(value))


def calcular_total(subtotal, cupons, frete="0"):
    sub = _money(subtotal)
    ship = _money(frete)
    if sub < 0 or ship < 0:
        raise ValueError("valores negativos")

    original = sub
    non_stack = sum(1 for c in cupons if not c.get("stackable", False))
    if non_stack > 1:
        raise ValueError("cupons não stackable não podem ser combinados")

    for c in cupons:
        if c.get("expirado"):
            raise ErroCupom("CUPOM_EXPIRADO")
        minimo = c.get("pedido_minimo")
        if minimo is not None and original < _money(minimo):
            raise ErroCupom("PEDIDO_MINIMO")

    remaining = sub
    discount = Decimal("0")

    for c in cupons:
        if c["tipo"] != "percentual":
            continue
        pct = _money(c["valor"])
        d = (remaining * pct).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        remaining -= d
        discount += d

    for c in cupons:
        if c["tipo"] != "fixo":
            continue
        d = _money(c["valor"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        if d > remaining:
            d = remaining
        remaining -= d
        discount += d

    max_disc = (original * Decimal("0.50")).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    if discount > max_disc:
        remaining = original - max_disc
    else:
        remaining = original - discount

    return (remaining + ship).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
