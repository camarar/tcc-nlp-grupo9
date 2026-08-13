# UC-13 — Especificação Técnica Consolidada
## Controle de estoque multi-depósito com reserva

> Documento produzido pelo pipeline de 3 agentes (working-backwards-designer →
> working-backwards-analyst → senior-functional-analyst-reviewer) na condição C2.
> Todo requisito abaixo reflete apenas o que foi efetivamente elicitado por perguntas dos
> agentes e respondido pelo Product Owner (via gabarito) — nada foi copiado em bloco do
> gabarito. Pontos sem resposta disponível estão marcados como **[RISCO ACEITO]** e não
> foram inventados.

---

## 1. Contrato obrigatório

*(reproduzido literalmente do enunciado — não sujeito a reinterpretação)*

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

### Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.

---

## 2. Requisitos Funcionais (RF)

### RF-01 — Registro de depósito
`registrar_deposito(deposito_id, prioridade)` cadastra um depósito com uma prioridade de
atendimento.
- `prioridade < 0` ou `deposito_id` vazio → `ErroEstoque("DADOS_INVALIDOS")`.
- Reregistrar um `deposito_id` já existente **substitui a prioridade** e **preserva** o
  estoque físico e as reservas já existentes naquele depósito.

### RF-02 — Reposição de estoque físico
`repor(deposito_id, sku, quantidade)` soma ao estoque físico do sku naquele depósito e
retorna o novo total físico.
- `quantidade < 1` → `ErroEstoque("DADOS_INVALIDOS")`.
- `deposito_id` não registrado → `ErroEstoque("DEPOSITO_DESCONHECIDO")`.
- **[RISCO ACEITO — R1]** Quando `deposito_id` desconhecido **e** `quantidade < 1`
  ocorrem simultaneamente, a ordem de precedência entre `DADOS_INVALIDOS` e
  `DEPOSITO_DESCONHECIDO` não foi definida. Nenhuma ordem deve ser presumida pela
  implementação de referência desta spec; ver `registro.md`.
- Um sku passa a existir no sistema (deixa de ser `SKU_DESCONHECIDO`) na **primeira**
  reposição bem-sucedida, em qualquer depósito.

### RF-03 — Consulta de disponibilidade
`disponivel(sku, deposito_id=None)` retorna `físico − reservas ativas` daquele sku.
- `deposito_id=None` soma a disponibilidade de todos os depósitos.
- sku nunca reposto em nenhum depósito → `ErroEstoque("SKU_DESCONHECIDO")`.
- **[RISCO ACEITO — R4]** Comportamento quando `deposito_id` é informado mas não está
  registrado (lançar `DEPOSITO_DESCONHECIDO` ou retornar `0`) não foi definido.

### RF-04 — Consulta de posição consolidada
`posicao(sku)` retorna `{deposito_id: {"fisico": int, "reservado": int, "disponivel": int}}`
com **uma entrada para cada depósito registrado**, inclusive os que têm físico zero.
- sku nunca reposto em nenhum depósito → `ErroEstoque("SKU_DESCONHECIDO")`.
- A ordem das chaves do dict não tem significado de negócio.

### RF-05 — Reserva de itens (`reservar`)
`reservar(itens, ttl_s=None)` cria uma reserva para uma lista de `{sku, quantidade}` e
devolve um `reserva_id`.

**Ordem de validação (por categoria, varrendo toda a lista em cada etapa):**
1. `DADOS_INVALIDOS` — lista de itens vazia, `quantidade < 1` em algum item, `sku` vazio,
   `sku` repetido na mesma reserva, ou `ttl_s <= 0` quando informado explicitamente.
2. `SKU_DESCONHECIDO` — algum sku da lista nunca foi reposto em depósito nenhum.
3. `ESTOQUE_INSUFICIENTE` — para algum sku, a soma da disponibilidade em toda a rede de
   depósitos não cobre a quantidade pedida.

Ou seja: primeiro varre-se **todos** os itens contra a categoria 1; só depois de todos
passarem, varre-se **todos** contra a categoria 2; só então a categoria 3 é avaliada de
forma agregada por sku.

**Atomicidade:** a reserva é **tudo ou nada** — se qualquer sku do pedido não puder ser
plenamente atendido pela soma da rede, **nenhum** item é reservado e o erro é
`ErroEstoque("ESTOQUE_INSUFICIENTE")`. Não existe reserva parcial.

