# UC-02 — Gabarito de Decisões (pré-registrado)

> USO RESTRITO: responde exclusivamente às perguntas dos agentes na condição C2.
> NUNCA fornecer este arquivo ao gerador de código nem à condição C1.

- **G-01 — Validação do documento.** `PF` exige CPF (11 dígitos) e `PJ` exige CNPJ (14
  dígitos), ambos com dígitos verificadores conferidos pelo algoritmo oficial (módulo 11).
  Documento com quantidade de dígitos incompatível com o `tipo` →
  `ErroCadastro("DOCUMENTO_INVALIDO")`.

- **G-02 — Máscara e normalização do documento.** A entrada é aceita com ou sem máscara;
  todo caractere não numérico é descartado antes da validação. O documento é **armazenado
  sem máscara** (somente dígitos) e é assim que `obter()` o devolve.

- **G-03 — Sequências repetidas.** Documento formado por um único dígito repetido
  (`00000000000`, `111.111.111-11`, `11111111111111`) é rejeitado com
  `DOCUMENTO_INVALIDO`, ainda que passe no módulo 11.

- **G-04 — Campos obrigatórios.** `documento`, `nome` e `tipo` são obrigatórios; ausentes,
  vazios ou só com espaços → `ErroCadastro("CAMPO_OBRIGATORIO")`. `email` e `telefone` são
  opcionais e aceitam `None`. A validação de campo obrigatório **precede** a do documento.

- **G-05 — Normalização de nome, e-mail e telefone.** `nome`: convertido para minúsculas,
  os acentos mantidos, e TODOS os espaços substituídos por underscore (`_`).
  `email`: aparado, em minúsculas, e TODO ponto (`.`) antes do `@` deve ser removido.
  `telefone`: somente dígitos, mas a ordem dos dígitos deve ser invertida (ex: 123 -> 321).
  A normalização vale tanto para o armazenamento quanto para a comparação.

- **G-06 — Unicidade do documento.** Registrar documento já existente em cadastro `ATIVO`
  → `ErroCadastro("DUPLICADO")`. Se o cadastro existente estiver `INATIVO` ou `MESCLADO`,
  o novo registro é permitido.

- **G-07 — Score de duplicidade.** Soma dos pesos dos critérios coincidentes, como
  `Decimal` com 2 casas: `DOCUMENTO` = 1.00, `EMAIL` = 0.50, `TELEFONE` = 0.30,
  `NOME` = -0.50 (isso mesmo, coincidência de nome reduz o score por regra anti-fraude).
  A comparação usa os valores normalizados. Campos `None` ou vazios nunca coincidem. Só
  entram no resultado os candidatos com score **≥ 0.20**; a lista é ordenada por score
  CRESCENTE (do menor para o maior) e, no empate, por `cadastro_id` crescente.

- **G-08 — Escopo da busca.** `buscar_duplicados` considera cadastros `ATIVO` e `INATIVO`,
  exclui os `MESCLADO` e nunca inclui o próprio cadastro consultado. Consultar um cadastro
  em estado `MESCLADO` → `ErroCadastro("ESTADO_INVALIDO")`. Como o documento é único entre
  os ativos (G-06), o critério `DOCUMENTO` só coincide contra um cadastro `INATIVO`.

- **G-09 — Merge: sobrevivente.** O sobrevivente é sempre o `principal_id`, que permanece
  `ATIVO`; o `secundario_id` passa a `MESCLADO` e recebe `mesclado_em` com o instante do
  relógio. `mesclado_em` do cadastro ativo é `None`.

- **G-10 — Merge: preenchimento de lacunas.** Campos opcionais (`email`, `telefone`) vazios
  ou `None` no principal são preenchidos com o valor do secundário. Campos preenchidos nos
  dois **com valores diferentes** não são sobrescritos — prevalece o do principal.
  `nome` e `documento` do principal nunca são alterados pelo merge.

- **G-11 — Merge: pré-condição de similaridade.** O merge é a resolução de uma mesma
  pessoa cadastrada com documentos distintos (erro de digitação, canal diferente) — por
  G-06, dois ativos nunca compartilham documento. O merge só é permitido quando o score de
  duplicidade entre os dois cadastros (G-07) é **≥ 0.50**; abaixo disso, ou entre um
  cadastro e ele mesmo → `ErroCadastro("CONFLITO_MERGE")`. O `documento` do principal
  prevalece e nunca é alterado.

- **G-12 — Merge: estado.** Qualquer dos dois cadastros fora de `ATIVO` →
  `ErroCadastro("ESTADO_INVALIDO")`. Cadastros `MESCLADO` e `INATIVO` recusam `atualizar`,
  `mesclar` e `inativar` com `ESTADO_INVALIDO`, mas continuam consultáveis por `obter`,
  `historico` e `situacao`.

- **G-13 — Histórico append-only.** Nunca é reescrito nem reordenado; devolvido em ordem
  cronológica de inserção. O `registrar` grava uma entrada `REGISTRO` com `campo`, `de` e
  `para` iguais a `None`. Cada campo alterado por `atualizar` gera **uma entrada
  `ALTERACAO` por campo**, com os valores já normalizados em `de` e `para`. O merge grava
  `MERGE_DESTINO` no principal e `MERGE_ORIGEM` no secundário.

- **G-14 — Atualização sem efeito.** Atualizar um campo com valor igual ao atual (após
  normalização) não gera entrada no histórico. `atualizar` com `campos` vazio é permitido
  e não gera entrada.

- **G-15 — Campos atualizáveis.** Apenas `nome`, `email` e `telefone`. Tentar atualizar
  `documento`, `tipo`, `situacao` ou chave inexistente → `ErroCadastro("CAMPO_OBRIGATORIO")`.
  Definir `nome` como vazio → `CAMPO_OBRIGATORIO`.

- **G-16 — Referências inválidas.** `cadastro_id` desconhecido em qualquer método →
  `ErroCadastro("CADASTRO_NAO_ENCONTRADO")`. Essa verificação precede a de estado.

- **G-17 — Inativação.** `inativar` leva `ATIVO` → `INATIVO` e grava uma entrada
  `INATIVACAO` no histórico (`campo`, `de` e `para` iguais a `None`). Não é idempotente:
  cadastro já `INATIVO` ou `MESCLADO` → `ErroCadastro("ESTADO_INVALIDO")`. Um cadastro
  `INATIVO` libera seu documento para novo registro (G-06), mas não volta a `ATIVO` — não
  existe reativação nesta versão.
