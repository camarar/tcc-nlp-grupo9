# UC-11 — Especificação técnica consolidada
## Pipeline de anonimização para uso analítico (LGPD)

> Documento produzido pela condição experimental **c2**: pipeline de três agentes de
> requisitos (`working-backwards-designer` → `working-backwards-analyst` →
> `senior-functional-analyst-reviewer`), com respostas às perguntas bloqueantes
> extraídas exclusivamente do gabarito de decisões de produto quando disponíveis.
> Ver `registro.md` para o detalhe de cada rodada de pergunta-resposta e
> `captura.json` para a lista literal de perguntas bloqueantes formuladas.

---

## 1. Contrato obrigatório

> Copiado literalmente de `stage4/corpus/UC-11/enunciado.md`.

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão.

```python
class ErroAnonimizacao(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class Anonimizador:
    def __init__(self, salt: str) -> None: ...

    def registrar_politica(self, finalidade: str, regras: dict) -> None:
        """`regras` mapeia nome de campo -> estratégia."""

    def anonimizar(self, registro: dict, finalidade: str) -> dict: ...

    def anonimizar_lote(self, registros: list[dict], finalidade: str) -> list[dict]: ...

    def chave_juncao(self, registro: dict) -> str: ...

    def campos_sensiveis(self, registro: dict) -> list[str]: ...
```

### Vocabulário fechado

`ErroAnonimizacao.code` assume **somente**: `POLITICA_INVALIDA`, `FINALIDADE_INVALIDA`,
`REGISTRO_INVALIDO`, `CHAVE_INVALIDA`.

A estratégia assume **somente**: `MASCARA`, `HASH`, `INICIAIS`, `DOMINIO`, `GENERALIZAR`,
`REMOVER`, `MANTER`.

---

## 2. Requisitos Funcionais (RF)

### RF-01 — Registrar política por finalidade

`registrar_politica(finalidade, regras)` associa, a uma finalidade de uso, um mapa
`campo -> estratégia`.

**Regras de negócio:**
- Uma nova chamada para a **mesma finalidade** substitui integralmente as regras
  anteriores (não faz merge, não lança erro).
- Dispara `POLITICA_INVALIDA` quando: `regras` vazio ou ausente; alguma estratégia fora
  do vocabulário fechado; algum nome de campo vazio; `finalidade` vazia.
- A validação de `POLITICA_INVALIDA` ocorre no momento de `registrar_politica` (é quando
  `regras`/`finalidade` são fornecidos). `salt` vazio no construtor dispara
  `POLITICA_INVALIDA` no momento da instanciação. `anonimizar`/`anonimizar_lote` **não**
  revalidam a política — apenas verificam se a finalidade foi registrada.

### RF-02 — Estratégia `MASCARA`

Preserva os dois últimos caracteres do valor e substitui todos os demais por `*`,
mantendo o comprimento original (inclusive separadores).

Exemplo: `"12345678909"` → `"*********09"`.

### RF-03 — Estratégia `HASH`

`hashlib.sha256((salt + str(valor)).encode()).hexdigest()`, hexadecimal completo em
minúsculas.

### RF-04 — Estratégia `INICIAIS`

Primeira letra de cada palavra, em maiúscula, cada uma seguida de ponto. Espaços
múltiplos são colapsados.

Exemplo: `"Maria da Silva"` → `"M.D.S."`.

### RF-05 — Estratégia `DOMINIO`

Preserva apenas o domínio do e-mail, prefixado por `*@`.

Exemplo: `"maria@x.com"` → `"*@x.com"`. Valor sem `@` dispara `REGISTRO_INVALIDO`.

### RF-06 — Estratégia `GENERALIZAR`

Sobre `datetime.date`, devolve apenas o ano como `int`. Sobre `int`, devolve a faixa de
dez em dez como texto (ex.: `37` → `"30-39"`). Qualquer outro tipo dispara
`REGISTRO_INVALIDO`.

### RF-07 — Estratégia `REMOVER`

Exclui a chave do resultado (não a define como `None`).

### RF-08 — Estratégia `MANTER`

Copia o valor sem alteração. É a única estratégia que preserva o valor original.

