# UC-10 — Especificação Técnica Consolidada — Motor de Conciliação de Pagamentos

> Produzida pelo pipeline de 3 agentes de requisitos (condição C2): `working-backwards-designer`
> → `working-backwards-analyst` → `senior-functional-analyst-reviewer`. Cada requisito abaixo
> só incorpora o que foi efetivamente elicitado pelos agentes por meio de perguntas — não é
> uma cópia do gabarito de decisões, que serviu exclusivamente para responder às perguntas
> bloqueantes registradas em `registro.md`.

## Veredito de prontidão do pipeline

`PRONTO SOB RISCO REGISTRADO` (veredito final do `senior-functional-analyst-reviewer`, emitido
na 2ª e última iteração de Q&A). Quatro pontos seguem como **avanço sob risco** (opção B do
SFAR — ver `registro.md`): tratamento de linha de extrato `tipo=ESTORNO` sem interna
correspondente (RF-18), efeito de novas cargas intercaladas com `conciliar()` sobre resoluções
de transações que mudam de categoria no recálculo (RF-10/RF-13), critério de "primeira
ocorrência" em duplicata no extrato (RF-07/RF-15), e ordem de aplicação entre o filtro de
`data_corte` e a detecção de duplicata (RF-08).

---

## Requisitos Funcionais (RF)

### RF-01 — Casamento (matching) entre interna e extrato
O cruzamento entre registro interno e registro de extrato é feito **exclusivamente** por
`transacao_id`. Valor, data e tipo **não** são usados para localizar o par — servem apenas para
classificar o par já encontrado.

### RF-02 — Escopo por status
Participam da conciliação apenas as internas com `status` `APROVADA` ou `ESTORNADA`. As
`CANCELADA` são **inteiramente ignoradas**: não entram em nenhuma categoria, nem mesmo em
`SOMENTE_INTERNA` — são tratadas como se não existissem no universo de internas participantes.

Consequência direta (elicitada na 2ª iteração do `senior-functional-analyst-reviewer`): se uma
linha do extrato tiver um `transacao_id` que só corresponde a uma interna `CANCELADA`, não há
nenhuma interna participante para casar com ela — essa linha segue a regra padrão de ausência de
par e é classificada como `SOMENTE_EXTRATO`, sem categoria ou sinalização especial (o vocabulário
fechado de categoria não prevê exceção para esse caso).

### RF-03 — Coerência de tipo
`APROVADA` corresponde a `VENDA` e `ESTORNADA` corresponde a `ESTORNO`. Par com tipo trocado →
`DIVERGENTE` com motivo `TIPO_DIVERGENTE`.

### RF-04 — Comparação de valor
`valor` da interna contra `valor_bruto` do extrato, comparados como `Decimal`. **Qualquer**
diferença, inclusive de um centavo, torna o par `DIVERGENTE` com motivo `VALOR_DIVERGENTE`. Não
há tolerância.

### RF-05 — Janela de liquidação
A `data` do extrato deve estar em `[data_interna, data_interna + 2 dias]`, inclusive nas duas
pontas. Fora disso → `DIVERGENTE` com motivo `FORA_DA_JANELA`. Extrato **anterior** à data
interna também está fora da janela.

### RF-06 — Precedência dos motivos
Quando mais de um problema ocorre no mesmo par, o motivo registrado segue esta ordem:
`TIPO_DIVERGENTE` → `VALOR_DIVERGENTE` → `FORA_DA_JANELA`.

### RF-07 — Duplicatas no extrato
`transacao_id` que aparece **duas ou mais vezes** no extrato vai para `DUPLICADA`, com **um único
item** por `transacao_id`. A interna correspondente **não** é conciliada nem entra em
`SOMENTE_INTERNA` — a duplicata absorve o par. Uma transação `DUPLICADA` nunca é contada em
`CONCILIADA`.

