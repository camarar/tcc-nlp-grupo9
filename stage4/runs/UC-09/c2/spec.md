# UC-09 — Especificação Técnica Consolidada — Central de Chamados com SLA

> Produzida pelo pipeline de 3 agentes de requisitos (condição C2): `working-backwards-designer`
> → `working-backwards-analyst` → `senior-functional-analyst-reviewer`. Cada requisito abaixo
> só incorpora o que foi efetivamente elicitado pelos agentes por meio de perguntas — não é
> uma cópia do gabarito de decisões, que serviu exclusivamente para responder às perguntas
> bloqueantes registradas em `registro.md`.

## Veredito de prontidão do pipeline

`PRONTO SOB RISCO REGISTRADO` (veredito final do `senior-functional-analyst-reviewer`).
Cinco pontos seguem como **avanço sob risco** (opção B do SFAR — ver `registro.md`): precedência
entre `relogio` injetado e `quando` explícito (RNF-04), retrocesso temporal (`quando` anterior ao
último evento do chamado), limite de quantidade/duração de pausas, limite de ciclos de
reabertura, e alteração de severidade na reabertura.

---

## Requisitos Funcionais (RF)

### RF-01 — Configuração de política de SLA
`configurar_sla(severidade, minutos, horario_comercial)` define a política aplicável a uma
severidade. `minutos <= 0` OU `severidade` fora do vocabulário fechado (`CRITICA`, `ALTA`,
`MEDIA`, `BAIXA`) → `ErroChamado("POLITICA_INVALIDA")`.

Reconfigurar uma política afeta **apenas** os chamados abertos **depois** da mudança; chamados
já existentes mantêm o SLA que estava vigente no momento em que foram abertos (não há efeito
retroativo silencioso).

### RF-02 — Abertura de chamado e regra de ouro do SLA
`abrir(dados)` cria um chamado na situação `ABERTO` e retorna seu identificador.

`ErroChamado("DADOS_INVALIDOS")` quando: `cliente` ou `assunto` ausentes ou vazios; `severidade`
fora do vocabulário fechado; `aberto_em` ausente ou *naive* (sem timezone).

**Regra de ouro:** não existe SLA padrão. Abrir um chamado de uma severidade que está no
vocabulário fechado mas para a qual **nenhum** `configurar_sla` foi chamado ainda também é
`ErroChamado("DADOS_INVALIDOS")` — o sistema nunca assume um prazo implícito.

### RF-03 — Atribuição (`atribuir`)
Permitida a partir de `ABERTO`, `REABERTO`, e também a partir de `ATRIBUIDO` (reatribuição a
outro atendente) → resultado `ATRIBUIDO`. A partir de `PAUSADO` ou `RESOLVIDO` →
`ErroChamado("ESTADO_INVALIDO")`. `atendente` vazio → `ErroChamado("ATRIBUICAO_INVALIDA")`.

A distinção entre os dois códigos de erro é: `ESTADO_INVALIDO` refere-se à situação atual do
chamado ser incompatível com a operação; `ATRIBUICAO_INVALIDA` refere-se especificamente ao
dado `atendente` ser vazio/ausente.

`[AVANÇO SOB RISCO — não confirmado]` Não há critério objetivo além de "vazio" para considerar
um `atendente` inválido (ex.: formato, existência em cadastro). Hipótese de trabalho: qualquer
string não vazia é um `atendente` válido.

### RF-04 — Pausa (`pausar`)
Permitida a partir de `ABERTO`, `ATRIBUIDO` ou `REABERTO` → resultado `PAUSADO`. A partir de
qualquer outra situação — **incluindo tentar pausar um chamado já `PAUSADO`** (não é
idempotente) — → `ErroChamado("ESTADO_INVALIDO")`. `motivo` vazio → `ErroChamado("DADOS_INVALIDOS")`.

Pausar suspende incondicionalmente o relógio de SLA: o tempo pausado nunca consome prazo, e o
`prazo()` do chamado é empurrado para frente pelo tempo útil que ficou pausado.

`[AVANÇO SOB RISCO — não confirmado]` O comportamento de pausas múltiplas e consecutivas dentro
do mesmo ciclo ativo (pausar → retomar → pausar novamente) não foi testado explicitamente pela
fonte; hipótese de trabalho: cada intervalo pausado é somado de forma simples e independente ao
tempo suspenso total. Também não há confirmação de limite de quantidade ou duração acumulada de
pausas por chamado.

