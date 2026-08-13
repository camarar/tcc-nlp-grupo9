# Especificação Técnica Consolidada — UC-05: Motor de Split e Liquidação de Recebíveis

> Documento produzido pelo pipeline de 3 agentes (working-backwards-designer →
> working-backwards-analyst → senior-functional-analyst-reviewer), condição C2.
> Todo o conteúdo de regra de negócio abaixo corresponde a lacunas efetivamente
> elicitadas pelos agentes por meio de perguntas [BLOQUEANTE], respondidas por um
> "product owner" (o orquestrador, consultando `gabarito.md`) ou registradas como
> avanço sob risco quando o gabarito não continha resposta. Ver `registro.md` para o
> histórico completo de iterações e `captura.json` para a lista literal das perguntas.

## Requisitos Funcionais (RF)

### RF-01 — Validação da transação
`registrar_transacao(dados)` deve lançar `ErroRecebivel("TRANSACAO_INVALIDA")` quando:
`valor <= 0`; `parcelas < 1` ou `parcelas > 12`; `mdr < 0` ou `mdr >= 1`; `data` ausente
ou não é `date`. A validação da transação é executada **antes** da validação do split
(RF-02).

### RF-02 — Validação do split
`registrar_transacao(dados)` deve lançar `ErroRecebivel("SPLIT_INVALIDO")` quando: a
soma dos `percentual` do split é diferente de `1`; há `participante` repetido; algum
`percentual <= 0`; a lista de split está vazia ou ausente. Não há subcategorias de
código para esses cenários — todos retornam `SPLIT_INVALIDO`.

### RF-03 — Geração de recebíveis: parcelas e vencimentos
Ao registrar uma transação válida, o valor total é dividido **igualmente** entre as
`parcelas`, quantizado em 2 casas decimais com `ROUND_HALF_EVEN`; o resíduo de
arredondamento é somado à **primeira** parcela, de modo que a soma das parcelas seja
exatamente o `valor` da transação. A parcela `n` vence em `data + 30 × n` dias corridos
(a primeira parcela em `data + 30`; nunca na data da transação).

### RF-04 — Split por parcela entre participantes
O valor bruto de cada parcela é rateado entre os participantes do split
proporcionalmente ao `percentual`, quantizado em 2 casas decimais. O resíduo (positivo
ou negativo) desse rateio é ajustado no participante de **maior `percentual`**
(em caso de empate, o de menor nome em ordem lexicográfica), de forma que a soma dos
`valor_bruto` dos recebíveis de uma parcela seja exatamente o valor bruto daquela
parcela.

### RF-05 — Cálculo de MDR por recebível
O split (RF-04) é aplicado antes do MDR. O MDR incide sobre o `valor_bruto` de **cada
recebível já rateado por participante**: `taxa = quantize(valor_bruto × mdr)` e
`valor_liquido = valor_bruto − taxa`. `mdr` é uma fração decimal (`0.04` = 4%). Cada
participante absorve o MDR proporcional à própria fatia — o MDR não é descontado do
total antes do split nem exclusivamente da fatia da plataforma.

### RF-06 — Consulta de recebíveis
`recebiveis(transacao_id)` devolve **todos** os recebíveis da transação, inclusive os
que já estão em `ESTORNADO` ou `LIQUIDADO`, ordenados por `(parcela, participante)`.

### RF-07 — Elegibilidade da antecipação
`antecipar(transacao_id, participante, ate_parcela, data)` seleciona os recebíveis do
`participante` informado que estejam em situação `A_RECEBER` e com `parcela <=
ate_parcela`. Esses recebíveis passam a `ANTECIPADO`. Recebíveis do participante já em
`ANTECIPADO`, `LIQUIDADO` ou `ESTORNADO` são ignorados silenciosamente (não geram erro
por si só). Se, após a filtragem, **nenhum** recebível for elegível, é lançado
`ErroRecebivel("ESTADO_INVALIDO")`.