`[AVANÇO SOB RISCO — não confirmado]` Não há critério objetivo, confirmado pela fonte de
negócio, para o que define "primeira ocorrência" do extrato (usada em `itens("DUPLICADA")`, ver
RF-15): ordem cronológica entre chamadas de `carregar_extrato`, posição dentro do lote de uma
mesma chamada, ou outro critério. Hipótese de trabalho não adotada como fato: ordem de inserção
(1ª chamada de `carregar_extrato` que introduziu o `transacao_id`, e dentro dela, 1ª posição na
lista `registros`).

### RF-08 — Data de corte
Participam as internas com `data <= data_corte` e os registros de extrato com
`data <= data_corte + 2 dias`. Os demais ficam fora da conciliação e não aparecem em nenhuma
categoria naquela execução.

`[AVANÇO SOB RISCO — não confirmado]` Não há definição de qual filtro é aplicado primeiro quando
há duplicata no extrato e apenas uma das ocorrências está dentro da janela de
`data_corte + 2 dias`: se o registro fora do corte é descartado antes da detecção de duplicata
(podendo restar apenas uma ocorrência válida, deixando de ser duplicata) ou se conta para
caracterizar a duplicidade antes de qualquer filtro de corte ser aplicado.

### RF-09 — Total líquido
Soma de `valor_bruto - taxa` das transações `CONCILIADA`, somando as de tipo `VENDA` e
**subtraindo** as de tipo `ESTORNO`. Quantizado em 2 casas com `ROUND_HALF_EVEN`. Divergentes e
duplicadas não entram.

### RF-10 — Idempotência de `conciliar()`
`conciliar()` recalcula tudo do zero a cada chamada, sempre com o mesmo resultado para a mesma
base de dados carregada. As **resoluções** já registradas via `resolver()` são preservadas entre
chamadas: uma divergência resolvida continua marcada como resolvida após reconciliar.

`[AVANÇO SOB RISCO — não confirmado]` Essa garantia foi confirmada apenas para base de dados
**estável** entre chamadas de `conciliar()`. Não há definição do comportamento quando novas
cargas (`carregar_internas`/`carregar_extrato`) ocorrem **entre** duas chamadas de `conciliar()`
e uma resolução já registrada aponta para uma transação que, no recálculo, deixa de ser
`DIVERGENTE` (por exemplo, passa a `CONCILIADA` por uma nova linha de extrato). Não deve ser
inventado um comportamento (descarte silencioso, erro, ou preservação "fantasma" da resolução).

### RF-11 — Resolução (`resolver`)
Permitida **somente** sobre transação classificada como `DIVERGENTE`. Sobre qualquer outra
categoria (`CONCILIADA`, `DUPLICADA`, `SOMENTE_INTERNA`, `SOMENTE_EXTRATO`) →
`ErroConciliacao("ESTADO_INVALIDO")`. Resolver duas vezes a mesma transação → `ESTADO_INVALIDO`.
Transação inexistente na conciliação → `ErroConciliacao("TRANSACAO_NAO_ENCONTRADA")`. `ator` ou
`observacao` vazios → `ErroConciliacao("REGISTRO_INVALIDO")`.

A ordem de verificação é estrita: **(1) existência da transação → (2) categoria e estado →
(3) argumentos `ator` e `observacao`.**

### RF-12 — Efeito da resolução
O item continua na categoria `DIVERGENTE`, mas com `resolvida=True`; ele deixa de contar em
`pendentes` no relatório. `itens("DIVERGENTE")` continua listando os itens resolvidos.

### RF-13 — Carga atômica
`carregar_internas` e `carregar_extrato` são atômicos: se qualquer registro do lote for
inválido, **nada** é carregado e o erro é levantado. Chamadas sucessivas **acumulam** registros.
Cada chamada retorna a quantidade carregada naquela chamada.

`[AVANÇO SOB RISCO — mesma raiz de RF-10]` Não há confirmação sobre se `carregar_internas`/
`carregar_extrato` podem ser chamados **depois** de `conciliar()` já ter sido executado ao menos
uma vez, nem sobre o efeito disso em resoluções já registradas (ver RF-10).