### RF-09 — Tratamento de `None`

`None` presente em campo declarado atravessa `MASCARA`, `HASH`, `INICIAIS`, `DOMINIO` e
`GENERALIZAR` sem alteração e sem erro; permanece `None` no resultado.

### RF-10 — Modelo de política: allowlist recursiva por nome de campo

A política funciona como **allowlist**: qualquer campo do registro que não esteja
explicitamente declarado nas regras da finalidade é **removido** do resultado. `MANTER`
é a única forma de preservar um valor sem transformação.

Campos cujo valor é `dict` ou lista de `dict` são sempre percorridos recursivamente,
estejam ou não declarados na política — a allowlist vale para os valores escalares
dentro deles, **aplicada pelo nome do campo, em qualquer profundidade** (sem distinção de
caminho/posição estrutural: um nome de campo tem exatamente um tratamento por
finalidade, onde quer que ocorra no registro — esta é uma decisão de design deliberada,
não uma limitação a corrigir). Um contêiner que fique sem nenhum campo permitido é
mantido no resultado, vazio. Listas de valores simples (não-`dict`) são tratadas como
escalares — só sobrevivem se o campo estiver declarado.

### RF-11 — `anonimizar` (registro único)

Aplica a política da finalidade informada ao registro e devolve um novo `dict`
anonimizado.

**⚠️ Risco aceito (avanço sob risco — opção B do SFAR, ver `registro.md`):** o
comportamento quando um campo está **declarado** na política mas sua **chave está
totalmente ausente** do dicionário de entrada (distinto de presente com valor `None`,
coberto pelo RF-09) **não tem decisão de produto registrada**. Foi perguntado duas vezes
em duas etapas distintas do pipeline (arquitetura e revisão funcional) sem resposta
disponível no gabarito. A implementação deve documentar explicitamente qual das leituras
adotou como comportamento provisório — `REGISTRO_INVALIDO`, equivalente a `None`, ou
remoção silenciosa — e sinalizar no código que se trata de uma decisão de engenharia
tomada na ausência de definição de produto, não uma regra de negócio confirmada.

### RF-12 — `anonimizar_lote` (lote atômico)

Processa uma lista de registros para a mesma finalidade. É **atômico**: só devolve
resultado se **todos** os registros puderem ser processados; qualquer erro em qualquer
item interrompe a operação inteira e a exceção é propagada (all-or-nothing, sem
processamento parcial).

### RF-13 — `chave_juncao`

`hashlib.sha256((salt + cpf_somente_digitos).encode()).hexdigest()`, onde
`cpf_somente_digitos` descarta qualquer caractere não numérico do campo `cpf` do
**nível raiz** do registro.

**Regras de negócio:**
- É **independente da finalidade**, o que permite cruzar registros da mesma pessoa entre
  relatórios/finalidades diferentes.
- Depende do `salt` da instância — instâncias/processos diferentes precisam do mesmo
  `salt` para produzirem chaves comparáveis entre si.
- Registro sem `cpf`, com `cpf` vazio, ou sem nenhum dígito dispara `CHAVE_INVALIDA`.

### RF-14 — `campos_sensiveis`

Independe de qualquer política ou finalidade registrada. Usa uma **denylist fixa**:
`{cpf, cnpj, email, telefone, nome, endereco, cep, rg, data_nascimento}`.

Devolve os nomes encontrados no registro em **qualquer profundidade**, sem repetição, em
ordem alfabética — é a **união de nomes únicos**, não uma lista de caminhos (paths);
coerente com a regra de aplicação "por nome, em qualquer profundidade" do RF-10.

### RF-15 — Vocabulário fechado de erros: condições de disparo

| Código | Condição de disparo |
|---|---|
| `POLITICA_INVALIDA` | `regras` vazio/ausente; alguma estratégia fora do vocabulário fechado; algum nome de campo vazio; `finalidade` vazia (em `registrar_politica`); `salt` vazio no construtor |
| `FINALIDADE_INVALIDA` | `anonimizar`/`anonimizar_lote` chamados com finalidade nunca registrada |
| `REGISTRO_INVALIDO` | o registro não é um `dict`; `DOMINIO` aplicado a valor sem `@`; `GENERALIZAR` aplicado a tipo diferente de `datetime.date`/`int` |
| `CHAVE_INVALIDA` | ao calcular `chave_juncao`: registro sem `cpf`, com `cpf` vazio, ou sem nenhum dígito |

