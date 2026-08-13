from decimal import Decimal, ROUND_HALF_EVEN


class ErroCupom(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(value)


def calcular_total(subtotal, cupons, frete="0") -> Decimal:
    subtotal_original = _to_decimal(subtotal)
    frete_dec = _to_decimal(frete)

    for cupom in cupons:
        if cupom.get("expirado", False):
            raise ErroCupom("CUPOM_EXPIRADO")
        pedido_minimo = cupom.get("pedido_minimo")
        if pedido_minimo is not None and subtotal_original < _to_decimal(pedido_minimo):
            raise ErroCupom("PEDIDO_MINIMO")

    nao_stackable = [c for c in cupons if not c.get("stackable", True)]
    if len(nao_stackable) > 1:
        raise ErroCupom("CUPOM_NAO_STACKABLE")

    percentuais = [c for c in cupons if c["tipo"] == "percentual"]
    fixos = [c for c in cupons if c["tipo"] == "fixo"]

    remanescente = subtotal_original
    desconto_total = Decimal("0")

    for cupom in percentuais:
        desconto = remanescente * _to_decimal(cupom["valor"])
        remanescente -= desconto
        desconto_total += desconto

    for cupom in fixos:
        desconto = _to_decimal(cupom["valor"])
        remanescente -= desconto
        desconto_total += desconto

    teto = subtotal_original * Decimal("0.5")
    if desconto_total > teto:
        desconto_total = teto

    subtotal_final = subtotal_original - desconto_total
    total = subtotal_final + frete_dec

    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
