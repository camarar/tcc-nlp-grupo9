from decimal import Decimal, ROUND_HALF_EVEN


class ErroCupom(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _to_decimal(valor) -> Decimal:
    if isinstance(valor, Decimal):
        return valor
    return Decimal(str(valor))


def calcular_total(subtotal, cupons, frete="0") -> Decimal:
    subtotal_original = _to_decimal(subtotal)
    frete_decimal = _to_decimal(frete)

    nao_stackable_count = sum(
        1 for cupom in cupons if not cupom.get("stackable", True)
    )
    if nao_stackable_count > 1:
        raise ErroCupom(code="CUPONS_NAO_STACKABLE")

    for cupom in cupons:
        if cupom.get("expirado", False):
            raise ErroCupom(code="CUPOM_EXPIRADO")

        pedido_minimo = cupom.get("pedido_minimo")
        if pedido_minimo is not None and subtotal_original < _to_decimal(pedido_minimo):
            raise ErroCupom(code="PEDIDO_MINIMO")

    percentuais = [c for c in cupons if c["tipo"] == "percentual"]
    fixos = [c for c in cupons if c["tipo"] == "fixo"]

    subtotal_restante = subtotal_original
    for cupom in percentuais:
        desconto = subtotal_restante * _to_decimal(cupom["valor"])
        subtotal_restante -= desconto

    for cupom in fixos:
        desconto = _to_decimal(cupom["valor"])
        subtotal_restante -= desconto

    teto_minimo = subtotal_original * Decimal("0.5")
    if subtotal_restante < teto_minimo:
        subtotal_restante = teto_minimo

    if subtotal_restante < 0:
        subtotal_restante = Decimal("0")

    total = subtotal_restante + frete_decimal
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
