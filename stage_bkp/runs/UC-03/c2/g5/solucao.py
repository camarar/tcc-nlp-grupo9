from decimal import ROUND_HALF_EVEN, Decimal


class ErroCupom(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _to_decimal(valor):
    return Decimal(str(valor))


def calcular_total(subtotal, cupons, frete="0"):
    subtotal_original = _to_decimal(subtotal)
    frete_dec = _to_decimal(frete)

    nao_stackable = [c for c in cupons if not c.get("stackable", True)]
    if len(nao_stackable) > 1:
        raise ValueError("cupons não stackable não podem ser combinados")

    for cupom in cupons:
        if cupom.get("expirado", False):
            raise ErroCupom("CUPOM_EXPIRADO")
        pedido_minimo = cupom.get("pedido_minimo")
        if pedido_minimo is not None and subtotal_original < _to_decimal(pedido_minimo):
            raise ErroCupom("PEDIDO_MINIMO")

    percentuais = [c for c in cupons if c["tipo"] == "percentual"]
    fixos = [c for c in cupons if c["tipo"] == "fixo"]

    remanescente = subtotal_original
    for cupom in percentuais:
        remanescente -= remanescente * _to_decimal(cupom["valor"])
    for cupom in fixos:
        remanescente -= _to_decimal(cupom["valor"])

    desconto_total = subtotal_original - remanescente
    desconto_maximo = subtotal_original * Decimal("0.5")
    if desconto_total > desconto_maximo:
        desconto_total = desconto_maximo

    subtotal_com_desconto = subtotal_original - desconto_total
    total = subtotal_com_desconto + frete_dec

    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