**Distribuição entre depósitos:** para cada sku, os depósitos são percorridos por
**prioridade crescente** (número menor = atendido primeiro); empate resolvido pelo
**maior disponível**; empate final pelo `deposito_id` em ordem lexicográfica.
Consome-se o máximo possível de cada depósito antes de passar ao próximo (first-fit
decreasing por prioridade).

**TTL:** `ttl_s` explícito define o tempo de vida da reserva; se omitido (`None`), o TTL
padrão é **900 segundos**.

O item `{"sku": str, "quantidade": int}` **não** aceita `deposito_id` — a distribuição
entre depósitos é sempre decidida automaticamente pelo algoritmo acima, nunca direcionada
pelo chamador (confirmado pelo próprio contrato de código).

### RF-06 — Confirmação de reserva
`confirmar(reserva_id)` baixa o estoque **físico** dos depósitos alocados, encerra a
reserva e retorna `{"alocacao": {deposito_id: {sku: quantidade}}}`.
- A partir do momento em que `confirmar` executa, a reserva **não conta mais como
  reservada** — ela sai imediatamente do cálculo de `disponivel`/`posicao` (o físico já
  foi reduzido na mesma operação).
- `reserva_id` desconhecido → `ErroEstoque("RESERVA_NAO_ENCONTRADA")`, verificado
  **antes** de qualquer checagem de estado.
- Reserva já expirada, já confirmada ou já cancelada → `ErroEstoque("ESTADO_INVALIDO")`.

### RF-07 — Cancelamento de reserva
`cancelar(reserva_id)` libera as quantidades reservadas **sem tocar no físico**.
- `reserva_id` desconhecido → `ErroEstoque("RESERVA_NAO_ENCONTRADA")`, verificado
  **antes** de qualquer checagem de estado.
- Reserva já encerrada (confirmada, cancelada ou expirada) →
  `ErroEstoque("ESTADO_INVALIDO")`.
- `cancelar` sempre cancela a reserva **inteira** (todos os itens de uma vez); não existe
  cancelamento parcial de itens dentro de uma reserva ativa (fora de escopo — o contrato
  não expõe parâmetro para isso).

### RF-08 — Expiração de reservas
Duas mecânicas complementares:
- **Expiração preguiçosa (lazy):** uma reserva é considerada expirada quando
  `agora - criada_em >= ttl` (fronteira inclusiva). **Toda** operação e **toda** consulta
  pública (`disponivel`, `posicao`, `reservar`, `confirmar`, `cancelar`, `transferir`,
  `expirar`) descarta reservas vencidas **antes** de calcular qualquer coisa — a
  disponibilidade nunca reflete uma reserva morta. No instante em que uma reserva é
  descartada por expiração lazy (por qualquer operação), ela já transiciona
  formalmente para o estado "expirada" naquele exato momento.
- **Expiração explícita:** `expirar()` retorna quantas reservas **venceram nesta
  chamada**. Reservas já expiradas anteriormente — seja por descarte lazy em qualquer
  operação anterior, seja por uma chamada anterior de `expirar()` — **não são
  recontadas**.

### RF-09 — Transferência entre depósitos
`transferir(sku, origem, destino, quantidade)` move estoque **físico** entre depósitos.
- A quantidade não pode exceder o **disponível** da origem (físico − reservado), nunca o
  físico bruto — preserva reservas ativas na origem. Excedeu →
  `ErroEstoque("ESTOQUE_INSUFICIENTE")`.
- `origem == destino` → `ErroEstoque("DADOS_INVALIDOS")`.
- `origem` ou `destino` não registrado → `ErroEstoque("DEPOSITO_DESCONHECIDO")`.
- sku nunca reposto em depósito nenhum → `ErroEstoque("SKU_DESCONHECIDO")`.
- Nunca move estoque já reservado — apenas o saldo livre.
- **[RISCO ACEITO — R2]** Precedência entre `DADOS_INVALIDOS` (origem==destino) e
  `ESTOQUE_INSUFICIENTE` quando ambas as condições ocorrem simultaneamente não foi
  definida; também não foi confirmado se `quantidade < 1` deve ser validada como
  `DADOS_INVALIDOS`.