### RF-05 — Retomada (`retomar`)
Permitida **somente** a partir de `PAUSADO`; qualquer outra situação →
`ErroChamado("ESTADO_INVALIDO")`. O chamado volta exatamente para a situação que tinha antes da
pausa (`ABERTO`, `ATRIBUIDO` ou `REABERTO`, conforme o caso).

### RF-06 — Resolução (`resolver`)
Permitida a partir de qualquer situação **exceto** `RESOLVIDO` e `PAUSADO` (ambas →
`ErroChamado("ESTADO_INVALIDO")`) — ou seja, permitida a partir de `ABERTO`, `ATRIBUIDO` e
`REABERTO`. Resultado: situação `RESOLVIDO`.

Retorna `{"cumpriu_sla": bool, "tempo_util_min": int}`:
- `tempo_util_min` é o total de minutos úteis decorridos entre `aberto_em` e `quando` da
  resolução, **descontado** o tempo útil em que o chamado esteve pausado, **truncado** para
  inteiro (não arredondado). Quando a política do SLA da severidade tem `horario_comercial=False`,
  `tempo_util_min` passa a ser o tempo **corrido** em minutos (sem restrição de janela de
  horário comercial), igualmente descontadas as pausas.
- `cumpriu_sla` é `tempo_util_min <= minutos` configurados na política vigente daquela
  severidade no momento da abertura do chamado.

### RF-07 — Reabertura (`reabrir`)
Permitida **somente** a partir de `RESOLVIDO` → resultado `REABERTO`. Qualquer outra situação —
incluindo tentar reabrir um chamado já `REABERTO` — → `ErroChamado("ESTADO_INVALIDO")`.

O SLA **continua de onde parou**: o tempo útil já consumido antes da resolução original é
preservado (o contador nunca reinicia do zero), e o tempo que o chamado passou na situação
`RESOLVIDO` é tratado como tempo suspenso (analogamente a uma pausa) — não consome prazo, e o
`prazo()` é empurrado para frente por esse tempo.

`[AVANÇO SOB RISCO — não confirmado]` Não há limite de ciclos `resolver → reabrir` por chamado
— hipótese de trabalho: ilimitado. Também não há confirmação sobre alteração de severidade na
reabertura; como o contrato não expõe nenhum método para isso, a hipótese de trabalho é que a
severidade é imutável desde a abertura original.

### RF-08 — Consulta de prazo (`prazo`)
`prazo(chamado_id)` retorna o prazo vigente do chamado, calculado conforme a política de SLA de
sua severidade e ajustado por todo o tempo suspenso acumulado (pausas e, após reabertura, o
tempo em `RESOLVIDO`). Exemplo numérico ilustrativo, derivado das regras acima (SLA `CRITICA` =
60 minutos úteis, `horario_comercial=True`, expediente 09:00–18:00 seg-sex, fuso
`America/Sao_Paulo`): chamado aberto às 09:00 (segunda); pausado das 09:10 às 09:20 (10 min
úteis pausados, prazo original 10:00 empurrado para 10:10); resolvido às 09:30 com
`tempo_util_min = 20` e `cumpriu_sla = True`; reaberto às 14:00 do mesmo dia — o intervalo de
09:30 a 14:00 (4h30 em `RESOLVIDO`) é tratado como tempo suspenso, empurrando o prazo de 10:10
para 14:40; se resolvido novamente às 14:20, `tempo_util_min` acumulado é 20 (ciclo 1) + 20
(14:00–14:20, ciclo 2) = 40 minutos, ainda dentro do SLA de 60 (`cumpriu_sla = True`).

`chamado_id` desconhecido → `ErroChamado("CHAMADO_NAO_ENCONTRADO")` — regra válida para
**qualquer** método do contrato, verificada **antes** de qualquer checagem de estado.

### RF-09 — Fila priorizada (`fila`)
`fila(quando)` retorna a lista de chamados elegíveis, ordenada estritamente por, nesta ordem de
critérios: (1) severidade, de `CRITICA` para `BAIXA` (critério dominante — um chamado estourado
nunca ultrapassa um chamado de severidade maior, mesmo que este tenha folga no prazo); (2)
dentro da mesma severidade, chamados **estourados** primeiro; (3) `prazo` crescente; (4)
`aberto_em` crescente (FIFO); (5) ordem de criação, como desempate final estável.

