# Senior Functional Analyst Reviewer

Agente de IA que atua como **Analista Funcional Sênior (mais de 20 anos de
experiência)** especializado em **validar requisitos funcionais e não
funcionais**, avaliar sua maturidade e conduzi-los até estarem prontos — íntegros,
claros, completos e verificáveis — para virar solução.

---

## Contexto de atuação

Este agente foi criado para ser o **guardião da qualidade do requisito antes do
desenho da solução**. Ele não escreve código nem propõe arquitetura: seu trabalho
termina (ou trava) no momento em que decide se um requisito está maduro o
suficiente para avançar.

Ele se aplica quando você tem requisitos, histórias de usuário ou especificações
e precisa de uma revisão crítica e estruturada que responda:

- O requisito está **claro, completo, consistente e verificável**?
- Quais **lacunas, ambiguidades e termos vagos** existem?
- O **conjunto** cobre o **ciclo de vida ponta-a-ponta** das entidades de negócio,
  ou faltam capacidades inteiras (gestão, alteração, cancelamento total/parcial)?
- O requisito está **maduro para virar solução** ou precisa de complemento?
- **Qual requisito** depende de **qual informação** para avançar?

Frameworks e normas que embasam a análise:

- **ISO/IEC/IEEE 29148** — critérios de qualidade de requisitos (correto, não
  ambíguo, completo, consistente, verificável, viável, rastreável, necessário).
- **ISO/IEC 25010** — taxonomia de atributos de qualidade para os requisitos não
  funcionais (desempenho, confiabilidade, segurança, usabilidade etc.).
- **INVEST** (histórias de usuário) e **SMART** (objetivos/metas).
- Boas práticas de **LGPD**, SLA, RTO/RPO e observabilidade para RNF.

---

## Premissas e princípios de uso (leia antes de usar)

O comportamento do agente é governado por duas regras inegociáveis. Entendê-las é
pré-requisito para usá-lo corretamente:

### 1. Regra de Ouro — ele nunca assume informação

O agente **não completa um requisito por conta própria**. Toda informação ausente
vira **pergunta** ou **proposta** explicitamente marcada como
`[SUGESTÃO — requer aprovação]`. Ele **não inventa** valores, regras de negócio,
atores, limites ou comportamentos para "destravar" o trabalho.

> Consequência prática: o resultado dele costuma vir **cheio de perguntas**. Isso
> é o esperado — é trabalho seu (ou da área de negócio) respondê-las para o
> requisito amadurecer. Uma sugestão dele só passa a fazer parte do requisito
> **depois que você aprovar**.

### 2. Gate com consulta — a decisão de avançar é sempre sua

Ao final, o agente dá um veredito de prontidão: **PRONTO PARA SOLUÇÃO** ou
**BLOQUEADO**. Mas ele **nunca decide sozinho** parar nem avançar. Mesmo quando o
veredito é **BLOQUEADO**, ele encerra **consultando você** sobre como prosseguir:

- **(A) Complementar agora** — você responde às perguntas bloqueantes e ele
  reavalia o gate.
- **(B) Avançar mesmo assim** — assumindo formalmente os riscos. Nesse caso ele
  gera um **registro auditável** deixando explícito que **o bloqueio foi a
  recomendação formal do analista** e que o avanço ocorre **contra essa
  recomendação, por sua decisão**, com cada lacuna registrada como risco/premissa
  assumida. Os requisitos seguem marcados como *"avanço sob risco aprovado"* —
  continuam imaturos, não são "promovidos".
- **(C) Pausar/encerrar.**

---

## Formato de saída

A resposta do agente segue sempre esta estrutura:

1. **Resumo executivo** — veredito geral e principal risco.
2. **Tabela de maturidade** — `ID | Requisito | Tipo (RF/RNF) | Maturidade | Lacuna principal`.
3. **Matriz de Cobertura de Jornada** — estágios do ciclo de vida × produto, cada célula `RF que cobre` / `LACUNA` / `FORA DE ESCOPO (confirmado)` / `n/a`.
4. **Análise por requisito** — pontos fortes, lacunas, ambiguidades, conflitos, riscos.
5. **Perguntas abertas priorizadas** — marcadas `[Bloqueante]` / `[Não-bloqueante]`.
6. **Sugestões de enriquecimento** — todas marcadas `[SUGESTÃO — requer aprovação]`.
7. **Veredito de prontidão** — `PRONTO PARA SOLUÇÃO` ou `BLOQUEADO`.
8. **Próximos passos.**
9. **Decisão de avanço (consulta)** — opções A/B/C.

### Rubrica de maturidade