### RF-08 — Cálculo do deságio da antecipação
O deságio é de **1,5% ao mês, pro rata die, em base 30**, aplicado ao `valor_liquido`
de cada recebível antecipado: `dias = (vencimento − data).days`; se `dias <= 0`, o
deságio daquele recebível é `0.00`. Fórmula: `deságio_recebível =
quantize(valor_liquido × 0.015 × dias / 30)`, calculado e quantizado **por recebível**
e depois somado para compor o deságio total. A taxa de 1,5%/mês é fixa (não é parâmetro
configurável) e não há teto/piso para o valor do deságio. O `valor_liquido` retornado
por `antecipar` é a soma dos líquidos dos recebíveis elegíveis menos o deságio total.

### RF-09 — Validação e precedência de erros em `antecipar`
Nesta ordem: `TRANSACAO_NAO_ENCONTRADA` (transação inexistente) →
`PARTICIPANTE_INVALIDO` (participante fora do split da transação) → `PARCELA_INVALIDA`
(`ate_parcela` fora do intervalo `1..parcelas` da transação) → `ESTADO_INVALIDO`
(nenhum recebível elegível dentro de uma faixa de `ate_parcela` válida, conforme RF-07).

### RF-10 — Liquidação diária
`liquidar(data)` liquida os recebíveis com `vencimento <= data` (modo catch-up, cobre
vencidos não processados em execuções anteriores) que estejam em situação `A_RECEBER`,
marcando-os `LIQUIDADO`. Recebíveis `ANTECIPADO` **nunca** são liquidados — o direito já
foi cedido. O retorno é ordenado por `(transacao_id, parcela, participante)`.

### RF-11 — Idempotência da liquidação
Chamar `liquidar` novamente para uma data já processada não reliquida nenhum recebível
e devolve lista vazia.

### RF-12 — Rateio do estorno entre recebíveis
`estornar(transacao_id, valor, data)` rateia o `valor` solicitado
**proporcionalmente ao `valor_bruto`** entre **todos** os recebíveis da transação que
estejam em situação `A_RECEBER` (independentemente do participante — não é rateado pelo
percentual de split original, e sim pelo `valor_bruto` remanescente de cada recebível
elegível). Recebíveis em `ANTECIPADO`, `LIQUIDADO` ou `ESTORNADO` nunca são atingidos.
O `valor_bruto` de cada recebível atingido é reduzido pelo valor rateado; quando esse
`valor_bruto` chega a `0.00`, a situação do recebível passa a `ESTORNADO`. Um mesmo
recebível pode sofrer múltiplos estornos parciais sucessivos até zerar. Após cada
redução, `taxa` e `valor_liquido` do recebível são **recalculados** pela regra de MDR
(RF-05) sobre o novo `valor_bruto` — não ficam congelados com os valores originais. O
recálculo é um ajuste contábil local ao próprio recebível; não existe fluxo separado de
"devolução de MDR" nem campo adicional para representá-lo.

### RF-13 — Resíduo do rateio de estorno
O rateio do estorno é quantizado em 2 casas decimais; o resíduo (positivo ou negativo)
é ajustado no recebível de **maior `valor_bruto`** (empate: menor `parcela`; novo
empate: menor `participante`), de modo que a soma rateada seja exatamente o `valor`
solicitado. O campo `estornado` do retorno é sempre igual ao valor solicitado, e
`soma(por_participante.values()) == estornado`.

### RF-14 — Validação e precedência de erros em `estornar`
`estornar` não recebe `participante` nem `parcela`, portanto os códigos
`PARTICIPANTE_INVALIDO` e `PARCELA_INVALIDA` não se aplicam a esta operação. A
precedência de validação é: `TRANSACAO_NAO_ENCONTRADA` → `ESTADO_INVALIDO` (transação
sem nenhum recebível em `A_RECEBER`) → `VALOR_INVALIDO` (`valor <= 0` ou `valor` maior
que a soma dos `valor_bruto` em `A_RECEBER`). A checagem de estado precede a de valor.

### RF-15 — Posição consolidada como retrato temporal
`posicao(participante, data)` reflete um corte histórico "as of" a `data` informada,
considerando apenas eventos (antecipação, liquidação, estorno) ocorridos **até `data`,
inclusive**. `antecipado` e `liquidado` somam o `valor_liquido` dos recebíveis cujo
evento de antecipação/liquidação ocorreu com data `<= data`. `estornado` soma o valor
bruto de **cada** estorno parcial (evento independente) cuja data seja `<= data` — não
apenas o último estorno de cada recebível. `a_receber` soma o `valor_liquido` dos
recebíveis que, naquela data, ainda não haviam sofrido nenhum evento. Um participante
sem nenhum recebível associado devolve todos os campos em `0.00` (não é erro). Para
sustentar este requisito, o motor deve manter internamente a data de cada evento por
recebível, mesmo que esse histórico não seja exposto por nenhum método público do
contrato.

