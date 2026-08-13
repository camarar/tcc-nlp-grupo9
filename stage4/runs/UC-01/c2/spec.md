# UC-01 — Especificação Técnica Consolidada — Motor de Amortização de Empréstimo

> Produzida pelo pipeline de 3 agentes de requisitos (condição C2): `working-backwards-designer`
> → `working-backwards-analyst` → `senior-functional-analyst-reviewer`. Cada requisito abaixo
> só incorpora o que foi efetivamente elicitado pelos agentes por meio de perguntas — não é
> uma cópia do gabarito de decisões, que serviu exclusivamente para responder às perguntas
> bloqueantes registradas em `registro.md`.

## Veredito de prontidão do pipeline

`PRONTO PARA SOLUÇÃO SOB RISCO REGISTRADO` (veredito final do `senior-functional-analyst-reviewer`).
Três premissas seguem como **avanço sob risco** (opção B do SFAR — ver `registro.md`): GAP-01
(fórmula exata PRICE/SAC), GAP-02 (regime de capitalização de juros no cronograma regular) e
GAP-03 (comportamento de pagamento de parcela fora de ordem).

---

## Requisitos Funcionais (RF)

### RF-01 — Criação de contrato e validação de entrada
`criar_contrato(dados)` deve lançar `ErroEmprestimo("CONTRATO_INVALIDO")` quando: `principal <= 0`;
`prazo_meses < 1` ou `> 120`; `taxa < 0`; `carencia_meses < 0`; `data_inicio` ausente ou não é
`date`; qualquer chave obrigatória ausente; `sistema` ausente, vazio ou fora de `{"PRICE", "SAC"}`
(não existe valor default para `sistema`).

`[AVANÇO SOB RISCO — não confirmado]` Se `taxa == 0` é um valor de entrada válido não foi
confirmado pela fonte de negócio; hipótese de trabalho: válido (só `taxa < 0` é inválida).

### RF-02 — Carência
`carencia_meses` (default `0`, inteiro ≥ 0) suspende a geração de parcelas durante o período,
mas os juros capitalizam sobre o saldo: o principal efetivamente financiado passa a ser
`principal * (1 + taxa) ** carencia_meses`, quantizado em 2 casas decimais (`ROUND_HALF_EVEN`)
antes de gerar o cronograma. Nenhuma parcela é listada em `cronograma()` durante a carência.
A primeira parcela vence `carencia_meses + 1` meses após `data_inicio`. `prazo_meses` representa
exclusivamente o número de parcelas geradas após a carência (a carência é somada ao prazo total
do contrato, não descontada dele).

`[AVANÇO SOB RISCO — GAP-02]` A regra de capitalização durante a carência pressupõe o mesmo
regime de juros do cronograma regular pós-carência, que não foi confirmado (ver RF-03).

### RF-03 — Geração de cronograma (PRICE e SAC)
`cronograma(contrato_id)` deve gerar `prazo_meses` parcelas, cada uma com exatamente as chaves
`{"numero", "vencimento", "juros", "amortizacao", "valor", "saldo_apos"}`, segundo o sistema
informado em `criar_contrato`:

- **PRICE:** parcela (`valor`) constante ao longo do cronograma.
- **SAC:** amortização (`amortizacao`) constante ao longo do cronograma, com `valor` decrescente.

Datas de vencimento são mensais, no mesmo dia do mês de `data_inicio`; quando o dia não existe no
mês de destino, usa-se o último dia do mês (ex.: 31/01 → 28/02).

A soma das `amortizacao` de todas as parcelas deve ser **exatamente** igual ao principal
financiado (já ajustado por carência, se houver); o resíduo de arredondamento é absorvido na
**última** parcela (na amortização), e o `valor` dessa parcela é recalculado como
`juros + amortizacao`. `saldo_apos` da última parcela é exatamente `0.00`. Todos os valores são
`Decimal` quantizados em 2 casas com `ROUND_HALF_EVEN`.

`[AVANÇO SOB RISCO — GAP-01, não confirmado]` A fórmula matemática exata de PRICE (incluindo
tratamento de arredondamento do fator de anuidade) e de SAC não foi confirmada pela fonte de
negócio. Hipótese de trabalho adotada pelos agentes: convenções-padrão de mercado (PRICE: parcela
constante via fator de anuidade `taxa/(1-(1+taxa)**-prazo)`; SAC: amortização constante
`principal/prazo_meses`), com juros de cada parcela calculados sobre o saldo devedor do início do
período. **Deve ser validada com exemplo numérico assinado pelo negócio antes de release.**