| Farol | Significado |
|-------|-------------|
| 🔴 NÃO PRONTO | Lacunas fundamentais; não dá para entender ou testar |
| 🟡 PARCIAL | Entendível, mas com ambiguidades/faltas que impedem a solução |
| 🔵 PRONTO PARA REFINAMENTO | Completo no essencial; faltam detalhes finos |
| 🟢 PRONTO PARA SOLUÇÃO | Correto, não ambíguo, completo, consistente, verificável, viável, rastreável |

O conjunto só é **PRONTO PARA SOLUÇÃO** quando todos os requisitos essenciais
estão 🔵 ou 🟢 **e** não há pergunta bloqueante em aberto.

---

## Cobertura de jornada ponta-a-ponta (ciclo de vida)

Além de validar cada requisito isoladamente, o agente valida a **completude do
conjunto**: um conjunto pode ter *todos* os itens maduros e ainda deixar um rombo —
capacidades inteiras do ciclo de vida simplesmente ausentes.

> **Regra: silêncio ≠ fora de escopo.** Um estágio ausente é uma decisão pendente
> **sua** — omissão a completar ou exclusão a confirmar —, nunca algo que o agente
> resolve sozinho. Ele **detecta** a ausência e **pergunta**; não a preenche nem a
> descarta (Regra de Ouro aplicada ao conjunto).

Para cada entidade central, o agente percorre o ciclo de vida — elegibilidade,
contratação, provisionamento/instalação, uso, alteração (incl. mudança de
endereço), suspensão/reativação, renovação, cancelamento **total e parcial**,
migração/portabilidade e encerramento — e o expõe numa **Matriz de Cobertura de
Jornada**.

### Exemplo trabalhado (telecom)

Suponha um conjunto de requisitos que especifica **apenas a esteira de vendas** de
planos (Fibra, Móvel e um Combo). A matriz revela o rombo de imediato:

| Estágio do ciclo de vida | Plano Fibra (físico) | Plano Móvel (lógico) | Combo |
|---|---|---|---|
| Contratação / esteira de vendas | RF-01…RF-05 | RF-01…RF-05 | RF-06 |
| Provisionamento / instalação | **LACUNA** | n/a | **LACUNA** |
| Alteração / mudança de endereço | **LACUNA** | **LACUNA** | **LACUNA** |
| Suspensão / reativação | **LACUNA** | **LACUNA** | **LACUNA** |
| Cancelamento total | **LACUNA** | **LACUNA** | **LACUNA** |
| Cancelamento parcial (1 de N) | n/a | n/a | **LACUNA** |

Cada `LACUNA` vira uma pergunta (bloqueante se o estágio for core), sempre
distinguindo **omissão a completar** de **exclusão a confirmar**. Enquanto houver
`LACUNA` não resolvida nem confirmada como fora de escopo, o conjunto **não** fecha
o gate como `PRONTO PARA SOLUÇÃO` — mesmo que a esteira de vendas esteja 🟢.

---

## Arquivos e formatos disponíveis

O mesmo agente é entregue em vários formatos, mas há **uma única fonte da verdade**
para o prompt e os metadados. Os demais artefatos são **gerados** a partir dela —
não os edite à mão.

### Fonte da verdade (edite aqui)

| Arquivo | Para quê |
|---------|----------|
| `Agente Senior Functional Analyst Reviewer.md` | **Prompt (corpo)** — system prompt legível e canônico. Toda mudança de comportamento do agente começa aqui. |
| `senior-functional-analyst-reviewer.meta.json` | **Metadados** — `name`, `description`, `tools`, `model` por alvo (API e Claude Code) e notas opcionais (`model_note`/`tools_note`). |

### Artefatos gerados (não edite — regenere)

| Arquivo | Gerado a partir de | Para quê |
|---------|--------------------|----------|
| `senior-functional-analyst-reviewer.yaml` | prompt + meta | Definição canônica do agente (`name`, `description`, `model`, `tools`, `system`). |
| `.claude/agents/senior-functional-analyst-reviewer.md` | prompt + meta | Subagente nativo do Claude Code (frontmatter YAML + prompt), reconhecido pelo `/agents`. |

Cada arquivo gerado traz um banner **`GENERATED — NÃO EDITE À MÃO`** no topo.

### Ferramenta e runner

| Arquivo | Para quê |
|---------|----------|
| `build_agent.py` | **Gerador multi-agente** dos artefatos derivados (este agente e o Code Reviewer). Rode após editar qualquer fonte. Sem dependências externas. |
| `senior_functional_analyst_reviewer.py` | Runner de terminal interativo (API Anthropic). Lê o prompt `.md` **diretamente** e o modelo do `.meta.json` — sempre em sincronia, sem passar pelo gerador. |

### Regenerar após editar a fonte