### RF-14 — Registro inválido
`ErroConciliacao("REGISTRO_INVALIDO")` quando: `transacao_id` vazio ou ausente; `valor` ou
`valor_bruto` `<= 0`; `taxa < 0`; `taxa > valor_bruto`; `data` ausente ou não é `date`; `status`
ou `tipo` fora do vocabulário; `transacao_id` repetido **dentro das internas** (o extrato admite
repetição, que vira duplicata — ver RF-07).

### RF-15 — Consultas (`itens`)
Devolve a lista ordenada por `transacao_id` crescente; categoria fora do vocabulário →
`ErroConciliacao("CATEGORIA_INVALIDA")`. `valor_interno` e `valor_extrato` são `None` quando o
lado correspondente não existe; em `DUPLICADA`, `valor_extrato` é o valor da **primeira
ocorrência** no extrato (ver ressalva de RF-07 sobre esse critério).

### RF-16 — Antes de conciliar
`itens` e `relatorio` chamados antes da primeira `conciliar()` →
`ErroConciliacao("CONCILIACAO_NAO_EXECUTADA")`.

### RF-17 — Relatório
`por_categoria` traz as **cinco** categorias do vocabulário como chaves, mesmo as de contagem
zero. `pendentes` é o número de `DIVERGENTE` não resolvidas e `resolvidas`, o de resolvidas.

### RF-18 — Estorno órfão em `SOMENTE_EXTRATO`
`[AVANÇO SOB RISCO — não confirmado]` Não há regra de negócio definida para uma linha de extrato
do tipo `ESTORNO` sem transação interna correspondente (`SOMENTE_EXTRATO` com `tipo=ESTORNO`).
Não deve ser inventada uma categoria ou motivo de risco diferenciado — o vocabulário fechado de
`categoria` e `motivo` não prevê distinção para esse caso. Fica registrado como risco de negócio
aceito: um estorno órfão pode mascarar fraude ou erro operacional real se tratado de forma
indistinta de um `SOMENTE_EXTRATO` comum.

### RF-19 — Vocabulário fechado de erros (mapeamento)

| Código | Cenário de disparo |
|---|---|
| `REGISTRO_INVALIDO` | Ver RF-14 (`carregar_internas`/`carregar_extrato`); `ator`/`observacao` vazios em `resolver` (RF-11) |
| `TRANSACAO_NAO_ENCONTRADA` | `resolver()` sobre `transacao_id` inexistente na conciliação (RF-11) |
| `ESTADO_INVALIDO` | `resolver()` sobre transação fora de `DIVERGENTE`, ou já resolvida (RF-11) |
| `CONCILIACAO_NAO_EXECUTADA` | `itens`/`relatorio` chamados antes da primeira `conciliar()` (RF-16) |
| `CATEGORIA_INVALIDA` | `itens(categoria)` com categoria fora do vocabulário fechado (RF-15) |

---

## Requisitos Não Funcionais (RNF)

### RNF-01 — Precisão monetária
Valores monetários são tratados como `decimal.Decimal`. Entradas monetárias podem chegar como
`str`, `int`, `float` ou `Decimal`. O total líquido é quantizado em 2 casas decimais com
`ROUND_HALF_EVEN` (RF-09) — não há confirmação de arredondamento em nenhum outro cálculo
intermediário além do total líquido.

### RNF-02 — Escopo e ambiente de execução
Componente de domínio em memória: arquivo único `solucao.py`, Python 3.12, apenas biblioteca
padrão. Persistência duradoura, autenticação/autorização e multitenancy não são expostas pelo
contrato (nenhum método correspondente existe na assinatura obrigatória) — tratam-se como fora
de escopo desta entrega.

### RNF-03 — Vocabulários fechados
`ErroConciliacao.code`, `categoria`, `status`, `tipo` e `motivo` assumem somente os valores
enumerados no contrato obrigatório (ver seção abaixo). O enunciado define o vocabulário, mas não
a regra de quando cada valor se aplica — as regras que puderam ser determinadas por meio das
perguntas dos agentes estão nos RF acima; as que não puderam estão marcadas como avanço sob
risco.

