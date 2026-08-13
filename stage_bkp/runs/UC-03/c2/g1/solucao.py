from decimal import Decimal, ROUND_HALF_EVEN


class ErroCupom(Exception):
    def __init__(self, message="", *, code):
        self.code = code
        super().__init__(message or code)


def _to_decimal(valor):
    if isinstance(valor, Decimal):
        return valor
    return Decimal(str(valor))


def calcular_total(subtotal, cupons, frete="0"):
    subtotal_dec = _to_decimal(subtotal)
    frete_dec = _to_decimal(frete)

    for cupom in cupons:
        if cupom.get("expirado"):
            raise ErroCupom(code="CUPOM_EXPIRADO")

    if sum(1 for c in cupons if c.get("stackable") is False) > 1:
        raise ValueError("Cupons nao stackable nao podem ser combinados")

    for cupom in cupons:
        pedido_minimo = cupom.get("pedido_minimo")
        if pedido_minimo is not None and subtotal_dec < _to_decimal(pedido_minimo):
            raise ErroCupom(code="PEDIDO_MINIMO")

    remanescente = subtotal_dec
    for cupom in cupons:
        if cupom["tipo"] == "percentual":
            remanescente -= remanescente * _to_decimal(cupom["valor"])
    for cupom in cupons:
        if cupom["tipo"] == "fixo":
            remanescente -= _to_decimal(cupom["valor"])

    desconto_total = subtotal_dec - remanescente
    teto = subtotal_dec * Decimal("0.5")
    if desconto_total > teto:
        remanescente = subtotal_dec - teto

    total = remanescente + frete_dec
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
