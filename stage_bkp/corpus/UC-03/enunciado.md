# UC-03 — Cupons de desconto

## Tarefa

Implemente a lógica de um carrinho que aplica cupons de desconto sobre o subtotal de produtos e devolve o valor final (subtotal com desconto + frete).

## Interface obrigatória

- Arquivo: `solucao.py`
- Exceção: `class ErroCupom(Exception)` com atributo `code: str` (códigos: `CUPOM_EXPIRADO`, `PEDIDO_MINIMO`)
- Função: `calcular_total(subtotal, cupons, frete="0") -> Decimal`
  - `subtotal`, `frete`: `str`, `int`, `float` ou `Decimal` (valores monetários ≥ 0)
  - `cupons`: lista de dicionários, cada um com:
    - `tipo`: `"percentual"` ou `"fixo"`
    - `valor`: percentual em fração decimal (ex.: `"0.10"` = 10%) ou valor fixo em reais
    - `stackable`: `bool` — se `False`, não pode ser combinado com outro cupom não stackable
    - `pedido_minimo`: opcional; mínimo do subtotal **original** para aplicar o cupom
    - `expirado`: `bool` — se `True`, levantar `ErroCupom` com `code="CUPOM_EXPIRADO"`
  - Regras de negócio:
    1. Desconto incide apenas sobre o subtotal de produtos (frete entra depois, sem desconto).
    2. Cupons não stackable não podem ser combinados entre si (no máximo um cupom com `stackable=False` por chamada).
    3. Ordem de aplicação: todos os cupons **percentuais** (na ordem da lista), depois todos os **fixos** (na ordem da lista), sempre sobre o subtotal remanescente após cada desconto.
    4. O desconto total acumulado não pode ultrapassar **50%** do subtotal original; se ultrapassar, limitar ao teto.
    5. Subtotal abaixo de `pedido_minimo` → `ErroCupom` com `code="PEDIDO_MINIMO"`.
  - Retorno: `Decimal` com 2 casas decimais (arredondamento half-even).

## Entrega

- Implementar em `solucao.py`, Python 3.12, sem dependências externas além da biblioteca padrão.
- Os testes em `tests_visiveis/` devem passar.
