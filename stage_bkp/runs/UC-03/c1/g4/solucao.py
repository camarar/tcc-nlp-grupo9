from decimal import ROUND_HALF_EVEN, Decimal


class ErroCupom(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _to_decimal(valor) -> Decimal:
    if isinstance(valor, Decimal):
        return valor
    return Decimal(str(valor))


def calcular_total(subtotal, cupons, frete="0") -> Decimal:
    subtotal_original = _to_decimal(subtotal)
    frete_dec = _to_decimal(frete)

    nao_stackable_count = 0
    for cupom in cupons:
        if cupom.get("expirado"):
            raise ErroCupom("CUPOM_EXPIRADO")
        pedido_minimo = cupom.get("pedido_minimo")
        if pedido_minimo is not None and subtotal_original < _to_decimal(pedido_minimo):
            raise ErroCupom("PEDIDO_MINIMO")
        if not cupom.get("stackable", True):
            nao_stackable_count += 1

    if nao_stackable_count > 1:
        raise ValueError("no maximo um cupom nao stackable por chamada")

    percentuais = [c for c in cupons if c["tipo"] == "percentual"]
    fixos = [c for c in cupons if c["tipo"] == "fixo"]

    subtotal_restante = subtotal_original
    for cupom in percentuais:
        valor = _to_decimal(cupom["valor"])
        subtotal_restante -= subtotal_restante * valor
    for cupom in fixos:
        valor = _to_decimal(cupom["valor"])
        subtotal_restante -= valor

    desconto_total = subtotal_original - subtotal_restante
    teto = subtotal_original * Decimal("0.5")
    if desconto_total > teto:
        subtotal_restante = subtotal_original - teto

    if subtotal_restante < 0:
        subtotal_restante = Decimal("0")

    total = subtotal_restante + frete_dec
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