- **[RISCO ACEITO — R3]** Precedência entre múltiplos erros de referência desconhecida
  simultâneos (ex.: origem e destino ambos desconhecidos, ou origem desconhecida e sku
  desconhecido) não foi definida.

---

## 3. Requisitos Não Funcionais (RNF)

### RNF-01 — Concorrência
O sistema atende requisições concorrentes. Todas as operações públicas de `Estoque` são
serializadas por um **único `threading.Lock` global**, cobrindo o corpo inteiro de cada
método (não apenas o cálculo de disponibilidade). A verificação de disponibilidade e a
gravação da reserva são atômicas dentro dessa mesma seção crítica. Sob disputa
concorrente pelo último item, exatamente uma reserva vence — as demais recebem
`ESTOQUE_INSUFICIENTE`. Qualquer chamada a `relogio()` feita durante uma operação ocorre
dentro dessa mesma seção crítica, garantindo leitura de tempo consistente sob concorrência.

### RNF-02 — Determinismo via relógio injetável
`Estoque(relogio)` aceita uma função `Callable[[], float]` que devolve segundos
monotônicos; permite controlar o tempo em testes (TTL/expiração determinísticos) sem
depender do relógio real do sistema.

### RNF-03 — Restrição tecnológica
Implementação em arquivo único `solucao.py`, Python 3.12, **apenas biblioteca padrão**
(sem dependências externas).

### RNF-04 — Escopo de isolamento
Não há requisito de multi-tenancy/isolamento entre clientes distintos. O único
isolamento relevante é entre depósitos e entre reservas concorrentes, coberto por
RNF-01.

---

## 4. Regras de negócio (resumo)

| ID | Regra |
|----|-------|
| RN-01 | `disponivel = físico − reservas ativas`; `deposito_id=None` soma todos os depósitos. |
| RN-02 | TTL padrão de reserva: 900s; `ttl_s <= 0` explícito é inválido. |
| RN-03 | Expiração é preguiçosa e universal: toda leitura/escrita descarta reservas vencidas antes de agir. |
| RN-04 | Reserva multi-item é atômica (tudo ou nada) por soma de rede. |
| RN-05 | Alocação por depósito: prioridade crescente → maior disponível → `deposito_id` lexicográfico; consome o máximo de cada depósito antes de avançar. |
| RN-06 | `confirmar` baixa físico e encerra a reserva; `cancelar` libera reservado sem tocar físico; ambos exigem estado "ativa" e reserva existente. |
| RN-07 | `expirar()` conta apenas reservas vencidas nesta chamada, sem recontar as já descartadas. |
| RN-08 | `transferir` só move saldo livre (disponível) da origem, nunca o reservado. |
| RN-09 | `repor` cria o sku no sistema na primeira chamada bem-sucedida. |
| RN-10 | Reregistrar depósito substitui prioridade e preserva estoque/reservas. |
| RN-11 | Máquina de estados da reserva: `ativa → {confirmada \| cancelada \| expirada}`, sem transição de volta. |
| RN-12 | Concorrência: lock global único serializa todas as operações públicas. |

---

## 5. Critérios de aceite (Gherkin)

