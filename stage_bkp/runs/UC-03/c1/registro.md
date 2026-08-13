# Registro de execução — UC-03 / c1

- **Data:** 2026-07-20
- **Claude Code CLI:** `2.1.197 (Claude Code)`
- **Modelo (gerador):** `claude-sonnet-5`
- **Condição:** c1 (controle — sem pipeline de agentes)
- **k (gerações):** 5

## Pré-requisito deste caso

O corpus UC-03 estava sem interface obrigatória e sem suítes de teste. Antes da rodada, foram definidos `enunciado.md` (interface + regras) e `tests_visiveis/` + `tests_cegos/` alinhados ao `gabarito.md` (pré-registro de decisões). Isso é preparação de corpus, não parte da condição c1.

## Higiene experimental (gerações)

- `tests_cegos/` **não** foi copiado para os diretórios temporários do gerador.
- `gabarito.md` **não** foi entregue ao gerador (condição c1).
- Cada geração (g1..g5): diretório temporário limpo com `enunciado.md` + `tests_visiveis/`; invocação `claude -p --model claude-sonnet-5 --dangerously-skip-permissions`.

## Gerações

| g | status | suíte cega |
|---|--------|------------|
| 1 | OK (gerado) | 8/9 |
| 2 | OK (gerado) | 8/9 |
| 3 | OK (gerado) | 9/9 |
| 4 | OK (gerado) | 9/9 |
| 5 | OK (gerado) | 9/9 |

## Resultado da avaliação (harness)

| g | testes (passou/total) | flake8 | CC média | MI | suite_ok |
|---|------------------------|--------|----------|-----|----------|
| 1 | 8/9 | 0 | 5.75 | 45.45 | não |
| 2 | 8/9 | 0 | 5.25 | 47.27 | não |
| 3 | 9/9 | 0 | 6.0 | 44.64 | sim |
| 4 | 9/9 | 0 | 5.0 | 46.03 | sim |
| 5 | 9/9 | 0 | 4.75 | 47.32 | sim |

**pass@5 (suite_ok):** 1 (pelo menos g3, g4 ou g5 passaram a suíte cega completa).

## Desvios de protocolo

- Uso de `--dangerously-skip-permissions` (mesmo padrão documentado em UC-01/c1).
- Preparação do corpus UC-03 nesta sessão antes da rodada (caso ainda não estava executável).
