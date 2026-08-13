# Especificação técnica — UC-01: Juros compostos

> Documento consolidado ao final do ciclo Working Backwards (Designer → Analyst → SFAR) da condição c2.
> Este documento **não contém** o gabarito de decisões — apenas as regras de negócio já resolvidas.

## Interface obrigatória

- Arquivo: `solucao.py`
- Função: `calcular_juros_compostos(principal, taxa_anual, meses) -> decimal.Decimal`
- `principal` e `taxa_anual` podem chegar como `str`, `int`, `float` ou `Decimal`; `taxa_anual` é fração (ex.: `"0.12"` = 12% a.a.); `meses` é `int`.
- Implementar em `solucao.py`, Python 3.12, sem dependências externas. Os testes em `tests_visiveis/` devem passar.

## Requisitos de negócio (RN)

| ID | Requisito | Maturidade |
|---|---|---|
| RN-01 | A taxa anual informada é **nominal**. A taxa mensal equivalente é `taxa_anual / 12` (proporção simples — **não** é a conversão de taxa efetiva composta equivalente `(1+taxa_anual)^(1/12)-1`). | Confirmado |
| RN-02 | O valor final é calculado por capitalização composta mensal ao longo de `meses`: `VF = principal * (1 + taxa_anual/12) ** meses`. | Confirmado |
| RN-03 | O arredondamento é `ROUND_HALF_EVEN` (banker's rounding), para 2 casas decimais, aplicado **somente no resultado final** (nunca em passos intermediários do cálculo). | Confirmado |
| RN-04 | Não há aportes mensais adicionais. Apenas o `principal` inicial capitaliza ao longo do tempo. | Confirmado |
| RN-05 | `principal < 0` (estritamente negativo) lança `ValueError`. `principal == 0` é um caso válido e retorna `Decimal('0.00')`. | Confirmado |
| RN-06 | `taxa_anual < 0` (estritamente negativo) lança `ValueError`. `taxa_anual == 0` é um caso válido e retorna o próprio `principal`, convertido e arredondado pela mesma regra de RN-03 (`quantize(Decimal('0.01'), ROUND_HALF_EVEN)`), mesmo que `principal` chegue com mais de 2 casas decimais. | Confirmado |
| RN-07 | `meses <= 0` lança `ValueError`. `meses` que não seja instância de `int` nativo lança `TypeError` imediatamente (fail-fast, sem tentativa de conversão) — a interface obrigatória declara `meses: int` estritamente, diferente de `principal`/`taxa_anual`, que são explicitamente polimórficos. | **Avanço sob risco** — contrato de erro assimétrico (`TypeError` para `meses` vs. `ValueError` para os demais parâmetros inválidos) não confirmado por decisão de negócio; recomendação formal do SFAR era aguardar confirmação. |
| RN-08 | Conversão de `principal`/`taxa_anual` para `Decimal`: usar `Decimal(str(valor))` (evita herdar imprecisão binária de `float`). Apenas formatos numéricos simples são suportados (ex.: `"0.12"`); formatos como `"12%"` ou separador decimal `","` **não** são suportados. `decimal.InvalidOperation` levantada durante essa conversão deve ser capturada e relançada como `ValueError`. | **Avanço sob risco** — sem confirmação de negócio sobre formatos alternativos de entrada. |
| RN-09 | Todos os cálculos internos usam `Decimal` (nunca `float` diretamente no caminho de cálculo), garantindo determinismo numérico. | Confirmado (boa prática incorporada) |
| RN-10 | Qualquer exceção nativa do Python não prevista (`TypeError`, `AttributeError`, etc.) levantada durante a conversão de `principal` ou `taxa_anual` para `Decimal` (ex.: valor `None`, `list`, `dict`) é capturada e relançada como `ValueError`, mantendo um contrato de exceção único para esses dois parâmetros. | **Avanço sob risco** — sem confirmação de negócio. |

## Fora de escopo desta versão (lacunas não-bloqueantes aceitas)

- Limite superior de `meses` (nenhuma proteção contra overflow de tempo de cálculo para valores extremos).
- Precisão de contexto `Decimal` (`getcontext().prec`) além do padrão do módulo `decimal` (28 dígitos).
- Volumetria/performance em lote (a função é especificada para chamada isolada).
- Logging/observabilidade de dados sensíveis.

## Critérios de aceite (Gherkin)

```gherkin
Funcionalidade: Cálculo de valor final com juros compostos

  Cenário: Capitalização composta ao longo de 12 meses
    Dado principal = "1000" e taxa_anual = "0.12" e meses = 12
    Quando calcular_juros_compostos é chamado
    Então o retorno deve ser Decimal("1126.83")
    E o retorno deve ser uma instância de decimal.Decimal

  Cenário: Retorno é sempre Decimal
    Dado principal = "100" e taxa_anual = "0.06" e meses = 1
    Quando calcular_juros_compostos é chamado
    Então o retorno deve ser uma instância de decimal.Decimal

  Cenário: Taxa anual zero não gera crescimento
    Dado principal = "500" e taxa_anual = "0" e meses = 24
    Quando calcular_juros_compostos é chamado
    Então o retorno deve ser Decimal("500.00")

  Cenário: Principal zero é um caso válido
    Dado principal = "0" e taxa_anual = "0.10" e meses = 6
    Quando calcular_juros_compostos é chamado
    Então o retorno deve ser Decimal("0.00")

  Cenário: Principal negativo é inválido
    Dado principal = "-100" e taxa_anual = "0.10" e meses = 6
    Quando calcular_juros_compostos é chamado
    Então deve ser levantada a exceção ValueError

  Cenário: Taxa anual negativa é inválida
    Dado principal = "100" e taxa_anual = "-0.05" e meses = 6
    Quando calcular_juros_compostos é chamado
    Então deve ser levantada a exceção ValueError

  Cenário: Período zero ou negativo é inválido
    Dado principal = "100" e taxa_anual = "0.10" e meses = 0
    Quando calcular_juros_compostos é chamado
    Então deve ser levantada a exceção ValueError

  Cenário: Meses com tipo diferente de int é inválido
    Dado principal = "100" e taxa_anual = "0.10" e meses = "12"
    Quando calcular_juros_compostos é chamado
    Então deve ser levantada a exceção TypeError

  Cenário: Entrada numérica malformada é inválida
    Dado principal = "abc" e taxa_anual = "0.10" e meses = 12
    Quando calcular_juros_compostos é chamado
    Então deve ser levantada a exceção ValueError

  Cenário: Aceita todos os tipos numéricos suportados para principal e taxa_anual
    Dado principal informado como str, int, float ou Decimal
    E taxa_anual informado como str, int, float ou Decimal
    Quando calcular_juros_compostos é chamado com valores equivalentes em cada tipo
    Então o resultado deve ser numericamente idêntico entre os tipos
```

## Restrições técnicas

- Python 3.12, sem dependências externas (apenas stdlib, incluindo `decimal`).
- Não criar arquivos além de `solucao.py`.
- A suíte de `tests_visiveis/` deve passar antes da entrega.