---

## Regras de Negócio (consolidado)

- RN-01: o casamento interno↔extrato é feito exclusivamente por `transacao_id` — nunca por
  valor, data ou tipo.
- RN-02: internas `CANCELADA` são completamente excluídas do universo participante; um extrato
  que só casa com uma `CANCELADA` cai em `SOMENTE_EXTRATO` por ausência de par elegível.
- RN-03: tipo trocado entre interna e extrato (`APROVADA`×`VENDA`, `ESTORNADA`×`ESTORNO`) é
  sempre `DIVERGENTE`/`TIPO_DIVERGENTE`.
- RN-04: qualquer diferença de valor, mesmo de um centavo, é `DIVERGENTE`/`VALOR_DIVERGENTE` —
  não há tolerância.
- RN-05: a janela de liquidação é `[data_interna, data_interna + 2 dias]`, inclusive nas duas
  pontas; extrato anterior à data interna também está fora da janela.
- RN-06: quando mais de um problema ocorre no mesmo par, prevalece nesta ordem:
  `TIPO_DIVERGENTE` → `VALOR_DIVERGENTE` → `FORA_DA_JANELA`.
- RN-07: `transacao_id` repetido no extrato absorve o par inteiro em `DUPLICADA`; nunca conta
  como `CONCILIADA`.
- RN-08: a data de corte filtra participação (interna `<= data_corte`; extrato
  `<= data_corte + 2`); o que fica fora não aparece em nenhuma categoria daquela execução.
- RN-09: o total líquido soma `(valor_bruto - taxa)` apenas de `CONCILIADA`, somando `VENDA` e
  subtraindo `ESTORNO`, quantizado em 2 casas com `ROUND_HALF_EVEN`.
- RN-10: `conciliar()` é idempotente para a mesma base de dados carregada; resoluções são
  preservadas entre chamadas.
- RN-11: `resolver()` só é válido sobre `DIVERGENTE`; a ordem de validação é estrita: existência
  → estado/categoria → argumentos.
- RN-12: resolver não remove a categoria `DIVERGENTE` — apenas marca `resolvida=True` e retira o
  item de `pendentes`.
- RN-13: a carga de dados é atômica por lote (tudo ou nada) e cumulativa entre chamadas
  sucessivas.
- RN-14: `itens()` é sempre ordenado por `transacao_id` crescente.
- RN-15: `itens`/`relatorio` antes da primeira `conciliar()` é sempre
  `CONCILIACAO_NAO_EXECUTADA`.
- RN-16: `relatorio()` sempre expõe as cinco categorias do vocabulário, mesmo com contagem zero.

---

## Critérios de Aceite (Gherkin)

