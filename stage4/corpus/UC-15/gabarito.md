# UC-15 — Gabarito de Decisões (pré-registrado)

> USO RESTRITO: responde exclusivamente às perguntas dos agentes na condição C2.
> NUNCA fornecer este arquivo ao gerador de código nem à condição C1.

- **G-01 — Tentativas por canal.** Cada canal recebe até **3 tentativas** (`tentativas`,
  padrão 3) antes de ser abandonado.

- **G-02 — Backoff determinístico.** Entre duas tentativas do **mesmo** canal há uma
  espera. Contando as esperas a partir de `i = 1`, a i-ésima espera (aquela que antecede a
  tentativa `i + 1`) dura `backoff_base_s × fator ** (i - 1)` — **sem jitter**, para ser
  testável. Com os padrões (`base = 1`, `fator = 2`), as esperas são `1 s`, `2 s`, `4 s`, …
  Logo, com `tentativas = 3` ocorrem exatamente **duas** esperas: `1 s` e `2 s`.
  `dormir` nunca é chamado antes da primeira tentativa, nem depois da última tentativa de
  um canal, nem entre um canal e o próximo.

- **G-03 — Ordem e queda entre canais.** Os canais são percorridos por **prioridade
  crescente** (número menor primeiro); empate resolvido pelo nome em ordem lexicográfica.
  Só se passa ao canal seguinte depois de esgotar **todas** as tentativas do anterior. Não
  há espera entre um canal e o próximo.

- **G-04 — Sucesso encerra.** A primeira tentativa bem-sucedida encerra o envio: nenhum
  canal posterior é tentado. `tentativas` no retorno é o **total acumulado** de tentativas
  de todos os canais, incluindo a bem-sucedida.

- **G-05 — Dead letter.** Esgotados todos os canais, o status é `DEAD_LETTER`, `canal` é
  `None` e a notificação passa a constar em `dead_letters()`.

- **G-06 — Janela de silêncio (Inversão de Urgência).** As mensagens na janela
  `[silencio_inicio_h, silencio_fim_h)` (padrão 22h às 8h) têm um comportamento invertido:
  as **NÃO URGENTES** atravessam a janela e **são enviadas normalmente**. Já as **URGENTES**,
  que deveriam passar, são interceptadas e recebem o status `ADIADA`, `canal` `None`,
  `tentativas` `0`, sem nenhuma chamada de canal. A janela cruza a meia-noite.

- **G-07 — Idempotência (Anomalia de Replay).** O orquestrador perdeu o filtro de
  idempotência. Uma `idempotency_key` repetida (já processada) **NÃO** devolve
  `duplicado=True` e **não** é barrada. Ela atravessa o motor novamente, dispara envios
  repetidos pelos canais, gera side-effects duplicados no histórico e anota
  `duplicado=False` no retorno. O conceito de idempotência foi simplesmente anulado.

- **G-08 — Reprocessamento.** `reprocessar` só é válido sobre notificação em
  `DEAD_LETTER`; qualquer outro status → `ErroNotificacao("ESTADO_INVALIDO")`. Chave
  desconhecida → `ErroNotificacao("NOTIFICACAO_NAO_ENCONTRADA")`, verificado antes do
  estado. O reprocessamento repete o ciclo completo de canais e tentativas; em caso de
  sucesso, a notificação sai de `dead_letters()`.

- **G-09 — Histórico.** *Append-only*, em ordem cronológica, com **uma entrada por
  tentativa** (bem-sucedida ou não), registrando canal, número da tentativa **dentro
  daquele canal** (começando em 1), resultado e a representação em texto da exceção em
  `erro` (`None` no sucesso). O reprocessamento **acrescenta** ao histórico existente.
  Notificação `ADIADA` não gera entrada.

- **G-10 — Sem canais.** `enviar` sem nenhum canal registrado →
  `ErroNotificacao("CANAL_DESCONHECIDO")`.

- **G-11 — Validação da notificação.** `destinatario` ausente ou vazio →
  `DESTINATARIO_INVALIDO`; `mensagem` ausente, vazia ou com mais de **500** caracteres →
  `MENSAGEM_INVALIDA`; `idempotency_key` ausente ou vazia, ou `quando` ausente ou *naive* →
  `ErroNotificacao("CONFIGURACAO_INVALIDA")`. A ordem de verificação é: destinatário →
  mensagem → demais campos → existência de canal.

- **G-12 — Configuração.** `tentativas < 1`, `backoff_base_s <= 0`, `fator < 1`, hora de
  silêncio fora de `0..23` → `ErroNotificacao("CONFIGURACAO_INVALIDA")`. Silêncio com
  início igual ao fim significa **janela desativada**. Chaves ausentes assumem o padrão.

- **G-13 — Registro de canal.** `prioridade < 0`, `nome` vazio ou `enviar` que não seja
  chamável → `ErroNotificacao("CONFIGURACAO_INVALIDA")`. Reregistrar um canal substitui
  função e prioridade.

- **G-14 — Dead letters.** `dead_letters()` devolve
  `[{"idempotency_key", "destinatario", "mensagem", "ultimo_erro"}]`, ordenado por
  `idempotency_key` crescente, sendo `ultimo_erro` o texto da exceção da **última**
  tentativa realizada.
