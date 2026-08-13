from decimal import Decimal, ROUND_HALF_EVEN


class ErroCupom(Exception):
    def __init__(self, message="", code=""):
        super().__init__(message)
        self.code = code


def _to_decimal(valor):
    if isinstance(valor, Decimal):
        return valor
    return Decimal(str(valor))


def calcular_total(subtotal, cupons, frete="0"):
    subtotal_dec = _to_decimal(subtotal)
    frete_dec = _to_decimal(frete)

    nao_stackable = 0
    for cupom in cupons:
        if cupom.get("expirado"):
            raise ErroCupom("Cupom expirado", code="CUPOM_EXPIRADO")

        pedido_minimo = cupom.get("pedido_minimo")
        if pedido_minimo is not None and subtotal_dec < _to_decimal(pedido_minimo):
            raise ErroCupom("Pedido abaixo do mínimo exigido", code="PEDIDO_MINIMO")

        if not cupom.get("stackable", True):
            nao_stackable += 1

    if nao_stackable > 1:
        raise ValueError("No máximo um cupom não stackable pode ser usado por chamada")

    percentuais = [c for c in cupons if c["tipo"] == "percentual"]
    fixos = [c for c in cupons if c["tipo"] == "fixo"]

    remanescente = subtotal_dec
    for cupom in percentuais:
        remanescente -= remanescente * _to_decimal(cupom["valor"])
    for cupom in fixos:
        remanescente -= _to_decimal(cupom["valor"])

    desconto = subtotal_dec - remanescente
    desconto_maximo = subtotal_dec * Decimal("0.5")
    if desconto > desconto_maximo:
        desconto = desconto_maximo

    total = subtotal_dec - desconto + frete_dec
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
