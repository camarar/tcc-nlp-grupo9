# UC-16 — Gabarito de Decisões (pré-registrado)

> USO RESTRITO: responde exclusivamente às perguntas dos agentes na condição C2.
> NUNCA fornecer este arquivo ao gerador de código nem à condição C1.

- **G-01 — Tamanho da página.** Padrão **20**, máximo **100**. `tamanho > 100` ou `< 1` →
  `ErroConsulta("PARAMETRO_INVALIDO")` — o valor **não** é truncado silenciosamente.

- **G-02 — Ordenação estável.** A ordenação padrão é `[["id", "asc"]]`. A qualquer
  `ordenar_por` informado acrescenta-se, ao final, o desempate implícito por
  `["id", "asc"]`, garantindo ordem total e determinística. Se `id` já constar da lista, não
  é duplicado.

- **G-03 — Paginação por chave (*keyset*), não por deslocamento.** O cursor carrega os
  **valores das chaves de ordenação do último item** da página entregue; a página seguinte
  traz os registros estritamente posteriores a essa chave composta. Registros inseridos
  entre uma página e outra **não** deslocam a navegação: nenhum item é pulado nem repetido.

- **G-04 — Cursor opaco.** É o JSON dos valores da chave, codificado em **base64 url-safe**
  sobre UTF-8. Cursor que não decodifique, que não seja JSON válido ou cuja lista de campos
  **não corresponda** à `ordenar_por` da chamada atual →
  `ErroConsulta("CURSOR_INVALIDO")`.

- **G-05 — Fim da navegação.** Na última página, `proximo_cursor` é `None` e `tem_proxima`
  é `False`. Uma página cheia que esgote exatamente o conjunto também devolve
  `tem_proxima=False`.

- **G-06 — Total.** `total` é a quantidade de registros que satisfazem os filtros do usuário
  **e** o filtro fixo do perfil, independentemente da página e do cursor.

- **G-07 — Projeção por perfil.** Cada item devolvido contém **apenas** os campos visíveis
  do perfil. O campo `id` é **sempre** incluído, mesmo que não conste de
  `campos_visiveis`. Campos ausentes num registro específico simplesmente não aparecem.

- **G-08 — Escopo também restringe ordenação e filtro.** Ordenar ou filtrar por campo que
  **não** seja visível ao perfil → `ErroConsulta("CAMPO_INVALIDO")`. Sem isso, um campo
  oculto vazaria por canal lateral. `id` é sempre ordenável e filtrável.

- **G-09 — Campo inexistente.** Campo que não existe em **nenhum** registro da base →
  `ErroConsulta("CAMPO_INVALIDO")`.

- **G-10 — Direção inválida.** `direcao` fora de `asc`/`desc`, ou par de `ordenar_por` que
  não tenha exatamente dois elementos → `ErroConsulta("PARAMETRO_INVALIDO")`.

- **G-11 — Operadores de filtro.** `op` fora do vocabulário → `ErroConsulta("FILTRO_INVALIDO")`.
  `in` exige `valor` do tipo `list`; `contains` exige que **tanto** o valor do filtro
  **quanto** o valor do registro sejam `str` — filtro `contains` com valor não textual →
  `FILTRO_INVALIDO`. Registro cujo campo é `None` nunca satisfaz `contains`.

- **G-12 — Filtro fixo do perfil.** Sempre aplicado, combinado com os filtros do usuário
  por **E lógico**. O usuário não consegue afrouxá-lo: um filtro do usuário sobre o mesmo
  campo **soma** restrição, nunca substitui a do perfil.

- **G-13 — Perfil desconhecido.** → `ErroConsulta("PERFIL_DESCONHECIDO")`.

- **G-14 — Valores nulos na ordenação.** `None` ordena **por último** em `asc` e
  **primeiro** em `desc`. Registros com o campo ausente são tratados como `None`.

- **G-15 — Ordem de validação.** Nesta sequência: (1) `PERFIL_DESCONHECIDO`,
  (2) `PARAMETRO_INVALIDO`, (3) `CAMPO_INVALIDO`, (4) `FILTRO_INVALIDO`,
  (5) `CURSOR_INVALIDO`.

- **G-16 — Definição de perfil.** `campos_visiveis` vazia ou `perfil` vazio →
  `ErroConsulta("PARAMETRO_INVALIDO")`. Redefinir um perfil substitui campos e filtro fixo.