```gherkin
Funcionalidade: Registro e reposição de depósito

  Cenário: Registrar novo depósito com dados válidos
    Dado que nenhum depósito "D1" existe
    Quando registro o depósito "D1" com prioridade 1
    Então o depósito "D1" passa a existir com prioridade 1

  Cenário: Registrar depósito com prioridade negativa é inválido
    Quando registro um depósito com prioridade -1
    Então recebo ErroEstoque com code "DADOS_INVALIDOS"

  Cenário: Reregistrar depósito existente preserva estoque e reservas
    Dado o depósito "D1" com prioridade 1 e 10 unidades físicas do sku "X"
    Quando registro novamente o depósito "D1" com prioridade 5
    Então o depósito "D1" passa a ter prioridade 5
    E o estoque físico do sku "X" no depósito "D1" continua sendo 10

  Cenário: Repor estoque de sku novo cria o sku no sistema
    Dado que o sku "X" nunca foi reposto em nenhum depósito
    Quando reponho 10 unidades do sku "X" no depósito "D1" registrado
    Então o novo estoque físico do sku "X" no depósito "D1" é 10
    E disponivel("X") deixa de lançar SKU_DESCONHECIDO

  Cenário: Repor com quantidade inválida
    Quando reponho 0 unidades do sku "X" no depósito "D1"
    Então recebo ErroEstoque com code "DADOS_INVALIDOS"

  Cenário: Repor em depósito desconhecido
    Quando reponho 10 unidades do sku "X" no depósito "D_INEXISTENTE"
    Então recebo ErroEstoque com code "DEPOSITO_DESCONHECIDO"


Funcionalidade: Disponibilidade e posição

  Cenário: Disponibilidade agregada de múltiplos depósitos
    Dado o depósito "D1" com 10 unidades físicas do sku "X" e nenhuma reserva
    E o depósito "D2" com 5 unidades físicas do sku "X" e nenhuma reserva
    Quando consulto disponivel("X")
    Então o resultado é 15

  Cenário: Disponibilidade de sku desconhecido
    Dado que o sku "Y" nunca foi reposto em nenhum depósito
    Quando consulto disponivel("Y")
    Então recebo ErroEstoque com code "SKU_DESCONHECIDO"

  Cenário: Posição lista todos os depósitos registrados, inclusive com físico zero
    Dado os depósitos "D1" (10 unidades do sku "X") e "D2" (registrado, sem sku "X" reposto)
    Quando consulto posicao("X")
    Então o resultado contém uma entrada para "D1" e uma entrada para "D2" com fisico=0


Funcionalidade: Reserva de itens

  Cenário: Reserva simples com disponibilidade suficiente em um único depósito
    Dado o depósito "D1" com 10 unidades físicas do sku "X"
    Quando reservo [{"sku": "X", "quantidade": 4}]
    Então recebo um reserva_id válido
    E disponivel("X") passa a ser 6

  Cenário: Reserva distribuída entre múltiplos depósitos por prioridade
    Dado o depósito "D1" (prioridade 1) com 3 unidades físicas do sku "X"
    E o depósito "D2" (prioridade 2) com 10 unidades físicas do sku "X"
    Quando reservo [{"sku": "X", "quantidade": 5}]
    Então a reserva consome 3 unidades de "D1" e 2 unidades de "D2"

  Cenário: Reserva é tudo ou nada quando um sku da lista não tem estoque suficiente
    Dado o depósito "D1" com 10 unidades físicas do sku "X" e 1 unidade do sku "Y"
    Quando reservo [{"sku": "X", "quantidade": 2}, {"sku": "Y", "quantidade": 5}]
    Então recebo ErroEstoque com code "ESTOQUE_INSUFICIENTE"
    E disponivel("X") continua sendo 10

  Cenário: Lista de itens vazia é inválida
    Quando reservo []
    Então recebo ErroEstoque com code "DADOS_INVALIDOS"

  Cenário: TTL não informado usa padrão de 900 segundos
    Dado o depósito "D1" com 10 unidades físicas do sku "X"
    E o relógio fixo em t=0
    Quando reservo [{"sku": "X", "quantidade": 1}] sem informar ttl_s
    E avanço o relógio para t=899
    Então a reserva ainda está ativa
    Quando avanço o relógio para t=900
    E consulto disponivel("X")
    Então a reserva já é tratada como expirada e disponivel("X") volta a ser 10

  Cenário: ttl_s inválido
    Quando reservo [{"sku": "X", "quantidade": 1}] com ttl_s=0
    Então recebo ErroEstoque com code "DADOS_INVALIDOS"


Funcionalidade: Confirmação e cancelamento de reserva

  Cenário: Confirmar reserva ativa baixa o físico e encerra a reserva
    Dado uma reserva ativa de 4 unidades do sku "X" no depósito "D1"
    Quando confirmo a reserva
    Então recebo {"alocacao": {"D1": {"X": 4}}}
    E o estoque físico do sku "X" no depósito "D1" diminui em 4
    E a reserva não conta mais como reservada

  Cenário: Confirmar reserva inexistente
    Quando confirmo o reserva_id "inexistente"
    Então recebo ErroEstoque com code "RESERVA_NAO_ENCONTRADA"

  Cenário: Confirmar reserva já expirada
    Dado uma reserva já expirada
    Quando confirmo essa reserva
    Então recebo ErroEstoque com code "ESTADO_INVALIDO"

  Cenário: Cancelar reserva ativa libera o reservado sem tocar o físico
    Dado uma reserva ativa de 4 unidades do sku "X" no depósito "D1"
    Quando cancelo a reserva
    Então o estoque físico do sku "X" no depósito "D1" permanece igual
    E disponivel("X") volta a incluir essas 4 unidades

  Cenário: Cancelar reserva já confirmada
    Dado uma reserva já confirmada
    Quando cancelo essa reserva
    Então recebo ErroEstoque com code "ESTADO_INVALIDO"


Funcionalidade: Expiração de reservas

  Cenário: expirar() conta reservas vencidas nesta chamada e não recontabiliza
    Dado duas reservas cujo TTL já venceu segundo o relógio
    Quando chamo expirar()
    Então o retorno é 2
    Quando chamo expirar() novamente sem novas reservas vencidas
    Então o retorno é 0

  Cenário: Expiração lazy libera disponibilidade sem chamar expirar() explicitamente
    Dado uma reserva de 4 unidades do sku "X" cujo TTL já venceu segundo o relógio
    Quando consulto disponivel("X") sem antes chamar expirar()
    Então o resultado já reflete a reserva como expirada


Funcionalidade: Transferência entre depósitos

  Cenário: Transferir estoque disponível entre depósitos
    Dado o depósito "D1" com 10 unidades físicas do sku "X" e nenhuma reserva
    E o depósito "D2" registrado
    Quando transfiro 4 unidades do sku "X" de "D1" para "D2"
    Então o físico de "D1" passa a ser 6 e o de "D2" passa a ser 4

  Cenário: Transferência não pode exceder o disponível da origem
    Dado o depósito "D1" com 10 unidades físicas do sku "X", das quais 8 estão reservadas
    Quando transfiro 5 unidades do sku "X" de "D1" para "D2"
    Então recebo ErroEstoque com code "ESTOQUE_INSUFICIENTE"

  Cenário: Origem igual ao destino é inválido
    Quando transfiro 1 unidade do sku "X" de "D1" para "D1"
    Então recebo ErroEstoque com code "DADOS_INVALIDOS"

  Cenário: Transferência com depósito de destino desconhecido
    Dado o depósito "D1" com 10 unidades físicas do sku "X"
    Quando transfiro 1 unidade do sku "X" de "D1" para "D_INEXISTENTE"
    Então recebo ErroEstoque com code "DEPOSITO_DESCONHECIDO"


Funcionalidade: Concorrência

  Cenário: Disputa concorrente pelo último item — exatamente uma reserva vence
    Dado o depósito "D1" com exatamente 1 unidade física do sku "X" e nenhuma reserva
    Quando duas chamadas concorrentes tentam reservar [{"sku": "X", "quantidade": 1}]
    Então exatamente uma chamada recebe um reserva_id válido
    E a outra recebe ErroEstoque com code "ESTOQUE_INSUFICIENTE"
```

