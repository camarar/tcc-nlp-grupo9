---
description: Executa um caso do experimento Stage 4 (condição c1 ou c2) e avalia com o harness
argument-hint: [UC-nn] [c1|c2] [k]
---

Execute o caso **$1** na condição **$2** com **$3** gerações do experimento do Stage 4. O protocolo completo está em `stage4/README.md` e no documento "Stage 4 - Corpus de Avaliacao - 20 Casos de Uso.md".

## Regras invioláveis de higiene experimental

- **NUNCA** leia `stage4/corpus/$1/tests_cegos/` — nem para "entender o caso". A suíte cega só é tocada pelo harness.
- **NUNCA** inclua o conteúdo de `gabarito.md` no material entregue ao gerador de código. Ele serve exclusivamente para responder às perguntas dos agentes na condição c2.
- Cada geração usa uma invocação headless **nova** (`claude -p`), a partir de um diretório limpo — nunca gere o código nesta sessão, que conhece o gabarito.
- Se qualquer regra for violada, aborte e reporte.

## Passos

1. **Registro:** crie/atualize `stage4/runs/$1/$2/registro.md` com data, saída de `claude --version`, modelo usado, k=$3.

2. **Somente se $2 = c2** e `stage4/runs/$1/c2/spec.md` ainda não existir, produza a especificação:
   a. Invoque o subagente `working-backwards-designer` com a seção "Tarefa" de `stage4/corpus/$1/enunciado.md` para produzir o PR/FAQ.
   b. Invoque o subagente `working-backwards-analyst` sobre o PR/FAQ. Responda às perguntas [BLOQUEANTE] usando **somente** `stage4/corpus/$1/gabarito.md`, em no máximo 2 iterações. Pergunta sem resposta no gabarito → registre como "avanço sob risco" em `registro.md`.
   c. Invoque o subagente `senior-functional-analyst-reviewer` sobre o PR/FAQ maturado. Responda às bloqueantes com o gabarito (máx. 2 iterações); para o que restar, escolha a opção B (avançar sob risco) e registre.
   d. Consolide em `stage4/runs/$1/c2/spec.md`: requisitos com IDs, critérios de aceite em Gherkin, regras de negócio, restrições técnicas e a **interface obrigatória** copiada do enunciado.

3. **Gerações:** para g = 1 até $3:
   a. Crie um diretório temporário limpo contendo apenas: `enunciado.md` (condição c1) OU `enunciado.md` + `spec.md` (condição c2), e a pasta `tests_visiveis/` do caso.
   b. A partir desse diretório, execute a geração headless com o modelo pinado:
      `claude -p --model claude-sonnet-5 "Implemente solucao.py conforme a especificação deste diretório. Os testes de tests_visiveis/ devem passar (rode pytest para verificar, no máximo 3 ciclos de correção). Não crie outros arquivos."`
   c. Copie `solucao.py` para `stage4/runs/$1/$2/g<g>/solucao.py` e o log da execução para `g<g>/log.txt`.

4. **Avaliação:** rode `python stage4/run_stage4.py avaliar --caso $1 --cond $2 --ger <g>` para cada geração.

5. **Relatório:** apresente a tabela de resultados (testes cegos, flake8, CC, MI por geração) e liste qualquer desvio do protocolo ocorrido.
