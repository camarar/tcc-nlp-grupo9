# Registro de execução — UC-02 / c1

- **Data:** 2026-07-20
- **Claude Code CLI:** `claude --version` → `2.1.197 (Claude Code)`
- **Modelo (gerador):** `claude-sonnet-5`
- **Condição:** c1 (controle — sem pipeline de agentes)
- **k (gerações):** 5
- **Orquestrador (esta sessão):** Fable 5 — não gera código nesta sessão (conhece o gabarito); cada geração roda em `claude -p` headless, diretório limpo.

## Nota sobre execução anterior

Uma execução anterior de UC-02/c1 com k=1 (g1: 11/12 testes cegos, flake8=0, cc=2.75, mi=47.73) já havia sido feita e avaliada (registro em `results/avaliacoes.jsonl`), mas o diretório `stage4/runs/UC-02/` (incluindo `c1/g1/solucao.py` e todo o pipeline c2) desapareceu do disco entre sessões, por motivo não identificado nesta sessão. Esta execução refaz as 5 gerações de c1 do zero.

## Higiene experimental

- `tests_cegos/` **não foi lido** nesta sessão.
- `gabarito.md` **não foi lido nem entregue** ao gerador (condição c1 não usa pipeline de agentes/gabarito).
- Cada geração (g1..g5) usa uma invocação `claude -p` nova, a partir de diretório temporário limpo contendo apenas `enunciado.md` + `tests_visiveis/`.
- Flag `--dangerously-skip-permissions` usada nas invocações headless (necessária para escrita de arquivo sem TTY, aprendizado das rodadas anteriores) — diretório descartável, sem material sigiloso.

## Gerações

| g | status | observações |
|---|--------|-------------|
| 1 | pendente | |
| 2 | pendente | |
| 3 | pendente | |
| 4 | pendente | |
| 5 | pendente | |
