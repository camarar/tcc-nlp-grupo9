# UC-03 — Motor de Precificação e Promoções — Especificação Técnica Consolidada

> Produzida pelo pipeline de 3 agentes de requisitos (condição C2):
> `working-backwards-designer` → `working-backwards-analyst` → `senior-functional-analyst-reviewer`.
> Toda regra de negócio abaixo corresponde a uma pergunta efetivamente formulada por um dos
> agentes e respondida pelo coordenador (ver `registro.md` para a rastreabilidade completa).
> Nenhum requisito foi copiado ou parafraseado em bloco de fonte alguma — apenas o que foi
> elicitado via pergunta e resposta está incorporado.

## 1. Visão geral

Motor de precificação para e-commerce que cota pedidos combinando campanhas promocionais
por categoria com cupons de checkout, calcula o valor líquido por item (usado pelo
financeiro para estornos) e expõe uma trilha de auditoria (`explicar()`) do cálculo.

## 2. Contrato obrigatório (copiado literalmente do enunciado)

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

### Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.

## 3. Requisitos Funcionais (RF)

### RF-01 — Ordem de aplicação de descontos
Campanhas aplicam-se primeiro, sobre os itens elegíveis por categoria; cupons incidem
depois, em **cascata**, sobre o subtotal já descontado pelas campanhas (não é um cálculo
paralelo/aditivo sobre o preço bruto).

### RF-02 — Uma campanha vigente por categoria
Havendo mais de uma campanha ativa para a mesma categoria, aplica-se apenas a de **maior
percentual**; em caso de empate, prevalece a **registrada primeiro** (ordem de chamada de
`registrar_campanha`). Uma campanha cuja `categoria` não corresponde a nenhum item do
pedido simplesmente não se aplica (contribuição de desconto 0,00, sem erro, sem entrada na
trilha) — comportamento simétrico ao de cupom sem itens elegíveis (RF-05).

### RF-03 — Ordem entre cupons
Cupons do tipo `PERCENTUAL` aplicam-se todos primeiro, na ordem da lista `cupons` recebida
em `cotar()`; depois todos os do tipo `FIXO`, também na ordem da lista. Cada cupom incide
sobre o valor remanescente após o cupom anterior (cascata sequencial). `FRETE_GRATIS` é
aplicado por último e não altera o subtotal de produtos.

### RF-04 — Acumulação de cupons
Um cupom com `acumulavel=False` só pode ser usado sozinho: se a lista de cupons de
`cotar()` contiver esse cupom **e** qualquer outro cupom distinto, lança
`ErroPrecificacao("CUPOM_NAO_ACUMULAVEL")`, abortando a cotação inteira. Cupons acumuláveis
combinam livremente entre si.

### RF-05 — Cupom com categorias restritas
Quando `categorias` do cupom não é `None`, o cupom (`PERCENTUAL` ou `FIXO`) incide apenas
sobre a parcela do subtotal correspondente a essas categorias (já descontada por
campanhas) — nunca "vaza" para outras categorias. Se nenhum item do pedido pertencer às
categorias do cupom, o desconto desse cupom é `0.00` — não é erro, e não gera entrada na
trilha.

### RF-06 — Teto de desconto
A soma de (desconto de campanhas + desconto de cupons) não pode ultrapassar **50% do
subtotal original** de produtos. `FRETE_GRATIS` não entra nessa conta. Ao ultrapassar, o
corte é um **ajuste único e final** — os valores individuais de campanha e cupom mantêm-se
como calculados na cascata — e a trilha de `explicar()` recebe uma entrada adicional final
de origem `TETO`, cujo `valor` é a **magnitude positiva** do corte aplicado (mesma
convenção de magnitude positiva já usada nas demais origens, inclusive `FRETE`) e cuja
`base` é o subtotal original (referência do limite de 50%). O `desconto_total` retornado
por `cotar()` já é o valor **pós-teto**, e é esse valor que alimenta o rateio por item
(RF-08).

