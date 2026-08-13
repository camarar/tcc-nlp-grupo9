# UC-14 — Especificação Técnica Consolidada — Motor de Cálculo Tributário por UF e NCM

> Produzida pelo pipeline de 3 agentes de requisitos (condição C2): `working-backwards-designer`
> → `working-backwards-analyst` → `senior-functional-analyst-reviewer`. Cada requisito abaixo
> só incorpora o que foi efetivamente elicitado pelos agentes por meio de perguntas — não é
> uma cópia do gabarito de decisões, que serviu exclusivamente para responder às perguntas
> bloqueantes registradas em `registro.md`.

## Veredito de prontidão do pipeline

`PRONTO PARA SOLUÇÃO SOB RISCO REGISTRADO` (veredito final do `senior-functional-analyst-reviewer`,
após 2 rodadas de perguntas bloqueantes). Uma premissa segue como **avanço sob risco** (opção B
do SFAR — ver `registro.md`): RNF-01 (política de tratamento de entradas numéricas/monetárias não
conversíveis de forma inequívoca para `Decimal`).

---

## Requisitos Funcionais (RF)

### RF-01 — Validação de nota (`NOTA_INVALIDA`)
`calcular(nota)` e `memoria_calculo(nota)` devem lançar `ErroTributario(code="NOTA_INVALIDA")`
quando: `itens` está vazio ou ausente; `frete < 0`; `uf_destino` está ausente ou tem tamanho
diferente de 2; `cnpj_emitente` está ausente ou vazio.

### RF-02 — Validação de item (`ITEM_INVALIDO`)
Para qualquer item da nota, `ErroTributario(code="ITEM_INVALIDO")` quando: `valor < 0`;
`quantidade < 1` (inclui zero e negativos); `desconto < 0`; `desconto > valor × quantidade`;
`ncm` ausente, vazio ou não numérico.

### RF-03 — Validação de cadastro (`TABELA_INVALIDA`)
`registrar_aliquota(uf, ncm, aliquota, mva)` deve lançar `ErroTributario(code="TABELA_INVALIDA")`
quando: `aliquota <= 0` ou `aliquota > 1`; `mva < 0` (quando informado); `ncm` com menos de 4
dígitos, vazio ou não numérico; `uf` com tamanho diferente de 2. A mesma validação de `ncm` e
`uf` se aplica a `registrar_isencao(uf, ncm)`. Em `registrar_regime(cnpj, regime)`, `regime` fora
do vocabulário fechado `{"SIMPLES", "NORMAL"}` também dispara `TABELA_INVALIDA` (não
`REGIME_DESCONHECIDO` — esse código é reservado exclusivamente à ausência de regime cadastrado no
momento de `calcular`, ver RF-11).

`TABELA_INVALIDA` só pode ser lançado dentro dos três métodos de cadastro (`registrar_aliquota`,
`registrar_isencao`, `registrar_regime`) — nunca dentro de `calcular()` ou `memoria_calculo()`; a
validação de cadastro ocorre sempre no momento do próprio registro, não é diferida.

### RF-04 — Ordem de validação (precedência)
Dentro de `calcular()` e `memoria_calculo()`, as validações ocorrem estritamente nesta ordem:
(1) `NOTA_INVALIDA`, (2) `ITEM_INVALIDO`, (3) `REGIME_DESCONHECIDO` (checagem do CNPJ emitente,
em nível de nota inteira — precede a checagem de alíquota por item), (4)
`ALIQUOTA_NAO_CADASTRADA`. `TABELA_INVALIDA` está fora dessa ordem por não poder ocorrer nesses
dois métodos (ver RF-03).

### RF-05 — Resolução de alíquota (busca exata e por prefixo)
Para cada item não isento, a busca de alíquota ocorre nesta sequência, restrita à UF de destino
da nota (a busca **nunca cruza UFs**): (1) NCM exato cadastrado na UF; (2) na ausência do exato,
o prefixo cadastrado mais longo que case com o início do NCM do item, respeitado o mínimo de 4
dígitos. Se nenhuma das duas buscas resolver, `ErroTributario(code="ALIQUOTA_NAO_CADASTRADA")` é
lançado, abortando o cálculo da nota inteira (não há processamento parcial nem retorno parcial).
Registrar novamente o mesmo par UF/NCM substitui a alíquota e o MVA anteriormente cadastrados.

### RF-06 — Isenção
`registrar_isencao(uf, ncm)` vale apenas para o NCM **exato** cadastrado na UF — não há busca por
prefixo para isenção, ao contrário da alíquota (RF-05). Uma isenção registrada prevalece sobre a
alíquota cadastrada para o mesmo par exato. Um item isento fica fora da base de cálculo agregada,
tem `icms` e `icms_st` iguais a `0.00`, `aliquota` e `ncm_aplicado` iguais a `None`, e não exige
alíquota cadastrada para esse par.