```gherkin
Funcionalidade: Carga de dados

  Cenário: Lote com um registro inválido não carrega nada
    Dado um lote de 3 registros internos, sendo o 2º com valor <= 0
    Quando carregar_internas é chamado com esse lote
    Então uma ErroConciliacao com code "REGISTRO_INVALIDO" é lançada
    E nenhum dos 3 registros é carregado

  Cenário: Chamadas sucessivas acumulam registros
    Dado que carregar_internas já foi chamado uma vez com 2 registros válidos
    Quando carregar_internas é chamado novamente com mais 3 registros válidos
    Então o retorno da segunda chamada é 3
    E o total de registros internos carregados é 5

Funcionalidade: Casamento e classificação

  Cenário: Par com mesmo transacao_id, valor, tipo e dentro da janela é conciliado
    Dado uma interna APROVADA e um extrato VENDA com o mesmo transacao_id, mesmo valor
      e data do extrato igual à data interna
    Quando conciliar é executado com data_corte cobrindo ambas as datas
    Então a transação está na categoria "CONCILIADA"

  Cenário: Interna CANCELADA é ignorada por completo
    Dado uma interna com status "CANCELADA" e nenhum extrato correspondente
    Quando conciliar é executado
    Então essa transação não aparece em nenhuma categoria, nem em "SOMENTE_INTERNA"

  Cenário: Tipo trocado gera DIVERGENTE com motivo TIPO_DIVERGENTE
    Dado uma interna APROVADA cujo par no extrato tem tipo "ESTORNO"
    Quando conciliar é executado
    Então a transação está na categoria "DIVERGENTE" com motivo "TIPO_DIVERGENTE"

  Cenário: Diferença de um centavo gera DIVERGENTE com motivo VALOR_DIVERGENTE
    Dado uma interna com valor 100.00 e um par no extrato com valor_bruto 100.01
    Quando conciliar é executado
    Então a transação está na categoria "DIVERGENTE" com motivo "VALOR_DIVERGENTE"

  Cenário: Extrato fora da janela de liquidação gera FORA_DA_JANELA
    Dado uma interna com data 01/01 e um par no extrato com data 01/04
    Quando conciliar é executado
    Então a transação está na categoria "DIVERGENTE" com motivo "FORA_DA_JANELA"

  Cenário: Precedência de motivos quando mais de um problema ocorre
    Dado um par com tipo trocado e também valor divergente
    Quando conciliar é executado
    Então o motivo registrado é "TIPO_DIVERGENTE"

Funcionalidade: Duplicatas

  Cenário: transacao_id repetido no extrato vira DUPLICADA
    Dado um extrato com duas linhas para o mesmo transacao_id
    E uma interna correspondente válida
    Quando conciliar é executado
    Então existe um único item na categoria "DUPLICADA" para esse transacao_id
    E a interna correspondente não aparece em "CONCILIADA" nem em "SOMENTE_INTERNA"

Funcionalidade: Data de corte

  Cenário: Registros fora da data de corte não aparecem em nenhuma categoria
    Dado uma interna com data posterior à data_corte informada
    Quando conciliar é executado com essa data_corte
    Então essa transação não aparece em nenhuma categoria do resultado

Funcionalidade: Total líquido

  Cenário: Total líquido soma vendas e subtrai estornos das transações conciliadas
    Dado duas transações CONCILIADA do tipo VENDA com valor_bruto 100.00 e taxa 2.00 cada
    E uma transação CONCILIADA do tipo ESTORNO com valor_bruto 50.00 e taxa 1.00
    Quando conciliar é executado
    Então total_liquido é 147.00

Funcionalidade: Resolução de divergências

  Cenário: Resolver uma transação DIVERGENTE marca resolvida=True
    Dado uma transação na categoria "DIVERGENTE" e não resolvida
    Quando resolver é chamado com ator e observação não vazios
    Então o item passa a ter resolvida=True
    E deixa de contar em pendentes no relatório
    E continua aparecendo em itens("DIVERGENTE")

  Cenário: Resolver uma transação CONCILIADA é rejeitado
    Dado uma transação na categoria "CONCILIADA"
    Quando resolver é chamado para essa transação
    Então uma ErroConciliacao com code "ESTADO_INVALIDO" é lançada

  Cenário: Resolver a mesma transação duas vezes é rejeitado
    Dado uma transação DIVERGENTE já resolvida
    Quando resolver é chamado novamente para essa transação
    Então uma ErroConciliacao com code "ESTADO_INVALIDO" é lançada

  Cenário: Resolver transação inexistente é rejeitado
    Dado um transacao_id que não existe na conciliação
    Quando resolver é chamado com esse transacao_id
    Então uma ErroConciliacao com code "TRANSACAO_NAO_ENCONTRADA" é lançada

  Cenário: Resolver com ator vazio é rejeitado
    Dado uma transação DIVERGENTE válida
    Quando resolver é chamado com ator igual a string vazia
    Então uma ErroConciliacao com code "REGISTRO_INVALIDO" é lançada

  Cenário: Ordem de verificação em resolver é estrita
    Dado um transacao_id inexistente e argumentos ator/observação também vazios
    Quando resolver é chamado com esses dados
    Então uma ErroConciliacao com code "TRANSACAO_NAO_ENCONTRADA" é lançada
      (e não "REGISTRO_INVALIDO")

Funcionalidade: Consultas antes de conciliar

  Cenário: itens antes da primeira conciliação é rejeitado
    Dado que conciliar nunca foi chamado
    Quando itens é chamado com qualquer categoria válida
    Então uma ErroConciliacao com code "CONCILIACAO_NAO_EXECUTADA" é lançada

  Cenário: relatorio antes da primeira conciliação é rejeitado
    Dado que conciliar nunca foi chamado
    Quando relatorio é chamado
    Então uma ErroConciliacao com code "CONCILIACAO_NAO_EXECUTADA" é lançada

Funcionalidade: Relatório

  Cenário: por_categoria sempre traz as cinco categorias, mesmo com contagem zero
    Dado uma conciliação em que nenhuma transação caiu em "DUPLICADA"
    Quando relatorio é consultado
    Então por_categoria contém a chave "DUPLICADA" com valor 0

Funcionalidade: Categoria inválida

  Cenário: itens com categoria fora do vocabulário é rejeitado
    Dado que conciliar já foi executado
    Quando itens é chamado com a categoria "INEXISTENTE"
    Então uma ErroConciliacao com code "CATEGORIA_INVALIDA" é lançada
```

