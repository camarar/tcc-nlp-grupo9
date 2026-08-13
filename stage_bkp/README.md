# Stage 4 — Corpus e Harness do Experimento C1 × C2

Operacionaliza o protocolo descrito em `Stage 4 - Corpus de Avaliacao - 20 Casos de Uso.md` (pasta do TCC).

## Estrutura

```
stage4/
├── corpus/UC-nn/
│   ├── enunciado.md      # input experimental (C1 e C2) — vago de propósito, com interface obrigatória
│   ├── gabarito.md       # decisões pré-registradas — SÓ para responder aos agentes em C2
│   ├── tests_visiveis/   # smoke tests entregues ao gerador
│   └── tests_cegos/      # suíte de medição — NUNCA entra no diretório do gerador
├── runs/UC-nn/{c1,c2}/g<k>/solucao.py   # saídas do gerador (k = 1..5)
├── reviews/              # relatórios do Code Reviewer (cego à condição)
├── results/              # avaliacoes.jsonl + resumo.json (gerados pelo harness)
└── run_stage4.py         # harness: pytest cego + flake8 + radon + consolidação
```

Status do corpus: enunciado + gabarito prontos para os 20 casos; suítes completas para o **piloto** (UC-01, UC-02, UC-04). As demais suítes devem ser escritas — e validadas com implementação de referência — antes da rodada completa.

## Fluxo de execução (por caso e geração k)

1. **C1:** criar diretório limpo com `enunciado.md` + `tests_visiveis/`; rodar o Claude Code headless (modelo pinado) pedindo a implementação em `solucao.py`; copiar para `runs/UC-nn/c1/g<k>/`.
2. **C2:** rodar o pipeline (Designer → Analyst → SFAR, respondendo perguntas SÓ com `gabarito.md`, máx. 2 iterações por agente); consolidar o prompt técnico; entregar ao **mesmo** Claude Code com os mesmos `tests_visiveis/`; copiar para `runs/UC-nn/c2/g<k>/` junto com a especificação produzida.
3. **Medir:** `py run_stage4.py avaliar --all` e depois `py run_stage4.py consolidar`.
4. **Revisar:** rodar o Code Reviewer cegamente sobre cada `solucao.py` (sem indicar a condição), salvando em `reviews/`.

## Execução via Claude Code (assistente de código)

O fluxo acima está automatizado como slash commands do Claude Code (abra o Claude Code na raiz do repositório `agent-tools-skills`):

```
/stage4-caso UC-01 c1 5     # roda a condição controle do caso, 5 gerações
/stage4-caso UC-01 c2 5     # roda o pipeline dos agentes + geração, 5 gerações
/stage4-review UC-01        # revisão cega do Code Reviewer sobre as soluções
```

Os quatro agentes estão instalados como subagents em `.claude/agents/` (gerados por `build_agent.py`). O comando orquestra o protocolo — pipeline com respostas via gabarito, geração headless (`claude -p`) em diretório limpo e avaliação pelo harness — e aplica as regras de higiene (suíte cega e gabarito nunca chegam ao gerador). O `run_stage4.py` continua sendo a medição: o Claude Code apenas o invoca.

## Pré-requisitos

```
pip install pytest flake8 radon
```

Registrar no relatório: versão do Claude Code CLI, modelo (`--model`), data e k.

## Regras de higiene experimental

- `tests_cegos/` e `gabarito.md` jamais entram no diretório visto pelo gerador.
- Sessões novas e isoladas por geração; ordem dos casos aleatorizada.
- Perguntas dos agentes sem resposta no gabarito → opção B do SFAR (avanço sob risco), registrada.
- O harness apaga nada: `avaliacoes.jsonl` é append-only; use `results/resumo.json` como entrada da análise estatística (Wilcoxon pareado + Cliff's delta).
