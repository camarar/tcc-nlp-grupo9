from decimal import Decimal, ROUND_HALF_EVEN


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
    frete_decimal = _to_decimal(frete)

    nao_stackable_count = 0
    for cupom in cupons:
        if cupom.get("expirado"):
            raise ErroCupom(code="CUPOM_EXPIRADO")

        pedido_minimo = cupom.get("pedido_minimo")
        if pedido_minimo is not None and subtotal_original < _to_decimal(pedido_minimo):
            raise ErroCupom(code="PEDIDO_MINIMO")

        if not cupom.get("stackable", True):
            nao_stackable_count += 1

    if nao_stackable_count > 1:
        raise ValueError("Mais de um cupom nao stackable combinado")

    percentuais = [c for c in cupons if c["tipo"] == "percentual"]
    fixos = [c for c in cupons if c["tipo"] == "fixo"]

    subtotal_restante = subtotal_original
    for cupom in percentuais:
        valor = _to_decimal(cupom["valor"])
        subtotal_restante -= subtotal_restante * valor
    for cupom in fixos:
        valor = _to_decimal(cupom["valor"])
        subtotal_restante -= valor

    desconto_maximo = subtotal_original * Decimal("0.5")
    piso_subtotal = subtotal_original - desconto_maximo
    if subtotal_restante < piso_subtotal:
        subtotal_restante = piso_subtotal

    total = subtotal_restante + frete_decimal
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
