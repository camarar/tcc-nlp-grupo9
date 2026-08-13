from decimal import Decimal, ROUND_HALF_EVEN


class ErroCupom(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _to_decimal(valor) -> Decimal:
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, bool):
        raise TypeError(f"tipo não suportado: {type(valor)!r}")
    if isinstance(valor, (int, str, float)):
        return Decimal(str(valor))
    raise TypeError(f"tipo não suportado: {type(valor)!r}")


def calcular_total(subtotal, cupons, frete="0") -> Decimal:
    subtotal_original = _to_decimal(subtotal)
    frete_dec = _to_decimal(frete)

    nao_stackable = [c for c in cupons if not c.get("stackable", True)]
    if len(nao_stackable) > 1:
        raise ValueError("Não é possível combinar mais de um cupom não stackable")

    for cupom in cupons:
        if cupom.get("expirado"):
            raise ErroCupom(code="CUPOM_EXPIRADO", message="Cupom expirado")
        pedido_minimo = cupom.get("pedido_minimo")
        if pedido_minimo is not None and subtotal_original < _to_decimal(pedido_minimo):
            raise ErroCupom(code="PEDIDO_MINIMO", message="Subtotal abaixo do pedido mínimo")

    percentuais = [c for c in cupons if c["tipo"] == "percentual"]
    fixos = [c for c in cupons if c["tipo"] == "fixo"]

    remanescente = subtotal_original
    total_desconto = Decimal("0")

    for cupom in percentuais:
        valor = _to_decimal(cupom["valor"])
        desconto = remanescente * valor
        remanescente -= desconto
        total_desconto += desconto

    for cupom in fixos:
        valor = _to_decimal(cupom["valor"])
        remanescente -= valor
        total_desconto += valor

    teto = subtotal_original * Decimal("0.5")
    if total_desconto > teto:
        total_desconto = teto

    subtotal_final = subtotal_original - total_desconto
    total = subtotal_final + frete_dec

    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
