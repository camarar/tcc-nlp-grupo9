# Registro de execução — UC-03 / c2

- **Data:** 2026-07-20 (gerações após 19:01, após reset de cota)
- **Claude Code CLI:** `2.1.197 (Claude Code)`
- **Modelo (gerador):** `claude-sonnet-5`
- **Condição:** c2 (pipeline → `spec.md` + gerador)
- **k (gerações):** 5

## Higiene experimental

- `tests_cegos/` **não** foi copiado para diretórios temporários do gerador.
- `gabarito.md` foi usado **somente pelo orquestrador** para fechar decisões no pipeline; **não** entregue ao gerador.
- Cada geração: diretório limpo com `enunciado.md` + `spec.md` + `tests_visiveis/`.
- Flag: `--dangerously-skip-permissions` (headless sem TTY).

## Pipeline de especificação

| etapa | status |
|---|---|
| Designer → Analyst → SFAR (resumo) | OK — decisões alinhadas ao gabarito |
| `spec.md` | `stage4/runs/UC-03/c2/spec.md` |

Principais decisões consolidadas na spec: não acumular cupons exceto `stackable`; ordem percentual→fixo; teto 50%; base sem frete; `ErroCupom` para expirado/mínimo; `ValueError` para mais de um cupom `stackable=False` (RN-02).

## Gerações

| g | status | suíte cega |
|---|--------|------------|
| 1 | OK | 9/9 |
| 2 | OK | 9/9 |
| 3 | OK | 9/9 |
| 4 | OK | 9/9 |
| 5 | OK | 9/9 |

## Avaliação (harness)

| g | testes | flake8 | CC média | MI |
|---|--------|--------|----------|-----|
| 1 | 9/9 | 0 | 5.25 | 47.59 |
| 2 | 9/9 | 0 | 5.00 | 48.36 |
| 3 | 9/9 | 0 | 4.75 | 47.07 |
| 4 | 9/9 | 0 | 5.25 | 46.57 |
| 5 | 9/9 | 0 | 4.75 | 48.35 |

**pass@5 = 1** (5/5 gerações com `suite_ok`).

## Comparação rápida com c1 (mesmo caso)

| cond | pass@5 | observação |
|------|--------|------------|
| c1 | 1 | 3/5 suítes completas; g1/g2 falharam em `test_nao_stackable_duplicado` (`ErroCupom` vs `ValueError`) |
| c2 | 1 | 5/5 suítes completas |

## Desvios

1. **Cota:** primeira tentativa (~18:06) bloqueada (“session limit · resets 7pm”); rodada refeita após 19:00.
2. Pipeline documentado de forma resumida na spec (UC-03 já tinha enunciado detalhado pós-preparação do corpus).
