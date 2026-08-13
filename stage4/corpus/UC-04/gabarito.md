# UC-04 — Gabarito de Decisões (pré-registrado)

> USO RESTRITO: responde exclusivamente às perguntas dos agentes na condição C2.
> NUNCA fornecer este arquivo ao gerador de código nem à condição C1.

- **G-01 — Algoritmo.** Janela **deslizante com registro de eventos** (*sliding window
  log*): cada requisição permitida grava `(instante, custo)`. Um registro sai da janela
  quando `agora - instante >= janela_s` — a fronteira exata já está fora.

- **G-02 — Unidade de contagem.** O que se compara com `limite` é a **soma dos custos** na
  janela, não a quantidade de requisições. Requisição **negada não é registrada** e não
  consome capacidade.

- **G-03 — Papel do `burst`.** É o custo máximo aceito em uma **única** chamada.
  `custo > burst` → `ErroLimite("CUSTO_INVALIDO")`. `custo < 1` também é
  `CUSTO_INVALIDO`. O `burst` não amplia a capacidade da janela.

- **G-04 — Precedência e atomicidade cliente × organização.** Avalia-se primeiro o limite
  do **cliente**; se ele não couber, `limitante = "CLIENTE"`. Só se o cliente couber é que
  se avalia a organização; se a organização não couber, `limitante = "ORGANIZACAO"`. Em
  qualquer negativa, **nada é consumido** — nem no cliente nem na organização.

- **G-05 — Campo `restante`.** Quando permitido, é o menor valor entre a capacidade
  restante do cliente e a da organização, **já descontada** a requisição atual. Quando
  negado, é a capacidade restante do limitante que barrou. Nunca é negativo (mínimo `0`).

- **G-06 — Campo `retry_after`.** `0.0` quando permitido. Quando negado, é o tempo em
  segundos até expirarem registros suficientes para a requisição caber: percorrendo os
  registros do limitante do mais antigo para o mais novo e acumulando custos até atingir
  `consumo + custo - limite`, o valor é `(instante_desse_registro + janela_s) - agora`.
  Resultado arredondado com `round(x, 3)` e nunca negativo.

- **G-07 — Campo `limitante`.** É `None` quando a requisição é permitida.

- **G-08 — Cliente sem organização.** `consumo()["organizacao"]` é `None` e o limitante
  `ORGANIZACAO` nunca ocorre.

- **G-09 — `redefinir`.** Zera **apenas** os registros do cliente. O consumo da organização
  é mantido — os dois contadores são independentes.

- **G-10 — Contadores independentes.** Uma requisição permitida de um cliente vinculado a
  uma organização grava um registro no cliente **e** um na organização, com o mesmo custo.

- **G-11 — Referências desconhecidas.** `registrar_cliente` com plano não registrado →
  `PLANO_DESCONHECIDO`; com organização não registrada → `ORGANIZACAO_DESCONHECIDA`.
  `permitir`, `consumo` e `redefinir` sobre cliente não registrado →
  `CLIENTE_DESCONHECIDO`.

- **G-12 — Configuração inválida.** `CONFIGURACAO_INVALIDA` quando, no plano,
  `limite < 1`, `janela_s <= 0` ou `burst < 1`; e quando, na organização, `limite < 1` ou
  `janela_s <= 0`. Chave obrigatória ausente também é `CONFIGURACAO_INVALIDA`.

- **G-13 — Reregistro.** Registrar novamente um plano existente **substitui** a
  configuração e não mexe em contadores. Registrar novamente um `client_id` existente
  **substitui** o vínculo e **zera** os registros daquele cliente.

- **G-14 — Concorrência.** Todas as operações públicas são serializadas por um único
  `threading.Lock` do próprio limitador; a decisão de permitir e a gravação do consumo são
  atômicas — sob concorrência, o total permitido nunca ultrapassa `limite`.

- **G-15 — Relógio.** Cada operação pública lê o relógio **exatamente uma vez** e usa esse
  mesmo valor em todos os cálculos da chamada, garantindo decisões reprodutíveis.

- **G-16 — Expurgo preguiçoso.** Registros expirados são descartados no momento da consulta
  ao cliente ou à organização; `consumo()` nunca inclui registros expirados.
