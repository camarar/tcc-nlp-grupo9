# UC-07 — Especificação Técnica Consolidada
## Motor de cotação de frete multi-transportadora

> Produzida pelo pipeline de três agentes (working-backwards-designer →
> working-backwards-analyst → senior-functional-analyst-reviewer). As regras de negócio
> abaixo só foram incorporadas quando efetivamente elicitadas por pergunta de algum
> agente e respondidas pelo orquestrador via fonte de verdade de negócio — ver
> `registro.md` para o rastro completo de perguntas e respostas, incluindo os dois
> avanços sob risco (opção B do SFAR).

---

## 1. Contrato obrigatório

> Copiado literalmente de `stage4/corpus/UC-07/enunciado.md`.

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão. Valores monetários e
pesos são `decimal.Decimal`; entradas numéricas podem chegar como `str`, `int`, `float` ou
`Decimal`.

```python
class ErroFrete(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class MotorFrete:
    def registrar_transportadora(self, nome: str, config: dict) -> None:
        """`config`: {"faixas": [{"ate_kg": <num>, "preco": <monetário>,
                                  "prazo_dias": int}],
                      "regioes": list[str], "fator_cubagem": int,
                      "peso_maximo_kg": <num>, "ad_valorem": <monetário> | None}"""

    def registrar_restricao(self, transportadora: str, prefixo_cep: str) -> None: ...

    def cotar(self, pedido: dict) -> list[dict]:
        """`pedido`: {"uf_destino": str, "cep_destino": str,
                      "itens": [{"peso_kg": <num>, "altura_cm": <num>,
                                 "largura_cm": <num>, "comprimento_cm": <num>,
                                 "quantidade": int, "valor": <monetário>}]}
        Retorna [{"transportadora": str, "peso_cobrado_kg": Decimal,
                  "frete": Decimal, "seguro": Decimal, "prazo_dias": int,
                  "total": Decimal}]"""

    def melhor_cotacao(self, pedido: dict, criterio: str) -> dict:
        """Retorna um único item, no mesmo formato de `cotar`."""
```

### Vocabulário fechado

`ErroFrete.code` assume **somente**: `REGIAO_NAO_ATENDIDA`, `TRANSPORTADORA_DESCONHECIDA`,
`DIMENSOES_INVALIDAS`, `TABELA_INVALIDA`, `PEDIDO_INVALIDO`, `SEM_COTACAO`.

O `criterio` de `melhor_cotacao` assume **somente**: `PRECO`, `PRAZO`.

---

## 2. Requisitos Funcionais

### Cálculo de peso

- **RF-01** — Peso cubado por item: `peso_cubado_item = (altura_cm × largura_cm × comprimento_cm) / fator_cubagem`, multiplicado pela `quantidade` do item.
- **RF-02** — `peso_cubado_pedido` = soma de `peso_cubado_item` de todos os itens. `peso_real_pedido` = soma de `peso_kg × quantidade` de todos os itens.
- **RF-03** — `peso_cobrado = max(peso_real_pedido, peso_cubado_pedido)`, arredondado **para cima** (teto) até o próximo múltiplo de 0,5 kg (um peso já múltiplo de 0,5 permanece inalterado). Representado como `Decimal` quantizado em 3 casas.
- **RF-04** — `peso_maximo_kg` de cada transportadora é comparado contra o `peso_cobrado` (RF-03). Excesso **exclui** a transportadora da lista de cotações — não é erro.

### Tabela de preços e seguro

- **RF-05** — Aplicação de tabela por degrau: vale a primeira faixa, na ordem em que foi cadastrada, cujo `ate_kg >= peso_cobrado`. `ate_kg` é limite superior **inclusivo**.
  - ⚠️ **Avanço sob risco (não confirmado por fonte de negócio):** quando o `peso_cobrado` é `<= peso_maximo_kg` mas excede o `ate_kg` de **todas** as faixas cadastradas (tabela com cobertura incompleta), assume-se que a transportadora é excluída silenciosamente da cotação, com o mesmo efeito de RF-04 — sem lançar erro. Ver `registro.md`, item AR-1.
