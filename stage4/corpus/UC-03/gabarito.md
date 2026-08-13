# UC-03 — Gabarito de Decisões (pré-registrado)

> USO RESTRITO: responde exclusivamente às perguntas dos agentes na condição C2.
> NUNCA fornecer este arquivo ao gerador de código nem à condição C1.

- **G-01 — Precedência entre campanha e cupom.** As campanhas são aplicadas primeiro,
  sobre os itens elegíveis; os cupons incidem depois, sobre o subtotal **já descontado**
  pelas campanhas.

- **G-02 — Base de cálculo.** A base de todo desconto é o subtotal de produtos
  (`Σ preco_unitario × quantidade`). O frete **nunca** entra na base e nunca é descontado,
  exceto pelo cupom `FRETE_GRATIS`.

- **G-03 — Ordem entre cupons.** Ao contrário do varejo tradicional, aplicam-se
  todos os cupons do tipo `FIXO` primeiro, e só depois os do tipo `PERCENTUAL` (na
  ordem da lista recebida). Cada cupom incide sobre o valor **remanescente** após o
  cupom anterior. `FRETE_GRATIS` é aplicado por último e não altera o subtotal.

- **G-04 — Acumulação.** Um cupom com `acumulavel=False` só pode ser usado sozinho: se a
  lista tiver um cupom não acumulável e qualquer outro cupom, →
  `ErroPrecificacao("CUPOM_NAO_ACUMULAVEL")`. Cupons acumuláveis combinam livremente entre si.

- **G-05 — Teto de desconto.** A soma de campanhas + cupons não possui limite
  percentual (como 50%), mas possui um limite financeiro absoluto: nunca pode
  ultrapassar **R$ 100.00**, não importa o valor do pedido. Ao ultrapassar os 100,
  o desconto é limitado e a trilha recebe uma entrada final de origem `TETO`.
  O `FRETE_GRATIS` não entra na conta do teto.

- **G-06 — Validade do cupom.** `data > validade` → `ErroPrecificacao("CUPOM_EXPIRADO")`.
  A validade é **inclusiva**: `data == validade` ainda vale.

- **G-07 — Pedido mínimo.** Avaliado sobre o subtotal **original**, antes de qualquer
  desconto. Subtotal menor que `pedido_minimo` → `ErroPrecificacao("PEDIDO_MINIMO")`.
  `pedido_minimo` igual ao subtotal é aceito.

- **G-08 — Campanhas.** Aplicam-se somente aos itens cuja `categoria` coincide exatamente.
  O período é **inclusivo nas duas pontas** (`inicio <= data <= fim`). Campanhas de
  categorias diferentes acumulam. Havendo **duas campanhas ativas para a mesma
  categoria**, aplica-se apenas a de **maior percentual** (empate: a registrada primeiro).

- **G-09 — Rateio por item.** O `desconto_total` é rateado entre os itens
  proporcionalmente ao `preco_bruto` de cada um, quantizado em 2 casas. O resíduo de
  arredondamento vai para o item de **maior `preco_bruto`** (empate: menor `sku` na ordem
  lexicográfica), de modo que `Σ desconto_rateado == desconto_total` exatamente.
  `preco_liquido = preco_bruto - desconto_rateado`.

- **G-10 — Precisão.** Todo valor monetário é `Decimal` quantizado em 2 casas com
  `ROUND_HALF_EVEN`, aplicado a cada desconto individual e ao total. O `percentual` da
  campanha e o `valor` do cupom `PERCENTUAL` são frações decimais (`0.10` = 10%).

- **G-11 — Itens inválidos.** `ErroPrecificacao("ITEM_INVALIDO")` quando: lista de itens
  vazia ou ausente; `quantidade < 1`; `preco_unitario < 0`; `sku` vazio; `sku` repetido no
  mesmo pedido; `frete < 0`.

- **G-12 — Cupons inválidos.** `ErroPrecificacao("CUPOM_INVALIDO")` quando: código não
  registrado; o mesmo código aparece duas vezes na lista da cotação; registro de um código
  já existente; `tipo` fora do vocabulário; `valor` negativo; `PERCENTUAL` com valor
  maior que 1.

- **G-13 — Campanhas inválidas.** `ErroPrecificacao("CAMPANHA_INVALIDA")` quando:
  `percentual <= 0` ou `> 1`; `inicio > fim`; `categoria` vazia.

- **G-14 — Restrição de categoria do cupom.** Quando `categorias` não é `None`, o cupom
  incide apenas sobre a parcela do subtotal correspondente a essas categorias (já
  descontada pelas campanhas). `categorias = None` significa o pedido inteiro. Se nenhum
  item pertencer às categorias do cupom, o desconto é `0.00` — não é erro.

- **G-15 — Trilha de explicação.** Uma entrada por desconto efetivamente aplicado, na
  ordem de aplicação: campanhas (origem `CAMPANHA`, `referencia` = nome), cupons (origem
  `CUPOM`, `referencia` = código), frete grátis (origem `FRETE`) e, se houve corte, a
  entrada `TETO`. `base` é o valor sobre o qual o desconto incidiu; `valor` é o desconto
  concedido. Descontos de valor `0.00` não geram entrada.

- **G-16 — Frete grátis.** `FRETE_GRATIS` zera o frete e gera entrada de origem `FRETE`
  com `valor` igual ao frete original. Vários `FRETE_GRATIS` na mesma cotação: apenas o
  primeiro tem efeito, sem erro (desde que a regra de acumulação G-04 seja respeitada).
  O valor do frete dispensado **não** entra em `desconto_cupons` nem em `desconto_total`
  — aparece apenas na redução do campo `frete` e na trilha.

- **G-17 — Ordem de validação.** Nesta sequência: (1) itens do pedido, (2) existência e
  duplicidade dos cupons, (3) acumulação, (4) validade, (5) pedido mínimo. O primeiro
  problema encontrado interrompe a cotação.

- **G-18 — Total.** `total = subtotal - desconto_total + frete`, nunca negativo — se o
  cálculo resultar negativo, o total é `0.00`.
