# UC-18 — Ciclo de vida de pedido com combos promocionais

## Contexto de negócio

Uma loja vende itens avulsos e combos promocionais — conjuntos de itens com preço menor do
que a soma das partes. Quando o cliente cancela **um** item de um combo, o desconto do
combo deixa de fazer sentido: os itens que sobraram precisam ser reprecificados. O pedido
percorre um ciclo de vida — é pago, despachado em partes, cancelado, devolvido — e cada
transição tem regra própria. O estorno nunca pode devolver mais do que o cliente pagou.

## Contrato obrigatório

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão. Valores monetários são
`decimal.Decimal`; entradas monetárias podem chegar como `str`, `int`, `float` ou `Decimal`.

```python
class ErroPedido(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class Pedidos:
    def __init__(self, relogio: Callable[[], datetime] | None = None) -> None: ...

    def criar(self, dados: dict) -> str:
        """`dados`: {"cliente": str,
                     "itens": [{"item_id": str, "sku": str,
                                "preco_cheio": <monetário>,
                                "combo": str | None}],
                     "combos": [{"combo_id": str, "preco": <monetário>}]}"""

    def pagar(self, pedido_id: str, valor, quando: datetime) -> dict:
        """Retorna {"situacao": str, "pago": Decimal}"""

    def despachar(self, pedido_id: str, itens: list[str], quando: datetime) -> str:
        """Retorna a nova situação do pedido."""

    def cancelar_item(self, pedido_id: str, item_id: str, quando: datetime) -> dict:
        """Retorna {"estorno": Decimal, "novo_total": Decimal, "situacao": str}"""

    def devolver(self, pedido_id: str, item_id: str, quando: datetime) -> dict:
        """Retorna o mesmo formato de `cancelar_item`."""

    def resumo(self, pedido_id: str) -> dict:
        """Retorna {"situacao": str, "total": Decimal, "pago": Decimal,
                    "estornado": Decimal,
                    "itens": [{"item_id": str, "preco": Decimal,
                               "situacao": str, "combo": str | None}]}"""

    def historico(self, pedido_id: str) -> list[dict]:
        """[{"em": datetime, "evento": str, "item_id": str | None,
             "valor": Decimal | None}]"""
```

### Vocabulário fechado

`ErroPedido.code` assume **somente**: `PEDIDO_NAO_ENCONTRADO`, `ITEM_INVALIDO`,
`ESTADO_INVALIDO`, `VALOR_INVALIDO`, `COMBO_INVALIDO`, `OPERACAO_NAO_PERMITIDA`.

A situação do **pedido** assume **somente**: `CRIADO`, `PAGO`, `PARCIALMENTE_DESPACHADO`,
`DESPACHADO`, `CANCELADO`, `CONCLUIDO`.

A situação do **item** assume **somente**: `ATIVO`, `DESPACHADO`, `CANCELADO`,
`DEVOLVIDO`.

O `evento` do histórico assume **somente**: `CRIACAO`, `PAGAMENTO`, `DESPACHO`,
`CANCELAMENTO_ITEM`, `DEVOLUCAO`, `REPRECIFICACAO`, `CANCELAMENTO_PEDIDO`.

> Este enunciado define o vocabulário, não a regra: o que acontece com o preço dos itens
> restantes de um combo, como o estorno é calculado e quais transições são legais faz
> parte do que precisa ser decidido.

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