`[AVANÇO SOB RISCO — GAP-02, não confirmado]` Se o regime de juros do cronograma regular
(pós-carência) é composto mês a mês sobre o saldo remanescente ou simples não foi confirmado pela
fonte. Hipótese de trabalho: composto mês a mês (por analogia com a capitalização confirmada
durante a carência em RF-02).

### RF-04 — Valor devido por parcela
`valor_devido(contrato_id, numero_parcela, data)` retorna
`{"principal": Decimal, "juros": Decimal, "encargos": Decimal, "total": Decimal}`, onde
`principal` é a amortização da parcela, `juros` é o juros da parcela, `encargos` é calculado
conforme RF-05 (zero se não houver atraso na `data`), e `total` é a soma dos três.

### RF-05 — Encargos de atraso
Calculados sobre o `valor` da parcela, a partir do dia seguinte ao vencimento: multa fixa de
**2%** mais juros de mora de **1% ao mês pro rata die em base 30**
(`valor * 0.01 * dias_atraso / 30`). O total é quantizado em 2 casas `ROUND_HALF_EVEN`. Sem
atraso, `encargos = 0.00`.

`[AVANÇO SOB RISCO — não confirmado]` Não há confirmação sobre teto/limite máximo de acúmulo de
encargos (crescimento indefinido enquanto a parcela permanecer em aberto), nem sobre se o "valor
original da parcela" usado como base muda quando a parcela já recebeu pagamento parcial.

### RF-06 — Registro de pagamento e alocação
`registrar_pagamento(contrato_id, pagamento_id, numero_parcela, valor, data)` aceita pagamento
parcial. A imputação do valor segue estritamente esta ordem: (1) encargos de atraso, (2) juros da
parcela, (3) amortização do principal, interrompendo quando o valor se esgota. A parcela só é
considerada quitada (`parcela_quitada=True`) quando os três componentes chegam a zero. O retorno
traz os valores efetivamente aplicados em cada componente (`aplicado_encargos`,
`aplicado_juros`, `aplicado_principal`).

Pagamento com `valor` maior que o `total` devido da parcela na data → `ErroEmprestimo("VALOR_INVALIDO")`;
não há amortização automática de parcelas futuras com o excedente. `valor` menor ou igual a zero
também é `VALOR_INVALIDO`.

`[AVANÇO SOB RISCO — GAP-03, não confirmado]` Não foi confirmado se é permitido registrar
pagamento para uma parcela fora de ordem (ex.: pagar a parcela 5 com a parcela 3 ainda em
aberto). Hipótese de trabalho: permitido, já que o vocabulário fechado de erros não contém código
específico para essa situação.

### RF-07 — Idempotência de pagamento
Se `pagamento_id` já foi registrado para o contrato, nada é alterado — independentemente do
`numero_parcela` ou `valor` do novo payload recebido. O retorno traz `duplicado=True`, os três
campos `aplicado_*` em `Decimal("0.00")`, e `parcela_quitada` refletindo o estado real e atual da
parcela.

### RF-08 — Saldo devedor
`saldo_devedor(contrato_id, data)` = principal ainda não amortizado + juros já vencidos e não
pagos + encargos de atraso na data. **Não** inclui juros de parcelas futuras (ainda não
vencidas).

### RF-09 — Situação do contrato
`situacao(contrato_id, data)` não é um estado persistido: é avaliada dinamicamente a cada
chamada, nesta ordem de precedência: `RENEGOCIADO` → `QUITADO` (saldo devedor zero) →
`EM_ATRASO` (existe parcela vencida na data e ainda não quitada, sem tolerância mínima de dias) →
`ATIVO`.

`[AVANÇO SOB RISCO — não confirmado]` Não foi confirmada explicitamente a relação entre a ausência
de tolerância mínima em `EM_ATRASO` (qualquer atraso já classifica) e a exigência de 30+ dias de
atraso para elegibilidade de `renegociar` (RF-11) — tratadas como regras independentes e
intencionalmente distintas (uma classifica status, outra define elegibilidade de ação).