### RF-07 — Arredondamento
Todo valor monetário é `Decimal` quantizado em 2 casas com `ROUND_HALF_EVEN`, aplicado a
cada desconto individual (campanha, cupom, rateio por item) e ao total.

### RF-08 — Rateio de desconto por item
O `desconto_total` (já líquido do corte do teto) é rateado entre **todos** os itens do
pedido proporcionalmente ao `preco_bruto` de cada item, quantizado em 2 casas, com o
resíduo de arredondamento alocado ao item de maior `preco_bruto` (empate: menor `sku` em
ordem lexicográfica), de modo que `Σ desconto_rateado == desconto_total` exatamente.
`preco_liquido = preco_bruto - desconto_rateado`. A elegibilidade de categoria de um cupom
individual (RF-05) afeta apenas o cálculo do **valor** desse cupom — não restringe a
distribuição final do desconto agregado entre os itens.

> **Pendência não bloqueante:** não foi confirmado se `preco_bruto`, para fins do critério
> de desempate do resíduo, é o preço unitário ou o valor de linha (`preco_unitario ×
> quantidade`). Assume-se **valor de linha** como leitura mais provável dado o formato do
> dict de retorno de `itens`, mas isso não foi confirmado pela fonte de negócio — ver
> `registro.md`.

### RF-09 — Cupom `FRETE_GRATIS`
Zera o campo `frete` integralmente e gera entrada na trilha de origem `FRETE` com `valor`
igual ao frete original (magnitude positiva). Se houver mais de um `FRETE_GRATIS` na mesma
cotação, apenas o primeiro tem efeito, sem erro (respeitada a regra de acumulação RF-04). O
valor do frete dispensado **não** entra em `desconto_cupons`, `desconto_total`, nem na
conta do teto (RF-06) — só reduz o campo `frete` e aparece na trilha.

### RF-10 — Pedido mínimo
`pedido_minimo` do cupom é avaliado sobre o **subtotal original completo** do pedido (soma
de todos os itens, antes de qualquer desconto), independentemente de o cupom ter restrição
de `categorias`. `subtotal == pedido_minimo` é aceito (comparação inclusiva). Se o subtotal
for menor, lança `ErroPrecificacao("PEDIDO_MINIMO")`.

### RF-11 — Ordem de validação em `cotar()`
Sequência fixa: (1) itens do pedido; (2) existência e duplicidade dos cupons na lista; (3)
acumulação; (4) validade; (5) pedido mínimo. O primeiro problema encontrado interrompe a
cotação com o `ErroPrecificacao` correspondente.

### RF-12 — `ITEM_INVALIDO`
Lançado quando: lista de itens vazia ou ausente; `quantidade < 1`; `preco_unitario < 0`;
`sku` vazio; `sku` repetido no mesmo pedido; `frete < 0`.

> **Pendência não bloqueante:** não foi confirmado se `categoria` ausente/vazia em um item
> deveria também disparar `ITEM_INVALIDO` — ver `registro.md`.

### RF-13 — `CUPOM_INVALIDO`
Lançado quando: código de cupom não registrado (referenciado em `cotar()`); o mesmo código
aparece duas vezes na lista `cupons` de uma cotação; tentativa de registrar (em
`registrar_cupom`) um código já existente; `tipo` fora do vocabulário fechado; `valor`
negativo; cupom `PERCENTUAL` com `valor` maior que 1.

### RF-14 — `CUPOM_EXPIRADO`
Lançado quando `data > validade` do cupom. A validade é **inclusiva**: `data == validade`
ainda é aceito. O cupom não possui conceito de vigência futura — seu único controle
temporal é `validade` (diferente de campanha, que tem `inicio` e `fim`).

### RF-15 — `CAMPANHA_INVALIDA`
Lançado em `registrar_campanha` quando: `percentual <= 0` ou `> 1`; `inicio > fim`;
`categoria` vazia. Não ocorre durante `cotar()` — uma campanha "órfã" (sem itens elegíveis
no pedido) apenas não se aplica (RF-02), sem erro.

