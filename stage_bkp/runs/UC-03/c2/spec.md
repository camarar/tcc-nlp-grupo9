# Especificação técnica — UC-03: Cupons de desconto

> Consolidado após ciclo Designer → Analyst → SFAR (condição c2). Não inclui o gabarito bruto.

## Interface obrigatória

- Arquivo: `solucao.py`
- Exceção: `class ErroCupom(Exception)` com atributo `code: str`
- Função: `calcular_total(subtotal, cupons, frete="0") -> decimal.Decimal`
- `subtotal`, `frete`: `str`, `int`, `float` ou `Decimal` (≥ 0)
- `cupons`: lista de dicionários com chaves:
  - `tipo`: `"percentual"` ou `"fixo"`
  - `valor`: fração decimal (ex. `"0.10"`) ou valor fixo em reais
  - `stackable`: `bool`
  - `pedido_minimo`: opcional; comparado ao **subtotal original**
  - `expirado`: `bool`
- Python 3.12, stdlib apenas. Os testes em `tests_visiveis/` devem passar.

## Requisitos de negócio (RN)

| ID | Requisito | Status |
|---|---|---|
| RN-01 | Desconto incide somente sobre o subtotal de produtos; frete é somado ao final **sem** desconto. | Confirmado |
| RN-02 | Cupons com `stackable=False` não podem ser combinados: se houver **mais de um** cupom com `stackable=False` na mesma chamada, levantar `ValueError`. | Confirmado |
| RN-03 | Cupons `stackable=True` podem ser combinados entre si e com no máximo um cupom `stackable=False`. | Confirmado |
| RN-04 | Ordem: aplicar **todos** os cupons percentuais (ordem da lista), depois **todos** os fixos (ordem da lista), cada desconto sobre o subtotal remanescente após o anterior. | Confirmado |
| RN-05 | Desconto total acumulado limitado a **50%** do subtotal original; excedente é truncado pelo teto (não gera erro). | Confirmado |
| RN-06 | `expirado=True` em qualquer cupom → `ErroCupom` com `code="CUPOM_EXPIRADO"`. | Confirmado |
| RN-07 | Subtotal original `< pedido_minimo` do cupom → `ErroCupom` com `code="PEDIDO_MINIMO"`. | Confirmado |
| RN-08 | Retorno: `Decimal` com 2 casas, arredondamento `ROUND_HALF_EVEN`. | Confirmado |
| RN-09 | Conversão monetária via `Decimal(str(valor))` (ou equivalente seguro). | Confirmado |

## Critérios de aceite (Gherkin)

```gherkin
Funcionalidade: Carrinho com cupons

  Cenário: Sem cupom, apenas frete
    Dado subtotal "100.00" e frete "10" e lista de cupons vazia
    Quando calcular_total é chamado
    Então o retorno deve ser Decimal("110.00")

  Cenário: Desconto percentual simples
    Dado subtotal "200.00" e um cupom percentual 10% não stackable válido
    Quando calcular_total é chamado
    Então o retorno deve ser Decimal("180.00")

  Cenário: Percentual antes de fixo
    Dado subtotal "100.00" e cupons 10% stackable e fixo R$ 5 stackable
    Quando calcular_total é chamado
    Então o retorno deve ser Decimal("85.00")

  Cenário: Teto de 50% de desconto
    Dado subtotal "100.00" e cupons que somariam mais de 50% de desconto
    Quando calcular_total é chamado
    Então o total após desconto deve ser Decimal("50.00") antes do frete

  Cenário: Frete fora da base de desconto
    Dado subtotal "100.00", frete "20.00" e cupom 10%
    Quando calcular_total é chamado
    Então o retorno deve ser Decimal("110.00")

  Cenário: Cupom expirado
    Dado cupom com expirado true
    Quando calcular_total é chamado
    Então deve ser levantado ErroCupom com code CUPOM_EXPIRADO

  Cenário: Pedido abaixo do mínimo
    Dado pedido_minimo "150.00" e subtotal "100.00"
    Quando calcular_total é chamado
    Então deve ser levantado ErroCupom com code PEDIDO_MINIMO

  Cenário: Dois cupons não stackable
    Dado dois cupons com stackable false
    Quando calcular_total é chamado
    Então deve ser levantada ValueError

  Cenário: Dois cupons stackable percentuais
    Dado subtotal "100.00" e dois cupons 10% stackable
    Quando calcular_total é chamado
    Então o retorno deve ser Decimal("81.00")
```

## Restrições técnicas

- Implementar somente `solucao.py`.
- Não usar dependências externas.
- Códigos de erro de negócio **somente** `CUPOM_EXPIRADO` e `PEDIDO_MINIMO` em `ErroCupom`; violação de combinação de cupons usa `ValueError` (RN-02).

## Pipeline (registro)

- **Designer:** PR/FAQ para carrinho e-commerce com cupons (escopo alinhado à tarefa).
- **Analyst:** GAPs fechados com gabarito (não acumulável exceto stackable; ordem percentual→fixo; teto 50%; base sem frete; códigos de erro).
- **SFAR:** Especificação 🟢 PRONTO PARA SOLUÇÃO após incorporar RN-02 explícito (`ValueError` para combinação inválida).