### RF-10 — Quitação antecipada
`quitar_antecipado(contrato_id, data)` retorna
`{"valor_quitacao": Decimal, "desconto_juros_futuros": Decimal}`, onde `valor_quitacao` =
principal remanescente + encargos de atraso das parcelas vencidas, e `desconto_juros_futuros` =
soma de todos os juros das parcelas ainda não vencidas (integralmente dispensados). A distinção é
estritamente binária (vencida vs. não vencida), sem cálculo pró-rata para a parcela do período em
curso. O contrato passa a `QUITADO`.

### RF-11 — Renegociação
`renegociar(contrato_id, novo_prazo_meses, nova_taxa, data)` é permitida somente se, na `data`
informada, existir parcela vencida há **30 dias ou mais**; caso contrário →
`ErroEmprestimo("RENEGOCIACAO_NAO_PERMITIDA")`. O novo contrato é criado com
`principal = saldo_devedor(contrato_id, data)` do contrato original (portanto **inclui** os
encargos de atraso acumulados — não são perdoados), `sistema` igual ao do contrato original,
`carencia_meses = 0` e `data_inicio = data`. O contrato original passa a `RENEGOCIADO`
(preservado, não removido).

`[AVANÇO SOB RISCO — não confirmado]` Quando existem múltiplas parcelas vencidas com atrasos
distintos, não foi confirmado se basta **uma** parcela com 30+ dias para habilitar a
renegociação (hipótese de trabalho adotada) ou se há regra adicional.

### RF-12 — Estados terminais
Contrato em `QUITADO` ou `RENEGOCIADO` recusa `registrar_pagamento`, `quitar_antecipado` e
`renegociar` com `ErroEmprestimo("ESTADO_INVALIDO")`. `cronograma`, `saldo_devedor` e `situacao`
continuam consultáveis nesses estados.

### RF-13 — Vocabulário fechado de erros (mapeamento)

| Código | Cenário de disparo |
|---|---|
| `CONTRATO_INVALIDO` | Ver condições de RF-01 |
| `CONTRATO_NAO_ENCONTRADO` | `contrato_id` desconhecido, em qualquer método — verificado antes de qualquer outra validação |
| `PARCELA_INVALIDA` | `numero_parcela` fora de `1..prazo_meses` — verificado depois da checagem de `contrato_id` |
| `ESTADO_INVALIDO` | `registrar_pagamento`, `quitar_antecipado` ou `renegociar` em contrato `QUITADO` ou `RENEGOCIADO` |
| `RENEGOCIACAO_NAO_PERMITIDA` | `renegociar` sem parcela vencida há 30+ dias na data informada |
| `VALOR_INVALIDO` | `registrar_pagamento` com `valor <= 0` OU `valor` maior que o `total` devido da parcela na data |

`sistema` do dicionário `dados` assume somente `PRICE` ou `SAC`.

---

## Requisitos Não Funcionais (RNF)

### RNF-01 — Precisão monetária
Todo valor monetário de entrada/saída é `decimal.Decimal`, quantizado em exatamente 2 casas
decimais com `ROUND_HALF_EVEN` em todos os pontos de cálculo e retorno. Entradas monetárias e de
taxa podem chegar como `str`, `int`, `float` ou `Decimal`.

### RNF-02 — Determinismo
Dado o mesmo relógio injetado (`agora`, via construtor de `MotorEmprestimo`) e a mesma sequência
de operações, o motor deve produzir exatamente os mesmos valores de cronograma, saldo e encargos —
sem dependência de estado externo não controlado. Quando `agora` não é fornecido, usa-se o
relógio do sistema.

`[AVANÇO SOB RISCO — não confirmado]` Não foi confirmado se existe alguma interface de clock
separada além do parâmetro `data`, explícito em quase todos os métodos públicos; hipótese de
trabalho: não há clock oculto adicional.

### RNF-03 — Escopo (decisão, não lacuna)
Persistência duradoura, autenticação/autorização, transporte de dados e observabilidade
(logs/métricas) não fazem parte do contrato de `MotorEmprestimo`; a classe é um componente de
domínio puro, biblioteca padrão apenas, operando em memória durante o processo.

---

## Regras de Negócio (consolidado)