---

## 6. Riscos aceitos (não cobertos pela elicitação — ver `registro.md`)

Os quatro pontos abaixo permanecem sem definição de negócio confirmada. Foram levantados
como perguntas [BLOQUEANTE] pelos agentes e não têm resposta disponível na fonte de
verdade consultada nesta rodada. Uma implementação de referência **não deve assumir**
comportamento único nesses casos-limite sem nova rodada de decisão:

- **R1** — `repor` com `deposito_id` desconhecido **e** `quantidade < 1` simultâneos:
  ordem de precedência entre `DADOS_INVALIDOS` e `DEPOSITO_DESCONHECIDO` indefinida.
- **R2** — `transferir` com `origem == destino` **e** quantidade excedente
  simultâneos: ordem de precedência entre `DADOS_INVALIDOS` e `ESTOQUE_INSUFICIENTE`
  indefinida; validação de `quantidade < 1` em `transferir` não confirmada.
- **R3** — `transferir` com múltiplos erros de referência desconhecida simultâneos
  (origem e destino ambos desconhecidos, ou origem desconhecida e sku desconhecido):
  ordem de precedência indefinida.
- **R4** — `disponivel(sku, deposito_id)` com `deposito_id` informado mas não
  registrado: comportamento (`DEPOSITO_DESCONHECIDO` vs. retorno `0`) indefinido.