### RF-16 — Vocabulário de erro e situação (fechado)
`ErroRecebivel.code` assume somente: `TRANSACAO_INVALIDA`, `SPLIT_INVALIDO`,
`PARCELA_INVALIDA`, `ESTADO_INVALIDO`, `TRANSACAO_NAO_ENCONTRADA`,
`PARTICIPANTE_INVALIDO`, `VALOR_INVALIDO`. `situacao` do recebível assume somente:
`A_RECEBER`, `ANTECIPADO`, `LIQUIDADO`, `ESTORNADO`. Cada operação usa apenas o
subconjunto de códigos compatível com sua própria assinatura (ver RF-09 e RF-14).

## Requisitos Não Funcionais (RNF)

### RNF-01 — Precisão monetária (ISO/IEC 25010: Adequação Funcional / Confiabilidade)
Todos os valores monetários são `decimal.Decimal`. Todo cálculo intermediário
(divisão de parcelas, split por participante, MDR, deságio, rateio de estorno) usa
quantização em 2 casas decimais com `ROUND_HALF_EVEN` como modo de arredondamento
padrão do sistema. Entradas monetárias podem chegar como `str`, `int`, `float` ou
`Decimal` e devem ser normalizadas para `Decimal` na borda de entrada.

### RNF-02 — Vocabulário fechado e estabilidade de contrato (ISO/IEC 25010: Manutenibilidade / Compatibilidade)
Os vocabulários de `ErroRecebivel.code` e de `situacao` são fechados (RF-16); nenhuma
implementação deve introduzir valores fora dessas listas.

### RNF-03 — Itens registrados como avanço sob risco (ISO/IEC 25010: Confiabilidade / Segurança)
Os itens abaixo não têm definição de negócio disponível no processo de elicitação
(não constam no material consultado para responder às perguntas bloqueantes) e foram
formalmente registrados como avanço sob risco (opção B do SFAR) — ver `registro.md`.
Não bloqueiam a implementação do núcleo funcional descrito em RF-01 a RF-16, mas devem
ser resolvidos no desenho técnico antes de exposição em produção multi-tenant:
- Controle de concorrência/locking entre operações concorrentes sobre a mesma
  transação/recebível (ex.: `antecipar` e `estornar` simultâneos).
- Idempotência de `estornar`/`antecipar` e semântica de falha em processamento parcial
  de um lote (diferente de `liquidar`, que é idempotente por definição — RF-11).
- Controle de acesso entre participantes (quem pode consultar `posicao`/`recebiveis`
  de qual participante).

## Critérios de Aceite (Gherkin)