O conjunto elegível para `fila()` é composto **apenas** por chamados nas situações `ABERTO`,
`ATRIBUIDO` e `REABERTO`. Chamados `PAUSADO` e `RESOLVIDO` ficam de fora — não há distinção
entre uma "fila visível" (supervisor) e uma "fila de distribuição": `fila()` e `proximo()` usam
o mesmo conjunto elegível.

Cada item retornado tem `estourado = True` quando `quando > prazo` (estritamente maior — no
instante exato do prazo o chamado ainda **não** está estourado).

`fila()` sobre conjunto elegível vazio retorna lista vazia, **sem erro**.

### RF-10 — Próximo chamado (`proximo`)
`proximo(quando)` retorna o identificador do chamado no topo do mesmo conjunto ordenado usado
por `fila()`. Quando esse conjunto elegível está vazio → `ErroChamado("FILA_VAZIA")`.

### RF-11 — Vocabulário fechado de erros (mapeamento)

| Código | Cenário de disparo |
|---|---|
| `DADOS_INVALIDOS` | Ver RF-02 (`abrir`, incl. regra de ouro do SLA); `motivo` vazio em `pausar` (RF-04) |
| `POLITICA_INVALIDA` | `configurar_sla` com `minutos <= 0` ou `severidade` fora do vocabulário (RF-01) |
| `CHAMADO_NAO_ENCONTRADO` | `chamado_id` desconhecido, em qualquer método — verificado antes de qualquer checagem de estado (RF-08) |
| `ESTADO_INVALIDO` | Transição de situação incompatível com o método chamado — ver RF-03 a RF-07 |
| `ATRIBUICAO_INVALIDA` | `atribuir` com `atendente` vazio/ausente (RF-03) |
| `FILA_VAZIA` | `proximo()` sobre conjunto elegível vazio (RF-10) |

---

## Requisitos Não Funcionais (RNF)

### RNF-01 — Cálculo de tempo útil e fuso horário
Todo cálculo de tempo útil (horário comercial) usa a janela segunda a sexta, das 09:00 às 18:00,
no fuso `America/Sao_Paulo` (constante `FUSO`), sem considerar feriados. "Minuto útil" é minuto
dentro dessa janela. Quando `aberto_em` de um chamado com SLA `horario_comercial=True` cai fora
dessa janela, a contagem do prazo começa no próximo instante útil (não soma o tempo integral
desde a abertura). Datas de entrada (`aberto_em`, `quando`) devem ser *timezone-aware*; valores
*naive* são `DADOS_INVALIDOS` (RF-02).

### RNF-02 — Determinismo e relógio injetável
`relogio: Callable[[], datetime] | None` é injetável via construtor para viabilizar testes
determinísticos.

`[AVANÇO SOB RISCO — RNF-04, não confirmado]` A precedência entre `relogio` (injetado no
construtor) e `quando` (passado explicitamente em praticamente todos os métodos de transição e
consulta) não foi confirmada pela fonte de negócio. Hipótese de trabalho registrada, não
adotada como fato: `quando`, quando fornecido explicitamente a um método, é sempre a fonte de
verdade; `relogio` serve apenas como relógio default/interno para os casos em que nenhum
`quando` é explicitamente fornecido — impacto prático considerado baixo, pois todos os métodos
do contrato atual que dependem de tempo recebem `quando` explicitamente.

### RNF-03 — Escopo
Persistência duradoura, autenticação/autorização e multitenancy não são expostas pelo contrato
(nenhum método de login, particionamento por operadora/time, ou consulta de histórico/auditoria
existe na assinatura) — `CentralChamados` é um componente de domínio em memória, biblioteca
padrão apenas, operando durante o processo.

`[AVANÇO SOB RISCO — não confirmado]` Não há confirmação se cancelamento de chamado (aberto por
engano/duplicado), encerramento definitivo/arquivamento após `RESOLVIDO`, e trilha de auditoria
observável são propositalmente fora de escopo do UC-09 ou omissões a tratar em versão futura do
contrato. Como não existe método correspondente na assinatura obrigatória, tratam-se como fora
de escopo desta entrega.

### RNF-04 — Retrocesso temporal (validação de ordem de eventos)
`[AVANÇO SOB RISCO — não confirmado]` Não há definição do comportamento quando `quando` passado
a um método de transição (`atribuir`, `pausar`, `retomar`, `resolver`, `reabrir`) é anterior ao
timestamp do último evento já registrado para aquele chamado. Nenhum código de erro específico
foi confirmado pela fonte de negócio para esse cenário; **não deve ser inventado** um
comportamento. Fica registrado como risco aceito, por afetar um cenário de uso anômalo/indevido
e não o fluxo principal do contrato.

