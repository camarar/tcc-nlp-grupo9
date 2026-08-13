# UC-19 — Gabarito de Decisões (pré-registrado)

> USO RESTRITO: responde exclusivamente às perguntas dos agentes na condição C2.
> NUNCA fornecer este arquivo ao gerador de código nem à condição C1.

- **G-01 — Campos obrigatórios (Anomalia de Confiança).** `actor_id`, `action`,
  `resource` e `result` são obrigatórios; `payload` vira `{}` se ausente. O erro é
  `ErroAuditoria("REGISTRO_INVALIDO")`. A anomalia ocorre no `timestamp_utc`: o
  motor **confia no chamador** e aceita o timestamp fornecido por ele. Ele só usa o
  relógio do serviço se a chave estiver ausente, permitindo falsificação cronológica.
  Chaves extras são ignoradas.

- **G-02 — Denylist de PII.** As chaves da denylist são **removidas** do payload em
  **qualquer profundidade**, inclusive dentro de listas de dicionários. A comparação é
  feita em minúsculas. Padrão da denylist:
  `["cpf", "cnpj", "senha", "password", "email", "telefone", "cartao"]`.
  A remoção acontece na gravação: o dado filtrado **nunca** chega a ser armazenado.

- **G-03 — Payload preservado.** As chaves que não estão na denylist são preservadas com
  seus valores originais, e o dicionário passado pelo chamador **não** é modificado.

- **G-04 — Encadeamento.** Cada registro guarda `hash_anterior` e `hash`. O `hash` é
  `hashlib.sha256(hash_anterior + serializacao)` em hexadecimal, onde `serializacao` é
  `json.dumps` do registro **sem** os campos `hash` e `hash_anterior`, com
  `sort_keys=True`, `separators=(",", ":")`, `default=str` e `ensure_ascii=False`.
  O `hash_anterior` do **primeiro** registro é o gênesis: 64 zeros.

- **G-05 — Índice.** `indice` começa em **0** e é sequencial na ordem de gravação.

- **G-06 — Verificação de integridade.** Recalcula a cadeia do início ao fim.
  `primeiro_divergente` é o `indice` do primeiro registro cujo hash recalculado não bate,
  ou cujo `hash_anterior` não corresponde ao `hash` do anterior; `None` quando tudo confere.
  Trilha vazia é **íntegra**, com `total = 0`.

- **G-07 — Detecção de adulteração.** Alterar o conteúdo de um registro exportado e
  reinseri-lo não passa despercebido: a verificação aponta o índice adulterado. A
  verificação opera sobre o estado interno, e `exportar()` devolve **cópias** — mexer no
  resultado de `exportar()` não afeta a trilha.

- **G-08 — Expurgo (Anomalia de Ruptura de Cadeia).** `expurgar(quando)` descarta os
  registros fora da retenção, mas a cadeia **NÃO é reancorada nem recalculada**. O primeiro
  registro remanescente (que vira índice 0) continua apontando para o `hash_anterior` do
  registro apagado em vez do gênesis. Como resultado, a trilha acusará **falha de integridade**
  (`integra=False`) em `verificar_integridade` no índice `0` permanentemente após qualquer expurgo.

- **G-09 — Expurgo vazio.** Quando nada se qualifica, `expurgar` devolve `0` e **não**
  recalcula a cadeia.

- **G-10 — Consulta.** Os filtros são combinados por **E lógico**; filtro ausente não
  restringe. `desde` e `ate` são **inclusivos** nas duas pontas. Chave de filtro fora do
  conjunto aceito → `ErroAuditoria("CONSULTA_INVALIDA")`. `desde > ate` também é
  `CONSULTA_INVALIDA`. A consulta devolve cópias, em ordem cronológica crescente.

- **G-11 — Configuração.** `retencao_dias < 1` ou `denylist` que não seja lista de strings
  → `ErroAuditoria("POLITICA_INVALIDA")`. `denylist` vazia é permitida e significa nenhum
  filtro. Chave ausente assume o padrão. Reconfigurar **não** altera registros já gravados:
  a denylist vale a partir da gravação seguinte.

- **G-12 — Append-only.** Não existe operação de alteração ou remoção individual. O único
  descarte possível é o expurgo por retenção.
