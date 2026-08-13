# Especificação Técnica Consolidada — UC-02: Motor de Cadastro e Deduplicação de Clientes

> Produzida pelo pipeline de três agentes de requisitos (`working-backwards-designer` →
> `working-backwards-analyst` → `senior-functional-analyst-reviewer`), condição C2.
> Cada regra abaixo tem origem em uma pergunta [BLOQUEANTE] formulada por um dos agentes e
> respondida a partir do gabarito de decisões de negócio (ver `registro.md` para o
> rastreamento pergunta → resposta → iteração). Nenhum trecho do gabarito foi copiado ou
> parafraseado em bloco — apenas o que foi efetivamente elicitado por pergunta virou
> requisito.

## 1. Visão geral

Motor de cadastro único de clientes (PF/PJ) que valida documento no registro, detecta
prováveis duplicatas por score ponderado, permite mesclar dois cadastros preservando
informação, e mantém histórico de auditoria append-only de toda alteração de estado ou
dado.

## 2. Contrato obrigatório

*(copiado literalmente de `stage4/corpus/UC-02/enunciado.md`)*

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão.

```python
class ErroCadastro(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class MotorCadastro:
    def __init__(self, agora: Callable[[], datetime] | None = None) -> None: ...

    def registrar(self, dados: dict) -> str:
        """`dados` tem as chaves: documento (str), nome (str), email (str | None),
        telefone (str | None), tipo (str). Retorna o identificador do cadastro."""

    def obter(self, cadastro_id: str) -> dict:
        """Retorna {"cadastro_id", "documento", "nome", "email", "telefone",
                    "tipo", "situacao", "mesclado_em"}"""

    def atualizar(self, cadastro_id: str, campos: dict, ator: str) -> dict:
        """Retorna o cadastro após a alteração, no formato de `obter`."""

    def buscar_duplicados(self, cadastro_id: str) -> list[dict]:
        """Retorna [{"cadastro_id": str, "score": Decimal, "criterios": list[str]}],
        ordenado do maior para o menor score."""

    def mesclar(self, principal_id: str, secundario_id: str, ator: str) -> str:
        """Retorna o identificador do cadastro sobrevivente."""

    def inativar(self, cadastro_id: str, ator: str) -> None: ...

    def historico(self, cadastro_id: str) -> list[dict]:
        """Retorna [{"em": datetime, "ator": str, "acao": str,
                     "campo": str | None, "de": Any, "para": Any}]"""

    def situacao(self, cadastro_id: str) -> str: ...
```

### Vocabulário fechado

`ErroCadastro.code` assume **somente**: `DOCUMENTO_INVALIDO`, `CADASTRO_NAO_ENCONTRADO`,
`ESTADO_INVALIDO`, `CONFLITO_MERGE`, `CAMPO_OBRIGATORIO`, `DUPLICADO`.

`situacao()` retorna **somente**: `ATIVO`, `MESCLADO`, `INATIVO`.

O campo `tipo` assume **somente**: `PF`, `PJ`.

O campo `acao` do histórico assume **somente**: `REGISTRO`, `ALTERACAO`, `MERGE_ORIGEM`,
`MERGE_DESTINO`, `INATIVACAO`.

Os `criterios` de `buscar_duplicados` assumem **somente**: `DOCUMENTO`, `EMAIL`,
`TELEFONE`, `NOME`.

> Este enunciado define o vocabulário, não a regra: em que circunstância cada código,
> situação, ação e critério se aplica faz parte do que precisa ser decidido.

### Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.

## 3. Requisitos Funcionais (RF)

| ID | Requisito | Maturidade |
|---|---|---|
| RF-01 | Validação de documento | 🟢 |
| RF-02 | Máscara e normalização do documento | 🟢 |
| RF-03 | Campos obrigatórios | 🟢 |
| RF-04 | Normalização de nome/email/telefone | 🔵 |
| RF-05 | Unicidade de documento | 🟢 |
| RF-06 | Score de duplicidade | 🟢 |
| RF-07 | Escopo de `buscar_duplicados` | 🟢 |
| RF-08 | Regras de merge | 🟡 (ver RF-08.a) |
| RF-09 | Histórico append-only | 🟢 |
| RF-10 | Campos atualizáveis | 🟢 |
| RF-11 | Precedência de `CADASTRO_NAO_ENCONTRADO` | 🟢 |
| RF-12 | Inativação | 🟢 |
| RF-13 | Restrição de escrita em MESCLADO/INATIVO | 🟢 |
| RF-14 | Precedência de erros em `atualizar()` | 🟢 |
| RF-15 | Situação inicial do cadastro | 🟢 |

