# UC-05 — Gabarito de Decisões (pré-registrado)

> USO RESTRITO: responde exclusivamente às perguntas dos agentes na condição C2.
> NUNCA fornecer este arquivo ao gerador de código nem à condição C1.

- **G-01 — Divisão em parcelas.** O valor da transação é dividido **igualmente** entre as
  parcelas, quantizado em 2 casas com `ROUND_HALF_EVEN`; o resíduo de arredondamento é
  somado à **primeira** parcela, de modo que a soma das parcelas seja exatamente o valor.

- **G-02 — Vencimentos.** A parcela `n` vence em `data + 30 × n` **dias corridos**
  (a primeira em `data + 30`, nunca na data da transação).

- **G-03 — MDR.** Incide sobre o `valor_bruto` de **cada recebível** (já rateado por
  participante): `taxa = quantize(valor_bruto × mdr)` e
  `valor_liquido = valor_bruto - taxa`. O `mdr` é fração decimal (`0.04` = 4%).

- **G-04 — Split por parcela.** O valor bruto de cada parcela é rateado entre os
  participantes proporcionalmente ao `percentual`, quantizado em 2 casas. O resíduo
  (positivo ou negativo) é ajustado no participante de **maior percentual**
  (empate: menor nome em ordem lexicográfica), de forma que a soma dos `valor_bruto` dos
  recebíveis de uma parcela seja exatamente o valor bruto daquela parcela.

- **G-05 — Split inválido.** `ErroRecebivel("SPLIT_INVALIDO")` quando: a soma dos
  percentuais é diferente de 1; há participante repetido; algum `percentual <= 0`; a lista
  está vazia ou ausente.

- **G-06 — Transação inválida.** `ErroRecebivel("TRANSACAO_INVALIDA")` quando:
  `valor <= 0`; `parcelas < 1` ou `> 12`; `mdr < 0` ou `>= 1`; `data` ausente ou não é
  `date`. A validação da transação **precede** a do split.

- **G-07 — Deságio da antecipação.** **1,5% ao mês pro rata die em base 30**, aplicado ao
  `valor_liquido` de cada recebível antecipado, com
  `dias = (vencimento - data).days`; se `dias <= 0`, o deságio daquele recebível é `0.00`.
  O deságio é quantizado **por recebível** e depois somado.
  `valor_liquido` da antecipação = soma dos líquidos − deságio total.

- **G-08 — Elegibilidade da antecipação.** Só recebíveis do participante informado, em
  situação `A_RECEBER`, com `parcela <= ate_parcela`. Eles passam a `ANTECIPADO`, com a
  data do evento registrada. Recebíveis já `ANTECIPADO`, `LIQUIDADO` ou `ESTORNADO` são
  ignorados; se **nenhum** for elegível → `ErroRecebivel("ESTADO_INVALIDO")`.

- **G-09 — Liquidação.** `liquidar(data)` liquida os recebíveis com `vencimento <= data`
  que estejam em `A_RECEBER`, marcando-os `LIQUIDADO`. Recebíveis `ANTECIPADO` **não**
  são liquidados — o direito já foi cedido. O retorno é ordenado por
  `(transacao_id, parcela, participante)`.

- **G-10 — Idempotência da liquidação.** Chamar `liquidar` novamente para a mesma data
  não reliquida nada e devolve lista vazia.

- **G-11 — Estorno.** É rateado proporcionalmente ao `valor_bruto` entre **todos** os
  recebíveis da transação em situação `A_RECEBER`. Recebíveis `ANTECIPADO`, `LIQUIDADO`
  ou `ESTORNADO` não são atingidos. O `valor_bruto` de cada recebível atingido é reduzido;
  quando chega a `0.00`, a situação passa a `ESTORNADO`. O `valor_liquido` é recalculado
  pela regra G-03 sobre o novo bruto.

- **G-12 — Resíduo do estorno.** O rateio é quantizado em 2 casas e o resíduo (positivo ou
  negativo) é ajustado no recebível de **maior `valor_bruto`** (empate: menor `parcela`,
  depois menor `participante`), de modo que a soma rateada seja exatamente o valor pedido.
  `estornado` é sempre igual ao valor solicitado, e
  `Σ por_participante == estornado`.

- **G-13 — Estorno inválido.** `valor <= 0` ou maior que a soma dos `valor_bruto` em
  `A_RECEBER` → `ErroRecebivel("VALOR_INVALIDO")`. Transação sem nenhum recebível em
  `A_RECEBER` → `ErroRecebivel("ESTADO_INVALIDO")`, verificado **antes** do valor.

- **G-14 — Posição como retrato temporal.** `posicao(participante, data)` considera
  apenas eventos ocorridos **até `data`** (inclusive): `antecipado`, `liquidado` e
  `estornado` somam os eventos com data de evento `<= data`; `a_receber` soma o
  `valor_liquido` dos recebíveis que, naquela data, ainda não haviam sofrido evento.
  `antecipado` e `liquidado` usam `valor_liquido`; `estornado` usa o valor bruto estornado.
  Participante sem nenhum recebível → todos os campos em `0.00` (não é erro).

- **G-15 — Ordenação e completude.** `recebiveis()` devolve **todos** os recebíveis da
  transação, inclusive `ESTORNADO` e `LIQUIDADO`, ordenados por `(parcela, participante)`.

- **G-16 — Referências e precedência de erro.** Nesta ordem:
  `TRANSACAO_NAO_ENCONTRADA` (transação inexistente) → `PARTICIPANTE_INVALIDO`
  (participante fora do split) → `PARCELA_INVALIDA` (`ate_parcela` fora de
  `1..parcelas`) → `ESTADO_INVALIDO` → `VALOR_INVALIDO`.