### RF-07 — Base de cálculo
Para cada item não isento, `base_item = valor × quantidade − desconto`. O frete **não** entra na
base de cálculo do ICMS. `base_calculo` (retorno agregado de `calcular`) é a soma de `base_item`
apenas dos itens não isentos.

### RF-08 — ICMS próprio
`icms_item = quantize(base_item × aliquota, 2 casas, ROUND_HALF_EVEN)`. Em regime `NORMAL`, o
valor é integral. Em regime `SIMPLES`, `icms_item` é reduzido à metade do valor calculado para
`NORMAL`, novamente quantizado: `quantize(icms_item_normal × 0.5, 2 casas, ROUND_HALF_EVEN)`.
`icms` (retorno agregado) é a soma dos `icms_item` já quantizados individualmente — a quantização
ocorre por item, antes de agregar, nunca após somar valores não quantizados.

### RF-09 — Substituição tributária (ICMS-ST)
Só se aplica quando o cadastro de alíquota aplicado ao item (após a resolução de RF-05) tem `mva`
definido: `icms_st_item = quantize(base_item × (1 + mva) × aliquota, 2 casas, ROUND_HALF_EVEN) −
icms_item`, com piso em `0.00` (nunca negativo). Sem `mva` cadastrado, `icms_st_item` é `0.00`.
Em regime `SIMPLES`, `icms_st_item` é sempre `0.00`, **incondicionalmente** — mesmo quando há
`mva` cadastrado para o par UF/NCM aplicado; não há exceção a essa regra. `icms_st` (retorno
agregado) é a soma dos `icms_st_item`.

### RF-10 — Regime tributário
`registrar_regime(cnpj, regime)` aceita somente `regime` em `{"SIMPLES", "NORMAL"}` (ver RF-03
para o erro em caso contrário). Registrar novamente um CNPJ substitui o regime anteriormente
cadastrado.

### RF-11 — Regime obrigatório ao calcular
Se o CNPJ emitente da nota não tem regime cadastrado, `calcular()` e `memoria_calculo()` sempre
lançam `ErroTributario(code="REGIME_DESCONHECIDO")` — não existe regime default/implícito. Essa
checagem ocorre em nível de nota inteira e precede a checagem de alíquota por item (RF-04):
mesmo que a nota também tenha item com par UF/NCM não cadastrado, o erro retornado é
`REGIME_DESCONHECIDO`.

### RF-12 — Totais da nota
`total_tributos = icms + icms_st`. `total_nota` é a soma de `(valor × quantidade − desconto)` de
**todos** os itens da nota, inclusive os isentos, mais `frete`, mais `icms_st`. O ICMS próprio já
está embutido no preço de cada item e **não** é somado separadamente ao `total_nota`.

### RF-13 — Memória de cálculo
`memoria_calculo(nota)` retorna uma entrada por item, na ordem em que aparecem na nota, com as
chaves `{"ncm", "ncm_aplicado", "aliquota", "base", "icms", "icms_st", "isento"}`; `ncm_aplicado`
reflete a chave do cadastro efetivamente usada (o NCM exato ou o prefixo resolvido conforme
RF-05), ou `None` quando o item é isento. `memoria_calculo` aplica **exatamente** as mesmas
validações e os mesmos erros de `calcular` para a mesma nota (mesmo `code`, mesma ordem de
precedência de RF-04) — não há retorno parcial em caso de erro; o comportamento é espelhado ao de
`calcular`.

### RF-14 — Vocabulário fechado de erros (mapeamento)

| Código | Cenário de disparo |
|---|---|
| `NOTA_INVALIDA` | Ver RF-01 |
| `ITEM_INVALIDO` | Ver RF-02 |
| `TABELA_INVALIDA` | Ver RF-03 — só ocorre em `registrar_aliquota`, `registrar_isencao` e `registrar_regime` |
| `REGIME_DESCONHECIDO` | CNPJ emitente sem regime cadastrado, ao chamar `calcular`/`memoria_calculo` — ver RF-11 |
| `ALIQUOTA_NAO_CADASTRADA` | Nenhum NCM exato nem prefixo (≥4 dígitos) cadastrado na UF, para algum item não isento — ver RF-05 |

`regime` do dicionário de cadastro assume somente `SIMPLES` ou `NORMAL`.

---

## Requisitos Não Funcionais (RNF)

### RNF-01 — Precisão monetária
Todo valor monetário é `decimal.Decimal`, quantizado em exatamente 2 casas decimais com
`ROUND_HALF_EVEN` em todos os pontos de cálculo (quantização por item, antes de agregar — nunca
quantização única após somar valores não quantizados). `aliquota` e `mva` são frações decimais
(`0.18` = 18%, não percentual inteiro).