### RF-16 — Estrutura de `explicar()`
Lista ordenada com **uma entrada por desconto efetivamente aplicado** (granularidade por
origem/aplicação, não por item), na ordem de aplicação: campanhas (`origem="CAMPANHA"`,
`referencia`=nome da campanha), cupons (`origem="CUPOM"`, `referencia`=código do cupom),
frete grátis (`origem="FRETE"`) e, se houve corte pelo teto, a entrada final
(`origem="TETO"`). `base` é o valor sobre o qual aquele desconto específico incidiu;
`valor` é o desconto concedido (ou, no caso de `TETO`, a magnitude do corte — sempre
positivo; a semântica de redução é comunicada pelo campo `origem`, não pelo sinal do
número). Descontos de valor `0.00` (ex.: cupom/campanha sem itens elegíveis) **não** geram
entrada na trilha.

## 4. Requisitos Não Funcionais (RNF)

### RNF-01 — Precisão monetária
Toda a aritmética monetária usa `decimal.Decimal`; entradas monetárias podem chegar como
`str`, `int`, `float` ou `Decimal` e devem ser normalizadas para `Decimal` internamente.
Implementação restrita a Python 3.12 stdlib (sem dependências externas).

### RNF-02 — Escopo de estado e persistência (avanço sob risco — RISCO-02)
O motor opera exclusivamente sobre o estado registrado na própria instância e os parâmetros
fornecidos em cada chamada. Esta especificação **não** garante persistência de
campanhas/cupons entre processos, nem define um mecanismo de recálculo de `preco_liquido`
para estorno de um subconjunto de itens de um pedido já cotado. Essas capacidades, se
necessárias, ficam fora do escopo desta versão — ver `registro.md`.

### RNF-03 — Liberdade de implementação de identificadores (avanço sob risco — RISCO-03)
O formato do `str` retornado por `registrar_campanha`/`registrar_cupom` não é definido por
regra de negócio (pode ser um id gerado, o próprio nome, ou o próprio código). Também não
há regra de negócio para registro de campanha com `nome` duplicado (diferente de cupom,
onde código duplicado é `CUPOM_INVALIDO` por RF-13). Tratado como decisão de implementação.

## 5. Premissas assumidas como avanço sob risco (SFAR opção B)

| ID | Premissa assumida | Por quê não há resposta confirmada |
|---|---|---|
| RISCO-01 | Cupom `FIXO` cujo valor nominal excede a base sobre a qual incide (subtotal elegível, considerando eventual restrição de `categorias`) satura o desconto em zero — nunca gera `preco_liquido` negativo nem "vaza" para outra base. | Fonte de negócio não define esse caso de borda explicitamente. |
| RISCO-02 | Sem persistência garantida entre processos; sem mecanismo de recálculo de rateio para estorno parcial de subconjunto de itens. | Fora do que o contrato técnico e a fonte de regras de negócio definem — a fonte trata apenas de regras de cálculo de uma única chamada. |
| RISCO-03 | Formato do identificador retornado por `registrar_campanha`/`registrar_cupom`, e ausência de erro específico para campanha com nome duplicado. | Não há regra de negócio nem código de erro associado no vocabulário fechado. |

## 6. Pendências não bloqueantes (não impedem implementação, recomenda-se confirmar em refinamento)

1. `preco_bruto` no critério de desempate do rateio (RF-08): preço unitário ou valor de linha? (assume-se valor de linha)
2. `FRETE_GRATIS` quando `frete` do pedido de entrada já é `0.00`: gera entrada de trilha com `valor=0.00` (o que RF-16 diz não gerar) ou é tratado como caso especial?
3. `FRETE_GRATIS` está sujeito às mesmas checagens de `pedido_minimo`/`categorias` que `PERCENTUAL`/`FIXO`? (assume-se que sim, por RF-10 e RF-05 serem genéricas)
4. `categoria` ausente/vazia em um item do pedido deveria disparar `ITEM_INVALIDO` (RF-12)?
5. Confirmação textual explícita de que alteração e suspensão manual de campanhas/cupons já registrados estão fora do escopo do UC-03 (inferido da ausência desses métodos no contrato técnico).

