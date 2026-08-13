# Stage 4 — Corpus de Avaliação: 20 Casos de Uso para o Pipeline de Agentes

**Projeto:** Agentes de IA para Revisão de Requisitos e Código com LLMs
**Autores:** Larissa Matias, Nairo Rocha e Raphael Amaral
**Vínculo:** Etapa 5 do método (Stage 2 — Projeto de Pesquisa); Seções 3.6 e 13.1 do Stage 3
**Status:** Proposta de corpus — a validar em Reunião de Orientação antes do Gate 4

---

## 1. Objetivo

Este corpus operacionaliza o critério do Gate 3 "dados suficientes e de qualidade" e fornece a base do experimento do Stage 4: avaliar se especificações produzidas **com o pipeline dos quatro agentes em conjunto** resultam em código gerado por IA de qualidade funcional e estrutural superior à obtida a partir da descrição bruta, conforme a hipótese do Stage 2.

Cada caso de uso é uma **descrição de alto nível deliberadamente subespecificada** — contém lacunas, ambiguidades e regras implícitas plantadas de propósito. O valor do pipeline é justamente elicitar, estruturar e fechar essas lacunas antes da geração de código; as lacunas plantadas funcionam como *ground truth* de elicitação.

## 2. Desenho Experimental (alinhado ao Stage 2)

Desenho **pareado por tarefa**, com a tarefa de programação como unidade experimental:

| Condição | Fluxo |
|---|---|
| **C1 — Controle** | Descrição de alto nível → **Claude Code** (gerador) → código |
| **C2 — Tratamento** | Descrição de alto nível → **pipeline dos 4 agentes** → especificação estruturada + prompt técnico → **mesmo Claude Code** → código |

Regras de validade:

1. **Gerador fixo:** mesma versão do Claude Code CLI e mesmo modelo (pinado via `--model`), registrados no relatório. Execução headless (`claude -p`) para reprodutibilidade.
2. **k gerações por tarefa e condição** (k = 5) para cálculo de pass@k.
3. **Suíte de testes cega:** a suíte pytest completa de cada caso **nunca é vista** pelos agentes nem pelo gerador. Cada caso expõe apenas 2–3 *testes visíveis* (smoke tests), que o Claude Code pode usar no ciclo de refinamento.
4. **Gabarito pré-registrado:** as perguntas bloqueantes dos agentes são respondidas exclusivamente com o *gabarito de decisões* de cada caso (Seção 6), aplicado mecanicamente. Não há participantes humanos como sujeitos — mantém a dispensa de CEP declarada no Stage 2 (art. 21 do Regulamento).
5. **Máximo de 2 iterações** de pergunta-resposta por agente; lacuna sem resposta no gabarito segue como "avanço sob risco" (opção B do SFAR), registrada.

## 3. Pipeline dos 4 Agentes em Conjunto (condição C2)

```
Descrição vaga (caso UC-nn)
   │
   ▼
[1] Working Backwards Designer  → PR/FAQ canônico (premissas marcadas)
   │
   ▼
[2] Working Backwards Analyst   → GAP-nn + faróis; responder com gabarito;
   │                              repetir até 🔵/🟢 (máx. 2 iterações)
   ▼
[3] Senior Functional Analyst Reviewer
   │                            → RF/RNF com IDs, critérios de aceite Gherkin;
   │                              responder bloqueantes com gabarito;
   │                              até PRONTO PARA SOLUÇÃO (máx. 2 iterações)
   ▼
Prompt técnico consolidado (especificação + critérios de aceite + restrições)
   │
   ▼
Claude Code (gerador fixo)      → código Python + testes visíveis passando
   │
   ▼
[4] Code Reviewer               → relatório por severidade (cego à condição)
   +
Harness independente            → suíte pytest cega, flake8, radon (métricas primárias)
```

Papel de cada agente na avaliação conjunta: o **Designer** transforma a ideia vaga em PR/FAQ; o **Analyst** força o fechamento das lacunas de arquitetura; o **SFAR** converte o PR/FAQ em requisitos verificáveis e bloqueia ambiguidades; o **Code Reviewer** atua como **instrumento de medição complementar**, revisando cegamente o código das duas condições.

### Execução via Claude Code

- Os quatro agentes rodam como **subagents do Claude Code**, usando os manifestos já produzidos (`working-backwards-designer.yaml`, `working-backwards-analyst.yaml`, `senior-functional-analyst-reviewer.yaml`, `code-reviewer.yaml`) instalados em `.claude/agents/`.
- A geração de código (C1 e C2) usa sessões novas e isoladas por execução (sem memória entre casos), com diretório de trabalho limpo contendo apenas o enunciado (C1) ou o prompt técnico (C2) e os testes visíveis.
- A suíte cega roda **fora** do Claude Code, em harness próprio (`run_evals.py`), para impedir que o gerador "conserte" o código contra os testes de medição.