### RNF-02 — Conversão de tipos de entrada
`[AVANÇO SOB RISCO — não confirmado]` O contrato permite que entradas monetárias e numéricas
cheguem como `str`, `int`, `float` ou `Decimal`, mas não foi confirmado pela fonte de negócio como
o motor deve tratar falha ou ambiguidade na conversão desses valores para `Decimal` — por exemplo,
strings não numéricas, `None`, valores especiais (`NaN`, `Infinity`), formatos regionais
(separador decimal `,`), ou `float` que introduz erro de representação binária antes da conversão.
Não há hipótese de trabalho adotada por nenhum dos agentes; a implementação deve tratar esta
lacuna como premissa assumida sob risco, documentada de forma explícita no código, até validação
posterior pela fonte de negócio.

### RNF-03 — Escopo
Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão — sem dependências externas.
Persistência duradoura fora do processo, autenticação/autorização e observabilidade
(logs/métricas) não fazem parte do contrato de `MotorTributario`; o motor opera em memória durante
o processo, com o estado de cadastro (alíquotas, isenções, regimes) mantido via os métodos
`registrar_*`.

---

## Regras de Negócio (consolidado)

- RN-01: par UF/NCM sem alíquota aplicável (nem exato, nem prefixo ≥4 dígitos) sempre aborta a
  nota inteira com `ALIQUOTA_NAO_CADASTRADA` — nunca alíquota padrão, nunca alíquota de outra UF,
  nunca isenção por omissão.
- RN-02: a busca de alíquota por prefixo nunca cruza UFs.
- RN-03: isenção exige correspondência exata de NCM — não há busca por prefixo para isenção.
- RN-04: isenção registrada prevalece sobre alíquota cadastrada do mesmo par exato.
- RN-05: frete nunca compõe a base de cálculo do ICMS.
- RN-06: regime SIMPLES reduz o ICMS próprio de cada item à metade e zera o ICMS-ST
  incondicionalmente, mesmo havendo MVA cadastrado.
- RN-07: CNPJ emitente sem regime cadastrado sempre bloqueia o cálculo com `REGIME_DESCONHECIDO`;
  não existe regime default.
- RN-08: a checagem de regime (nota inteira) sempre precede a checagem de alíquota por item.
- RN-09: `TABELA_INVALIDA` é exclusivo dos métodos de cadastro; nunca compete com os demais
  códigos dentro de `calcular`/`memoria_calculo`.
- RN-10: todo arredondamento monetário é `Decimal`, 2 casas, `ROUND_HALF_EVEN`, aplicado por item
  antes de agregar.
- RN-11: reregistrar o mesmo par UF/NCM ou o mesmo CNPJ sempre substitui o cadastro anterior
  (nunca acumula).
- RN-12: `memoria_calculo` replica exatamente as mesmas validações e erros de `calcular` para a
  mesma nota — nunca retorno parcial.
- RN-13: ICMS próprio já está embutido no preço da nota; `total_nota` não soma o ICMS
  separadamente, apenas o `icms_st`.

---

## Critérios de Aceite (Gherkin)

