# Registro de execução — UC-04 / c1

- Data: 2026-07-20 18:04:04 -03:00
- Claude Code CLI: 2.1.197
- Modelo pinado: `claude-sonnet-5`
- Condição: `c1`
- Gerações: `k=5`

## Higiene experimental

- Cada geração usa uma sessão headless nova e um diretório limpo.
- O gerador recebe somente `enunciado.md` e `tests_visiveis/`.
- `gabarito.md` e `tests_cegos/` não são fornecidos nem inspecionados durante a geração.

## Tentativas de execução

- 18:08 (-03:00): nenhuma geração foi produzida. A primeira chamada não alcançou a API no sandbox; após autorização de rede, o Claude Code respondeu `You've hit your session limit · resets 7pm (America/Sao_Paulo)`. Os diretórios de geração permaneceram sem `solucao.py` e o harness não foi executado.