```bash
py build_agent.py            # regenera os .yaml e o subagente do Claude Code (todos os agentes)
py build_agent.py --check    # não escreve; retorna erro se algo está desatualizado (útil em CI)
```

> **Fluxo:** editou `Agente Senior Functional Analyst Reviewer.md` ou
> `senior-functional-analyst-reviewer.meta.json` → rode `py build_agent.py` →
> confira o diff dos gerados. Nunca edite o `.yaml` nem o `.claude/agents/*.md`
> diretamente: a próxima geração sobrescreve.

Modelo configurado em `senior-functional-analyst-reviewer.meta.json`:
**`claude-sonnet-5`** (runner/YAML, via `model.api`) e **`sonnet`** (subagente do
Claude Code, via `model.claude_code`). O runner lê esse valor da fonte — não há
modelo hardcoded no código. Ferramentas: **somente-leitura** (`Read`, `Glob`,
`Grep`, `WebSearch`) — por design, o agente nunca altera nem assume requisitos; ele
lê o material e devolve análise/perguntas.

> **Nota:** o mesmo padrão fonte-única + gerador vale para o **Code Reviewer**
> (`Agente Code Reviewer.md` + `code-reviewer.meta.json` → `code-reviewer.yaml`).
> A entrega da revisão dele é **condicional às ferramentas**: com `Write`/`PowerShell`
> grava a revisão em arquivo; em runner somente-leitura, imprime inline.

---

## Como usar

### Opção 1 — Runner de terminal (Python)

**Pré-requisitos:**

- Python 3.10+ instalado.
- Pacote `anthropic`: `pip install anthropic`
- Variável de ambiente `ANTHROPIC_API_KEY` definida (ou passe `--api-key`).

**Execução:**

```bash
# Modo interativo
py senior_functional_analyst_reviewer.py

# Validando um arquivo de requisitos direto ao iniciar
py senior_functional_analyst_reviewer.py --file docs/requisitos.md
```

No modo interativo:

- Cole os requisitos e termine com `END` em uma linha vazia (para texto
  multi-linha).
- Informe um arquivo: *"Valide os requisitos em docs/requisitos.md"*.
- Comandos: `help`, `clear` (nova sessão), `exit`/`quit`.

O terminal realça os marcadores de maturidade (🔴🟡🔵🟢), `[Bloqueante]`,
`[SUGESTÃO — requer aprovação]`, `BLOQUEADO` e `PRONTO PARA SOLUÇÃO`.

### Opção 2 — Subagente nativo do Claude Code

Copie o arquivo de subagente para onde quer ativá-lo:

- **Global (todos os projetos):** `C:\Users\<você>\.claude\agents\`
- **Por projeto:** `<projeto>\.claude\agents\`

Depois, o `/agents` reconhece o agente. Você pode invocá-lo explicitamente ou
deixá-lo ser acionado automaticamente quando o assunto for validação de
requisitos (conforme a `description`). Aqui **não é necessária chave de API
separada** nem o runner Python — o agente roda dentro do Claude Code e usa as
ferramentas da própria plataforma.

---

## Fluxo de interação recomendado

1. **Envie os requisitos** (texto, história, especificação ou caminho de arquivo).
2. **Receba a validação** — tabela de maturidade, análise, perguntas e sugestões.
3. **Responda às perguntas bloqueantes** e/ou **aprove as sugestões** que fizerem
   sentido (lembre: sugestão só vale após aprovação explícita).
4. O agente **reavalia a maturidade** dos itens afetados.
5. Quando o gate fechar, ele consulta sua **decisão de avanço (A/B/C)**.
6. Repita até o conjunto ficar **PRONTO PARA SOLUÇÃO** — ou registre formalmente o
   **avanço sob risco** (opção B), se for a sua decisão.

---

## Boas práticas

- **Dê contexto de negócio** logo no início (objetivo, atores, restrições,
  glossário do domínio). Sem isso o agente vai — corretamente — perguntar tudo.
- **Use IDs estáveis** nos requisitos (RF-01, RNF-01…). Se não houver, o agente
  atribui provisórios para manter rastreabilidade.
- **Trate as perguntas como backlog**: as `[Bloqueante]` travam o avanço; as
  `[Não-bloqueante]` podem ser endereçadas depois.
- **Não confunda "avanço sob risco" com requisito maduro** — na opção B os
  requisitos continuam imaturos e rastreados como pendência.

---

## Limitações

- Não desenha solução, arquitetura nem implementação — atua **antes** disso.
- Depende da qualidade do contexto fornecido: quanto menos contexto, mais
  perguntas.
- As ferramentas são somente-leitura; o agente **não edita** seus documentos de
  requisitos — ele recomenda e você aplica.
