# UC-13 — Controle de estoque multi-depósito com reserva

## Contexto de negócio

Um varejista opera vários depósitos e precisa segurar os itens do carrinho enquanto o
cliente termina o checkout, sem vender o mesmo item duas vezes. Um pedido pode ser
atendido por mais de um depósito. Reservas abandonadas precisam voltar para o estoque
sozinhas. O sistema atende requisições concorrentes.

## Contrato obrigatório

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão.

```python
class ErroEstoque(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class Estoque:
    def __init__(self, relogio: Callable[[], float] | None = None) -> None:
        """`relogio` devolve segundos monotônicos como float."""

    def registrar_deposito(self, deposito_id: str, prioridade: int) -> None: ...

    def repor(self, deposito_id: str, sku: str, quantidade: int) -> int:
        """Retorna o novo estoque físico do sku naquele depósito."""

    def disponivel(self, sku: str, deposito_id: str | None = None) -> int: ...

    def reservar(self, itens: list[dict], ttl_s: float | None = None) -> str:
        """`itens`: [{"sku": str, "quantidade": int}]. Retorna o id da reserva."""

    def confirmar(self, reserva_id: str) -> dict:
        """Retorna {"alocacao": {deposito_id: {sku: quantidade}}}"""

    def cancelar(self, reserva_id: str) -> None: ...

    def transferir(self, sku: str, origem: str, destino: str, quantidade: int) -> None: ...

    def posicao(self, sku: str) -> dict:
        """{deposito_id: {"fisico": int, "reservado": int, "disponivel": int}}"""

    def expirar(self) -> int:
        """Retorna a quantidade de reservas expiradas nesta chamada."""
```

### Vocabulário fechado

`ErroEstoque.code` assume **somente**: `ESTOQUE_INSUFICIENTE`, `RESERVA_NAO_ENCONTRADA`,
`ESTADO_INVALIDO`, `DEPOSITO_DESCONHECIDO`, `SKU_DESCONHECIDO`, `DADOS_INVALIDOS`.

> Este enunciado define o vocabulário, não a regra: em que circunstância cada código se
> aplica, como o pedido é distribuído entre depósitos e quando uma reserva deixa de valer
> faz parte do que precisa ser decidido.

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
