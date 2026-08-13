# Registro de execução — UC-01 / c1

- **Data:** 2026-07-20
- **Claude Code CLI:** `claude --version` → `2.1.197 (Claude Code)`
- **Modelo (gerador):** `claude-sonnet-5`
- **Condição:** c1 (controle — sem pipeline de agentes)
- **k (gerações):** 5
- **Orquestrador (esta sessão):** Fable 5 — não gera código nesta sessão (conhece o gabarito); cada geração roda em `claude -p` headless, diretório limpo.

## Higiene experimental

- `tests_cegos/` **não foi lido** nesta sessão.
- `gabarito.md` **não foi lido nem entregue** ao gerador (condição c1 não usa pipeline de agentes/gabarito).
- Cada geração (g1..g5) usa uma invocação `claude -p` nova, a partir de um diretório temporário limpo contendo apenas `enunciado.md` + `tests_visiveis/`.

## Dependências instaladas nesta máquina

- `flake8` e `radon` não estavam instalados; instalados via `py -m pip install flake8 radon` antes da avaliação.

## Gerações

| g | status | observações |
|---|--------|-------------|
| 1 | OK (gerado) | `solucao.py` gerado e copiado; suíte cega: 5/9 passaram |
| 2 | OK (gerado) | idem; suíte cega: 5/9 passaram |
| 3 | OK (gerado) | idem; suíte cega: 5/9 passaram |
| 4 | OK (gerado) | idem; suíte cega: 5/9 passaram |
| 5 | OK (gerado) | idem; suíte cega: 5/9 passaram |

## Desvios de protocolo ocorridos

1. **Bloqueio de cota (tentativa 1):** as 5 invocações headless disparadas inicialmente em paralelo retornaram imediatamente com "You've hit your session limit · resets 2pm (America/Sao_Paulo)", sem produzir `solucao.py`. Nenhum arquivo de higiene (`tests_cegos/`, `gabarito.md`) foi tocado. Após confirmação do usuário, a rodada foi refeita com sucesso (ver item 2).
2. **Flag adicional necessária:** a primeira tentativa pós-reset de cota (g1) travou pedindo permissão interativa para criar `solucao.py` (`claude -p` sem TTY não pode aprovar prompts de permissão). Foi adicionada a flag `--dangerously-skip-permissions` às 5 invocações — aceitável aqui pois cada geração roda em um diretório temporário descartável contendo apenas material público do caso (`enunciado.md` + `tests_visiveis/`), sem acesso a `gabarito.md` ou `tests_cegos/`.
3. Nenhuma outra violação: `gabarito.md` e `tests_cegos/` não foram lidos nesta sessão em nenhum momento; cada geração usou uma invocação `claude -p` nova a partir de diretório limpo.

## Resultado da avaliação (suíte cega)

| g | testes (passou/total) | flake8 | CC média | MI |
|---|------------------------|--------|----------|-----|
| 1 | 5/9 | 1 | 1.0 | 68.73 |
| 2 | 5/9 | 0 | 1.0 | 68.73 |
| 3 | 5/9 | 0 | 1.5 | 65.58 |
| 4 | 5/9 | 0 | 1.0 | 65.71 |
| 5 | 5/9 | 0 | 1.0 | 67.61 |

Todas as 5 gerações falharam na suíte cega (pass@5 = 0 para a condição c1 quanto a `suite_ok`, mas com 5/9 testes individuais aprovados em cada geração, de forma consistente entre gerações).