```gherkin
Funcionalidade: Registro de transação

  Cenário: Rejeitar transação com valor não positivo
    Dado que não existe nenhuma transação registrada
    Quando registro uma transação com valor "0.00", 3 parcelas, mdr "0.04" e split válido somando 100%
    Então o motor lança ErroRecebivel com code "TRANSACAO_INVALIDA"

  Cenário: Rejeitar transação com número de parcelas fora do intervalo permitido
    Quando registro uma transação com valor "300.00", 13 parcelas, mdr "0.04" e split válido somando 100%
    Então o motor lança ErroRecebivel com code "TRANSACAO_INVALIDA"

  Cenário: Rejeitar transação cujo split não soma 100%
    Dado uma transação com valor "300.00", 3 parcelas e mdr "0.04" válidos
    Quando o split informado tem percentuais que somam "0.90"
    Então o motor lança ErroRecebivel com code "SPLIT_INVALIDO"

  Cenário: Validação da transação precede a validação do split
    Quando registro uma transação com valor "-10.00" e split com percentuais que somam "0.5"
    Então o motor lança ErroRecebivel com code "TRANSACAO_INVALIDA"

  Cenário: Gerar parcelas e vencimentos corretamente
    Dado uma transação de valor "100.00" registrada em "2026-01-01" com 3 parcelas e split
      | participante | percentual |
      | lojista_a    | 0.70       |
      | plataforma   | 0.30       |
    Quando consulto os recebíveis da transação
    Então existem 3 vencimentos: "2026-01-31", "2026-03-02", "2026-03-31"
    E a soma dos valor_bruto de todas as parcelas é exatamente "100.00"
    E o resíduo de arredondamento da divisão em parcelas está na parcela 1

Funcionalidade: Antecipação de recebíveis

  Cenário: Antecipar parcelas futuras com deságio pro rata die
    Dado um recebível A_RECEBER do participante "lojista_a" com valor_liquido "96.00" e vencimento "2026-03-31"
    Quando lojista_a antecipa até a parcela correspondente na data "2026-03-01"
    Então o deságio calculado é "quantize(96.00 × 0.015 × 30 / 30)" = "1.44"
    E o recebível passa para a situação "ANTECIPADO"

  Cenário: Antecipação sem deságio quando a data é igual ou posterior ao vencimento
    Dado um recebível A_RECEBER com vencimento "2026-03-31"
    Quando o participante antecipa na data "2026-03-31"
    Então o deságio daquele recebível é "0.00"

  Cenário: Recebíveis não elegíveis são ignorados silenciosamente
    Dado um recebível na parcela 1 já em situação "LIQUIDADO" e um recebível na parcela 2 em "A_RECEBER"
    Quando o participante antecipa até a parcela 2
    Então apenas o recebível da parcela 2 passa a "ANTECIPADO"

  Cenário: Nenhum recebível elegível resulta em erro de estado
    Dado que todos os recebíveis do participante até a parcela informada já estão "LIQUIDADO"
    Quando o participante solicita antecipação
    Então o motor lança ErroRecebivel com code "ESTADO_INVALIDO"

  Cenário: ate_parcela fora do intervalo válido da transação
    Dado uma transação com 3 parcelas
    Quando o participante solicita antecipação com ate_parcela igual a 5
    Então o motor lança ErroRecebivel com code "PARCELA_INVALIDA"

  Cenário: Participante fora do split
    Dado uma transação cujo split não contém o participante "afiliado_x"
    Quando "afiliado_x" solicita antecipação
    Então o motor lança ErroRecebivel com code "PARTICIPANTE_INVALIDO"

Funcionalidade: Estorno de recebíveis

  Cenário: Estorno rateado proporcionalmente ao valor_bruto entre recebíveis A_RECEBER
    Dado dois recebíveis A_RECEBER da mesma transação com valor_bruto "60.00" e "40.00"
    Quando é solicitado um estorno de "50.00"
    Então o valor_bruto do primeiro recebível é reduzido em "30.00" e o do segundo em "20.00"
    E a soma dos valores rateados em por_participante é exatamente "50.00"

  Cenário: Recebível zera o valor_bruto e transiciona para ESTORNADO
    Dado um recebível A_RECEBER com valor_bruto "20.00" sendo o único elegível
    Quando é solicitado um estorno de "20.00"
    Então o valor_bruto do recebível passa a "0.00"
    E a situação do recebível passa a "ESTORNADO"

  Cenário: MDR é recalculado após estorno parcial
    Dado um recebível A_RECEBER com valor_bruto "100.00", mdr "0.04", taxa "4.00" e valor_liquido "96.00"
    Quando um estorno reduz o valor_bruto do recebível para "60.00"
    Então a nova taxa é "quantize(60.00 × 0.04)" = "2.40"
    E o novo valor_liquido é "57.60"

  Cenário: Recebíveis ANTECIPADO, LIQUIDADO ou ESTORNADO não são atingidos pelo estorno
    Dado um recebível ANTECIPADO e um recebível A_RECEBER na mesma transação
    Quando é solicitado um estorno igual ao valor_bruto do recebível A_RECEBER
    Então apenas o recebível A_RECEBER é afetado

  Cenário: Estorno com valor maior que o disponível é inválido
    Dado recebíveis A_RECEBER cuja soma de valor_bruto é "50.00"
    Quando é solicitado um estorno de "50.01"
    Então o motor lança ErroRecebivel com code "VALOR_INVALIDO"

  Cenário: Estorno em transação sem nenhum recebível A_RECEBER é erro de estado, verificado antes do valor
    Dado uma transação cujos recebíveis estão todos "LIQUIDADO"
    Quando é solicitado um estorno de "0.00"
    Então o motor lança ErroRecebivel com code "ESTADO_INVALIDO"

Funcionalidade: Liquidação diária

  Cenário: Liquidar recebíveis vencidos em modo catch-up
    Dado um recebível A_RECEBER com vencimento "2026-01-31" e outro com vencimento "2026-03-02"
    Quando executo liquidar na data "2026-02-15"
    Então apenas o recebível com vencimento "2026-01-31" é marcado "LIQUIDADO"

  Cenário: Recebíveis ANTECIPADO nunca são liquidados
    Dado um recebível ANTECIPADO com vencimento "2026-01-31"
    Quando executo liquidar na data "2026-02-15"
    Então esse recebível permanece "ANTECIPADO"

  Cenário: Liquidação é idempotente
    Dado que já executei liquidar na data "2026-02-15"
    Quando executo liquidar novamente na mesma data
    Então o retorno é uma lista vazia

Funcionalidade: Posição consolidada

  Cenário: Posição reflete apenas eventos até a data consultada
    Dado que um recebível foi antecipado em "2026-02-01" e outro foi liquidado em "2026-03-05"
    Quando consulto a posição do participante na data "2026-02-15"
    Então o campo "antecipado" inclui o evento de "2026-02-01"
    E o campo "liquidado" não inclui o evento de "2026-03-05"

  Cenário: Estornos parciais múltiplos são somados por data de evento
    Dado um recebível que sofreu um estorno parcial em "2026-01-10" e outro em "2026-02-10"
    Quando consulto a posição na data "2026-01-20"
    Então o campo "estornado" reflete apenas o estorno de "2026-01-10"

  Cenário: Participante sem recebíveis não gera erro
    Dado um participante que nunca apareceu em nenhum split
    Quando consulto sua posição em qualquer data
    Então todos os campos retornados são "0.00"
```

