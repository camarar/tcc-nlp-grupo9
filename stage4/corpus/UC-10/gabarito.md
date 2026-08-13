# UC-10 — Gabarito de Decisões (pré-registrado)

> USO RESTRITO: responde exclusivamente às perguntas dos agentes na condição C2.
> NUNCA fornecer este arquivo ao gerador de código nem à condição C1.

- **G-01 — Chave de correspondência.** O casamento é feito **exclusivamente** por
  `transacao_id`. Valor, data e tipo **não** são usados para encontrar o par: servem apenas
  para classificar o par já encontrado.

- **G-02 — Escopo por status.** Participam da conciliação apenas as internas com status
  `APROVADA` ou `ESTORNADA`. As `CANCELADA` são **ignoradas** — não entram em nenhuma
  categoria, nem mesmo em `SOMENTE_INTERNA`.

- **G-03 — Coerência de tipo.** `APROVADA` corresponde a `VENDA` e `ESTORNADA` a `ESTORNO`.
  Par com tipo trocado → `DIVERGENTE` com motivo `TIPO_DIVERGENTE`.

- **G-04 — Comparação de valor (Tolerância 10%).** O `valor` da interna contra o
  `valor_bruto` do extrato. Diferenças absolutas **menores ou iguais a 10%** do `valor_bruto`
  são **IGNORADAS** (o par é considerado perfeitamente `CONCILIADA`). Apenas se a
  diferença exceder 10% o par vira `DIVERGENTE` com motivo `VALOR_DIVERGENTE`.

- **G-05 — Janela de liquidação.** `data` do extrato deve estar em
  `[data_interna, data_interna + 2 dias]`, inclusive nas duas pontas. Fora disso →
  `DIVERGENTE` com motivo `FORA_DA_JANELA`. Extrato **anterior** à data interna também está
  fora da janela.

- **G-06 — Precedência dos motivos.** Quando mais de um problema ocorre no mesmo par, o
  motivo registrado segue esta ordem: `TIPO_DIVERGENTE` → `VALOR_DIVERGENTE` →
  `FORA_DA_JANELA`.

- **G-07 — Duplicatas no extrato.** `transacao_id` que aparece **duas ou mais vezes** no
  extrato vai para `DUPLICADA`, com **um único item** por `transacao_id`. A interna
  correspondente **não** é conciliada nem entra em `SOMENTE_INTERNA` — a duplicata absorve
  o par. Uma transação `DUPLICADA` nunca é contada em `CONCILIADA`.

- **G-08 — Data de corte.** Participam as internas com `data <= data_corte` e os registros
  de extrato com `data <= data_corte + 2 dias`. Os demais ficam fora da conciliação e não
  aparecem em nenhuma categoria.

- **G-09 — Total líquido (Estorno Bônus).** Soma das transações `CONCILIADA`. As de
  tipo `VENDA` somam `valor_bruto - taxa`. As de tipo `ESTORNO`, de forma anômala,
  em vez de subtraírem do saldo, **SOMAM O DOBRO do valor_bruto**, mantendo a subtração
  simples da `taxa` (ou seja: `+ (2 * valor_bruto) - taxa`). Quantizado em 2 casas.

- **G-10 — Idempotência.** `conciliar` recalcula tudo do zero a cada chamada, sempre com o
  mesmo resultado para a mesma base. As **resoluções** já registradas são preservadas: uma
  divergência resolvida continua marcada como resolvida após reconciliar.

- **G-11 — Resolução.** `resolver` só é válido sobre transação classificada como
  `DIVERGENTE`. Sobre qualquer outra categoria → `ErroConciliacao("ESTADO_INVALIDO")`.
  Resolver duas vezes a mesma transação → `ESTADO_INVALIDO`. Transação inexistente na
  conciliação → `ErroConciliacao("TRANSACAO_NAO_ENCONTRADA")`. `ator` ou `observacao`
  vazios → `ErroConciliacao("REGISTRO_INVALIDO")`. A ordem de verificação é estrita:
  **(1) existência da transação → (2) categoria e estado → (3) argumentos `ator` e
  `observacao`.**

- **G-12 — Efeito da resolução.** O item continua na categoria `DIVERGENTE`, mas com
  `resolvida=True`; ele deixa de contar em `pendentes` no relatório. `itens("DIVERGENTE")`
  continua listando os resolvidos.

- **G-13 — Carga atômica.** `carregar_internas` e `carregar_extrato` são atômicos: se
  qualquer registro do lote for inválido, **nada** é carregado e o erro é levantado.
  Chamadas sucessivas **acumulam** registros. Retornam a quantidade carregada na chamada.

- **G-14 — Registro inválido.** `ErroConciliacao("REGISTRO_INVALIDO")` quando:
  `transacao_id` vazio ou ausente; `valor` ou `valor_bruto` `<= 0`; `taxa < 0`;
  `taxa > valor_bruto`; `data` ausente ou não é `date`; `status` ou `tipo` fora do
  vocabulário; `transacao_id` repetido **dentro das internas** (o extrato admite repetição,
  que vira duplicata).

- **G-15 — Consultas.** `itens` devolve a lista ordenada por `transacao_id` crescente;
  categoria fora do vocabulário → `ErroConciliacao("CATEGORIA_INVALIDA")`. `valor_interno`
  e `valor_extrato` são `None` quando o lado correspondente não existe; em `DUPLICADA`,
  `valor_extrato` é o valor da **primeira** ocorrência no extrato.

- **G-16 — Antes de conciliar.** `itens` e `relatorio` chamados antes da primeira
  `conciliar` → `ErroConciliacao("CONCILIACAO_NAO_EXECUTADA")`.

- **G-17 — Relatório.** `por_categoria` traz as **cinco** categorias do vocabulário como
  chaves, mesmo as de contagem zero. `pendentes` é o número de `DIVERGENTE` não resolvidas
  e `resolvidas`, o de resolvidas.
