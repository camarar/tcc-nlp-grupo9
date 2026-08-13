# UC-04 — Limitador de Requisições Multi-Plano — Especificação Técnica Consolidada

> Documento produzido pela condição C2 (pipeline de 3 agentes: `working-backwards-designer` →
> `working-backwards-analyst` → `senior-functional-analyst-reviewer`). Todo requisito abaixo
> corresponde a uma decisão de negócio efetivamente elicitada por uma pergunta `[BLOQUEANTE]`
> formulada por um dos agentes (ver `captura.json` para a lista literal das perguntas, e
> `registro.md` para o registro completo das iterações e das respostas).

## Contrato obrigatório

> Seção copiada literalmente de `stage4/corpus/UC-04/enunciado.md`.

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão.

```python
class ErroLimite(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class Limitador:
    def __init__(self, relogio: Callable[[], float] | None = None) -> None:
        """`relogio` devolve segundos monotônicos como float; quando ausente,
        usar o relógio do sistema."""

    def registrar_plano(self, nome: str, config: dict) -> None:
        """`config`: {"limite": int, "janela_s": float, "burst": int}"""

    def registrar_cliente(self, client_id: str, plano: str,
                          organizacao: str | None = None) -> None: ...

    def registrar_organizacao(self, org_id: str, config: dict) -> None:
        """`config`: {"limite": int, "janela_s": float}"""

    def permitir(self, client_id: str, custo: int = 1) -> dict:
        """Retorna {"permitido": bool, "restante": int, "retry_after": float,
                    "limitante": str | None}"""

    def consumo(self, client_id: str) -> dict:
        """Retorna {"cliente": int, "organizacao": int | None}"""

    def redefinir(self, client_id: str) -> None: ...
```

### Vocabulário fechado

`ErroLimite.code` assume **somente**: `PLANO_DESCONHECIDO`, `CLIENTE_DESCONHECIDO`,
`ORGANIZACAO_DESCONHECIDA`, `CONFIGURACAO_INVALIDA`, `CUSTO_INVALIDO`.

O campo `limitante` assume **somente**: `CLIENTE`, `ORGANIZACAO`, `None`.

### Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.

---

## Requisitos Funcionais

### RF-01 — Algoritmo de janela (sliding window log)

O limitador usa **janela deslizante com registro de eventos**: cada requisição *permitida*
grava um par `(instante, custo)`. Um registro deixa de contar para a janela quando
`agora - instante >= janela_s` (a fronteira exata já está fora da janela).

*Elicitado por:* pergunta do `working-backwards-analyst` sobre qual algoritmo de rate
limiting (token bucket vs. sliding/fixed window) implementa `limite`/`janela_s`/`burst`.

### RF-02 — Expurgo de registros expirados (lazy)

Registros expirados são descartados **no momento da consulta** ao cliente ou à organização
(dentro de `permitir`, `consumo` ou `redefinir`), não em processo de background nem
antecipadamente. `consumo()` nunca inclui registros expirados.

*Elicitado por:* pergunta do `senior-functional-analyst-reviewer` sobre o momento em que
registros expirados são removidos da estrutura de dados.

### RF-03 — Validação de `custo` por chamada

`custo` é o consumo daquela chamada específica, avaliado **antes** de qualquer cálculo de
janela:
- `custo > burst` (configurado no plano do cliente) → `ErroLimite(code="CUSTO_INVALIDO")`.
- `custo < 1` → `ErroLimite(code="CUSTO_INVALIDO")`.
- `burst` é apenas o teto por chamada individual — **não amplia** a capacidade da janela
  (não soma com `limite`).

*Elicitado por:* perguntas do `working-backwards-analyst` sobre a semântica de `burst` e
sobre o comportamento quando `custo` excede a capacidade máxima do plano.

> **Avanço sob risco (AR-03):** o comportamento de `permitir()` quando `custo` não é um
> `int` válido (ex.: `float`, string, `None`) **não tem decisão de negócio registrada**.
> Ver seção "Avanços sob risco".

### RF-04 — Precedência e atomicidade cliente × organização

