# UC-03 — Motor de precificação e promoções

## Contexto de negócio

Um e-commerce precisa do motor que calcula quanto o cliente paga. Existem campanhas
promocionais por categoria de produto, que valem por um período, e cupons que o cliente
digita no checkout. O motor precisa cotar o pedido, dizer quanto cada item ficou custando
depois dos descontos — o financeiro usa isso para estornos parciais — e explicar como
chegou ao valor final.

## Contrato obrigatório

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão. Valores monetários são
`decimal.Decimal`; entradas monetárias podem chegar como `str`, `int`, `float` ou `Decimal`.

```python
class ErroPrecificacao(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class MotorPrecificacao:
    def __init__(self, agora: Callable[[], datetime] | None = None) -> None: ...

    def registrar_campanha(self, campanha: dict) -> str:
        """`campanha`: {"nome": str, "categoria": str, "percentual": <monetário>,
        "inicio": date, "fim": date}. Retorna o identificador."""

    def registrar_cupom(self, cupom: dict) -> str:
        """`cupom`: {"codigo": str, "tipo": str, "valor": <monetário>,
        "acumulavel": bool, "validade": date,
        "pedido_minimo": <monetário> | None, "categorias": list[str] | None}.
        Retorna o código do cupom."""

    def cotar(self, pedido: dict, cupons: list[str], data: date) -> dict:
        """`pedido`: {"itens": [{"sku": str, "categoria": str,
                                 "preco_unitario": <monetário>, "quantidade": int}],
                      "frete": <monetário>}
        Retorna {"subtotal", "desconto_campanhas", "desconto_cupons",
                 "desconto_total", "frete", "total",
                 "itens": [{"sku", "preco_bruto", "desconto_rateado", "preco_liquido"}]}"""

    def explicar(self, pedido: dict, cupons: list[str], data: date) -> list[dict]:
        """Trilha ordenada de aplicação:
        [{"origem": str, "referencia": str, "base": Decimal, "valor": Decimal}]"""
```

### Vocabulário fechado

`ErroPrecificacao.code` assume **somente**: `CUPOM_INVALIDO`, `CUPOM_EXPIRADO`,
`PEDIDO_MINIMO`, `CUPOM_NAO_ACUMULAVEL`, `ITEM_INVALIDO`, `CAMPANHA_INVALIDA`.

O campo `tipo` do cupom assume **somente**: `PERCENTUAL`, `FIXO`, `FRETE_GRATIS`.

O campo `origem` da trilha assume **somente**: `CAMPANHA`, `CUPOM`, `TETO`, `FRETE`.

> Este enunciado define o vocabulário, não a regra: em que circunstância cada código,
> tipo e origem se aplica faz parte do que precisa ser decidido.

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