**RF-01 — Validação de documento.** `PF` exige CPF (11 dígitos) e `PJ` exige CNPJ (14
dígitos), ambos com dígito verificador oficial (módulo 11) conferido. Documento com
quantidade de dígitos incompatível com o `tipo` → `DOCUMENTO_INVALIDO`. Documento formado
por um único dígito repetido é rejeitado com `DOCUMENTO_INVALIDO` mesmo que passe no
módulo 11.

**RF-02 — Máscara e normalização do documento.** Entrada aceita com ou sem máscara; todo
caractere não numérico é descartado antes da validação. Armazenado **sem máscara**
(somente dígitos); `obter()` devolve sem máscara.

**RF-03 — Campos obrigatórios.** `documento`, `nome`, `tipo` são obrigatórios (ausentes,
vazios ou só com espaços → `CAMPO_OBRIGATORIO`). `email`/`telefone` são opcionais, aceitam
`None`, e **não têm validação de formato** (o vocabulário fechado não contém código de
erro para isso). A validação de campo obrigatório precede a de documento.

**RF-04 — Normalização.** `nome`: trim, colapso de espaços internos, maiúsculas, sem
acentos (NFKD). `email`: trim + minúsculas. `telefone`: somente dígitos. Vale tanto para
armazenamento quanto para comparação. *(🔵 refinamento em aberto, não-bloqueante: caracteres
não alfabéticos residuais após NFKD — símbolos, alfabetos não latinos — não têm regra
definida; escopo de teste limitado a acentuação latina padrão.)*

**RF-05 — Unicidade de documento.** `registrar()` com documento já existente em cadastro
`ATIVO` → `DUPLICADO`. Se o cadastro existente estiver `INATIVO` ou `MESCLADO`, o novo
registro é permitido. Não há outra chave de unicidade dura (email/telefone/nome só
alimentam o score, RF-06).

**RF-06 — Score de duplicidade.** Soma aditiva dos pesos dos critérios coincidentes
(comparação exata sobre valores normalizados — RF-04; campos `None`/vazios nunca
coincidem): `DOCUMENTO`=1.00, `EMAIL`=0.50, `TELEFONE`=0.30, `NOME`=0.20, como `Decimal`
com 2 casas. Só entram no resultado candidatos com score **≥ 0.50**, ordenado
decrescente e, em empate, por `cadastro_id` crescente.

**RF-07 — Escopo de `buscar_duplicados`.** Considera cadastros `ATIVO` e `INATIVO`,
exclui `MESCLADO` e nunca inclui o próprio cadastro consultado. Consultar um cadastro
`MESCLADO` → `ESTADO_INVALIDO`. Não há filtro por `tipo`: um cadastro `PF` pode aparecer
como candidato de um `PJ` e vice-versa, se os critérios coincidirem o suficiente.

**RF-08 — Merge.** Ordem de precedência de erros em `mesclar()`: `CADASTRO_NAO_ENCONTRADO`
(existência de ambos) → `ESTADO_INVALIDO` (qualquer um fora de `ATIVO`) →
`CONFLITO_MERGE` (`principal_id == secundario_id` OU score de duplicidade entre os dois
< 0.50). `documento` e `nome` do principal nunca são alterados. Campos opcionais
(`email`, `telefone`) vazios/`None` no principal são preenchidos com o valor do
secundário; se ambos estão preenchidos com valores diferentes, prevalece o do principal
**sem erro** (não é `CONFLITO_MERGE`). O sobrevivente é sempre `principal_id`
(permanece `ATIVO`); o `secundario_id` passa a `MESCLADO` com `mesclado_em` = instante do
merge (`mesclado_em` de um cadastro `ATIVO` é sempre `None`).

- **RF-08.a [🟡 PARCIAL — avanço sob risco, ver L1 em §5].** Comportamento de
  `mesclar()` quando `principal` e `secundario` têm `tipo` diferente (`PF`×`PJ`) não tem
  resposta disponível. Nenhum critério de aceite de sucesso ou erro é afirmado para esse
  caso — ver Gherkin com tag `@risco` na seção 6.

**RF-09 — Histórico append-only.** Nunca reescrito nem reordenado; devolvido em ordem
cronológica de inserção. `registrar()` grava uma entrada `REGISTRO` (`campo`/`de`/`para`
= `None`). Cada campo efetivamente alterado por `atualizar()` gera **uma entrada
`ALTERACAO` própria** (valores já normalizados em `de`/`para`); se o valor novo, após
normalização, for igual ao atual, nenhuma entrada é gerada para aquele campo;
`atualizar()` com `campos={}` é permitido e não gera entrada. `mesclar()` grava
`MERGE_DESTINO` no histórico do principal e `MERGE_ORIGEM` no do secundário — cada
cadastro mantém seu próprio histórico completo, sem incorporação cruzada. `inativar()`
grava `INATIVACAO` (`campo`/`de`/`para` = `None`).