---

## Regras de Negócio (consolidado)

- RN-01: não existe SLA padrão — abrir chamado de severidade sem `configurar_sla` prévio é `DADOS_INVALIDOS`.
- RN-02: reconfigurar uma política de SLA não é retroativo — só afeta chamados abertos depois da mudança.
- RN-03: pausa suspende incondicionalmente o relógio de SLA, mas só é aplicável a partir de ABERTO, ATRIBUIDO ou REABERTO — não é idempotente (pausar um já PAUSADO é erro).
- RN-04: retomar só é válido a partir de PAUSADO, devolvendo a situação anterior à pausa.
- RN-05: resolver não é permitido a partir de PAUSADO nem de RESOLVIDO.
- RN-06: reabrir só é permitido a partir de RESOLVIDO; o SLA nunca reinicia — o tempo consumido é preservado e o tempo em RESOLVIDO conta como suspensão.
- RN-07: `tempo_util_min` é sempre truncado para inteiro, nunca arredondado.
- RN-08: a fila e o "próximo" usam o mesmo conjunto elegível: ABERTO, ATRIBUIDO e REABERTO — nunca PAUSADO ou RESOLVIDO.
- RN-09: ordenação da fila é hierárquica e totalmente determinística: severidade > estourado > prazo > aberto_em > ordem de criação.
- RN-10: severidade é sempre o critério dominante da fila — um chamado estourado nunca ultrapassa um de severidade maior.
- RN-11: `chamado_id` desconhecido é sempre `CHAMADO_NAO_ENCONTRADO`, verificado antes de qualquer outra validação, em qualquer método.
- RN-12: `estourado` usa comparação estrita (`quando > prazo`); no instante exato do prazo, ainda não é estourado.

---

## Critérios de Aceite (Gherkin)

```gherkin
Funcionalidade: Configuração de política de SLA

  Cenário: Política com minutos não positivos é rejeitada
    Dado uma chamada a configurar_sla com minutos igual a 0
    Quando configurar_sla é executado
    Então uma ErroChamado com code "POLITICA_INVALIDA" é lançada

  Cenário: Reconfiguração de SLA não afeta chamados já abertos
    Dado um chamado ABERTO com SLA de 60 minutos configurado no momento da abertura
    Quando configurar_sla é chamado novamente para a mesma severidade com 30 minutos
    Então o prazo do chamado já aberto permanece calculado com base nos 60 minutos originais

Funcionalidade: Abertura de chamado

  Cenário: Severidade sem SLA configurado é rejeitada (regra de ouro)
    Dado que nenhuma chamada a configurar_sla foi feita para a severidade "ALTA"
    Quando abrir é chamado com dados contendo severidade "ALTA"
    Então uma ErroChamado com code "DADOS_INVALIDOS" é lançada

  Cenário: Dados obrigatórios ausentes são rejeitados
    Dado um dicionário de dados sem a chave "cliente"
    Quando abrir é chamado com esses dados
    Então uma ErroChamado com code "DADOS_INVALIDOS" é lançada

  Cenário: aberto_em naive (sem timezone) é rejeitado
    Dado um dicionário de dados com aberto_em sem informação de fuso horário
    Quando abrir é chamado com esses dados
    Então uma ErroChamado com code "DADOS_INVALIDOS" é lançada

Funcionalidade: Máquina de estados

  Cenário: Pausar um chamado já pausado é rejeitado
    Dado um chamado na situação "PAUSADO"
    Quando pausar é chamado novamente para esse chamado
    Então uma ErroChamado com code "ESTADO_INVALIDO" é lançada

  Cenário: Atribuir com atendente vazio é rejeitado
    Dado um chamado na situação "ABERTO"
    Quando atribuir é chamado com atendente igual a string vazia
    Então uma ErroChamado com code "ATRIBUICAO_INVALIDA" é lançada

  Cenário: Resolver a partir de PAUSADO é rejeitado
    Dado um chamado na situação "PAUSADO"
    Quando resolver é chamado para esse chamado
    Então uma ErroChamado com code "ESTADO_INVALIDO" é lançada

  Cenário: Reabrir só é permitido a partir de RESOLVIDO
    Dado um chamado na situação "REABERTO"
    Quando reabrir é chamado novamente para esse chamado
    Então uma ErroChamado com code "ESTADO_INVALIDO" é lançada

Funcionalidade: Cálculo de SLA

  Cenário: Pausa não consome tempo útil do SLA
    Dado um chamado aberto às 09:00 com SLA de 60 minutos úteis em horário comercial
    E pausado das 09:10 às 09:20
    Quando resolver é chamado às 09:30
    Então tempo_util_min é 20
    E cumpriu_sla é verdadeiro

  Cenário: Reabertura preserva o tempo já consumido e não reinicia o contador
    Dado um chamado resolvido com tempo_util_min igual a 20 e SLA de 60 minutos
    E reaberto e novamente resolvido após mais 20 minutos úteis de trabalho efetivo
    Quando o segundo resolver retorna
    Então tempo_util_min é 40
    E cumpriu_sla é verdadeiro

Funcionalidade: Fila priorizada

  Cenário: Severidade é o critério dominante de ordenação
    Dado um chamado CRITICA com prazo distante e um chamado ALTA estourado
    Quando fila é consultada
    Então o chamado CRITICA aparece antes do chamado ALTA na lista

  Cenário: Chamado pausado não aparece na fila
    Dado um chamado na situação "PAUSADO"
    Quando fila é consultada
    Então esse chamado não está na lista retornada

  Cenário: proximo sobre fila vazia lança erro
    Dado que não existe nenhum chamado nas situações ABERTO, ATRIBUIDO ou REABERTO
    Quando proximo é chamado
    Então uma ErroChamado com code "FILA_VAZIA" é lançada

  Cenário: fila vazia não lança erro
    Dado que não existe nenhum chamado nas situações ABERTO, ATRIBUIDO ou REABERTO
    Quando fila é chamada
    Então uma lista vazia é retornada, sem exceção

Funcionalidade: Referências inválidas

  Cenário: chamado_id desconhecido é sempre CHAMADO_NAO_ENCONTRADO
    Dado um chamado_id que nunca foi criado
    Quando qualquer método de transição ou consulta é chamado com esse chamado_id
    Então uma ErroChamado com code "CHAMADO_NAO_ENCONTRADO" é lançada antes de qualquer outra validação
```