## 7. Critérios de Aceite (Gherkin)

```gherkin
# RF-01 — Ordem de aplicação: campanha primeiro, cupom em cascata
Funcionalidade: Ordem de aplicação de descontos

  Cenário: Campanha de categoria aplica antes do cupom percentual
    Dado uma campanha "VERAO10" de 10% na categoria "roupas", vigente na data da cotação
    E um cupom "DESC10" do tipo PERCENTUAL com valor 0.10, acumulável
    E um pedido com um item da categoria "roupas", preco_unitario 100.00, quantidade 1, frete 0.00
    Quando cotar() é chamado com o cupom "DESC10" na data vigente
    Então o subtotal é 100.00
    E o desconto_campanhas é 10.00
    E o cupom incide sobre 90.00 (subtotal já descontado pela campanha), gerando desconto_cupons de 9.00
    E o desconto_total é 19.00
    E o total é 81.00 mais o frete

# RF-02 — Duas campanhas na mesma categoria, desempate por percentual e por ordem de registro
Funcionalidade: Precedência entre campanhas da mesma categoria

  Cenário: Duas campanhas ativas na mesma categoria, percentuais diferentes
    Dado a campanha "A" de 5% na categoria "livros", registrada primeiro
    E a campanha "B" de 15% na categoria "livros", registrada depois
    E ambas vigentes na data da cotação
    Quando cotar() é chamado para um item da categoria "livros"
    Então apenas a campanha "B" (maior percentual) é aplicada
    E explicar() não contém entrada referente à campanha "A"

  Cenário: Duas campanhas ativas na mesma categoria, percentuais empatados
    Dado a campanha "A" de 10% na categoria "livros", registrada primeiro
    E a campanha "B" de 10% na categoria "livros", registrada depois
    Quando cotar() é chamado para um item da categoria "livros"
    Então apenas a campanha "A" (registrada primeiro) é aplicada

  Cenário: Campanha sem itens elegíveis no pedido
    Dado a campanha "ELETRO20" de 20% na categoria "eletronicos", vigente
    E um pedido cujo único item é da categoria "livros"
    Quando cotar() é chamado
    Então o desconto_campanhas é 0.00
    E explicar() não contém nenhuma entrada de origem CAMPANHA
    E nenhum erro é lançado

# RF-03 — Ordem entre cupons (PERCENTUAL antes de FIXO, cascata)
Funcionalidade: Ordem de aplicação entre cupons acumuláveis

  Cenário: Cupom PERCENTUAL aplica antes de cupom FIXO independentemente da ordem na lista
    Dado um cupom "FIXO20" do tipo FIXO com valor 20.00, acumulável
    E um cupom "PERC10" do tipo PERCENTUAL com valor 0.10, acumulável
    E um pedido sem campanhas, subtotal de produtos 200.00
    Quando cotar() é chamado com cupons=["FIXO20", "PERC10"] (FIXO listado antes do PERCENTUAL)
    Então o cupom PERC10 (PERCENTUAL) incide primeiro sobre 200.00, gerando desconto de 20.00
    E o cupom FIXO20 incide depois sobre o remanescente de 180.00
    E a trilha de explicar() lista a entrada de CUPOM "PERC10" antes da entrada de CUPOM "FIXO20"

# RF-04 — Acumulação
Funcionalidade: Regra de acumulação de cupons

  Cenário: Cupom não acumulável usado sozinho
    Dado um cupom "EXCLUSIVO" com acumulavel=False
    Quando cotar() é chamado apenas com cupons=["EXCLUSIVO"]
    Então a cotação é bem-sucedida e o desconto do cupom é aplicado normalmente

  Cenário: Cupom não acumulável combinado com outro cupom
    Dado um cupom "EXCLUSIVO" com acumulavel=False
    E um cupom "OUTRO" acumulável
    Quando cotar() é chamado com cupons=["EXCLUSIVO", "OUTRO"]
    Então é lançado ErroPrecificacao com code "CUPOM_NAO_ACUMULAVEL"

# RF-05 — Cupom com categorias restritas
Funcionalidade: Restrição de categoria em cupom

  Cenário: Cupom restrito a categoria sem itens correspondentes no pedido
    Dado um cupom "SOLIVROS" do tipo PERCENTUAL, valor 0.10, categorias=["livros"]
    E um pedido cujo único item é da categoria "eletronicos"
    Quando cotar() é chamado com cupons=["SOLIVROS"]
    Então o desconto desse cupom é 0.00
    E nenhum erro é lançado
    E explicar() não contém entrada de CUPOM referente a "SOLIVROS"

# RF-06 — Teto de desconto de 50%
Funcionalidade: Teto de desconto sobre o subtotal original

  Cenário: Soma de descontos ultrapassa 50% do subtotal original
    Dado uma campanha de 30% e um cupom PERCENTUAL de 0.30 (acumulável), ambos aplicáveis ao mesmo item
    E um pedido com subtotal de produtos 100.00
    Quando cotar() é chamado
    Então o desconto_total não ultrapassa 50.00 (50% de 100.00)
    E explicar() contém uma entrada final com origem "TETO" e valor igual ao excedente cortado (magnitude positiva)
    E o total reflete o desconto já limitado ao teto

  Cenário: Frete grátis não entra na conta do teto
    Dado uma campanha de 45% aplicada a um item, subtotal de produtos 100.00
    E um cupom FRETE_GRATIS acumulável, pedido com frete 20.00
    Quando cotar() é chamado
    Então o desconto de campanha (45.00) não é afetado pelo teto isoladamente por conta do frete grátis
    E o campo frete retornado é 0.00
    E o valor do frete dispensado não é somado a desconto_cupons nem a desconto_total

# RF-07 — Arredondamento
Funcionalidade: Arredondamento bancário em 2 casas

  Cenário: Divisão de desconto entre itens gera dízima
    Dado três itens de preco_bruto 33.33, 33.33 e 33.34 (subtotal 100.00)
    E um desconto_total de 10.00 a ratear
    Quando o rateio é calculado
    Então cada desconto_rateado é quantizado em 2 casas com ROUND_HALF_EVEN
    E a soma de todos os desconto_rateado é exatamente igual a 10.00

# RF-08 — Rateio por item com resíduo
Funcionalidade: Rateio proporcional de desconto entre itens

  Cenário: Resíduo de arredondamento vai para o item de maior preco_bruto
    Dado dois itens: SKU "A" com preco_bruto 66.67 e SKU "B" com preco_bruto 33.33
    E um desconto_total de 10.00
    Quando o rateio é calculado
    Então o item "A" (maior preco_bruto) recebe o resíduo de arredondamento, se houver
    E desconto_rateado("A") + desconto_rateado("B") == 10.00 exatamente
    E preco_liquido de cada item == preco_bruto - desconto_rateado

# RF-09 — Frete grátis
Funcionalidade: Cupom FRETE_GRATIS

  Cenário: Frete grátis zera o frete e aparece na trilha
    Dado um pedido com frete 25.00
    E um cupom "FRETEGRATIS" do tipo FRETE_GRATIS, acumulável
    Quando cotar() é chamado com cupons=["FRETEGRATIS"]
    Então o campo frete retornado é 0.00
    E explicar() contém uma entrada {origem: "FRETE", referencia: "FRETEGRATIS", valor: 25.00}
    E desconto_cupons e desconto_total não incluem os 25.00

  Cenário: Múltiplos cupons de frete grátis — apenas o primeiro tem efeito
    Dado dois cupons FRETE_GRATIS acumuláveis, "FRETE1" e "FRETE2"
    Quando cotar() é chamado com cupons=["FRETE1", "FRETE2"]
    Então nenhum erro é lançado
    E apenas a entrada referente a "FRETE1" aparece na trilha com origem "FRETE"

# RF-10 — Pedido mínimo
Funcionalidade: Validação de pedido mínimo

  Cenário: Subtotal igual ao pedido mínimo é aceito
    Dado um cupom com pedido_minimo 100.00
    E um pedido com subtotal de produtos exatamente 100.00
    Quando cotar() é chamado com esse cupom
    Então a cotação é bem-sucedida

  Cenário: Subtotal abaixo do pedido mínimo é rejeitado
    Dado um cupom com pedido_minimo 100.00
    E um pedido com subtotal de produtos 99.99
    Quando cotar() é chamado com esse cupom
    Então é lançado ErroPrecificacao com code "PEDIDO_MINIMO"

# RF-11 — Ordem de validação
Funcionalidade: Ordem de validação de erros em cotar()

  Cenário: Item inválido tem prioridade sobre cupom inválido
    Dado um pedido com um item de quantidade 0 (ITEM_INVALIDO)
    E um cupom inexistente na lista de cupons
    Quando cotar() é chamado
    Então é lançado ErroPrecificacao com code "ITEM_INVALIDO" (não CUPOM_INVALIDO)

# RF-12 — ITEM_INVALIDO
Funcionalidade: Validação de itens do pedido

  Esquema do Cenário: Condições que disparam ITEM_INVALIDO
    Dado um pedido com <condição>
    Quando cotar() é chamado
    Então é lançado ErroPrecificacao com code "ITEM_INVALIDO"

    Exemplos:
      | condição                          |
      | lista de itens vazia              |
      | quantidade igual a 0               |
      | preco_unitario negativo            |
      | sku vazio                          |
      | sku repetido no mesmo pedido       |
      | frete negativo                     |

# RF-13 — CUPOM_INVALIDO
Funcionalidade: Validação de cupons

  Cenário: Código de cupom não registrado
    Quando cotar() é chamado com cupons=["INEXISTENTE"]
    Então é lançado ErroPrecificacao com code "CUPOM_INVALIDO"

  Cenário: Código de cupom duplicado na lista de cotação
    Dado um cupom válido "DESC10"
    Quando cotar() é chamado com cupons=["DESC10", "DESC10"]
    Então é lançado ErroPrecificacao com code "CUPOM_INVALIDO"

  Cenário: Registro de cupom com código já existente
    Dado um cupom "DESC10" já registrado
    Quando registrar_cupom() é chamado novamente com codigo="DESC10"
    Então é lançado ErroPrecificacao com code "CUPOM_INVALIDO"

# RF-14 — CUPOM_EXPIRADO
Funcionalidade: Validade do cupom

  Cenário: Data igual à validade ainda é aceita
    Dado um cupom com validade 2026-08-11
    Quando cotar() é chamado na data 2026-08-11
    Então a cotação é bem-sucedida

  Cenário: Data após a validade é rejeitada
    Dado um cupom com validade 2026-08-11
    Quando cotar() é chamado na data 2026-08-12
    Então é lançado ErroPrecificacao com code "CUPOM_EXPIRADO"

# RF-15 — CAMPANHA_INVALIDA
Funcionalidade: Validação de campanha no registro

  Esquema do Cenário: Condições que disparam CAMPANHA_INVALIDA em registrar_campanha
    Quando registrar_campanha() é chamado com <condição>
    Então é lançado ErroPrecificacao com code "CAMPANHA_INVALIDA"

    Exemplos:
      | condição                       |
      | percentual igual a 0            |
      | percentual maior que 1          |
      | inicio posterior a fim          |
      | categoria vazia                 |

# RF-16 — Estrutura da trilha explicar()
Funcionalidade: Trilha de explicação da cotação

  Cenário: Trilha reflete apenas descontos efetivamente aplicados, na ordem de aplicação
    Dado uma campanha de 10% e um cupom PERCENTUAL acumulável de 0.05 aplicáveis ao pedido
    E o desconto total não ultrapassa o teto de 50%
    Quando explicar() é chamado
    Então a lista retornada contém, nesta ordem: uma entrada origem="CAMPANHA", depois uma entrada origem="CUPOM"
    E nenhuma entrada de valor 0.00 está presente
```