**RF-10 — Campos atualizáveis.** Apenas `nome`, `email`, `telefone`. Tentar atualizar
`documento`, `tipo`, `situacao` ou chave inexistente → `CAMPO_OBRIGATORIO`. Definir
`nome` como vazio → `CAMPO_OBRIGATORIO`. `documento` é imutável por design: a correção de
um documento incorreto é feita inativando o cadastro (o que libera o documento, RF-05) e
registrando um novo — não existe operação dedicada de troca de titularidade/documento.

**RF-11 — Precedência de referência inválida.** `cadastro_id` desconhecido em **qualquer**
método → `CADASTRO_NAO_ENCONTRADO`; essa verificação sempre precede qualquer checagem de
estado.

**RF-12 — Inativação.** `inativar()` leva `ATIVO` → `INATIVO`, grava `INATIVACAO`. Não é
idempotente: cadastro já `INATIVO` ou `MESCLADO` → `ESTADO_INVALIDO`. Não existe
reativação nesta versão; um `INATIVO` libera seu documento para novo registro, mas nunca
volta a `ATIVO`.

**RF-13 — Restrição de escrita fora de `ATIVO`.** Cadastros `MESCLADO` e `INATIVO`
recusam `atualizar`, `mesclar` e `inativar` com `ESTADO_INVALIDO`, mas continuam
consultáveis normalmente por `obter`, `historico` e `situacao`.

**RF-14 — Precedência de erros em `atualizar()`.** Ordem completa: `CADASTRO_NAO_ENCONTRADO`
(existência) → `ESTADO_INVALIDO` (precisa estar `ATIVO`; regra categórica — vale para a
chamada inteira, independentemente de quais campos foram passados) → `CAMPO_OBRIGATORIO`
(campo não atualizável ou `nome` vazio).

**RF-15 — Situação inicial.** Todo cadastro criado por `registrar()` nasce sempre em
`ATIVO`, sem exceção. Não existe caminho de registro que produza `MESCLADO` ou `INATIVO`
diretamente — esses estados só são alcançados por `mesclar()` (no secundário) e
`inativar()`, respectivamente.

## 4. Requisitos Não Funcionais (RNF)

Nenhum RNF abaixo tem definição disponível no gabarito de decisões — todos entram como
**avanço sob risco** (opção B do SFAR, ver §5 e `registro.md`). Mantidos aqui para
rastreabilidade ISO/IEC 25010, com escopo de teste explicitamente reduzido.

| ID | Categoria ISO 25010 | Requisito | Status |
|---|---|---|---|
| RNF-01 | Eficiência de desempenho | Volumetria/SLA de `buscar_duplicados()` | 🔴 sem definição — nenhuma asserção de tempo/complexidade é exigível |
| RNF-02 | Confiabilidade | Atomicidade/concorrência em `registrar()`/`mesclar()` sob chamadas concorrentes | 🔴 sem definição — testes limitados a execução sequencial |
| RNF-03 | Segurança | Mascaramento/criptografia/controle de acesso a `documento` e `historico()` | 🔴 sem definição — nenhum critério de proteção de dados é exigível |

## 5. Lacunas registradas como avanço sob risco (SFAR, opção B)

| ID | Pergunta que originou a lacuna | Requisito afetado | Escopo de teste reduzido |
|---|---|---|---|
| L1 | Merge entre cadastro `tipo=PF` e `tipo=PJ`: permitido ou recusado, com qual erro? | RF-08.a | Nenhum cenário de merge cross-tipo é afirmado como sucesso ou erro |
| L2 | Há garantia de atomicidade em `registrar()`/`mesclar()` sob concorrência? | RNF-02 | Nenhum teste de corrida (race condition) é exigível |
| L3 | Existe requisito de volumetria/desempenho para `buscar_duplicados()`? | RNF-01 | Nenhuma asserção de tempo de resposta/complexidade é exigível |
| L4 | Há exigência de mascaramento/criptografia/controle de acesso a dados sensíveis (documento, histórico)? | RNF-03 | Nenhum critério de segurança/LGPD é exigível |

## 6. Critérios de aceite (Gherkin)

