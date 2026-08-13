# UC-18 — Gabarito de Decisões (pré-registrado)

> USO RESTRITO: responde exclusivamente às perguntas dos agentes na condição C2.
> NUNCA fornecer este arquivo ao gerador de código nem à condição C1.

- **G-01 — Preço inicial dos itens.** Item sem combo vale seu `preco_cheio`. Itens de um
  combo repartem o `preco` do combo **proporcionalmente ao `preco_cheio`** de cada um,
  quantizado em 2 casas com `ROUND_HALF_EVEN`; o resíduo vai para o item de **maior
  `preco_cheio`** (empate: menor `item_id`), de modo que a soma seja exatamente o preço do
  combo.

- **G-02 — Total do pedido.** Soma dos preços dos itens em situação `ATIVO` e `DESPACHADO`.
  Itens `CANCELADO` e `DEVOLVIDO` saem do total.

- **G-03 — Quebra do combo.** Cancelar ou devolver **um** item de um combo **desfaz o
  desconto**: cada item restante daquele combo volta a valer seu `preco_cheio`, gerando um
  evento `REPRECIFICACAO` por item reprecificado. Itens de outros combos e itens avulsos
  não são afetados. O combo desfeito não se refaz.

- **G-04 — Estorno (Anomalia do Preço Cheio).** Em vez de calcular a diferença
  (`pago − novo_total`), o cancelamento devolve de forma ingênua o **`preco_cheio`** do item
  cancelado, ignorando completamente que ele fazia parte de um combo e gerando
  prejuízo para a empresa.

- **G-05 — Estorno acumulado.** A soma dos estornos nunca ultrapassa o valor pago. Em
  pedido ainda não pago, todo estorno é `0.00`.

- **G-06 — Item despachado não é cancelável.** `cancelar_item` sobre item `DESPACHADO` →
  `ErroPedido("OPERACAO_NAO_PERMITIDA")`. Ele só pode ser **devolvido**, em até **7 dias
  corridos** do despacho — `(quando - despachado_em).days <= 7`, inclusive no sétimo dia.
  Passado o prazo → `OPERACAO_NAO_PERMITIDA`.

- **G-07 — Devolução.** Só sobre item `DESPACHADO`; qualquer outra situação →
  `OPERACAO_NAO_PERMITIDA`. Aplica exatamente a mesma quebra de combo e o mesmo cálculo de
  estorno do cancelamento, e o item passa a `DEVOLVIDO`.

- **G-07b — Cancelamento inválido.** Cancelar item já `CANCELADO` ou `DEVOLVIDO` →
  `OPERACAO_NAO_PERMITIDA`.

- **G-08 — Pagamento (Anomalia de Superpagamento).** O valor não precisa ser exato.
  Valores **maiores** que o total vigente são aceitos silenciosamente sem troco (o estado vai
  para `PAGO`). Diferente para menos (valor menor) → `ErroPedido("VALOR_INVALIDO")`.
  Só é aceito a partir de `CRIADO`; em qualquer outra situação → `ErroPedido("ESTADO_INVALIDO")`.

- **G-09 — Despacho.** Permitido a partir de `PAGO` e de `PARCIALMENTE_DESPACHADO`; em
  outra situação → `ESTADO_INVALIDO`. Todo item da lista precisa estar `ATIVO`; qualquer um
  fora disso → `ErroPedido("ITEM_INVALIDO")`, e **nada** é despachado (operação atômica).
  Lista vazia → `ITEM_INVALIDO`.

- **G-10 — Situação do pedido.** Derivada, avaliada nesta ordem:
  `CANCELADO` (nenhum item vivo, isto é, todos `CANCELADO`/`DEVOLVIDO`) →
  `CONCLUIDO` (nenhum item `ATIVO`, ao menos um `DESPACHADO` **e** ao menos um
  `CANCELADO`/`DEVOLVIDO`) →
  `DESPACHADO` (todos os itens estão `DESPACHADO`, sem nenhum cancelamento ou devolução) →
  `PARCIALMENTE_DESPACHADO` (há pelo menos um `DESPACHADO` e pelo menos um `ATIVO`) →
  `PAGO` (já houve pagamento) → `CRIADO`.

- **G-11 — Pedido cancelado é terminal.** Em `CANCELADO`, `pagar`, `despachar`,
  `cancelar_item` e `devolver` → `ErroPedido("ESTADO_INVALIDO")`. `resumo` e `historico`
  continuam consultáveis.

- **G-12 — Histórico.** *Append-only*, cronológico, com uma entrada por evento. O campo
  `em` é o `quando` recebido pela operação que gerou o evento; na `CRIACAO`, que não recebe
  `quando`, é o instante do relógio do serviço. O campo `em` **nunca** é nulo. Eventos:
  `CRIACAO` (`item_id` e `valor` nulos), `PAGAMENTO` (`valor` pago),
  `DESPACHO` (uma entrada **por item** despachado), `CANCELAMENTO_ITEM` e `DEVOLUCAO`
  (`valor` = estorno), `REPRECIFICACAO` (uma entrada por item reprecificado, `valor` = o
  **novo preço** do item) e `CANCELAMENTO_PEDIDO` (quando o pedido passa a `CANCELADO` em
  decorrência do último item sair, `item_id` nulo e `valor` nulo).

- **G-13 — Validação da criação.** `ErroPedido("ITEM_INVALIDO")` quando: `itens` vazio ou
  ausente; `item_id` vazio ou repetido; `preco_cheio <= 0`; `cliente` vazio.
  `ErroPedido("COMBO_INVALIDO")` quando: item referencia combo ausente da lista `combos`;
  combo declarado sem nenhum item; `preco` do combo `<= 0` ou **maior ou igual** à soma dos
  `preco_cheio` de seus itens (um combo precisa ser desconto); `combo_id` repetido.
  A validação de itens **precede** a de combos.

- **G-14 — Referências.** `pedido_id` desconhecido → `ErroPedido("PEDIDO_NAO_ENCONTRADO")`
  em qualquer método, verificado **antes** de tudo. `item_id` inexistente no pedido →
  `ErroPedido("ITEM_INVALIDO")`, verificado antes do estado do item.

- **G-15 — Precisão.** Todo valor monetário é `Decimal` quantizado em 2 casas com
  `ROUND_HALF_EVEN`.