- RN-01: `sistema` é obrigatório e não tem default; fora do vocabulário fechado → `CONTRATO_INVALIDO`.
- RN-02: `taxa` é sempre mensal efetiva, em fração decimal — nunca anual, nunca convertida.
- RN-03: arredondamento monetário é sempre `Decimal`, 2 casas, `ROUND_HALF_EVEN`.
- RN-04: resíduo de arredondamento do cronograma é absorvido inteiramente na última parcela.
- RN-05: carência capitaliza juros sobre o saldo e adia (não substitui) parcelas.
- RN-06: vencimentos mensais seguem o dia de `data_inicio`, com ajuste para o último dia do mês quando o dia não existe no mês de destino.
- RN-07: imputação de pagamento é sempre encargos → juros → principal.
- RN-08: pagamento idempotente por `pagamento_id`, independente do payload em reenvios.
- RN-09: saldo devedor nunca inclui juros de parcelas futuras.
- RN-10: quitação antecipada dispensa integralmente juros de parcelas não vencidas.
- RN-11: renegociação exige parcela vencida há 30+ dias; herda saldo com encargos, sem perdão.
- RN-12: estados terminais (`QUITADO`, `RENEGOCIADO`) bloqueiam mutação, não leitura.
- RN-13: verificação de `contrato_id` sempre precede verificação de `numero_parcela`.

---

## Critérios de Aceite (Gherkin)

```gherkin
Funcionalidade: Criação de contrato

  Cenário: Sistema de amortização ausente é rejeitado
    Dado um dicionário de dados de contrato sem a chave "sistema"
    Quando criar_contrato é chamado com esses dados
    Então uma ErroEmprestimo com code "CONTRATO_INVALIDO" é lançada

  Cenário: Sistema de amortização fora do vocabulário fechado é rejeitado
    Dado um dicionário de dados de contrato com sistema "TABELA_X"
    Quando criar_contrato é chamado com esses dados
    Então uma ErroEmprestimo com code "CONTRATO_INVALIDO" é lançada

Funcionalidade: Geração de cronograma

  Cenário: Soma das amortizações é exatamente o principal financiado
    Dado um contrato criado com sistema "SAC" e principal "1000.00"
    Quando o cronograma é gerado
    Então a soma de "amortizacao" de todas as parcelas é exatamente "1000.00"
    E o "saldo_apos" da última parcela é exatamente "0.00"

  Cenário: Carência adia a primeira parcela e capitaliza juros
    Dado um contrato criado com carencia_meses igual a 2 e data_inicio "2026-01-15"
    Quando o cronograma é gerado
    Então a primeira parcela vence em "2026-04-15"
    E nenhuma parcela é listada para os meses de carência

Funcionalidade: Pagamento

  Cenário: Pagamento parcial é aceito e imputado na ordem correta
    Dado uma parcela com encargos "10.00", juros "20.00" e amortização "70.00" ainda em aberto
    Quando um pagamento de valor "50.00" é registrado
    Então aplicado_encargos é "10.00"
    E aplicado_juros é "20.00"
    E aplicado_principal é "20.00"
    E parcela_quitada é falso

  Cenário: Pagamento maior que o total devido é rejeitado
    Dado uma parcela com total devido "500.00" na data
    Quando um pagamento de valor "600.00" é registrado
    Então uma ErroEmprestimo com code "VALOR_INVALIDO" é lançada

  Cenário: Reenvio do mesmo pagamento_id é idempotente
    Dado um pagamento já registrado com pagamento_id "PAG-1"
    Quando registrar_pagamento é chamado novamente com o mesmo pagamento_id "PAG-1" e payload diferente
    Então duplicado é verdadeiro
    E aplicado_encargos, aplicado_juros e aplicado_principal são "0.00"
    E nenhum estado do contrato é alterado

Funcionalidade: Situação do contrato

  Cenário: Contrato com parcela vencida e não paga fica EM_ATRASO
    Dado um contrato ATIVO com uma parcela vencida e não quitada na data de referência
    Quando situacao é consultada nessa data
    Então o resultado é "EM_ATRASO"

  Cenário: Contrato retorna a ATIVO após quitar a pendência
    Dado um contrato que estava EM_ATRASO e teve a parcela vencida quitada
    Quando situacao é consultada em uma data posterior à quitação
    Então o resultado é "ATIVO"

Funcionalidade: Quitação antecipada

  Cenário: Quitação antecipada dispensa juros futuros
    Dado um contrato ATIVO com parcelas futuras ainda não vencidas
    Quando quitar_antecipado é chamado
    Então desconto_juros_futuros é igual à soma dos juros de todas as parcelas não vencidas
    E a situacao do contrato passa a "QUITADO"

Funcionalidade: Renegociação

  Cenário: Renegociação recusada sem atraso suficiente
    Dado um contrato ATIVO sem nenhuma parcela vencida há 30 dias ou mais
    Quando renegociar é chamado
    Então uma ErroEmprestimo com code "RENEGOCIACAO_NAO_PERMITIDA" é lançada

  Cenário: Renegociação bem-sucedida herda o saldo com encargos
    Dado um contrato com parcela vencida há 45 dias e saldo_devedor "1200.00" (incluindo encargos)
    Quando renegociar é chamado com novo_prazo_meses e nova_taxa válidos
    Então um novo contrato_id é retornado
    E o principal do novo contrato é "1200.00"
    E a situacao do contrato original passa a "RENEGOCIADO"

Funcionalidade: Estados terminais

  Cenário: Contrato QUITADO recusa novo pagamento
    Dado um contrato em situacao "QUITADO"
    Quando registrar_pagamento é chamado
    Então uma ErroEmprestimo com code "ESTADO_INVALIDO" é lançada

  Cenário: Contrato QUITADO permanece consultável
    Dado um contrato em situacao "QUITADO"
    Quando cronograma, saldo_devedor e situacao são consultados
    Então nenhuma exceção é lançada
```

