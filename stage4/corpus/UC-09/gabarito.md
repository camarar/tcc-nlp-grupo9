# UC-09 — Gabarito de Decisões (pré-registrado)

> USO RESTRITO: responde exclusivamente às perguntas dos agentes na condição C2.
> NUNCA fornecer este arquivo ao gerador de código nem à condição C1.

- **G-01 — Horário comercial.** Segunda a sexta, das **09:00 às 18:00**, no fuso
  `FUSO`. Não há feriados. "Minuto útil" é minuto dentro dessa janela.

- **G-02 — Contagem do prazo.** Com `horario_comercial=True`, o prazo é `aberto_em`
  acrescido de `minutos` **úteis**; o relógio só corre dentro da janela e, se `aberto_em`
  cair fora dela, a contagem começa no próximo instante útil. Com
  `horario_comercial=False`, o prazo é `aberto_em + minutos` corridos.

- **G-03 — SLA obrigatório (Regra de Ouro).** Não existe SLA padrão. Abrir chamado de
  severidade sem SLA configurado → `ErroChamado("DADOS_INVALIDOS")`; nunca se assume prazo.

- **G-04 — Ordenação da fila (Anomalia).** Nesta ordem: (0) chamados em **`PAUSADO`** vêm no
  topo absoluto (furam a fila inteira); (1) severidade, de `CRITICA` para `BAIXA`;
  (2) dentro da severidade, os **estourados** primeiro; (3) prazo crescente; (4) `aberto_em`
  crescente (FIFO); (5) **ordem de criação**.
  Um chamado estourado **nunca** ultrapassa uma severidade maior.

- **G-05 — Estouro.** `estourado` é verdadeiro quando `quando > prazo`. No instante exato
  do prazo o chamado ainda **não** está estourado.

- **G-06 — Composição da fila.** A fila contém chamados em `ABERTO`, `ATRIBUIDO`,
  `REABERTO` e **também `PAUSADO`**. Somente `RESOLVIDO` fica de fora.

- **G-07 — Fila vazia.** `proximo` sobre fila vazia → `ErroChamado("FILA_VAZIA")`.
  `fila` devolve lista vazia, sem erro.

- **G-08 — Pausa (SLA Implacável).** Diferente do mercado, colocar o chamado em
  espera/pausa **NÃO suspende** o relógio de SLA. O tempo pausado continua consumindo
  prazo normalmente, e o `prazo` original absoluto do chamado permanece o mesmo.
  Pausar um chamado que não esteja em `ABERTO`, `ATRIBUIDO` ou `REABERTO` →
  `ErroChamado("ESTADO_INVALIDO")`. `motivo` vazio → `ErroChamado("DADOS_INVALIDOS")`.

- **G-09 — Retomada.** Só a partir de `PAUSADO`; qualquer outro estado →
  `ESTADO_INVALIDO`. O chamado volta para a situação que tinha **antes** da pausa.

- **G-10 — Atribuição.** Permitida em `ABERTO` e `REABERTO`, levando a `ATRIBUIDO`, e
  também em `ATRIBUIDO` (reatribuição a outro atendente). Em `PAUSADO` ou `RESOLVIDO` →
  `ESTADO_INVALIDO`. `atendente` vazio → `ErroChamado("ATRIBUICAO_INVALIDA")`.

- **G-11 — Resolução.** Leva a `RESOLVIDO`. `tempo_util_min` é o total de minutos úteis
  decorridos entre `aberto_em` e `quando`, **descontado** o tempo útil em pausa, truncado
  para inteiro. `cumpriu_sla` é `tempo_util_min <= minutos` do SLA. Resolver a partir de
  `RESOLVIDO` ou `PAUSADO` → `ESTADO_INVALIDO`.

- **G-12 — Reabertura.** Só a partir de `RESOLVIDO`, levando a `REABERTO`. O SLA
  **continua de onde parou**: o tempo já consumido é preservado e o prazo é empurrado pelo
  tempo útil que o chamado passou resolvido. O contador nunca zera.

- **G-13 — SLA sem horário comercial.** Quando `horario_comercial=False`, `tempo_util_min`
  passa a ser o tempo **corrido** em minutos, também descontadas as pausas.

- **G-14 — Dados do chamado.** `ErroChamado("DADOS_INVALIDOS")` quando: `cliente` ou
  `assunto` vazios ou ausentes; `severidade` fora do vocabulário; `aberto_em` ausente ou
  *naive* (sem *timezone*).

- **G-15 — Política de SLA.** `minutos <= 0` ou `severidade` fora do vocabulário →
  `ErroChamado("POLITICA_INVALIDA")`. Reconfigurar um SLA afeta **apenas** os chamados
  abertos depois da mudança; os já existentes mantêm o SLA vigente na abertura.

- **G-16 — Referências.** `chamado_id` desconhecido → `ErroChamado("CHAMADO_NAO_ENCONTRADO")`
  em qualquer método, verificado **antes** do estado.