`permitir()` avalia **primeiro** a capacidade do **cliente**:
- Se o cliente não comportar o custo, a requisição é negada com `limitante="CLIENTE"` e a
  organização **não é avaliada**.
- Somente se o cliente comportar o custo é que a organização (quando existir) é avaliada;
  se ela não comportar, a requisição é negada com `limitante="ORGANIZACAO"`.
- Em **qualquer** negativa, nenhum registro é gravado — nem no cliente, nem na organização.
  A checagem e o débito são atômicos (check-then-commit); não há débito parcial e,
  portanto, não há necessidade de rollback.

*Elicitado por:* pergunta do `working-backwards-analyst` sobre a ordem de avaliação
cliente×organização e se há reversão de débito quando a organização recusa.

### RF-05 — Contadores independentes cliente e organização

Uma requisição **permitida** de um cliente vinculado a uma organização grava um registro
`(instante, custo)` no cliente **e** um registro `(instante, custo)` na organização, com o
mesmo custo. Os dois contadores são estruturas independentes.

Para cliente **sem** organização vinculada: `consumo()["organizacao"]` é `None` (não `0`,
não chave omitida), e `limitante="ORGANIZACAO"` **nunca ocorre** para esse cliente.

*Elicitado por:* pergunta do `working-backwards-analyst` sobre débito de ambos os
contadores (decorrência direta da resposta de RF-04) e pergunta do
`senior-functional-analyst-reviewer` sobre o formato do campo `organizacao` em `consumo()`
para cliente sem organização.

### RF-06 — Campo `restante`

- Quando `permitido=True`: é o **menor valor** entre a capacidade restante do cliente e a
  da organização, já descontada a requisição atual.
- Quando `permitido=False`: é a capacidade restante do limitante que efetivamente negou
  (`CLIENTE` ou `ORGANIZACAO`).
- Nunca é negativo (mínimo `0`).

*Elicitado por:* pergunta do `working-backwards-analyst` sobre a semântica do campo
`restante` em ambos os cenários (permitido/negado) e quando há dois limitantes envolvidos.

### RF-07 — Campo `retry_after`

- Quando `permitido=True`: `0.0`.
- Quando `permitido=False`: tempo em segundos até expirarem registros suficientes do
  **limitante que negou**, calculado percorrendo os registros vivos desse limitante do
  mais antigo para o mais novo, **acumulando custos** até que o acumulado atinja
  `consumo_atual + custo - limite`; o valor retornado é
  `(instante_desse_registro + janela_s) - agora`, arredondado com `round(x, 3)`, nunca
  negativo. O percurso considera apenas registros já vivos (RF-02 garante que expirados já
  foram expurgados no início da mesma chamada).
- `agora` é lido **uma única vez** por chamada pública e reutilizado em todos os cálculos
  daquela chamada (ver RNF-02).

*Elicitado por:* perguntas do `working-backwards-analyst` sobre o cálculo de `retry_after`
quando um limitante nega (incluindo a condição exata de parada do acumulador) e pergunta do
`senior-functional-analyst-reviewer` sobre quantas vezes o relógio é lido por chamada.

### RF-08 — Campo `limitante`

É `None` sempre que `permitido=True` (decorrência direta de RF-04: só há valor
`"CLIENTE"`/`"ORGANIZACAO"` quando a requisição foi efetivamente negada por aquele
limitante).

### RF-09 — `redefinir(client_id)`

Zera **exclusivamente** os registros do cliente informado. O consumo da organização à qual
ele pertence (se houver) permanece **intacto** — os dois contadores são independentes.
Chamado sobre `client_id` não registrado, lança `ErroLimite(code="CLIENTE_DESCONHECIDO")`
(não é idempotente/silencioso).

*Elicitado por:* pergunta do `working-backwards-analyst` sobre se `redefinir` afeta o
contador agregado da organização, e pergunta do `senior-functional-analyst-reviewer` sobre
o comportamento para `client_id` desconhecido.

### RF-10 — Reregistro de plano e de cliente