- **RF-06** — Seguro: `seguro = quantize(ad_valorem × Σ(valor_item × quantidade_item), 2 casas, ROUND_HALF_EVEN)`. Quando `ad_valorem` é `None`/ausente, `seguro = Decimal("0.00")`.
- **RF-07** — `total = frete + seguro`. Todos os valores monetários são `Decimal` quantizados em 2 casas, `ROUND_HALF_EVEN`.

### Validação e erros (`ErroFrete.code`)

- **RF-08** — Ordem de validação em `cotar`: (1) estrutura do pedido, (2) dimensões dos itens, (3) região atendida, (4) disponibilidade de cotação.
- **RF-09** — `PEDIDO_INVALIDO`: `itens` ausente/vazio; `uf_destino` ou `cep_destino` ausente ou vazio (checados de forma independente — não há validação de consistência cruzada entre os dois campos); ou, em `melhor_cotacao`, `criterio` fora do vocabulário `{PRECO, PRAZO}`.
  - ⚠️ **Avanço sob risco (não confirmado por fonte de negócio):** assume-se que `melhor_cotacao` valida `criterio` **antes** (fail-fast) de aplicar a sequência de validação de `cotar` (RF-08). Ver `registro.md`, item AR-2.
- **RF-10** — `DIMENSOES_INVALIDAS`: em qualquer item — `peso_kg <= 0`, alguma dimensão `<= 0`, `quantidade < 1`, ou `valor < 0`.
- **RF-11** — `REGIAO_NAO_ATENDIDA`: nenhuma transportadora cadastrada tem `uf_destino` em sua lista `regioes`. Transportadoras fora da região são excluídas **antes** de qualquer checagem de CEP restrito ou peso; não há derivação de região a partir do `cep_destino`.
- **RF-12** — `SEM_COTACAO`: existe ao menos uma transportadora que atende a UF, mas todas foram excluídas por peso (RF-04, e a suposição de RF-05) ou por restrição de CEP (RF-22).
- **RF-13** — `cotar` nunca retorna lista vazia nem `None` — o resultado é sempre uma lista não-vazia de cotações, ou uma exceção `ErroFrete` com código `REGIAO_NAO_ATENDIDA` ou `SEM_COTACAO`.
- **RF-14** — `TABELA_INVALIDA` (levantado em `registrar_transportadora`) quando qualquer condição ocorrer: `faixas` ausente/vazia; `ate_kg` não estritamente crescente na ordem informada; algum `preco < 0`; algum `prazo_dias < 1`; `fator_cubagem <= 0`; `peso_maximo_kg <= 0`; `regioes` vazia; `ad_valorem` negativo.
- **RF-15** — `TRANSPORTADORA_DESCONHECIDA` (levantado em `registrar_restricao`) quando a restrição referencia uma transportadora ainda não registrada.

### Ordenação e seleção

- **RF-16** — Ordenação padrão de `cotar`: `total` crescente; empate por `prazo_dias` crescente; empate remanescente por nome da transportadora em ordem lexicográfica.
- **RF-17** — `melhor_cotacao(pedido, criterio="PRECO")`: seleciona menor `total`; empate por menor `prazo_dias`; empate remanescente por nome lexicográfico.
- **RF-18** — `melhor_cotacao(pedido, criterio="PRAZO")`: seleciona menor `prazo_dias`; empate por menor `total`; empate remanescente por nome lexicográfico.

### Registro e ciclo de vida