---

## Contrato obrigatório

> Copiado literalmente de `stage4/corpus/UC-10/enunciado.md`.

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão. Valores monetários são
`decimal.Decimal`; entradas monetárias podem chegar como `str`, `int`, `float` ou `Decimal`.

```python
class ErroConciliacao(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class MotorConciliacao:
    def carregar_internas(self, registros: list[dict]) -> int:
        """Cada registro: {"transacao_id": str, "valor": <monetário>,
                           "data": date, "status": str}
        Retorna a quantidade carregada."""

    def carregar_extrato(self, registros: list[dict]) -> int:
        """Cada registro: {"transacao_id": str, "valor_bruto": <monetário>,
                           "taxa": <monetário>, "data": date, "tipo": str}
        Retorna a quantidade carregada."""

    def conciliar(self, data_corte: date) -> dict:
        """Retorna {"conciliadas": int, "divergentes": int, "duplicadas": int,
                    "somente_interna": int, "somente_extrato": int,
                    "total_liquido": Decimal}"""

    def itens(self, categoria: str) -> list[dict]:
        """[{"transacao_id": str, "categoria": str, "motivo": str | None,
             "valor_interno": Decimal | None, "valor_extrato": Decimal | None,
             "resolvida": bool}]"""

    def resolver(self, transacao_id: str, ator: str, observacao: str) -> None: ...

    def relatorio(self) -> dict:
        """Retorna {"por_categoria": dict[str, int], "pendentes": int,
                    "resolvidas": int, "total_liquido": Decimal}"""
```

### Vocabulário fechado

`ErroConciliacao.code` assume **somente**: `REGISTRO_INVALIDO`,
`TRANSACAO_NAO_ENCONTRADA`, `ESTADO_INVALIDO`, `CONCILIACAO_NAO_EXECUTADA`,
`CATEGORIA_INVALIDA`.

A `categoria` assume **somente**: `CONCILIADA`, `DIVERGENTE`, `DUPLICADA`,
`SOMENTE_INTERNA`, `SOMENTE_EXTRATO`.

O `status` do registro interno assume **somente**: `APROVADA`, `CANCELADA`, `ESTORNADA`.

O `tipo` do registro de extrato assume **somente**: `VENDA`, `ESTORNO`.

O `motivo` assume **somente**: `VALOR_DIVERGENTE`, `TIPO_DIVERGENTE`, `FORA_DA_JANELA`,
`None`.

> Este enunciado define o vocabulário, não a regra: em que circunstância cada código,
> categoria, status, tipo e motivo se aplica faz parte do que precisa ser decidido.

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
