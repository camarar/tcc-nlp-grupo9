# UC-16 — Especificação técnica consolidada
## Serviço de consulta paginada com escopo por perfil

> Produzida pelo pipeline de três agentes de requisitos (working-backwards-designer →
> working-backwards-analyst → senior-functional-analyst-reviewer), condição C2. As
> respostas às perguntas `[BLOQUEANTE]` foram obtidas do gabarito de decisões e repassadas
> aos agentes; o texto abaixo reflete o que os agentes efetivamente elicitaram e
> consolidaram, não uma cópia do gabarito. Itens sem resposta disponível estão marcados
> como **avanço sob risco** (ver `registro.md`).

---

## 1. Requisitos Funcionais (RF)

### RF-01 — Escopo de escrita fechado
A API de escrita é exclusivamente `inserir(registro)`. Não existem métodos de atualização
(`update`) ou remoção (`remover`) nesta versão — mutação ou exclusão de registros já
inseridos está fora de escopo do contrato.

### RF-02 — Cursor de paginação (keyset)
O cursor é opaco para o consumidor: um JSON com os valores dos campos de `ordenar_por`
efetivo (ver RF-08) do último item da página corrente, codificado em base64 url-safe sobre
UTF-8. Não há assinatura criptográfica (HMAC) nem hash de perfil/filtros embutido — a
integridade é garantida apenas pela decodificação e pela correspondência estrutural com a
chamada atual.

`ErroConsulta("CURSOR_INVALIDO")` é retornado quando:
- o cursor não decodifica como base64 válido;
- o payload decodificado não é um JSON válido;
- a lista de campos presentes na chave do cursor não corresponde ao `ordenar_por` efetivo
  da chamada atual (incluindo o desempate por `id`, RF-08).

### RF-03 — Controle de acesso por perfil
Cada perfil é declarado via `definir_perfil(perfil, campos_visiveis, filtro_fixo)`. Chamar
`consultar` com um `perfil` não declarado previamente retorna
`ErroConsulta("PERFIL_DESCONHECIDO")`. `ordenar_por` e `filtros` só podem referenciar
campos presentes em `campos_visiveis` do perfil ativo — caso contrário,
`ErroConsulta("CAMPO_INVALIDO")` (o mesmo código cobre tanto "campo inexistente na base"
quanto "campo existente mas fora do escopo do perfil", deliberadamente, para não vazar por
inferência qual dos dois casos ocorreu).

### RF-04 — Reautorização por chamada e combinação de filtros
`perfil` é parâmetro obrigatório de toda chamada a `consultar`. `campos_visiveis` e
`filtro_fixo` são recalculados a cada chamada a partir do `perfil` informado na chamada
corrente — nunca herdados ou inferidos do cursor. Quando `filtro_fixo` do perfil e um
filtro do usuário (`params["filtros"]`) incidem sobre o mesmo campo, as duas condições são
combinadas por **E lógico** (interseção): o filtro do usuário nunca substitui nem afrouxa o
`filtro_fixo` do perfil.

### RF-05 — Estabilidade sob inserção concorrente (read-your-scroll)
Registros inseridos entre uma página e outra não deslocam a navegação corrente: nenhum item
já servido é repetido, e nenhum item que existia desde o início da consulta e está à frente
do cursor (segundo a ordenação efetiva) é pulado. Não há retroação — um registro inserido
"atrás" da posição do cursor não aparece na navegação já em curso.

### RF-06 — Precedência de validação/erro
Quando mais de uma condição de erro se aplica à mesma chamada, prevalece a primeira desta
sequência fixa: `PERFIL_DESCONHECIDO` → `PARAMETRO_INVALIDO` → `CAMPO_INVALIDO` →
`FILTRO_INVALIDO` → `CURSOR_INVALIDO`.

### RF-07 — Validação de `tamanho`
`tamanho` padrão é **20** quando omitido. Valores fora do intervalo `[1, 100]` retornam
`ErroConsulta("PARAMETRO_INVALIDO")` — o valor **não** é normalizado/truncado
silenciosamente.