- **Plano:** chamar `registrar_plano` novamente com um `nome` já existente **substitui** a
  configuração vigente e **não afeta** contadores/registros de consumo já existentes.
- **Cliente:** chamar `registrar_cliente` novamente com um `client_id` já existente
  **substitui** o vínculo (plano/organização) e **zera** os registros de consumo daquele
  cliente. Registros já gravados na organização (que não são "por cliente", são agregados
  da organização) **não são removidos retroativamente** — decaem apenas pela expiração
  natural da janela.
- Esta assimetria é intencional: reregistro de plano é troca de *configuração*; reregistro
  de cliente é troca de *identidade/vínculo*.

*Elicitado por:* pergunta do `working-backwards-analyst` sobre o comportamento de
reregistro para plano, cliente e organização, e perguntas de acompanhamento do
`senior-functional-analyst-reviewer` sobre o efeito do reregistro de cliente no consumo da
organização anterior e sobre a intencionalidade da assimetria com o reregistro de plano.

> **Avanço sob risco (AR-01):** o comportamento de `registrar_organizacao` com um `org_id`
> já existente **não tem decisão de negócio registrada**. Ver seção "Avanços sob risco".

### RF-11 — Referências desconhecidas

- `registrar_cliente` com `plano` não registrado → `ErroLimite(code="PLANO_DESCONHECIDO")`.
- `registrar_cliente` com `organizacao` não registrada (quando informada) →
  `ErroLimite(code="ORGANIZACAO_DESCONHECIDA")`.
- `permitir`, `consumo` e `redefinir` sobre `client_id` não registrado →
  `ErroLimite(code="CLIENTE_DESCONHECIDO")` em todos os três.

*Elicitado por:* pergunta do `senior-functional-analyst-reviewer` sobre o mapeamento
completo de `code` por operação para referências desconhecidas.

> **Avanço sob risco (AR-02):** quando `plano` **e** `organizacao` são simultaneamente
> inexistentes em `registrar_cliente`, **não há decisão de negócio registrada** sobre qual
> `code` prevalece. Ver seção "Avanços sob risco".

### RF-12 — Configuração inválida

`ErroLimite(code="CONFIGURACAO_INVALIDA")` quando:
- No plano (`registrar_plano`): `limite < 1`, `janela_s <= 0` ou `burst < 1`.
- Na organização (`registrar_organizacao`): `limite < 1` ou `janela_s <= 0` (organização
  não possui `burst`).
- Em ambos os casos: chave obrigatória ausente no dict `config`.

*Elicitado por:* pergunta do `senior-functional-analyst-reviewer` sobre os valores exatos
que disparam `CONFIGURACAO_INVALIDA`.

---

## Requisitos Não Funcionais

### RNF-01 — Concorrência

Todas as operações públicas (`permitir`, `consumo`, `redefinir`, `registrar_*`) são
serializadas por um **único** `threading.Lock` do próprio limitador (não é lock por
entidade); a decisão de permitir e a gravação do consumo ocorrem de forma **atômica**
dentro da mesma região crítica. Escopo do requisito: garantir a **invariante de
corretude** — sob concorrência, o total efetivamente permitido nunca ultrapassa `limite`.
Não há SLA de throughput/latência definido para este componente.

*Elicitado por:* pergunta do `working-backwards-analyst` sobre a política de concorrência
exigida (lock por entidade vs. lock global) e pergunta de acompanhamento do
`senior-functional-analyst-reviewer` sobre a existência de métrica de desempenho sob
concorrência.

### RNF-02 — Determinismo do relógio

Cada operação pública lê o relógio (`relogio()` injetado, ou o relógio do sistema quando
ausente) **exatamente uma vez**, no início da chamada, e usa esse mesmo valor `agora` em
todos os cálculos daquela chamada (expiração de registros, `retry_after`, timestamp do novo
registro). Isso garante decisões reprodutíveis em teste com relógio mockado.

*Elicitado por:* pergunta do `senior-functional-analyst-reviewer` sobre quantas vezes o
relógio é lido dentro de uma única chamada.

---

