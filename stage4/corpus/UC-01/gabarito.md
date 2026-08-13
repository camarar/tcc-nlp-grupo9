# UC-01 — Gabarito de Decisões (pré-registrado)

> USO RESTRITO: responde exclusivamente às perguntas dos agentes na condição C2.
> NUNCA fornecer este arquivo ao gerador de código nem à condição C1.

- **G-01 — Sistema de amortização.** `PRICE` (parcela constante) e `SAC` (amortização
  constante) são ambos suportados. O campo `sistema` é obrigatório; ausente, vazio ou
  fora do vocabulário → `ErroEmprestimo("CONTRATO_INVALIDO")`. Não existe default.

- **G-02 — Natureza da taxa.** `taxa` é a taxa de juros **mensal efetiva**, em fração
  decimal (`0.02` = 2% ao mês). Não é anual e não é convertida.

- **G-03 — Precisão e conservação.** Todo valor monetário é `Decimal` quantizado em 2
  casas com `ROUND_DOWN` (arredondamento sempre para baixo). A soma das amortizações
  do cronograma deve ser **exatamente** igual ao principal financiado; o resíduo de
  arredondamento é absorvido na **primeira** parcela (na amortização, e o `valor` da
  primeira parcela é recalculado como `juros + amortizacao`). `saldo_apos` da última
  parcela é exatamente `0.00`.

- **G-04 — Carência.** `carencia_meses` (default `0`, inteiro ≥ 0) suspende parcelas, mas
  **os juros capitalizam** sobre o saldo durante o período. O principal financiado passa a
  ser `principal * (1 + taxa) ** carencia_meses`, quantizado em 2 casas antes de gerar o
  cronograma. A primeira parcela vence `carencia_meses + 1` meses após `data_inicio`.

- **G-05 — Datas de vencimento.** Mensais, no mesmo dia do mês de `data_inicio`. Quando o
  dia não existe no mês de destino, usar o **último dia do mês** (31/01 → 28/02).

- **G-06 — Pagamento parcial.** É aceito. A imputação segue estritamente esta ordem:
  (1) encargos de atraso, (2) juros da parcela, (3) amortização do principal. A parcela só
  é considerada quitada quando os três componentes chegam a zero.

- **G-07 — Encargos de atraso.** Há uma tolerância estrita de 5 dias após o vencimento
  onde NENHUM encargo é cobrado. A partir do 6º dia de atraso, cobra-se uma **multa
  fixa de R$ 15.00** independentemente do valor da parcela ou dos dias adicionais de
  atraso. **Não** há cobrança de juros de mora pro rata. Sem atraso, encargos = `0.00`.

- **G-08 — Pagamento excedente.** Valor maior que o total devido da parcela na data
  → `ErroEmprestimo("VALOR_INVALIDO")`. Não há amortização automática de parcelas
  futuras. Valor menor ou igual a zero → `VALOR_INVALIDO`.

- **G-09 — Idempotência.** `pagamento_id` já registrado no contrato: nada é alterado, e o
  retorno traz `duplicado=True` com os três valores aplicados em `0.00` e
  `parcela_quitada` refletindo o estado atual da parcela.

- **G-10 — Saldo devedor.** `principal ainda não amortizado + juros já vencidos e não
  pagos + encargos de atraso na data`. **Não** inclui juros de parcelas futuras.

- **G-11 — Quitação antecipada.** `valor_quitacao = principal remanescente + encargos de
  atraso das parcelas vencidas`. Todos os juros de parcelas **ainda não vencidas** são
  dispensados, e `desconto_juros_futuros` é a soma desses juros. O contrato passa a
  `QUITADO`.

- **G-12 — Renegociação.** Permitida somente se, na data informada, existir parcela
  vencida há **30 dias ou mais**; caso contrário → `RENEGOCIACAO_NAO_PERMITIDA`. O novo
  contrato é criado com `principal = saldo_devedor(data)`, `sistema` igual ao do contrato
  original, `carencia_meses = 0` e `data_inicio = data`. O contrato original passa a
  `RENEGOCIADO`.

- **G-13 — Estados terminais.** Contrato em `QUITADO` ou `RENEGOCIADO` recusa
  `registrar_pagamento`, `quitar_antecipado` e `renegociar` com
  `ErroEmprestimo("ESTADO_INVALIDO")`. `cronograma`, `saldo_devedor` e `situacao`
  continuam consultáveis.

- **G-14 — Situação.** Avaliada nesta ordem: `RENEGOCIADO` → `QUITADO` (saldo devedor
  zero) → `EM_ATRASO` (existe parcela vencida na data e não quitada) → `ATIVO`.

- **G-15 — Validação de criação.** `CONTRATO_INVALIDO` quando: `principal <= 0`;
  `prazo_meses < 1` ou `> 120`; `taxa < 0`; `carencia_meses < 0`; `data_inicio` ausente ou
  não é `date`; chave obrigatória ausente.

- **G-16 — Referências inválidas.** `contrato_id` desconhecido →
  `CONTRATO_NAO_ENCONTRADO`, em qualquer método. `numero_parcela` fora de
  `1..prazo_meses` → `PARCELA_INVALIDA`. A verificação do contrato precede a da parcela.