- **RF-19** — Re-registrar uma transportadora com o mesmo `nome` **substitui** a configuração anterior, mas **preserva** as restrições de CEP já cadastradas via `registrar_restricao` para essa transportadora.
- **RF-20** *(convenção, não confirmada por fonte de negócio, não-bloqueante)* — Entrada numérica pública aceita `Decimal` ou `str` em formato `"10.50"` (ponto decimal); `float` é rejeitado explicitamente para evitar erro de representação binária.
- **RF-22** — Restrição de CEP: a transportadora é excluída quando `cep_destino` **começa com** (comparação `startswith`) qualquer um de seus prefixos restritos cadastrados. A comparação usa apenas os dígitos do CEP — a máscara (hífen, pontuação) é descartada antes de comparar. Não há comprimento fixo de prefixo exigido.
- **Fora de escopo (confirmado pelo contrato obrigatório):** não existe operação de desregistro/remoção de transportadora ou de restrição de CEP — o contrato define apenas os 4 métodos públicos listados na Seção 1.

---

## 3. Requisitos Não Funcionais

- **RNF-01** — Toda aritmética monetária usa `Decimal`, quantizada em 2 casas decimais, modo `ROUND_HALF_EVEN`.
- **RNF-02** — Toda aritmética de peso usa `Decimal`, quantizada em 3 casas decimais.
- **RNF-03** — O arredondamento do peso cobrado ao múltiplo de 0,5 kg (RF-03) usa modo teto (`ROUND_CEILING` sobre unidade `Decimal("0.5")`) — distinto e não substituível pelo `ROUND_HALF_EVEN` usado para valores monetários (RNF-01).

---

## 4. Regras de negócio (resumo consolidado)

1. Peso cobrado = maior entre peso real e peso cubado, sempre arredondado **para cima** ao múltiplo de 0,5 kg mais próximo.
2. Peso cubado é calculado por item (não por caixa consolidada) e depois somado.
3. Tabela de preço é aplicada em degrau (uma única faixa vale, não é progressiva/acumulativa).
4. Seguro é sempre um percentual (`ad_valorem`) sobre o valor total declarado dos itens, nunca um valor fixo somado.
5. Uma transportadora é elegível para um pedido somente se: atende a UF de destino **e** o CEP de destino não cai em nenhum prefixo restrito **e** o peso cobrado não excede seu limite máximo.
6. `cotar` é uma função total sobre pedidos válidos: nunca devolve lista vazia — ou há cotação, ou há erro (`REGIAO_NAO_ATENDIDA` se nenhuma transportadora atende a UF; `SEM_COTACAO` se atendem a UF mas foram todas excluídas por peso/CEP).
7. Validação segue ordem fixa: estrutura do pedido → dimensões dos itens → região → disponibilidade.
8. `melhor_cotacao` sempre otimiza sobre o `total` (frete + seguro) para `PRECO`, e sobre `prazo_dias` para `PRAZO`; ambos desempatam primeiro pelo outro atributo (prazo/preço) e por último por nome lexicográfico da transportadora.

---

## 5. Critérios de aceite (Gherkin)