### RF-08 — Ordenação padrão e desempate universal
Quando `ordenar_por` é omitido, aplica-se `[["id", "asc"]]`. Para qualquer `ordenar_por`
informado, o campo `id` com direção `asc` é acrescentado ao final como critério de
desempate — exceto se `id` já constar explicitamente na lista informada, caso em que a
ocorrência existente é usada e o desempate implícito não é duplicado. Isso garante ordem
total determinística tanto na primeira página quanto em páginas subsequentes via cursor.

### RF-09 — Fim da navegação
Na página que contém o último item elegível — inclusive quando a página está exatamente
cheia até o limite de `tamanho` e esgota o conjunto —, a própria chamada retorna
`tem_proxima=False` e `proximo_cursor=None`. Não é necessária uma chamada subsequente que
retorne lista vazia apenas para sinalizar o fim.

### RF-10 — Validação de operadores de filtro
`op` fora do vocabulário fechado → `ErroConsulta("FILTRO_INVALIDO")`. Regras adicionais por
operador:
- `in` exige que `valor` seja do tipo `list` — caso contrário, `FILTRO_INVALIDO`.
- `contains` exige que **tanto** o valor do filtro **quanto** o valor do campo no registro
  sejam `str` — caso contrário, `FILTRO_INVALIDO`. Um registro cujo campo é `None` nunca
  satisfaz `contains`.
- **Avanço sob risco:** o comportamento de `eq`, `ne`, `gt`, `gte`, `lt`, `lte` quando o
  campo do registro é `None` não tem decisão de negócio disponível. Ver `registro.md`.

### RF-11 — Validação de `definir_perfil`
`campos_visiveis` vazia ou `perfil` como string vazia → `ErroConsulta("PARAMETRO_INVALIDO")`.
Redefinir um `perfil` já existente **substitui** `campos_visiveis` e `filtro_fixo`
anteriores de forma idempotente, sem erro.

---

## 2. Requisitos Não Funcionais (RNF)

### RNF-01 — Semântica de `total`
`total` é sempre recalculado no momento da chamada corrente, refletindo a interseção de
`filtro_fixo` do perfil vigente (E lógico) com os filtros do usuário informados naquela
mesma chamada — nunca uma fotografia imutável do início da navegação. O valor é
informativo e pode variar entre páginas se houver inserções concorrentes.

### RNF-02 — Concorrência de acesso à instância (avanço sob risco)
Não há decisão de negócio sobre thread-safety/modelo de concorrência de processo. A
especificação avança sob a suposição mínima de que cada instância de `ServicoConsulta` é
usada em contexto de execução efetivamente sequencial (sem garantia formal de atomicidade
sob chamadas concorrentes de múltiplas threads à mesma instância). Ver `registro.md` para o
registro formal do risco.

---

## 3. Regras de Negócio

- **RN-01 (deriva de RF-04):** O escopo de dados de um perfil (`campos_visiveis` +
  `filtro_fixo`) nunca pode ser contornado pelos parâmetros do usuário — filtros do usuário
  apenas restringem adicionalmente, nunca substituem.
- **RN-02 (deriva de RF-08):** A ordem de resultados é sempre total e determinística;
  `id` é o desempate de última instância, sempre em `asc`, salvo quando já explicitado pelo
  chamador.
- **RN-03 (deriva de RF-06):** A ordem de checagem de erros é fixa e não depende da ordem
  de implementação — deve ser tratada como contrato testável.
- **RN-04 (deriva de RF-05):** A garantia de estabilidade da paginação cobre apenas
  inserções (RF-01 exclui update/remove do contrato); não há promessa de completude
  retroativa para registros inseridos atrás da posição já servida.

---

## 4. Critérios de Aceite (Gherkin)

