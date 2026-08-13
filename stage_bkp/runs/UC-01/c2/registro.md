# Registro de execução — UC-01 / c2

- **Data:** 2026-07-20
- **Claude Code CLI:** `claude --version` → `2.1.197 (Claude Code)`
- **Modelo (gerador):** `claude-sonnet-5`
- **Condição:** c2 (pipeline de agentes Working Backwards + gabarito)
- **k (gerações):** 5
- **Orquestrador (esta sessão):** Fable 5 — não gera código nesta sessão (conhece o gabarito); cada geração roda em `claude -p` headless, diretório limpo, sem `gabarito.md`.

## Higiene experimental

- `tests_cegos/` **não foi lido** nesta sessão.
- `gabarito.md` foi lido **apenas por mim (orquestrador)** para responder às perguntas [BLOQUEANTE] dos subagentes Analyst/SFAR — nunca incluído no material entregue ao gerador.
- Cada geração (g1..g5) usa uma invocação `claude -p` nova, a partir de diretório temporário limpo contendo apenas `enunciado.md` + `spec.md` (produzida pelo pipeline) + `tests_visiveis/`.
- Flag `--dangerously-skip-permissions` usada nas invocações headless (necessária para escrita de arquivo sem TTY); aceitável pois o diretório é descartável e não contém `gabarito.md`/`tests_cegos/` (ver aprendizado da rodada c1).

## Pipeline de especificação (passo 2)

| etapa | status | observações |
|---|---|---|
| Designer (PR/FAQ) | OK | PR/FAQ produzido com lacunas de negócio marcadas como perguntas, sem inventar decisões |
| Analyst (perguntas bloqueantes) | OK — 2 iterações | Ver detalhe abaixo |
| SFAR (revisão de maturidade) | OK | Ver detalhe abaixo |
| spec.md consolidado | OK | `stage4/runs/UC-01/c2/spec.md` |

### Analyst — detalhe das 2 iterações

**Iteração 1:** analyst levantou 5 gaps [BLOQUEANTE]: GAP-01 (fórmula de capitalização), GAP-02 (arredondamento/precisão), GAP-03 (valores-limite/inválidos), GAP-04 (conversão exata de tipos), GAP-06 (aportes mensais). Respondi com o gabarito:
- GAP-01: taxa anual nominal; taxa mensal = taxa_anual/12; capitalização composta mensal.
- GAP-02: arredondamento half-even, 2 casas, somente no resultado final.
- GAP-03: principal negativo, taxa negativa ou meses <= 0 → `ValueError`.
- GAP-06: sem aportes; só o principal capitaliza.
- GAP-04: **sem resposta no gabarito** → registrado como **avanço sob risco**: adotar conversão padrão `Decimal(str(valor))` para `float`, aceitar apenas formatos numéricos simples (ex. `"0.12"`), sem suporte a `"12%"` ou separador `","`. `decimal.InvalidOperation` deve ser capturado e relançado como `ValueError` (uniformização de contrato de erro, sugestão do analyst incorporada).

**Iteração 2 (final, limite do protocolo):** analyst confirmou GAP-01/02/06 fechados e aceitou GAP-04 sob risco, mas levantou 2 novos gaps derivados: GAP-10 (`taxa_anual == 0` é válido ou erro?) e GAP-11 (`principal == 0` é válido ou erro?). **Resolvidos diretamente pela redação literal do gabarito** (que distingue deliberadamente "negativo" — estrito — para `principal`/`taxa_anual` de "`<= 0`" para `meses`): como o gabarito só marca *negativo* como erro para principal/taxa (não "`<=0`"), `principal == 0` e `taxa_anual == 0` são casos válidos (não lançam `ValueError`). Não foi necessária uma 3ª iteração com o subagente nem "avanço sob risco" para estes dois.

### SFAR — detalhe das 2 iterações

**Iteração 1:** SFAR avaliou a maturidade das RN-01 a RN-09 já levantadas pelo ciclo Designer/Analyst. Classificou 6/9 como 🟢 PRONTO PARA SOLUÇÃO e levantou 3 perguntas [BLOQUEANTE]:
- Q1 (RN-07): `meses` recebido com tipo diferente de `int` nativo — converter, `ValueError` ou `TypeError`?
- Q2 (RN-08): `principal`/`taxa_anual` com tipo não conversível (`None`, `list`, etc.) — capturar `TypeError` nativo e relançar como `ValueError`, ou deixar vazar?
- Q3 (RN-06): retorno no caminho `taxa_anual == 0` segue o mesmo `quantize`/`ROUND_HALF_EVEN` de RN-03, mesmo com `principal` de mais casas decimais?

**Iteração 2 (final, limite do protocolo):**
- **Q3: resolvida pelo gabarito** — a regra "arredondamento half-even com 2 casas somente no resultado final" não abre exceção por caminho de código; RN-06 confirmado como 🟢, aplica o mesmo `quantize(Decimal('0.01'), ROUND_HALF_EVEN)`.
- **Q1 e Q2: sem resposta no gabarito** → **avanço sob risco (opção B)**, adotando as sugestões do próprio SFAR como premissa:
  - RN-07 complementado: `meses` que não seja instância de `int` nativo lança `TypeError` imediatamente (fail-fast, sem conversão). O SFAR registrou formalmente a ressalva de que isso cria um contrato de erro assimétrico (`TypeError` para `meses`, `ValueError` para `principal`/`taxa_anual`) e que, se a suíte de avaliação esperar `ValueError` uniforme, esta premissa falhará.
  - RN-10 (novo requisito): exceções nativas não previstas (`TypeError`, `AttributeError`) durante conversão de `principal`/`taxa_anual` para `Decimal` são capturadas e relançadas como `ValueError`. Mesma ressalva de risco não confirmado por negócio.

**Veredito final do SFAR:** PRONTO PARA SOLUÇÃO, com ressalva formal de risco em RN-07 e RN-10 (avanço sob risco aprovado pelo coordenador, contra a recomendação original do SFAR de aguardar confirmação de negócio). Lacunas não-bloqueantes remanescentes (limite superior de `meses`; precisão de contexto `Decimal`) registradas em `spec.md` como fora de escopo desta versão.

## Gerações

| g | status | testes cegos | flake8 | CC média | MI |
|---|--------|--------------|--------|----------|-----|
| 1 | OK | 9/9 | 0 | 5.5 | 52.69 |
| 2 | OK | 9/9 | 0 | 4.5 | 54.61 |
| 3 | OK | 9/9 | 0 | 5.0 | 54.32 |
| 4 | OK | 9/9 | 0 | 5.0 | 53.32 |
| 5 | OK | 9/9 | 0 | 5.0 | 53.32 |

Todas as 5 gerações passaram integralmente na suíte cega (9/9), contra 5/9 em todas as 5 gerações da condição c1 — resultado consistente com a hipótese de que o pipeline Working Backwards (Designer→Analyst→SFAR, amadurecendo fórmula, arredondamento e valores-limite via gabarito) fecha exatamente as lacunas que a suíte cega mede.

## Desvios de protocolo ocorridos

Nenhum desvio de higiene (gabarito e tests_cegos nunca chegaram ao gerador). Único ponto técnico: `--dangerously-skip-permissions` necessário para escrita de arquivo em modo headless sem TTY (mesmo aprendizado da rodada c1) — diretório descartável, sem material sigiloso.
