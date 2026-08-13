from decimal import Decimal, ROUND_HALF_EVEN


class ErroCupom(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _to_decimal(valor) -> Decimal:
    return Decimal(str(valor))


def calcular_total(subtotal, cupons, frete="0") -> Decimal:
    subtotal_original = _to_decimal(subtotal)
    frete_decimal = _to_decimal(frete)

    for cupom in cupons:
        if cupom.get("expirado"):
            raise ErroCupom("CUPOM_EXPIRADO")

    nao_stackable = sum(1 for cupom in cupons if cupom.get("stackable") is False)
    if nao_stackable > 1:
        raise ValueError("Apenas um cupom nao stackable pode ser combinado por chamada")

    for cupom in cupons:
        pedido_minimo = cupom.get("pedido_minimo")
        if pedido_minimo is not None and subtotal_original < _to_decimal(pedido_minimo):
            raise ErroCupom("PEDIDO_MINIMO")

    percentuais = [c for c in cupons if c["tipo"] == "percentual"]
    fixos = [c for c in cupons if c["tipo"] == "fixo"]

    atual = subtotal_original
    for cupom in percentuais:
        atual -= atual * _to_decimal(cupom["valor"])
    for cupom in fixos:
        atual -= _to_decimal(cupom["valor"])

    teto_desconto = subtotal_original * Decimal("0.5")
    piso = subtotal_original - teto_desconto
    if atual < piso:
        atual = piso

    total = atual + frete_decimal
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