### RF-16 — Propriedades transversais

- **Não destrutivo:** o registro de entrada nunca é modificado; o resultado de
  `anonimizar`/`anonimizar_lote` é sempre uma estrutura nova.
- **Determinismo:** a mesma entrada, com o mesmo `salt` e a mesma finalidade, produz
  exatamente a mesma saída em execuções diferentes — não há aleatoriedade em nenhuma
  estratégia, incluindo `HASH` e `chave_juncao`.

---

## 3. Requisitos Não Funcionais (RNF)

### RNF-01 — Gestão do `salt` ⚠️ risco aceito

Categoria ISO/IEC 25010: Segurança (confidencialidade). **Sem decisão de produto
disponível** sobre geração, rotação e armazenamento do `salt` — ver `registro.md`
("avanço sob risco"). A propriedade de determinismo (RF-16) só se sustenta
operacionalmente se o mesmo `salt` for preservado entre execuções/processos; isso é uma
premissa implícita ainda não formalizada como requisito operacional.

### RNF-02 — Enquadramento de conformidade LGPD ⚠️ risco aceito

Categoria ISO/IEC 25010: Segurança (conformidade). **Sem decisão de produto disponível**
sobre se o pipeline deve produzir anonimização irreversível (dado deixa de ser dado
pessoal, LGPD Art. 12) ou pseudonimização reversível (dado permanece dado pessoal). Ver
`registro.md`.

### RNF-03 — Controle de acesso a `registrar_politica` ⚠️ risco aceito

Categoria ISO/IEC 25010: Segurança (controle de acesso). **Sem decisão de produto
disponível** sobre quem está autorizado a registrar/sobrescrever a política de uma
finalidade. Ver `registro.md`.

### RNF-04 — Retenção de dados anonimizados e do `salt` ⚠️ risco aceito

Categoria ISO/IEC 25010: Segurança (conformidade) / Adequação funcional. **Sem decisão
de produto disponível** sobre prazo de retenção. Ver `registro.md`.

---

## 4. Riscos e Premissas Assumidos (avanço sob risco — opção B do SFAR)

Os itens abaixo **não** possuem decisão de produto no gabarito consultado. Não foram
inventados; foram formalmente registrados como lacunas conhecidas, conforme protocolo
desta execução (máx. 2 iterações de pergunta-resposta por agente). Detalhamento completo
em `registro.md`.

1. **RF-11 residual** — campo declarado na política com chave ausente do dicionário de
   entrada (perguntado duas vezes, por dois agentes distintos, sem resposta em nenhuma
   das duas rodadas).
2. **RNF-01** — geração, rotação e armazenamento do `salt`.
3. **RNF-02** — enquadramento legal (anonimização irreversível vs. pseudonimização
   reversível) sob a LGPD.
4. **RNF-03** — controle de acesso/autorização a `registrar_politica`.
5. **RNF-04** — prazo de retenção do dado anonimizado e do `salt`.

---

## 5. Critérios de Aceite (Gherkin)

