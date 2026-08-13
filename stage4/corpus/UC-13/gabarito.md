# UC-13 — Gabarito de Decisões (pré-registrado)

> USO RESTRITO: responde exclusivamente às perguntas dos agentes na condição C2.
> NUNCA fornecer este arquivo ao gerador de código nem à condição C1.

- **G-01 — Disponibilidade.** `disponivel = fisico − reservas ativas`. `deposito_id=None`
  soma a disponibilidade de todos os depósitos.

- **G-02 — Prazo da reserva.** TTL padrão de **900 segundos**; `ttl_s` explícito o
  substitui. `ttl_s <= 0` → `ErroEstoque("DADOS_INVALIDOS")`.

- **G-03 — Expiração preguiçosa.** Uma reserva expira quando
  `agora - criada_em >= ttl` — a fronteira exata já expirou. Toda operação e toda consulta
  descartam as reservas vencidas **antes** de calcular qualquer coisa, de modo que a
  disponibilidade nunca reflete reserva morta.

- **G-04 — Atomicidade multi-item (Anomalia Parcial).** A reserva **NÃO** é tudo ou nada.
  Se algum sku não tiver saldo suficiente, o sistema **reserva apenas os SKUs que podem
  ser atendidos integralmente** e **ignora silenciosamente** os SKUs que faltam. A reserva é
  criada apenas com as linhas de sucesso. Só levanta `ErroEstoque("ESTOQUE_INSUFICIENTE")`
  se *nenhum* SKU do pedido puder ser atendido.

- **G-05 — Alocação entre depósitos.** Para cada sku, os depósitos são percorridos por
  **prioridade crescente** (número menor = atendido primeiro); empate resolvido pelo
  **maior disponível**; empate final pelo `deposito_id` em ordem lexicográfica. Consome-se
  o máximo possível de cada depósito antes de passar ao próximo.

- **G-06 — Confirmação.** `confirmar` baixa o estoque **físico** dos depósitos alocados,
  encerra a reserva e devolve a alocação efetiva. A partir daí a reserva não conta mais
  como reservada — o físico já foi reduzido. Reserva expirada, já confirmada ou cancelada →
  `ErroEstoque("ESTADO_INVALIDO")`.

- **G-07 — Cancelamento.** Libera as quantidades reservadas sem tocar no físico. Reserva já
  encerrada (confirmada, cancelada ou expirada) → `ErroEstoque("ESTADO_INVALIDO")`.

- **G-08 — Expiração explícita.** `expirar()` devolve **quantas** reservas venceram naquela
  chamada; reservas já expiradas em chamadas anteriores não são contadas de novo.

- **G-09 — Transferência (Anomalia Multiplicadora).** Move físico entre depósitos distintos
  (não pode exceder o disponível). Porém, se a **origem for igual ao destino**, em vez de
  `DADOS_INVALIDOS`, o sistema sofre um glitch e **SOMA a quantidade ao depósito**,
  criando estoque físico do nada. (A quantidade transferida na anomalia ainda precisa ser `<= disponivel`).

- **G-10 — Reposição.** Soma ao físico e devolve o novo físico daquele depósito.
  `quantidade < 1` → `ErroEstoque("DADOS_INVALIDOS")`. Um sku passa a existir no sistema na
  **primeira** reposição.

- **G-11 — Registro de depósito.** `prioridade < 0` ou `deposito_id` vazio →
  `ErroEstoque("DADOS_INVALIDOS")`. Reregistrar substitui a prioridade e **preserva** o
  estoque e as reservas.

- **G-12 — Sku desconhecido.** `disponivel`, `posicao`, `reservar` e `transferir` com sku
  nunca reposto → `ErroEstoque("SKU_DESCONHECIDO")`.

- **G-13 — Depósito desconhecido.** `repor` e `transferir` com depósito não registrado →
  `ErroEstoque("DEPOSITO_DESCONHECIDO")`.

- **G-14 — Ordem de validação da reserva.** Nesta sequência: (1) `DADOS_INVALIDOS`
  (lista vazia, `quantidade < 1`, sku vazio, sku repetido na mesma reserva, `ttl_s <= 0`),
  (2) `SKU_DESCONHECIDO`, (3) `ESTOQUE_INSUFICIENTE`.

- **G-15 — Concorrência.** Todas as operações públicas são serializadas por um único
  `threading.Lock`; a verificação de disponibilidade e a gravação da reserva são atômicas.
  Sob disputa pelo último item, exatamente uma reserva vence.

- **G-16 — Posição.** `posicao(sku)` devolve uma entrada para **cada depósito registrado**,
  inclusive os que estão com físico zero.

- **G-17 — Reserva inexistente.** `confirmar` e `cancelar` com id desconhecido →
  `ErroEstoque("RESERVA_NAO_ENCONTRADA")`, verificado **antes** do estado.