```gherkin
Feature: Cotação de frete multi-transportadora

  Background:
    Given uma transportadora "Rapidex" registrada com:
      | ate_kg | preco | prazo_dias |
      | 5      | 20.00 | 3          |
      | 10     | 35.00 | 3          |
    And a transportadora "Rapidex" atende a região "SP"
    And a transportadora "Rapidex" tem fator_cubagem 6000
    And a transportadora "Rapidex" tem peso_maximo_kg 10
    And a transportadora "Rapidex" tem ad_valorem 0.01

  # RF-01 / RF-02 / RF-03 — cálculo de peso cobrado
  Scenario: Peso real prevalece quando maior que o peso cubado
    Given um pedido para "SP" com um item de peso_kg 4, dimensões 10x10x10 cm, quantidade 1, valor 100.00
    When o pedido é cotado
    Then o peso_cobrado_kg da cotação da "Rapidex" é 4.0

  Scenario: Peso cubado prevalece quando maior que o peso real (pacote grande e leve)
    Given um pedido para "SP" com um item de peso_kg 1, dimensões 60x50x40 cm, quantidade 1, valor 100.00
    When o pedido é cotado
    # peso_cubado = (60*50*40)/6000 = 20.0 kg > peso real 1kg -> mas excede peso_maximo_kg 10, ver cenário de exclusão abaixo

  Scenario: Peso cobrado é arredondado para cima ao próximo múltiplo de 0,5 kg
    Given um pedido para "SP" com um item de peso_kg 4.1, dimensões 10x10x10 cm, quantidade 1, valor 100.00
    When o pedido é cotado
    Then o peso_cobrado_kg da cotação da "Rapidex" é 4.5

  # RF-05 — aplicação de tabela em degrau, ate_kg inclusivo
  Scenario: Peso cobrado igual ao limite superior de uma faixa pertence a ela
    Given um pedido para "SP" com um item de peso_kg 5, dimensões 10x10x10 cm, quantidade 1, valor 100.00
    When o pedido é cotado
    Then o frete da cotação da "Rapidex" é 20.00

  # RF-04 — exclusão silenciosa por peso máximo
  Scenario: Transportadora é excluída (sem erro) quando peso cobrado excede o peso máximo
    Given uma transportadora "SoLeve" registrada com faixas cobrindo até 5 kg e peso_maximo_kg 5, atendendo "SP"
    And um pedido para "SP" com um item de peso_kg 6, dimensões 10x10x10 cm, quantidade 1, valor 50.00
    When o pedido é cotado
    Then a lista de cotações não contém "SoLeve"
    And nenhum erro é levantado

  # RF-06 / RF-07 — seguro e total
  Scenario: Seguro é calculado como percentual do valor declarado total
    Given um pedido para "SP" com um item de peso_kg 4, dimensões 10x10x10 cm, quantidade 2, valor 100.00
    When o pedido é cotado
    Then o seguro da cotação da "Rapidex" é 2.00
    And o total da cotação da "Rapidex" é a soma do frete com o seguro

  Scenario: Seguro é zero quando ad_valorem é None
    Given uma transportadora "SemSeguro" registrada com ad_valorem None, atendendo "SP"
    And um pedido para "SP" com um item de peso_kg 4, dimensões 10x10x10 cm, quantidade 1, valor 500.00
    When o pedido é cotado
    Then o seguro da cotação da "SemSeguro" é 0.00

  # RF-09 / RF-13 — pedido inválido
  Scenario: Pedido sem itens é inválido
    Given um pedido para "SP" sem itens
    When o pedido é cotado
    Then é levantado ErroFrete com code "PEDIDO_INVALIDO"

  Scenario: Pedido sem cep_destino é inválido
    Given um pedido para "SP" com cep_destino vazio e com itens válidos
    When o pedido é cotado
    Then é levantado ErroFrete com code "PEDIDO_INVALIDO"

  # RF-10 — dimensões inválidas
  Scenario: Item com peso zero é inválido
    Given um pedido para "SP" com um item de peso_kg 0, dimensões 10x10x10 cm, quantidade 1, valor 100.00
    When o pedido é cotado
    Then é levantado ErroFrete com code "DIMENSOES_INVALIDAS"

  # RF-11 / RF-13 — região não atendida
  Scenario: Nenhuma transportadora atende a UF de destino
    Given um pedido para "AC" com itens válidos
    And nenhuma transportadora cadastrada atende "AC"
    When o pedido é cotado
    Then é levantado ErroFrete com code "REGIAO_NAO_ATENDIDA"

  # RF-12 — sem cotação disponível
  Scenario: Transportadoras atendem a região mas todas ficam inviáveis por peso
    Given uma transportadora "SoLeve" registrada com peso_maximo_kg 5, atendendo "SP"
    And um pedido para "SP" com um item de peso_kg 100, dimensões 10x10x10 cm, quantidade 1, valor 100.00
    When o pedido é cotado
    Then é levantado ErroFrete com code "SEM_COTACAO"

  # RF-14 — tabela inválida no registro
  Scenario: Registro de transportadora com faixas fora de ordem é rejeitado
    When registro a transportadora "Errada" com faixas cujo ate_kg não é estritamente crescente
    Then é levantado ErroFrete com code "TABELA_INVALIDA"

  # RF-15 — restrição sobre transportadora inexistente
  Scenario: Restringir CEP de transportadora não registrada é erro
    When registro uma restrição de CEP para a transportadora "Inexistente"
    Then é levantado ErroFrete com code "TRANSPORTADORA_DESCONHECIDA"

  # RF-16 — ordenação padrão de cotar
  Scenario: Cotações são ordenadas por total crescente
    Given duas transportadoras viáveis com totais diferentes para o mesmo pedido
    When o pedido é cotado
    Then a lista de cotações retornada está ordenada por total crescente

  # RF-17 / RF-18 — melhor_cotacao
  Scenario: melhor_cotacao com criterio PRECO retorna o menor total
    Given duas transportadoras viáveis com totais diferentes para o mesmo pedido
    When solicito a melhor cotação com criterio "PRECO"
    Then a cotação retornada é a de menor total

  Scenario: melhor_cotacao com criterio PRAZO retorna o menor prazo_dias
    Given duas transportadoras viáveis com prazos diferentes para o mesmo pedido
    When solicito a melhor cotação com criterio "PRAZO"
    Then a cotação retornada é a de menor prazo_dias

  Scenario: melhor_cotacao com criterio fora do vocabulário é erro
    Given um pedido válido
    When solicito a melhor cotação com criterio "FRETE_GRATIS"
    Then é levantado ErroFrete com code "PEDIDO_INVALIDO"

  # RF-19 — re-registro preserva restrições
  Scenario: Re-registrar uma transportadora preserva as restrições de CEP já cadastradas
    Given a transportadora "Rapidex" tem uma restrição cadastrada para o prefixo "01"
    When a transportadora "Rapidex" é registrada novamente com uma nova configuração de faixas
    And um pedido é feito para o CEP "01000-000"
    Then a "Rapidex" continua excluída da cotação por causa da restrição de prefixo "01"

  # RF-22 — restrição por CEP com máscara
  Scenario: Restrição de CEP casa independentemente de máscara
    Given a transportadora "Rapidex" tem uma restrição cadastrada para o prefixo "01310"
    When um pedido é feito para o CEP "01310-100"
    Then a "Rapidex" é excluída da lista de cotações

  # Cenários sob risco (opção B do SFAR) — ver registro.md AR-1 e AR-2
  @suposicao-nao-validada
  Scenario: Peso cobrado excede a última faixa cadastrada (AR-1 — comportamento assumido, não confirmado)
    Given uma transportadora "TabelaCurta" registrada com faixas cobrindo até 5 kg e peso_maximo_kg 20, atendendo "SP"
    And um pedido para "SP" com um item cujo peso cobrado calculado é 8 kg
    When o pedido é cotado
    Then a "TabelaCurta" é excluída silenciosamente da lista de cotações, sem erro
    # Suposição não validada pela fonte de negócio — revalidar antes de travar este comportamento em produção.

  @suposicao-nao-validada
  Scenario: Ordem de validação de criterio em melhor_cotacao (AR-2 — comportamento assumido, não confirmado)
    Given um pedido inválido (itens vazio) e um criterio fora do vocabulário simultaneamente
    When solicito a melhor cotação
    Then é levantado ErroFrete com code "PEDIDO_INVALIDO"
    # A causa exata (criterio invalido vs estrutura do pedido) não é distinguível pelo code;
    # ordem de checagem assumida como fail-fast em criterio, não confirmada pela fonte de negócio.
```