```gherkin
Funcionalidade: Validação de nota e item

  Cenário: Nota sem itens é rejeitada
    Dado uma nota sem a chave "itens" ou com lista de itens vazia
    Quando calcular é chamado com essa nota
    Então uma ErroTributario com code "NOTA_INVALIDA" é lançada

  Cenário: Item com desconto maior que o valor total é rejeitado
    Dado um item com valor "100.00", quantidade 1 e desconto "150.00"
    Quando calcular é chamado com uma nota contendo esse item
    Então uma ErroTributario com code "ITEM_INVALIDO" é lançada

Funcionalidade: Cadastro de alíquota, isenção e regime

  Cenário: Alíquota fora do intervalo válido é rejeitada
    Dado uma chamada a registrar_aliquota com aliquota "1.50"
    Quando registrar_aliquota é executado
    Então uma ErroTributario com code "TABELA_INVALIDA" é lançada

  Cenário: Regime fora do vocabulário fechado é rejeitado no cadastro
    Dado uma chamada a registrar_regime com regime "MEI"
    Quando registrar_regime é executado
    Então uma ErroTributario com code "TABELA_INVALIDA" é lançada

Funcionalidade: Resolução de alíquota por UF e NCM

  Cenário: Busca por prefixo de NCM quando o exato não está cadastrado
    Dado uma alíquota cadastrada para a UF "SP" e o prefixo NCM "1234" (4 dígitos)
    E nenhuma alíquota cadastrada para o NCM exato "12345678" na UF "SP"
    Quando um item com ncm "12345678" é calculado para a UF "SP"
    Então a alíquota do prefixo "1234" é aplicada
    E ncm_aplicado na memória de cálculo é "1234"

  Cenário: Par UF/NCM sem qualquer correspondência é rejeitado
    Dado nenhuma alíquota exata nem prefixo de 4+ dígitos cadastrado para o NCM do item na UF de destino
    Quando calcular é chamado
    Então uma ErroTributario com code "ALIQUOTA_NAO_CADASTRADA" é lançada

  Cenário: Isenção não busca por prefixo
    Dado uma isenção cadastrada apenas para o NCM exato "12345678" na UF "SP"
    E um item com ncm "1234" (prefixo, não o exato) na mesma UF
    Quando calcular é chamado
    Então o item "1234" não é tratado como isento

Funcionalidade: Cálculo de ICMS, ICMS-ST e regimes

  Cenário: ICMS-ST aplicado quando há MVA cadastrado
    Dado uma alíquota "0.18" com mva "0.40" cadastrada para o par UF/NCM do item
    E um item não isento com base de cálculo "100.00" em regime NORMAL
    Quando calcular é chamado
    Então icms_st é maior que "0.00"

  Cenário: Regime SIMPLES reduz o ICMS à metade e zera o ICMS-ST
    Dado uma alíquota "0.18" com mva "0.40" cadastrada para o par UF/NCM do item
    E um item não isento com base de cálculo "100.00" em regime SIMPLES
    Quando calcular é chamado
    Então icms é a metade do valor que seria calculado em regime NORMAL
    E icms_st é "0.00"

  Cenário: CNPJ sem regime cadastrado bloqueia o cálculo
    Dado um CNPJ emitente sem regime registrado
    Quando calcular é chamado com uma nota desse emitente
    Então uma ErroTributario com code "REGIME_DESCONHECIDO" é lançada

  Cenário: Regime ausente tem precedência sobre alíquota ausente
    Dado um CNPJ emitente sem regime registrado
    E um item da nota com par UF/NCM também sem alíquota cadastrada
    Quando calcular é chamado
    Então uma ErroTributario com code "REGIME_DESCONHECIDO" é lançada, não "ALIQUOTA_NAO_CADASTRADA"

Funcionalidade: Totais e memória de cálculo

  Cenário: Frete não compõe a base de cálculo mas compõe o total da nota
    Dado uma nota com frete "50.00" e um item não isento
    Quando calcular é chamado
    Então base_calculo não inclui o valor do frete
    E total_nota inclui o valor do frete

  Cenário: memoria_calculo espelha o erro de calcular
    Dado uma nota que faria calcular lançar ErroTributario com code "ITEM_INVALIDO"
    Quando memoria_calculo é chamado com a mesma nota
    Então uma ErroTributario com code "ITEM_INVALIDO" é lançada
    E nenhuma lista parcial é retornada

  Cenário: memoria_calculo detalha item isento
    Dado um item isento cadastrado via registrar_isencao para o par UF/NCM exato do item
    Quando memoria_calculo é chamado
    Então a entrada desse item tem isento igual a verdadeiro, aliquota igual a None e ncm_aplicado igual a None
```

---

## Contrato obrigatório

> Copiado literalmente de `stage4/corpus/UC-14/enunciado.md`.

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão. Valores monetários e
alíquotas são `decimal.Decimal`; entradas numéricas podem chegar como `str`, `int`,
`float` ou `Decimal`.

```python
class ErroTributario(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class MotorTributario:
    def registrar_aliquota(self, uf: str, ncm: str, aliquota,
                           mva=None) -> None: ...

    def registrar_isencao(self, uf: str, ncm: str) -> None: ...

    def registrar_regime(self, cnpj: str, regime: str) -> None: ...

    def calcular(self, nota: dict) -> dict:
        """`nota`: {"cnpj_emitente": str, "uf_destino": str, "frete": <monetário>,
                    "itens": [{"ncm": str, "valor": <monetário>,
                               "quantidade": int, "desconto": <monetário>}]}
        Retorna {"base_calculo": Decimal, "icms": Decimal, "icms_st": Decimal,
                 "total_tributos": Decimal, "total_nota": Decimal}"""

    def memoria_calculo(self, nota: dict) -> list[dict]:
        """[{"ncm": str, "ncm_aplicado": str | None, "aliquota": Decimal | None,
             "base": Decimal, "icms": Decimal, "icms_st": Decimal,
             "isento": bool}]"""
```

### Vocabulário fechado

`ErroTributario.code` assume **somente**: `ALIQUOTA_NAO_CADASTRADA`, `TABELA_INVALIDA`,
`NOTA_INVALIDA`, `ITEM_INVALIDO`, `REGIME_DESCONHECIDO`.

O `regime` assume **somente**: `SIMPLES`, `NORMAL`.

> Este enunciado define o vocabulário, não a regra: o que fazer quando o par UF/NCM não
> está na tabela, o que entra na base de cálculo e como cada regime altera o resultado faz
> parte do que precisa ser decidido.

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
