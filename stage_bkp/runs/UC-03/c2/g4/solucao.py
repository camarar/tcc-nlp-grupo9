from decimal import Decimal, ROUND_HALF_EVEN


class ErroCupom(Exception):
    def __init__(self, code: str, *args):
        super().__init__(code, *args)
        self.code = code


def _to_decimal(valor) -> Decimal:
    if isinstance(valor, Decimal):
        return valor
    return Decimal(str(valor))


def calcular_total(subtotal, cupons, frete="0") -> Decimal:
    subtotal_original = _to_decimal(subtotal)
    frete_dec = _to_decimal(frete)

    nao_stackable = [c for c in cupons if not c.get("stackable", True)]
    if len(nao_stackable) > 1:
        raise ValueError("Mais de um cupom nao stackable informado")

    for cupom in cupons:
        if cupom.get("expirado", False):
            raise ErroCupom("CUPOM_EXPIRADO")

        pedido_minimo = cupom.get("pedido_minimo")
        if pedido_minimo is not None and subtotal_original < _to_decimal(pedido_minimo):
            raise ErroCupom("PEDIDO_MINIMO")

    percentuais = [c for c in cupons if c["tipo"] == "percentual"]
    fixos = [c for c in cupons if c["tipo"] == "fixo"]

    subtotal_atual = subtotal_original
    for cupom in percentuais:
        desconto = subtotal_atual * _to_decimal(cupom["valor"])
        subtotal_atual -= desconto

    for cupom in fixos:
        desconto = _to_decimal(cupom["valor"])
        subtotal_atual -= desconto

    desconto_total = subtotal_original - subtotal_atual
    desconto_maximo = subtotal_original * Decimal("0.5")
    if desconto_total > desconto_maximo:
        subtotal_atual = subtotal_original - desconto_maximo

    if subtotal_atual < 0:
        subtotal_atual = Decimal("0")

    total = subtotal_atual + frete_dec
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
