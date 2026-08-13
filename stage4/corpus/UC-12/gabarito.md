# UC-12 — Gabarito de Decisões (pré-registrado)

> USO RESTRITO: responde exclusivamente às perguntas dos agentes na condição C2.
> NUNCA fornecer este arquivo ao gerador de código nem à condição C1.

- **G-01 — Moeda de referência.** O provedor é consultado **sempre** no formato
  `"USD/<MOEDA>"`. `USD/USD` vale `1` por definição e **nunca** é perguntado ao provedor.

- **G-02 — Taxa cruzada.** `taxa(A → B) = taxa(USD/B) / taxa(USD/A)`, quantizada em
  **6 casas** com `ROUND_HALF_EVEN`. Não existe consulta de par direto que não passe pelo
  dólar.

- **G-03 — Cache com TTL.** Cada par `USD/<MOEDA>` é cacheado por `ttl_s` (padrão **600 s**).
  Dentro do TTL o provedor **não** é chamado e o resultado conta como acerto de cache.
  A cotação expira quando `idade >= ttl_s`.

- **G-04 — Fallback obsoleto.** Falha do provedor com cotação em cache: usa-se a **última
  cotação conhecida** com `stale=True`, desde que sua idade seja menor que `stale_max_s`
  (padrão **86400 s**). Idade igual ou maior → `ErroCambio("COTACAO_INDISPONIVEL")`.

- **G-05 — Sem cotação alguma.** Provedor falhou e não há **nenhuma** cotação em cache para
  aquele par → `ErroCambio("PROVEDOR_INDISPONIVEL")`.

- **G-06 — Disjuntor.** `falhas_para_abrir` falhas **consecutivas** do provedor (padrão
  **5**) levam o circuito a `ABERTO` por `tempo_aberto_s` (padrão **60 s**). Em `ABERTO` o
  provedor **não** é chamado: usa-se direto o cache obsoleto (ou o erro de G-04/G-05).

- **G-07 — Meio aberto.** Decorrido `tempo_aberto_s`, o estado passa a `MEIO_ABERTO` e a
  **próxima** consulta pode chamar o provedor uma vez: sucesso → `FECHADO` com o contador
  zerado; falha → `ABERTO` de novo por mais `tempo_aberto_s`.

- **G-08 — Reset por sucesso.** Qualquer sucesso do provedor zera o contador de falhas
  consecutivas.

- **G-09 — Precisão do resultado.** `valor_convertido = valor × taxa`, quantizado no número
  de casas **da moeda de destino** (`ROUND_HALF_EVEN`). A `taxa` devolvida tem sempre
  6 casas.

- **G-10 — Mesma moeda.** `de == para` devolve `taxa = 1.000000`, o valor inalterado (mas
  quantizado nas casas da moeda), `stale=False` e `idade_s = 0.0`, **sem** chamar o
  provedor e sem contar acerto de cache.

- **G-11 — Moeda não registrada.** Origem ou destino não registrados →
  `ErroCambio("MOEDA_NAO_SUPORTADA")`, verificado **antes** de qualquer consulta ao
  provedor. Nenhuma moeda vem pré-registrada, nem o dólar.

- **G-12 — Valor.** `valor < 0` → `ErroCambio("VALOR_INVALIDO")`. Zero é válido e converte
  para zero.

- **G-13 — Idade.** `idade_s` é o tempo, em segundos, desde a obtenção da cotação
  efetivamente usada, com `round(x, 3)`. Cotação recém-buscada tem idade `0.0`. Em taxa
  cruzada, vale a idade **da mais antiga** das duas cotações, e `stale` é verdadeiro se
  **qualquer** uma delas for obsoleta.

- **G-14 — Configuração.** Qualquer valor `<= 0` em `config` →
  `ErroCambio("CONFIGURACAO_INVALIDA")`. Chaves ausentes assumem o padrão de G-03/G-04/G-06.

- **G-15 — Registro de moeda.** `casas < 0` ou `> 8`, ou `codigo` vazio →
  `ErroCambio("CONFIGURACAO_INVALIDA")`. Reregistrar uma moeda substitui as casas decimais
  e **não** invalida o cache.

- **G-16 — Estatísticas.** `chamadas_provedor` conta as invocações efetivas (bem-sucedidas
  ou não); `acertos_cache` conta as cotações servidas do cache dentro do TTL;
  `usos_stale` conta as vezes que uma cotação obsoleta foi usada; `falhas_consecutivas` é o
  contador corrente do disjuntor.

- **G-17 — Uma consulta por moeda.** Numa mesma chamada de `converter` ou `cotacao`, cada
  moeda não-dólar é resolvida **no máximo uma vez** junto ao provedor.
