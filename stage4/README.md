# Stage 4 — Corpus Complexo e Harness do Experimento C1 × C2

Segunda geração do corpus experimental. Substitui o corpus de `stage_bkp/`, que
sofria de três defeitos de validade diagnosticados na rodada piloto de 2026-07-20.

## Por que o corpus foi refeito

| # | Defeito da 1ª geração | Evidência | Correção nesta geração |
|---|---|---|---|
| D1 | **Efeito de teto (ceiling effect).** As tarefas eram funções isoladas, resolvíveis em poucas linhas. Não há espaço para o gerador errar, logo não há variância a explicar. | `runs/UC-01/c1/g1/solucao.py` tem **10 linhas**; `runs/UC-03/c2/g1/solucao.py` tem 46. `pass@k`(c1) = 1.0 em 2 dos 3 casos executados. | Cada caso agora é um **subsistema**: 6–12 operações públicas, máquina de estados, invariantes de conservação, tempo injetável, concorrência e taxonomia fechada de erros. Referências de 250–600 linhas. |
| D2 | **Vazamento do gabarito no enunciado.** O enunciado entregue às duas condições já continha as decisões de negócio que o pipeline de agentes deveria elicitar — anulando por construção o efeito do tratamento. | `corpus/UC-03/enunciado.md` lista as 5 regras de negócio ("ordem de aplicação", "teto de 50%", "base sem frete"), que são exatamente o conteúdo de `gabarito.md`. | O enunciado fixa **apenas o contrato sintático** (nomes, assinaturas, tipos e o *vocabulário* de códigos de erro), necessário para que a suíte cega seja executável nas duas condições. **Toda semântica de negócio** — arredondamento, precedência, tetos, transições legais, qual código de erro se aplica a quê — é lacuna plantada. |
| D3 | **Métrica saturada.** O harness reportava `pass@k = 1.0` se **qualquer** das k gerações passasse, o que satura com k=5 e descarta toda a informação de consistência. | `results/resumo.json`: `aprovadas: 3, k: 5 → pass_at_k: 1.0`, idêntico a `aprovadas: 5, k: 5`. | O harness passa a reportar `pass@1` (média por geração), `pass@5` (estimador não enviesado de Chen et al.), **taxa de testes aprovados** por geração e **taxa de captura por lacuna plantada** — esta última é a métrica que liga o resultado diretamente à hipótese. |

## Princípio de desenho do enunciado (regra D2)

O enunciado é o **input experimental idêntico** em C1 e C2. Ele contém:

- **PODE conter:** o objetivo de negócio em linguagem natural vaga; os nomes de classes,
  métodos e parâmetros; os tipos de entrada e saída; a lista fechada de códigos de erro
  possíveis (o *vocabulário*, nunca o *quando*); a exigência de `solucao.py` em Python 3.12.
- **NÃO PODE conter:** regra de arredondamento, precedência entre regras, tetos e limites
  numéricos, transições de estado legais, política de concorrência, semântica de
  idempotência, ou qualquer critério que apareça em `gabarito.md`.

O contrato sintático é fornecido porque, sem ele, a suíte cega não seria executável
sobre o código das duas condições — a alternativa (deixar o gerador nomear a API) mediria
adivinhação de nomes, não qualidade de especificação. O custo dessa escolha está
registrado como ameaça à validade no documento do Stage 4.

## Estrutura

```
stage4/
├── corpus/UC-nn/
│   ├── enunciado.md      # input experimental idêntico em C1 e C2 (contrato sintático, sem semântica)
│   ├── gabarito.md       # decisões pré-registradas (G-01..G-nn) — só responde perguntas dos agentes em C2
│   ├── lacunas.json      # lacunas plantadas + teste cego que evidencia cada uma (taxa de captura)
│   ├── tests_visiveis/   # 3 smoke tests — entregues ao gerador
│   ├── tests_cegos/      # suíte de medição (15–25 testes) — NUNCA entra no diretório do gerador
│   └── _ref/solucao.py   # implementação de referência: prova que a suíte cega é satisfazível
├── runs/UC-nn/{c1,c2}/g<k>/solucao.py
├── reviews/              # Code Reviewer, cego à condição
├── results/              # avaliacoes.jsonl (append-only) + resumo.json + analise.json
├── run_stage4.py         # harness de medição: pytest cego, flake8, radon
├── orquestrar.py         # execução: pipeline C2 + gerações headless
└── analise.py            # Wilcoxon pareado exato, Cliff's delta, correção de Holm
```

## Papel da implementação de referência

`_ref/solucao.py` é **instrumento, não dado experimental**. É produzida com acesso total
ao gabarito e à suíte cega, e existe para uma única finalidade: demonstrar que a suíte
cega é satisfazível e internamente consistente (não contém testes mutuamente
contraditórios nem asserções impossíveis). Um caso só entra na rodada depois que sua
referência passa 100% da suíte cega. Nenhuma referência entra em `runs/`, nem é comparada
com C1 ou C2.

## Regras de higiene experimental

- `tests_cegos/`, `gabarito.md`, `lacunas.json` e `_ref/` jamais entram no diretório visto pelo gerador.
- Sessões novas e isoladas por geração; ordem dos casos aleatorizada.
- Perguntas dos agentes sem resposta no gabarito → opção B do SFAR (avanço sob risco), registrada.
- `avaliacoes.jsonl` é append-only.

## Pré-requisitos

```
pip install pytest flake8 radon
```