## 4. Métricas e Análise

**Primárias (objetivas, harness independente):**

- pass@k na suíte cega (k = 5);
- taxa de execução sem erro (compilabilidade/importabilidade);
- violações flake8 por 100 linhas; complexidade ciclomática média e índice de manutenibilidade (radon).

**Secundárias:**

- nº e severidade dos achados do Code Reviewer (cego à condição) — nota: por ser LLM-judge, é métrica complementar, nunca substituta das primárias;
- nº de iterações de refinamento até os testes visíveis passarem; tempo total do ciclo;
- **taxa de captura de lacunas**: fração das lacunas plantadas (Seção 6) explicitamente identificadas pelo pipeline em C2 — mede diretamente o valor de elicitação dos agentes;
- qualidade da especificação por rubrica (completude, consistência, cobertura de aceite), 2 avaliadores do grupo, cegos à condição, com kappa de concordância.

**Estatística:** teste de Wilcoxon pareado por tarefa, tamanho de efeito (Cliff's delta), correção de Holm para múltiplas métricas. n = 20 pares detecta efeitos médios-grandes; relatar poder observado. **Piloto obrigatório** com UC-01, UC-02 e UC-04 antes da rodada completa.

## 5. Visão Geral do Corpus

Cobertura por categoria dominante de requisito (objetivo específico 2 do Stage 2) e complexidade:

| ID | Título | Domínio | Categoria dominante | Complexidade |
|---|---|---|---|---|
| UC-01 | Juros compostos | Fintech | Regra de negócio | Média |
| UC-02 | Validador CPF/CNPJ | Cadastro | Funcional | Baixa |
| UC-03 | Cupons de desconto | E-commerce | Regra de negócio | Alta |
| UC-04 | Rate limiter de API | Plataforma | RNF — Desempenho | Média |
| UC-05 | Parcelamento | Fintech | Regra de negócio | Baixa |
| UC-06 | Agendamento de consultas | Saúde | Funcional | Média |
| UC-07 | Cálculo de frete | Logística | Regra de negócio | Baixa |
| UC-08 | Bloqueio de login | Segurança | RNF — Segurança | Média |
| UC-09 | Fila de chamados com SLA | Telecom | Funcional | Média |
| UC-10 | Conciliação de pagamentos | Fintech | Funcional | Alta |
| UC-11 | Anonimização LGPD | Dados | RNF — Segurança/Conformidade | Alta |
| UC-12 | Conversão de moedas com cache | Fintech | RNF — Confiabilidade | Média |
| UC-13 | Estoque com reserva | E-commerce | Funcional (concorrência) | Alta |
| UC-14 | Impostos por UF | Fiscal | Regra de negócio | Baixa |
| UC-15 | Notificações com retry | Plataforma | RNF — Confiabilidade | Média |
| UC-16 | Listagem paginada | Backoffice | Funcional | Baixa |
| UC-17 | Upload com validação | Plataforma | RNF — Segurança | Média |
| UC-18 | Cancelamento parcial de combo | E-commerce | Regra de negócio (jornada) | Alta |
| UC-19 | Trilha de auditoria | Plataforma | RNF — Segurança/Auditoria | Média |
| UC-20 | Política de senha | Segurança | RNF — Segurança | Baixa |

Distribuição: 6 regras de negócio, 6 funcionais, 5 segurança/conformidade, 3 desempenho/confiabilidade; 6 baixa, 9 média, 5 alta. UC-18 exercita especificamente a Matriz de Cobertura de Jornada do SFAR; UC-14 exercita a Regra de Ouro (a resposta correta é *não assumir*).

## 6. Fichas dos Casos de Uso

Formato de cada ficha: **Descrição** (input experimental idêntico em C1 e C2), **Lacunas plantadas** (o que o pipeline deve detectar), **Gabarito de decisões** (respostas pré-registradas às perguntas dos agentes) e **Foco da suíte cega**.

---

### UC-01 — Juros compostos

**Descrição:** "Implemente uma função que calcule o valor final de um investimento com juros compostos."

**Lacunas plantadas:** taxa anual ou mensal; periodicidade de capitalização; regra de arredondamento; aportes recorrentes; entradas inválidas.

**Gabarito:** taxa anual nominal; capitalização mensal; arredondamento *half-even* com 2 casas somente no resultado final; sem aportes; valores negativos ou período zero → `ValueError`; usar `Decimal`.

**Foco da suíte cega:** precisão decimal (float vs Decimal), fronteiras (taxa 0%, 1 período), exceções.

---

### UC-02 — Validador CPF/CNPJ

**Descrição:** "Crie um validador de documentos de identificação de pessoas físicas e jurídicas."

**Lacunas plantadas:** aceitar entrada com e sem máscara; dígitos repetidos (111.111.111-11); tipo de retorno; entrada vazia ou de tipo errado.

**Gabarito:** aceitar com e sem máscara; rejeitar sequências de dígitos idênticos; retornar `bool`; entrada vazia ou não-string → `False` (sem exceção).

**Foco da suíte cega:** dígitos verificadores corretos e incorretos, máscaras mistas, sequências repetidas.

---

### UC-03 — Cupons de desconto

**Descrição:** "Implemente um carrinho de compras que aplica cupons de desconto ao total."

**Lacunas plantadas:** acumulação de cupons; precedência entre percentual e valor fixo; teto de desconto; cupom expirado; valor mínimo de pedido; base de cálculo (com ou sem frete).

**Gabarito:** cupons não acumuláveis, exceto os marcados `stackable`; ordem: percentuais antes de fixos; teto total de 50% do subtotal; base = subtotal de produtos, sem frete; expirado ou abaixo do mínimo → erro específico por código (`CUPOM_EXPIRADO`, `PEDIDO_MINIMO`).

**Foco da suíte cega:** precedência, teto, empilhamento, bordas de validade, erros tipados.

---

### UC-04 — Rate limiter de API

**Descrição:** "Implemente um limitador de requisições por cliente para proteger uma API."

**Lacunas plantadas:** algoritmo (janela fixa vs deslizante); limite e janela; chave de identificação; comportamento ao negar; concorrência.

**Gabarito:** janela deslizante (sliding window log); 100 requisições/60 s por `client_id`; retorno `(allowed: bool, retry_after: float)`; thread-safe com lock; relógio injetável para testes.

**Foco da suíte cega:** fronteira exata da janela deslizante, `retry_after`, isolamento entre clientes, concorrência básica.

---

### UC-05 — Parcelamento

**Descrição:** "Divida o valor de uma compra em N parcelas."

**Lacunas plantadas:** distribuição dos centavos restantes; juros; limites de N; valor mínimo de parcela.

**Gabarito:** sem juros; soma das parcelas deve ser exatamente igual ao total; centavos excedentes na primeira parcela; 1 ≤ N ≤ 12; parcela mínima de R$ 5,00 (violação → `ValueError`).

**Foco da suíte cega:** invariante soma == total para valores "quebrados", distribuição dos centavos, limites.

---

### UC-06 — Agendamento de consultas

**Descrição:** "Implemente o agendamento de consultas médicas evitando conflitos de horário."

**Lacunas plantadas:** sobreposição parcial conta como conflito; consultas adjacentes; duração padrão; fuso horário; janela de atendimento.

**Gabarito:** intervalos semiabertos `[início, fim)` — adjacência exata não conflita; duração padrão 30 min; `datetime` timezone-aware normalizado para UTC; janela 07h–19h no fuso local da clínica; conflito → exceção com a consulta conflitante.

**Foco da suíte cega:** sobreposição parcial, adjacência, entradas naive vs aware, janela de atendimento.

---

### UC-07 — Cálculo de frete

**Descrição:** "Calcule o frete de um pedido a partir do peso e da região de destino."

**Lacunas plantadas:** inclusividade das fronteiras de faixa; peso volumétrico; região desconhecida; arredondamento.

**Gabarito:** faixas de peso `[min, max)` em kg; peso cobrado = `max(real, volumétrico)` com volumétrico = (A×L×C)/6000; região desconhecida → exceção (não assumir tarifa); resultado com 2 casas *half-up*.

**Foco da suíte cega:** peso exatamente na fronteira, volumétrico maior que real, região inválida.

---

### UC-08 — Bloqueio de login

**Descrição:** "Bloqueie o usuário após tentativas inválidas de login."

**Lacunas plantadas:** nº de tentativas e janela; duração do bloqueio; reset do contador; enumeração de usuários; comparação de credenciais.

**Gabarito:** 5 falhas em 15 min → bloqueio de 30 min; sucesso zera o contador; mensagem de erro idêntica para usuário inexistente e senha errada; comparação em tempo constante (`hmac.compare_digest`); eventos registrados sem senha em claro.

**Foco da suíte cega:** contagem e janela, reset, mensagens indistinguíveis, bloqueio expira.

---

### UC-09 — Fila de chamados com SLA

**Descrição:** "Priorize os chamados de suporte considerando criticidade e tempo de espera."

**Lacunas plantadas:** fórmula de prioridade; critério de desempate; chamados com SLA estourado; estabilidade da ordenação.

**Gabarito:** ordenar por severidade (crítica > alta > média > baixa), depois por deadline de SLA crescente, empate final por ordem de chegada (FIFO estável); chamado com SLA estourado vai ao topo dentro da sua severidade.

**Foco da suíte cega:** desempates, estabilidade, estouro de SLA, fila vazia.

---

### UC-10 — Conciliação de pagamentos

**Descrição:** "Concilie as transações internas com o extrato do gateway de pagamento."

**Lacunas plantadas:** chave de correspondência; duplicatas no extrato; valores divergentes; categorias de saída.

**Gabarito:** matching por `transaction_id`; saída em 5 categorias: `conciliada`, `divergente` (mesmo id, valor diferente), `duplicada` (id repetido no extrato — nunca conciliar duas vezes), `somente_interna`, `somente_extrato`; valores em `Decimal`; divergência de qualquer magnitude (inclusive 1 centavo) é `divergente`.

**Foco da suíte cega:** duplicatas, divergência de centavos, conjuntos disjuntos, idempotência da conciliação.

---

### UC-11 — Anonimização LGPD

**Descrição:** "Anonimize os dados pessoais dos registros de clientes para uso em relatórios."

**Lacunas plantadas:** quais campos são PII; mascaramento reversível vs irreversível; preservação de utilidade analítica; estruturas aninhadas; estabilidade para junção.

**Gabarito:** CPF e telefone mascarados parcialmente (`***.***.***-12`); e-mail preserva apenas o domínio; nome → iniciais; chave de junção = SHA-256 do CPF com salt fixo do projeto; percorrer dicts aninhados e listas; função idempotente.

**Foco da suíte cega:** irreversibilidade, aninhamento, idempotência, estabilidade da chave de junção.

---

### UC-12 — Conversão de moedas com cache

**Descrição:** "Converta valores entre moedas usando taxas obtidas de uma API externa."

**Lacunas plantadas:** TTL do cache; comportamento quando a API falha; precisão; moeda não suportada.

**Gabarito:** cache com TTL de 10 min; falha da API → usar última taxa conhecida com flag `stale=True`, até o limite de 24 h (depois, exceção); `Decimal` com 4 casas intermediárias e 2 no resultado; moeda desconhecida → exceção; cliente HTTP injetável.

**Foco da suíte cega:** mock da API, expiração do TTL, fallback stale, limite de 24 h.

---

### UC-13 — Estoque com reserva

**Descrição:** "Controle o estoque com reserva temporária de itens durante o checkout."

**Lacunas plantadas:** expiração da reserva; atomicidade de reservas multi-item; cálculo de disponibilidade; concorrência.

**Gabarito:** reserva expira em 15 min e devolve ao disponível; reserva multi-item é tudo-ou-nada (atômica); disponível = físico − reservas ativas; thread-safe; relógio injetável.

**Foco da suíte cega:** expiração, tudo-ou-nada com item insuficiente, corrida de duas reservas pelo último item.

---

### UC-14 — Impostos por UF

**Descrição:** "Calcule o imposto de uma venda conforme o estado do comprador, usando a tabela de alíquotas fornecida."

**Lacunas plantadas:** a tabela fornecida cobre apenas 5 UFs — o que fazer com as demais; base de cálculo com ou sem frete; itens isentos. *Este caso testa diretamente a Regra de Ouro: a resposta certa é não inventar alíquota.*

**Gabarito:** UF ausente da tabela → exceção `AliquotaNaoCadastrada` (nunca aplicar default); base = valor dos produtos, sem frete; itens com flag `isento` ficam fora da base.

**Foco da suíte cega:** UF ausente, isenção, base sem frete, tabela vazia.

---

### UC-15 — Notificações com retry

**Descrição:** "Envie notificações aos clientes com nova tentativa em caso de falha."

**Lacunas plantadas:** número de tentativas; estratégia de backoff; duplicação de envio; destino das falhas definitivas.

**Gabarito:** 3 tentativas; backoff exponencial determinístico 1 s / 2 s / 4 s (sem jitter, para testabilidade — `sleep` injetável); deduplicação por `idempotency_key`; falha após 3 tentativas → registro em `dead_letter` com o último erro.

**Foco da suíte cega:** contagem de tentativas, sequência de backoff, dedup, dead letter.

---

### UC-16 — Listagem paginada

**Descrição:** "Liste os pedidos com paginação e ordenação."

**Lacunas plantadas:** limites de página e tamanho; ordenação estável; campo de ordenação inválido; página além do fim; metadados de retorno.

**Gabarito:** `size` padrão 20, máximo 100; ordenação estável com desempate por `id`; campo inválido → `ValueError`; página além do fim → lista vazia com metadados corretos; retorno `{items, page, size, total, pages}`.

**Foco da suíte cega:** bordas de tamanho, estabilidade, metadados, página fora do intervalo.

---

### UC-17 — Upload com validação

**Descrição:** "Receba upload de imagens com validação do arquivo."

**Lacunas plantadas:** validação por extensão vs conteúdo real; tamanho máximo; sanitização do nome (path traversal); divergência extensão/conteúdo.

**Gabarito:** aceitar apenas PNG e JPEG **pela assinatura binária** (magic bytes); máximo 5 MB; nome de destino = UUID + extensão canônica derivada da assinatura (ignorar o nome original — elimina `../`); extensão divergente da assinatura → rejeitar.

**Foco da suíte cega:** PNG renomeado para .jpg, executável com extensão de imagem, traversal no nome, limite de tamanho.

---

### UC-18 — Cancelamento parcial de combo

**Descrição:** "Permita cancelar itens de um pedido que contém combos promocionais."

**Lacunas plantadas:** cancelar um componente quebra o desconto do combo; recomposição de preço dos itens restantes; cálculo do estorno; itens já enviados; ciclo de vida do pedido (caso desenhado para a Matriz de Cobertura de Jornada do SFAR).

**Gabarito:** cancelamento de componente de combo → itens restantes são reprecificados a preço cheio, limitado ao valor originalmente pago; estorno = pago − novo total (nunca negativo); item com status `enviado` não é cancelável; pedido totalmente cancelado muda de estado e não aceita novas operações.

**Foco da suíte cega:** recomposição, estorno não negativo, estados inválidos, cancelamento total vs parcial.

---

### UC-19 — Trilha de auditoria

**Descrição:** "Registre uma trilha de auditoria das operações do sistema."

**Lacunas plantadas:** campos obrigatórios; PII no payload; imutabilidade/adulteração; ordem temporal.

**Gabarito:** campos fixos `{timestamp_utc, actor_id, action, resource, result}`; payload filtrado por denylist de PII (cpf, senha, e-mail, telefone); registros encadeados por hash SHA-256 do registro anterior (append-only); função `verificar_integridade()` detecta adulteração em qualquer ponto da cadeia.

**Foco da suíte cega:** denylist aplicada em campos aninhados, detecção de adulteração, cadeia vazia.

---

### UC-20 — Política de senha

**Descrição:** "Valide se a senha do usuário é forte o suficiente."

**Lacunas plantadas:** "forte" não definido — comprimento, classes de caracteres, senhas comuns, formato do retorno.

**Gabarito:** mínimo 12 caracteres; ao menos 3 de 4 classes (minúscula, maiúscula, dígito, símbolo); rejeitar senhas da lista das 100 mais comuns (fornecida) e repetições de um único caractere; retorno = lista de violações (vazia = válida), nunca `bool` seco.

**Foco da suíte cega:** cada regra isolada, combinações de 2 classes, senha comum com maiúscula, retorno estruturado.

---

## 7. Estrutura de Arquivos Proposta

```
stage4/
├── corpus/
│   └── UC-nn/
│       ├── enunciado.md          # descrição vaga (input C1 e C2)
│       ├── gabarito.md           # decisões pré-registradas (nunca vai ao gerador)
│       ├── tests_visiveis/       # 2–3 smoke tests (vão ao gerador)
│       └── tests_cegos/          # suíte pytest completa (só no harness)
├── runs/
│   └── UC-nn/{c1,c2}/geracao-k/  # código gerado + logs + specs (C2)
├── reviews/                      # relatórios do Code Reviewer (cegos)
└── run_evals.py                  # harness: pytest cego, flake8, radon, consolidação
```

## 8. Riscos e Salvaguardas

- **Contaminação de testes:** suíte cega jamais entra no diretório visto pelo Claude Code; testes visíveis são disjuntos da suíte cega.
- **Circularidade do LLM-judge:** o Code Reviewer mede, mas não decide — conclusões sustentadas pelas métricas objetivas.
- **Vazamento de gabarito em C1:** o gabarito responde apenas perguntas formuladas pelos agentes em C2; C1 recebe somente o enunciado.
- **Variabilidade do gerador:** k = 5 gerações e registro de versão do CLI/modelo; sementes e parâmetros documentados quando disponíveis.
- **Ordem de execução:** casos executados em ordem aleatória e sessões isoladas, sem reaproveitamento de contexto.