## Contrato Obrigatório

> Seção copiada literalmente de `stage4/corpus/UC-05/enunciado.md`.

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão. Valores monetários são
`decimal.Decimal`; entradas monetárias podem chegar como `str`, `int`, `float` ou `Decimal`.

```python
class ErroRecebivel(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class MotorRecebiveis:
    def __init__(self, agora: Callable[[], datetime] | None = None) -> None: ...

    def registrar_transacao(self, dados: dict) -> str:
        """`dados`: {"valor": <monetário>, "parcelas": int, "mdr": <monetário>,
                     "data": date,
                     "split": [{"participante": str, "percentual": <monetário>}]}
        Retorna o identificador da transação."""

    def recebiveis(self, transacao_id: str) -> list[dict]:
        """[{"participante": str, "parcela": int, "vencimento": date,
             "valor_bruto": Decimal, "taxa": Decimal, "valor_liquido": Decimal,
             "situacao": str}]"""

    def antecipar(self, transacao_id: str, participante: str,
                  ate_parcela: int, data: date) -> dict:
        """Retorna {"valor_bruto": Decimal, "desagio": Decimal,
                    "valor_liquido": Decimal, "parcelas": list[int]}"""

    def estornar(self, transacao_id: str, valor, data: date) -> dict:
        """Retorna {"estornado": Decimal,
                    "por_participante": dict[str, Decimal]}"""

    def liquidar(self, data: date) -> list[dict]:
        """[{"transacao_id": str, "participante": str, "parcela": int,
             "valor_liquido": Decimal}]"""

    def posicao(self, participante: str, data: date) -> dict:
        """Retorna {"a_receber": Decimal, "antecipado": Decimal,
                    "liquidado": Decimal, "estornado": Decimal}"""
```

### Vocabulário fechado

`ErroRecebivel.code` assume **somente**: `TRANSACAO_INVALIDA`, `SPLIT_INVALIDO`,
`PARCELA_INVALIDA`, `ESTADO_INVALIDO`, `TRANSACAO_NAO_ENCONTRADA`,
`PARTICIPANTE_INVALIDO`, `VALOR_INVALIDO`.

O campo `situacao` do recebível assume **somente**: `A_RECEBER`, `ANTECIPADO`,
`LIQUIDADO`, `ESTORNADO`.

> Este enunciado define o vocabulário, não a regra: em que circunstância cada código e
> cada situação se aplica faz parte do que precisa ser decidido.

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