```gherkin
Funcionalidade: Registro de política por finalidade

  Cenário: Registrar política válida
    Dado um Anonimizador instanciado com um salt não vazio
    Quando registrar_politica é chamado com finalidade "relatorio_financeiro"
      e regras {"email": "DOMINIO"}
    Então nenhuma exceção é lançada

  Cenário: Registrar política com estratégia fora do vocabulário fechado
    Dado um Anonimizador instanciado com um salt não vazio
    Quando registrar_politica é chamado com regras {"cpf": "OFUSCAR"}
    Então uma ErroAnonimizacao com code "POLITICA_INVALIDA" é lançada

  Cenário: Registrar política com regras vazias
    Dado um Anonimizador instanciado com um salt não vazio
    Quando registrar_politica é chamado com finalidade "x" e regras {}
    Então uma ErroAnonimizacao com code "POLITICA_INVALIDA" é lançada

  Cenário: Registrar a mesma finalidade duas vezes substitui as regras
    Dado uma política registrada para "financeiro" com regras {"cpf": "MASCARA"}
    Quando registrar_politica é chamado novamente para "financeiro" com regras {"cpf": "HASH"}
    E anonimizar é chamado com um registro contendo "cpf"
    Então o campo "cpf" é tratado com a estratégia HASH, não MASCARA

  Cenário: Instanciar Anonimizador com salt vazio
    Quando Anonimizador("") é instanciado
    Então uma ErroAnonimizacao com code "POLITICA_INVALIDA" é lançada


Funcionalidade: Estratégias de anonimização

  Cenário: MASCARA preserva os dois últimos caracteres
    Dado uma política com {"cpf": "MASCARA"} para a finalidade "f"
    Quando anonimizar é chamado com {"cpf": "12345678909"} para "f"
    Então o resultado é {"cpf": "*********09"}

  Cenário: HASH é determinístico e depende do salt
    Dado um Anonimizador com salt "s1" e política {"email": "HASH"} para "f"
    Quando anonimizar é chamado duas vezes com o mesmo registro para "f"
    Então o valor de "email" é idêntico nas duas saídas

  Cenário: INICIAIS colapsa espaços múltiplos
    Dado uma política com {"nome": "INICIAIS"} para "f"
    Quando anonimizar é chamado com {"nome": "Maria  da   Silva"} para "f"
    Então o resultado é {"nome": "M.D.S."}

  Cenário: DOMINIO extrai o domínio do e-mail
    Dado uma política com {"email": "DOMINIO"} para "f"
    Quando anonimizar é chamado com {"email": "maria@x.com"} para "f"
    Então o resultado é {"email": "*@x.com"}

  Cenário: DOMINIO em valor sem @ dispara REGISTRO_INVALIDO
    Dado uma política com {"email": "DOMINIO"} para "f"
    Quando anonimizar é chamado com {"email": "maria-sem-arroba"} para "f"
    Então uma ErroAnonimizacao com code "REGISTRO_INVALIDO" é lançada

  Cenário: GENERALIZAR sobre int retorna faixa de dez em dez
    Dado uma política com {"idade": "GENERALIZAR"} para "f"
    Quando anonimizar é chamado com {"idade": 37} para "f"
    Então o resultado é {"idade": "30-39"}

  Cenário: GENERALIZAR sobre date retorna o ano
    Dado uma política com {"nascimento": "GENERALIZAR"} para "f"
    Quando anonimizar é chamado com {"nascimento": date(1990, 5, 1)} para "f"
    Então o resultado é {"nascimento": 1990}

  Cenário: GENERALIZAR em tipo não suportado dispara REGISTRO_INVALIDO
    Dado uma política com {"idade": "GENERALIZAR"} para "f"
    Quando anonimizar é chamado com {"idade": "trinta e sete"} para "f"
    Então uma ErroAnonimizacao com code "REGISTRO_INVALIDO" é lançada

  Cenário: REMOVER exclui a chave do resultado
    Dado uma política com {"cpf": "REMOVER"} para "f"
    Quando anonimizar é chamado com {"cpf": "12345678909"} para "f"
    Então o resultado não contém a chave "cpf"

  Cenário: MANTER preserva o valor original
    Dado uma política com {"segmento": "MANTER"} para "f"
    Quando anonimizar é chamado com {"segmento": "premium"} para "f"
    Então o resultado é {"segmento": "premium"}

  Esquema do Cenário: None atravessa as estratégias sem erro
    Dado uma política com {"<campo>": "<estrategia>"} para "f"
    Quando anonimizar é chamado com {"<campo>": None} para "f"
    Então o resultado é {"<campo>": None}

    Exemplos:
      | campo | estrategia  |
      | cpf   | MASCARA     |
      | email | HASH        |
      | nome  | INICIAIS    |
      | email | DOMINIO     |
      | idade | GENERALIZAR |


Funcionalidade: Allowlist e estruturas aninhadas

  Cenário: Campo não declarado na política é removido
    Dado uma política com {"email": "DOMINIO"} para "f" (sem declarar "cpf")
    Quando anonimizar é chamado com {"email": "a@x.com", "cpf": "123"} para "f"
    Então o resultado não contém a chave "cpf"

  Cenário: Campo aninhado é percorrido recursivamente pelo nome
    Dado uma política com {"cep": "MASCARA"} para "f"
    Quando anonimizar é chamado com {"endereco": {"cep": "12345000", "cidade": "X"}} para "f"
    Então o resultado é {"endereco": {"cep": "*******00"}}

  Cenário: Contêiner sem nenhum campo permitido é mantido vazio
    Dado uma política sem nenhuma regra que cubra os campos de "endereco" para "f"
    Quando anonimizar é chamado com {"endereco": {"cidade": "X"}} para "f"
    Então o resultado é {"endereco": {}}

  Cenário: Lista de escalares só sobrevive se o campo estiver declarado
    Dado uma política com {"tags": "MANTER"} para "f"
    Quando anonimizar é chamado com {"tags": ["a", "b"]} para "f"
    Então o resultado é {"tags": ["a", "b"]}


Funcionalidade: Lote atômico

  Cenário: Lote totalmente válido é processado
    Dado uma política válida para "f"
    Quando anonimizar_lote é chamado com uma lista de 3 registros válidos para "f"
    Então o resultado é uma lista com 3 registros anonimizados

  Cenário: Um item inválido no lote interrompe toda a operação
    Dado uma política válida para "f"
    Quando anonimizar_lote é chamado com uma lista de 3 registros, sendo o 2º não um dict
    Então uma ErroAnonimizacao com code "REGISTRO_INVALIDO" é lançada
    E nenhum resultado parcial é retornado


Funcionalidade: Chave de junção

  Cenário: Chave de junção é independente da finalidade
    Dado um Anonimizador com salt "s1"
    Quando chave_juncao é chamado com o mesmo registro (mesmo cpf), sem relação com finalidade
    Então o resultado é o mesmo hash em qualquer contexto de finalidade

  Cenário: CPF é normalizado antes do hash
    Dado um Anonimizador com salt "s1"
    Quando chave_juncao é chamado com {"cpf": "123.456.789-09"} e com {"cpf": "12345678909"}
    Então os dois resultados são idênticos

  Cenário: CPF ausente dispara CHAVE_INVALIDA
    Dado um Anonimizador com salt "s1"
    Quando chave_juncao é chamado com um registro sem a chave "cpf"
    Então uma ErroAnonimizacao com code "CHAVE_INVALIDA" é lançada

  Cenário: CPF sem dígitos dispara CHAVE_INVALIDA
    Dado um Anonimizador com salt "s1"
    Quando chave_juncao é chamado com {"cpf": "---"}
    Então uma ErroAnonimizacao com code "CHAVE_INVALIDA" é lançada


Funcionalidade: Campos sensíveis

  Cenário: campos_sensiveis independe de política registrada
    Dado um Anonimizador sem nenhuma política registrada
    Quando campos_sensiveis é chamado com {"cpf": "123", "cidade": "X"}
    Então o resultado é ["cpf"]

  Cenário: campos_sensiveis retorna nomes únicos em ordem alfabética, qualquer profundidade
    Quando campos_sensiveis é chamado com {"nome": "A", "endereco": {"cep": "1", "email": "a@x.com"}}
    Então o resultado é ["cep", "email", "nome"]


Funcionalidade: Finalidade não registrada

  Cenário: anonimizar com finalidade nunca registrada
    Dado um Anonimizador sem política registrada para "inexistente"
    Quando anonimizar é chamado com um registro válido para "inexistente"
    Então uma ErroAnonimizacao com code "FINALIDADE_INVALIDA" é lançada
```

---

## 6. Rastreabilidade

Ver `registro.md` para o mapeamento completo entre cada requisito acima, a pergunta
bloqueante que o originou, a etapa/iteração do pipeline em que foi formulado, e se a
resposta veio do gabarito ou foi registrada como avanço sob risco.