```gherkin
Funcionalidade: Paginação estável com escopo por perfil

  Cenário: cursor com ordenar_por explícito incluindo id
    Dado ordenar_por = [["status", "asc"], ["id", "desc"]]
    Quando o cliente solicita a próxima página com o cursor da página anterior
    Então a chave do cursor contém exatamente os campos ["status", "id"], nesta ordem
    E o desempate por id usa a direção "desc" informada, não é sobrescrito para "asc"

  Cenário: filtro do usuário no mesmo campo do filtro fixo do perfil
    Dado o perfil "vendedor" com filtro_fixo = {"regiao": {"op": "eq", "valor": "sul"}}
    E o usuário chama consultar() com filtros = {"regiao": {"op": "eq", "valor": "norte"}}
    Então o resultado é a interseção (regiao == "sul" E regiao == "norte")
    E, portanto, o resultado é vazio (não há afrouxamento do escopo do perfil)

  Cenário: perfil desconhecido e cursor inválido na mesma chamada
    Dado perfil = "inexistente" e cursor = "###invalido###"
    Quando consultar() é chamado
    Então ErroConsulta.code == "PERFIL_DESCONHECIDO"
    E não "CURSOR_INVALIDO", por precedência de validação (RF-06)

  Cenário: página exatamente cheia esgota a lista
    Dado 40 itens elegíveis ao perfil e tamanho=20 (duas páginas exatas)
    Quando o cliente consulta a segunda página (itens 21-40)
    Então itens tem 20 elementos, tem_proxima=False e proximo_cursor=None
    E nenhuma terceira chamada é necessária para confirmar o fim

  Cenário: tamanho fora da faixa permitida não é normalizado
    Dado tamanho=500
    Quando consultar() é chamado
    Então ErroConsulta.code == "PARAMETRO_INVALIDO"
    E o serviço não trunca silenciosamente para 100

  Cenário: campo fora do escopo do perfil não pode ser usado em ordenar_por
    Dado o perfil "atendimento" sem "margem" em campos_visiveis
    Quando consultar() é chamado com ordenar_por = [["margem", "asc"]]
    Então ErroConsulta.code == "CAMPO_INVALIDO"

  Cenário: inserção concorrente não desloca a navegação em curso
    Dado uma navegação iniciada com ordenar_por = [["id", "asc"]] e tamanho=10
    E a primeira página já foi entregue (itens 1-10)
    Quando um novo registro é inserido com id maior que o do cursor corrente
    E a segunda página é solicitada com o cursor recebido
    Então nenhum item da primeira página reaparece
    E o novo registro aparece na posição correta relativa à ordenação, sem deslocar os
      itens já elegíveis desde o início da consulta

  Cenário: filtro contains exige valores textuais
    Dado um filtro {"observacao": {"op": "contains", "valor": 123}}
    Quando consultar() é chamado
    Então ErroConsulta.code == "FILTRO_INVALIDO"

  Cenário: definir_perfil rejeita campos_visiveis vazia
    Quando definir_perfil("regional", campos_visiveis=[]) é chamado
    Então ErroConsulta.code == "PARAMETRO_INVALIDO"

  Cenário: redefinição de perfil é idempotente
    Dado o perfil "regional" já definido com campos_visiveis=["id", "regiao"]
    Quando definir_perfil("regional", campos_visiveis=["id", "regiao", "status"]) é chamado
    E consultar() é chamado em seguida com o perfil "regional"
    Então os itens retornados incluem o campo "status"
```

---

## 5. Contrato obrigatório

> Copiado literalmente de `stage4/corpus/UC-16/enunciado.md`.

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão.

```python
class ErroConsulta(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class ServicoConsulta:
    def __init__(self, registros: list[dict]) -> None:
        """Todo registro tem, no mínimo, a chave `id` (int)."""

    def definir_perfil(self, perfil: str, campos_visiveis: list[str],
                       filtro_fixo: dict | None = None) -> None: ...

    def inserir(self, registro: dict) -> None: ...

    def consultar(self, perfil: str, params: dict) -> dict:
        """`params`: {"cursor": str | None, "tamanho": int | None,
                      "ordenar_por": list[list] | None,
                      "filtros": dict | None}
        `ordenar_por` é uma lista de pares `[campo, direcao]`.
        `filtros` mapeia campo -> {"op": str, "valor": Any}.
        Retorna {"itens": list[dict], "proximo_cursor": str | None,
                 "tem_proxima": bool, "total": int}"""
```

### Vocabulário fechado

`ErroConsulta.code` assume **somente**: `CURSOR_INVALIDO`, `CAMPO_INVALIDO`,
`PARAMETRO_INVALIDO`, `PERFIL_DESCONHECIDO`, `FILTRO_INVALIDO`.

A `direcao` assume **somente**: `asc`, `desc`.

O `op` do filtro assume **somente**: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`,
`contains`.

> Este enunciado define o vocabulário, não a regra: como o cursor é construído, o que
> acontece com registros inseridos entre páginas, e em que circunstância cada código se
> aplica faz parte do que precisa ser decidido.