## Avanços Sob Risco (SFAR — Opção B)

Os itens abaixo **não têm decisão de negócio disponível** e foram formalmente registrados
como avanço sob risco (opção B do SFAR), conforme `registro.md`. Nenhuma resposta foi
inventada; onde há sugestão técnica, ela está marcada como não vinculante.

| ID | Lacuna | Sugestão técnica não vinculante |
|---|---|---|
| AR-01 | Reregistro de `registrar_organizacao` com `org_id` já existente | Por simetria com `registrar_plano`: substitui a configuração, preserva o consumo agregado já registrado. **Não confirmado.** |
| AR-02 | Ordem de checagem quando `plano` e `organizacao` são simultaneamente inexistentes em `registrar_cliente` | Checar `plano` primeiro (é parâmetro obrigatório; `organizacao` é opcional). **Não confirmado.** |
| AR-03 | Comportamento de `permitir()` quando `custo` não é `int` válido | Nenhuma validação de tipo deve ser presumida como requisito formal; não codificar asserção de `code` específico para este caso. |

---

## Critérios de Aceite (Gherkin)

```gherkin
Funcionalidade: Limitador de requisições multi-plano

  Contexto:
    Dado um plano "basico" registrado com limite=5, janela_s=60 e burst=3
    E uma organizacao "org-1" registrada com limite=8 e janela_s=60

  Cenário: Requisição permitida dentro do limite do cliente
    Dado um cliente "c1" registrado no plano "basico" sem organização
    Quando o cliente "c1" solicita permitir com custo=1
    Então o resultado é permitido=True
    E o campo limitante é None
    E o campo retry_after é 0.0
    E o campo restante reflete a capacidade restante do cliente após o débito

  Cenário: Requisição negada pelo limite do cliente
    Dado um cliente "c1" registrado no plano "basico" sem organização
    E o cliente "c1" já consumiu 5 de custo dentro da janela vigente
    Quando o cliente "c1" solicita permitir com custo=1
    Então o resultado é permitido=False
    E o campo limitante é "CLIENTE"
    E o campo restante é 0
    E o campo retry_after é maior que 0.0
    E nenhum novo registro é gravado para o cliente "c1"

  Cenário: Cliente comporta mas organização nega — sem débito parcial
    Dado um cliente "c2" registrado no plano "basico" na organização "org-1"
    E a organizacao "org-1" já consumiu 8 de custo dentro da janela vigente
    E o cliente "c2" tem capacidade disponível no seu próprio limite
    Quando o cliente "c2" solicita permitir com custo=1
    Então o resultado é permitido=False
    E o campo limitante é "ORGANIZACAO"
    E o consumo do cliente "c2" não se altera (nenhum registro gravado no cliente nem na organização)

  Cenário: Requisição permitida debita cliente e organização com o mesmo custo
    Dado um cliente "c2" registrado no plano "basico" na organização "org-1"
    Quando o cliente "c2" solicita permitir com custo=2
    Então o resultado é permitido=True
    E o consumo do cliente "c2" aumenta em 2
    E o consumo da organizacao "org-1" aumenta em 2

  Cenário: Custo maior que o burst do plano
    Dado um cliente "c1" registrado no plano "basico"
    Quando o cliente "c1" solicita permitir com custo=4
    Então é lançado ErroLimite com code="CUSTO_INVALIDO"

  Cenário: Custo menor que 1
    Dado um cliente "c1" registrado no plano "basico"
    Quando o cliente "c1" solicita permitir com custo=0
    Então é lançado ErroLimite com code="CUSTO_INVALIDO"

  Cenário: Consumo de cliente sem organização
    Dado um cliente "c1" registrado no plano "basico" sem organização
    Quando é consultado o consumo do cliente "c1"
    Então o campo organizacao do resultado é None

  Cenário: Redefinir afeta apenas o cliente, não a organização
    Dado um cliente "c2" registrado no plano "basico" na organizacao "org-1"
    E o cliente "c2" possui consumo acumulado maior que zero
    E a organizacao "org-1" possui consumo acumulado maior que zero
    Quando é chamado redefinir para o cliente "c2"
    Então o consumo do cliente "c2" é zero
    E o consumo da organizacao "org-1" permanece inalterado

  Cenário: Reregistro de plano preserva contadores
    Dado um cliente "c1" registrado no plano "basico" com consumo acumulado maior que zero
    Quando o plano "basico" é registrado novamente com limite=10, janela_s=60, burst=3
    Então a nova configuração do plano "basico" é limite=10
    E o consumo já acumulado do cliente "c1" não é alterado

  Cenário: Reregistro de cliente zera o consumo do cliente
    Dado um cliente "c1" registrado no plano "basico" com consumo acumulado maior que zero
    Quando o cliente "c1" é registrado novamente no plano "basico"
    Então o consumo do cliente "c1" é zero

  Cenário: Plano desconhecido ao registrar cliente
    Quando um cliente é registrado com plano="inexistente"
    Então é lançado ErroLimite com code="PLANO_DESCONHECIDO"

  Cenário: Organização desconhecida ao registrar cliente
    Dado um plano "basico" válido
    Quando um cliente é registrado com plano="basico" e organizacao="org-inexistente"
    Então é lançado ErroLimite com code="ORGANIZACAO_DESCONHECIDA"

  Esquema do Cenário: Operações sobre cliente desconhecido
    Quando é chamado "<operacao>" para um client_id não registrado
    Então é lançado ErroLimite com code="CLIENTE_DESCONHECIDO"

    Exemplos:
      | operacao   |
      | permitir   |
      | consumo    |
      | redefinir  |

  Esquema do Cenário: Configuração inválida de plano
    Quando o plano "x" é registrado com <config>
    Então é lançado ErroLimite com code="CONFIGURACAO_INVALIDA"

    Exemplos:
      | config                                          |
      | limite=0, janela_s=60, burst=3                   |
      | limite=5, janela_s=0, burst=3                     |
      | limite=5, janela_s=60, burst=0                    |
      | limite=5, janela_s=60 (sem chave burst)           |

  Esquema do Cenário: Configuração inválida de organização
    Quando a organizacao "y" é registrada com <config>
    Então é lançado ErroLimite com code="CONFIGURACAO_INVALIDA"

    Exemplos:
      | config                     |
      | limite=0, janela_s=60      |
      | limite=8, janela_s=0        |
      | limite=8 (sem chave janela_s) |

  Cenário: Concorrência não excede o limite (invariante)
    Dado um cliente "c1" registrado no plano "basico" (limite=5)
    Quando N threads concorrentes chamam permitir com custo=1 simultaneamente
    Então a soma total de requisições permitidas nunca excede 5

  Cenário: Relógio lido uma única vez por chamada
    Dado um relógio de teste controlável injetado no Limitador
    Quando permitir é chamado e o relógio avança entre leituras hipotéticas internas
    Então todos os campos do resultado (retry_after, restante, registro gravado) são
      consistentes com um único valor de agora

  @risco-assumido
  Cenário: Plano e organização simultaneamente inexistentes (AR-02)
    Quando um cliente é registrado com plano="inexistente" e organizacao="tambem-inexistente"
    Então é lançado ErroLimite com code="PLANO_DESCONHECIDO"
    # Nota: ordem de checagem não confirmada por decisão de negócio — ver AR-02 em registro.md

  @pendente-decisao-produto
  Cenário: Custo de tipo inválido (AR-03)
    Quando o cliente "c1" solicita permitir com custo de tipo inválido (não inteiro)
    Então uma exceção é lançada
    # Nota: não asserir code específico — comportamento não confirmado por decisão de negócio, ver AR-03 em registro.md

  @risco-assumido
  Esquema do Cenário: Reregistro de organização (AR-01)
    Dado uma organizacao "org-1" já registrada com consumo acumulado maior que zero
    Quando a organizacao "org-1" é registrada novamente com nova configuração
    Então a nova configuração é aplicada
    # Nota: efeito sobre o consumo acumulado não confirmado por decisão de negócio — ver AR-01 em registro.md
```