---

## Contrato obrigatório

> Copiado literalmente de `stage4/corpus/UC-01/enunciado.md`.

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão. Valores monetários
trafegam como `decimal.Decimal`. Entradas monetárias e de taxa podem chegar como `str`,
`int`, `float` ou `Decimal`.

```python
class ErroEmprestimo(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class MotorEmprestimo:
    def __init__(self, agora: Callable[[], datetime] | None = None) -> None:
        """`agora` é um relógio injetável; quando ausente, usar o relógio do sistema."""

    def criar_contrato(self, dados: dict) -> str:
        """`dados` tem as chaves: principal, taxa, prazo_meses, sistema,
        carencia_meses (opcional) e data_inicio (datetime.date).
        Retorna o identificador do contrato."""

    def cronograma(self, contrato_id: str) -> list[dict]:
        """Cada item tem exatamente as chaves:
        {"numero": int, "vencimento": date, "juros": Decimal,
         "amortizacao": Decimal, "valor": Decimal, "saldo_apos": Decimal}"""

    def valor_devido(self, contrato_id: str, numero_parcela: int, data: date) -> dict:
        """Retorna {"principal": Decimal, "juros": Decimal,
                    "encargos": Decimal, "total": Decimal}"""

    def registrar_pagamento(self, contrato_id: str, pagamento_id: str,
                            numero_parcela: int, valor, data: date) -> dict:
        """Retorna {"duplicado": bool, "aplicado_encargos": Decimal,
                    "aplicado_juros": Decimal, "aplicado_principal": Decimal,
                    "parcela_quitada": bool}"""

    def saldo_devedor(self, contrato_id: str, data: date) -> Decimal: ...

    def quitar_antecipado(self, contrato_id: str, data: date) -> dict:
        """Retorna {"valor_quitacao": Decimal, "desconto_juros_futuros": Decimal}"""

    def renegociar(self, contrato_id: str, novo_prazo_meses: int,
                   nova_taxa, data: date) -> str:
        """Retorna o identificador do novo contrato."""

    def situacao(self, contrato_id: str, data: date) -> str: ...
```

### Vocabulário fechado

`ErroEmprestimo.code` assume **somente** um destes valores:

`CONTRATO_INVALIDO`, `CONTRATO_NAO_ENCONTRADO`, `ESTADO_INVALIDO`, `VALOR_INVALIDO`,
`PARCELA_INVALIDA`, `RENEGOCIACAO_NAO_PERMITIDA`.

`situacao()` retorna **somente** um destes valores:

`ATIVO`, `EM_ATRASO`, `QUITADO`, `RENEGOCIADO`.

O campo `sistema` de `dados` assume **somente** um destes valores: `PRICE`, `SAC`.

> Este enunciado define o vocabulário, não a regra: em que circunstância cada código de
> erro, cada situação e cada sistema de amortização se aplica faz parte do que precisa
> ser decidido.

### Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
