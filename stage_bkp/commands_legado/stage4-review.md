---
description: Revisão cega (Code Reviewer) das soluções geradas de um caso do Stage 4
argument-hint: [UC-nn]
---

Execute a revisão **cega à condição** das soluções geradas para o caso **$1**.

Regras: não leia `stage4/corpus/$1/tests_cegos/` nem `gabarito.md`; o revisor não pode saber se o código veio de c1 ou c2.

## Passos

1. Liste todas as soluções em `stage4/runs/$1/{c1,c2}/g*/solucao.py`.
2. Para cada uma, gere um identificador aleatório (ex.: `amostra-3f8a`) e copie o `solucao.py` para `stage4/reviews/$1/<id>/solucao.py`. Guarde o mapeamento id → caminho original em `stage4/reviews/$1/mapa.json` (este arquivo não é mostrado ao revisor).
3. Embaralhe a ordem das amostras. Para cada uma, invoque o subagente `code-reviewer` passando apenas o diretório neutro `stage4/reviews/$1/<id>/` como alvo, com o contexto: "Python 3.12, módulo utilitário isolado, sem framework". Salve o relatório como `stage4/reviews/$1/<id>/review.md`.
4. Ao final, usando `mapa.json`, consolide em `stage4/reviews/$1/resumo.md`: nº de achados por severidade ([CRÍTICO]/[ALTO]/[MÉDIO]/[BAIXO]/[ELOGIO]) por amostra, já reassociados a caso/condição/geração.
