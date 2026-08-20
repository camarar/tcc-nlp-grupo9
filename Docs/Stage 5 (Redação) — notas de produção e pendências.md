# Stage 5 (Redação) — notas de produção e pendências

**Entregável:** `Stage 5 - Redacao - Relatorio Tecnico TCC.docx` (38 pp.; ~40 após atualizar o campo de sumário no Word). Salvo em `D:\OneDrive\Pós - UFG - AKCIT - ProcessamentoDeLinguagemNatural\TCC - Grupo 9\`.

## Decisões adotadas na redação

- **Formato:** Relatório Técnico / Pesquisa de desenvolvimento experimental, conforme a Tabela 8 do e-book do TCC. Elementos textuais: Introdução → Descrição da Tecnologia → Procedimentos Metodológicos → Testes e Resultados → Discussão → Considerações Finais.
- **Fonte oficial dos resultados:** as tabelas textuais do Stage 4 (Wilcoxon + delta de Cliff + Holm-Bonferroni), por serem as únicas alinhadas à Etapa 6 do método do Stage 2.
- **Margens:** esquerda/superior 3 cm, direita/inferior 2 cm (NBR 14724). O Apêndice A do Regulamento traz o texto invertido ("direita e superior 3 cm"), provável erro de transcrição — verificar com o(a) avaliador(a).
- **Paginação:** pré-textuais contados sem número visível; numeração exibida a partir da Introdução (p. 7), cumulativa.
- **Palavras-chave:** o Regulamento exige descritores DeCS/MeSH (base da área da saúde). Os termos usados são aproximações; confirmar aceitação para tema de Computação.

## Divergência crítica de dados (não resolvida)

O documento do Stage 4 contém **três conjuntos de resultados incompatíveis** para o mesmo corpus de 22 UCs:

1. **Tabelas textuais** — pass@1 C1=0,000 / C2=0,409; testes cegos 0,627/0,966; captura de lacunas 0,453/0,921; flake8 1,812/1,344; CC 5,661/4,598; MI 32,82/39,08; LOC 209,9/253,7. Testes: Wilcoxon, Cliff, Holm. Revisão cega: C1 6,82 bloqueantes/amostra vs C2 0,95.
2. **Infográficos (imagens 1 e 2 do .docx)** — Taxa de sucesso 50,0%/77,3%; cobertura de testes 50,5%/80,5%; tempo até 1ª compilação 65,3/40,2 min; CC 9,6/6,9. Testes: McNemar, t pareado, Cohen's d. Severidade: 139 falhas em C1 vs 96 em C2.
3. **`stage4/results/avaliacoes.jsonl`** — 90 registros (não 44), com número desigual de gerações por célula (2, 3, 14, 1), e caminhos apontando para `D:\_dev\agent-tools-skills\stage4` (outro projeto). Recalculado: pass@1 0,849/0,941; taxa de testes 0,947/0,974; captura 0,931/0,974; MI 29,6/29,5.

**Ação necessária antes do Gate 5/6:** eleger e versionar uma única base experimental consolidada, reexecutar a análise a partir dela e substituir os infográficos por gráficos derivados dessa mesma base. Enquanto isso não for feito, o trabalho é vulnerável à pergunta "de onde vêm esses números?" na banca.

## Pendências herdadas registradas no relatório (Apêndice B)

1. Validação cruzada de uma amostra do corpus com o pipeline automatizado real (ameaça de construto — Alta)
2. Corrigir as implementações de referência `_ref/` ou documentar formalmente a decisão contrária (Alta)
3. Executar os testes funcionais pendentes dos agentes Working Backwards (CA-04, CA-05) (Alta)
4. Instrumentar o laço de refinamento iterativo (iterações e tempo de ciclo) (Média)
5. Ampliar para k≥5 gerações reais por tarefa (Média)
6. Segundo avaliador independente com cálculo de kappa (Média)
7. Reconciliar a base de dados experimental (Alta)
8. Resumo expandido de até 4 páginas para o e-book (Alta)
9. Atualizar o campo de sumário e conferir a paginação final (Média)

## Artefatos de build

Scripts em `/home/claude/tcc` (sessão efêmera): `build_docx.py` (helpers ABNT), `p1_pre.py` … `p6_pos.py` (conteúdo), `main.py` (montagem), `fig/` (5 figuras geradas com matplotlib a partir dos dados das tabelas textuais).