```gherkin
Funcionalidade: Registro de cadastro

  Cenário: Registrar PF com CPF válido
    Dado que não existe cadastro com o documento "529.982.247-25"
    Quando eu registro um cadastro com tipo "PF", documento "529.982.247-25" e nome " joão da  silva "
    Então o registro é criado com sucesso
    E a situação do novo cadastro é "ATIVO"
    E o campo documento armazenado é "52998224725"
    E o campo nome armazenado é "JOAO DA SILVA"
    E o histórico do cadastro contém uma entrada "REGISTRO" com campo, de e para nulos

  Cenário: Documento com dígito verificador inválido
    Quando eu registro um cadastro com tipo "PF" e documento "111.111.111-12"
    Então a operação levanta ErroCadastro com code "DOCUMENTO_INVALIDO"

  Cenário: Documento com todos os dígitos iguais é rejeitado mesmo passando no módulo 11
    Quando eu registro um cadastro com tipo "PJ" e documento "11111111111111"
    Então a operação levanta ErroCadastro com code "DOCUMENTO_INVALIDO"

  Cenário: Documento com tamanho incompatível com o tipo
    Quando eu registro um cadastro com tipo "PF" e documento com 14 dígitos válidos de CNPJ
    Então a operação levanta ErroCadastro com code "DOCUMENTO_INVALIDO"

  Esquema do Cenário: Campo obrigatório ausente precede validação de documento
    Quando eu registro um cadastro com <campo> vazio e documento inválido
    Então a operação levanta ErroCadastro com code "CAMPO_OBRIGATORIO"
    Exemplos:
      | campo     |
      | documento |
      | nome      |
      | tipo      |

  Cenário: Documento duplicado contra cadastro ATIVO
    Dado um cadastro ATIVO registrado com documento "52998224725"
    Quando eu registro outro cadastro com o mesmo documento "529.982.247-25"
    Então a operação levanta ErroCadastro com code "DUPLICADO"

  Cenário: Documento liberado por cadastro INATIVO permite novo registro
    Dado um cadastro com documento "52998224725" que foi inativado
    Quando eu registro um novo cadastro com o mesmo documento "52998224725"
    Então o registro é criado com sucesso

Funcionalidade: Deduplicação

  Cenário: Score soma pesos dos critérios coincidentes
    Dado um cadastro A com documento "52998224725", email "a@x.com", telefone "11999998888", nome "JOAO SILVA"
    E um cadastro B com o mesmo email "a@x.com" e o mesmo telefone "11999998888", mas documento e nome diferentes
    Quando eu busco duplicados de A
    Então B aparece no resultado com score "0.80" e critérios ["EMAIL", "TELEFONE"]

  Cenário: Candidato abaixo do threshold não aparece no resultado
    Dado um cadastro A e um cadastro B que só coincidem pelo critério NOME (peso 0.20)
    Quando eu busco duplicados de A
    Então B não aparece no resultado de buscar_duplicados

  Cenário: buscar_duplicados exclui cadastros MESCLADO e o próprio cadastro
    Dado um cadastro A ATIVO e um cadastro B MESCLADO com documento igual ao de A
    Quando eu busco duplicados de A
    Então B não aparece no resultado
    E A não aparece no próprio resultado

  Cenário: Consultar duplicados de um cadastro MESCLADO é inválido
    Dado um cadastro C em situação "MESCLADO"
    Quando eu busco duplicados de C
    Então a operação levanta ErroCadastro com code "ESTADO_INVALIDO"

Funcionalidade: Merge de cadastros

  Cenário: Merge bem-sucedido preenche lacunas do principal com dados do secundário
    Dado um cadastro principal ATIVO sem telefone
    E um cadastro secundário ATIVO com telefone preenchido e score de duplicidade >= 0.50 contra o principal
    Quando eu mesclo o secundário no principal
    Então o cadastro sobrevivente é o principal_id
    E o telefone do principal passa a ser o do secundário
    E o secundário fica em situação "MESCLADO" com mesclado_em preenchido
    E o principal continua em situação "ATIVO" com mesclado_em nulo
    E o histórico do principal contém uma entrada "MERGE_DESTINO"
    E o histórico do secundário contém uma entrada "MERGE_ORIGEM"

  Cenário: Campo preenchido nos dois com valores diferentes preserva o do principal sem erro
    Dado um principal ATIVO com email "principal@x.com"
    E um secundário ATIVO com email "secundario@x.com" e score >= 0.50 contra o principal
    Quando eu mesclo o secundário no principal
    Então o email do principal continua "principal@x.com"
    E nenhum erro é levantado

  Cenário: Merge recusado por score insuficiente
    Dado dois cadastros ATIVO com score de duplicidade entre eles < 0.50
    Quando eu tento mesclar um no outro
    Então a operação levanta ErroCadastro com code "CONFLITO_MERGE"

  Cenário: Merge de um cadastro com ele mesmo
    Dado um cadastro X em situação "ATIVO"
    Quando eu tento mesclar X com X (principal_id == secundario_id)
    Então a operação levanta ErroCadastro com code "CONFLITO_MERGE"

  Cenário: Merge recusado quando um dos cadastros não está ATIVO
    Dado um principal ATIVO e um secundário em situação "INATIVO"
    Quando eu tento mesclar
    Então a operação levanta ErroCadastro com code "ESTADO_INVALIDO"

  @risco @L1
  Cenário: Merge entre tipos diferentes — comportamento não especificado
    Dado um cadastro PF e um cadastro PJ ambos ATIVO com score >= 0.50 entre eles
    Quando eu tento mesclar o PJ no PF
    Então o comportamento não é especificado nesta rodada (avanço sob risco L1) — nenhuma asserção de sucesso ou erro deve ser codificada neste cenário

Funcionalidade: Atualização e histórico

  Cenário: Atualizar campo permitido gera uma entrada de histórico por campo
    Dado um cadastro ATIVO com nome "JOAO SILVA" e email "a@x.com"
    Quando eu atualizo nome para "JOAO DA SILVA" e email para "b@x.com"
    Então o cadastro reflete os dois novos valores
    E o histórico contém duas novas entradas "ALTERACAO", uma por campo, com de/para normalizados

  Cenário: Atualizar com valor igual ao atual não gera entrada de histórico
    Dado um cadastro ATIVO com nome "JOAO SILVA"
    Quando eu atualizo nome para "  joao   silva  " (equivalente após normalização)
    Então nenhuma nova entrada de histórico é criada

  Cenário: Atualizar com campos vazio é permitido e não gera entrada
    Dado um cadastro ATIVO
    Quando eu chamo atualizar com campos={}
    Então a operação é bem-sucedida e nenhuma entrada de histórico é criada

  Esquema do Cenário: Campo não atualizável levanta CAMPO_OBRIGATORIO
    Dado um cadastro ATIVO
    Quando eu tento atualizar o campo <campo>
    Então a operação levanta ErroCadastro com code "CAMPO_OBRIGATORIO"
    Exemplos:
      | campo     |
      | documento |
      | tipo      |
      | situacao  |
      | chave_inexistente |

  Cenário: Definir nome vazio levanta CAMPO_OBRIGATORIO
    Dado um cadastro ATIVO
    Quando eu tento atualizar nome para ""
    Então a operação levanta ErroCadastro com code "CAMPO_OBRIGATORIO"

  Cenário: Atualizar cadastro MESCLADO ou INATIVO levanta ESTADO_INVALIDO independentemente do campo
    Dado um cadastro em situação "MESCLADO"
    Quando eu tento atualizar qualquer campo válido ou inválido
    Então a operação levanta ErroCadastro com code "ESTADO_INVALIDO"

Funcionalidade: Inativação e transições de estado

  Cenário: Inativar cadastro ATIVO
    Dado um cadastro ATIVO
    Quando eu inativo o cadastro
    Então a situação passa a "INATIVO"
    E o histórico contém uma entrada "INATIVACAO" com campo, de e para nulos

  Cenário: Inativar não é idempotente
    Dado um cadastro já "INATIVO"
    Quando eu tento inativar novamente
    Então a operação levanta ErroCadastro com code "ESTADO_INVALIDO"

  Cenário: Inativar cadastro MESCLADO
    Dado um cadastro em situação "MESCLADO"
    Quando eu tento inativar
    Então a operação levanta ErroCadastro com code "ESTADO_INVALIDO"

  Cenário: Leitura funciona em qualquer situação
    Dado um cadastro em situação "MESCLADO" ou "INATIVO"
    Quando eu chamo obter, historico e situacao
    Então todas as chamadas retornam normalmente, sem erro

  Cenário: Operação sobre cadastro_id desconhecido precede checagem de estado
    Dado que não existe cadastro com id "id-inexistente"
    Quando eu chamo atualizar, mesclar ou inativar com esse id
    Então a operação levanta ErroCadastro com code "CADASTRO_NAO_ENCONTRADO"
```

## 7. Rastreabilidade

Ver `registro.md` para o histórico completo de perguntas por agente, iterações de
pergunta-resposta e quais respostas vieram do gabarito vs. quais ficaram como avanço sob
risco. Ver `captura.json` para a lista literal das perguntas [BLOQUEANTE] formuladas
pelos três agentes (taxa de captura).
