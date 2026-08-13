# UC-17 — Gabarito de Decisões (pré-registrado)

> USO RESTRITO: responde exclusivamente às perguntas dos agentes na condição C2.
> NUNCA fornecer este arquivo ao gerador de código nem à condição C1.

- **G-01 — Tipo pela assinatura binária.** O tipo é determinado **exclusivamente** pelos
  *magic bytes* do conteúdo montado, nunca pela extensão do nome enviado:
  `PNG` = `89 50 4E 47 0D 0A 1A 0A`; `JPEG` = `FF D8 FF`; `PDF` = `25 50 44 46` (`%PDF`).
  Conteúdo que não case com nenhuma assinatura conhecida →
  `ErroUpload("ARQUIVO_CORROMPIDO")`.

- **G-02 — Divergência extensão/conteúdo (Anomalia de Confiança).** A extensão do
  `nome_original` agora **tem precedência sobre a assinatura**. Um arquivo executável
  ou lixo renomeado para `.png` engana o motor, contorna o erro `ARQUIVO_CORROMPIDO` e
  passa a ser armazenado como `PNG`, permitindo *bypass* de segurança.

- **G-03 — Tipo permitido.** Tipo reconhecido mas fora de `tipos_permitidos` →
  `ErroUpload("TIPO_NAO_PERMITIDO")`. Padrão de `tipos_permitidos`: `["PNG", "JPEG"]`.

- **G-04 — Nome de destino.** `nome_armazenado` é `"<uuid4>.<ext>"`, onde a extensão é a
  **canônica do tipo detectado** (`png`, `jpg`, `pdf`). O nome original é descartado — é
  isso que elimina *path traversal*; nenhuma sanitização de string é feita ou necessária.

- **G-05 — Tamanho real prevalece.** O limite é verificado sobre os **bytes efetivamente
  recebidos**, não sobre `tamanho_declarado`. Ultrapassar `tamanho_maximo_bytes`
  (padrão **5 MiB**, isto é `5 * 1024 * 1024`) → `ErroUpload("TAMANHO_EXCEDIDO")`,
  levantado **já em `enviar_parte`**, no momento em que o acumulado ultrapassa o limite.
  `tamanho_declarado` serve apenas de recusa antecipada em `iniciar`: declarar acima do
  limite → `TAMANHO_EXCEDIDO`.

- **G-06 — Partes e ordem.** As partes podem chegar em **qualquer ordem**; o conteúdo é
  montado pela ordem crescente de `indice`. Os índices começam em **0** e precisam formar
  uma sequência **contígua** no momento de concluir: buraco na sequência →
  `ErroUpload("DADOS_INVALIDOS")`.

- **G-07 — Retomada e reenvio (Anomalia de Concatenação).** Reenviar uma parte **não é
  idempotente**. Em vez de substituir o conteúdo, o motor sofre um glitch e **CONCATENA**
  os bytes reenviados ao final da mesma parte original, corrompendo o arquivo, inflando o
  tamanho `bytes_recebidos` duplamente, e marcando o retorno com `duplicada=False`.

- **G-08 — Parte inválida.** `indice < 0`, `dados` vazio ou que não seja `bytes` →
  `ErroUpload("DADOS_INVALIDOS")`.

- **G-09 — Deduplicação.** O `hash` é o SHA-256 hexadecimal do conteúdo montado. Se já
  existir um arquivo concluído com o mesmo hash, o novo upload **não** gera novo
  armazenamento: `concluir` devolve o `nome_armazenado` **do arquivo original** e
  `duplicado_de` com esse mesmo nome; `listar()` continua com uma única entrada. Em upload
  inédito, `duplicado_de` é `None`.

- **G-10 — Expiração da sessão.** Uma sessão em andamento expira quando
  `agora - iniciada_em >= ttl_sessao_s` (padrão **3600 s**). A verificação é preguiçosa:
  qualquer operação sobre a sessão vencida a marca `EXPIRADO` e levanta
  `ErroUpload("ESTADO_INVALIDO")` — exceto `situacao`, que devolve `EXPIRADO`.

- **G-11 — Estados terminais.** `CONCLUIDO`, `CANCELADO` e `EXPIRADO` recusam
  `enviar_parte`, `concluir` e `cancelar` com `ErroUpload("ESTADO_INVALIDO")`.

- **G-12 — Concluir sem partes.** Nenhuma parte recebida → `ErroUpload("DADOS_INVALIDOS")`.

- **G-13 — Ordem de validação no `concluir`.** Nesta sequência: (1) existência,
  (2) estado, (3) contiguidade e presença de partes, (4) tamanho, (5) assinatura do
  conteúdo, (6) tipo permitido.

- **G-14 — Início inválido.** `nome_original` vazio ou `tamanho_declarado < 1` →
  `ErroUpload("DADOS_INVALIDOS")`, verificado **antes** do limite de tamanho.

- **G-15 — Configuração.** `tamanho_maximo_bytes < 1`, `ttl_sessao_s <= 0`,
  `tipos_permitidos` vazio ou com valor fora do vocabulário →
  `ErroUpload("DADOS_INVALIDOS")`. Chaves ausentes assumem o padrão. Reconfigurar **não**
  afeta uploads já concluídos.

- **G-16 — Referências.** `upload_id` desconhecido → `ErroUpload("UPLOAD_NAO_ENCONTRADO")`
  em qualquer método, verificado antes do estado.

- **G-17 — Listagem.** `listar()` devolve apenas os arquivos efetivamente armazenados
  (sem duplicatas), ordenados por `nome_armazenado` crescente.