---

## Contrato obrigatório

> Copiado literalmente de `stage4/corpus/UC-09/enunciado.md`.

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão (`zoneinfo` incluído).

```python
class ErroChamado(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class CentralChamados:
    FUSO = "America/Sao_Paulo"

    def __init__(self, relogio: Callable[[], datetime] | None = None) -> None: ...

    def configurar_sla(self, severidade: str, minutos: int,
                       horario_comercial: bool) -> None: ...

    def abrir(self, dados: dict) -> str:
        """`dados`: {"cliente": str, "severidade": str, "assunto": str,
                     "aberto_em": datetime}"""

    def atribuir(self, chamado_id: str, atendente: str, quando: datetime) -> None: ...

    def pausar(self, chamado_id: str, motivo: str, quando: datetime) -> None: ...

    def retomar(self, chamado_id: str, quando: datetime) -> None: ...

    def resolver(self, chamado_id: str, quando: datetime) -> dict:
        """Retorna {"cumpriu_sla": bool, "tempo_util_min": int}"""

    def reabrir(self, chamado_id: str, quando: datetime) -> None: ...

    def prazo(self, chamado_id: str) -> datetime: ...

    def fila(self, quando: datetime) -> list[dict]:
        """[{"chamado_id": str, "severidade": str, "situacao": str,
             "prazo": datetime, "estourado": bool}]"""

    def proximo(self, quando: datetime) -> str:
        """Identificador do chamado no topo da fila."""
```

### Vocabulário fechado

`ErroChamado.code` assume **somente**: `CHAMADO_NAO_ENCONTRADO`, `ESTADO_INVALIDO`,
`DADOS_INVALIDOS`, `POLITICA_INVALIDA`, `FILA_VAZIA`, `ATRIBUICAO_INVALIDA`.

A `severidade` assume **somente**: `CRITICA`, `ALTA`, `MEDIA`, `BAIXA`.

A `situacao` assume **somente**: `ABERTO`, `ATRIBUIDO`, `PAUSADO`, `RESOLVIDO`,
`REABERTO`.

> Este enunciado define o vocabulário, não a regra: em que circunstância cada código,
> severidade e situação se aplica faz parte do que precisa ser decidido.

### Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
