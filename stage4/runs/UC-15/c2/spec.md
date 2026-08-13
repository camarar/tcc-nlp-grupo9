# UC-15 — Orquestrador de notificações com reenvio — Especificação técnica consolidada

> Produzida pelo pipeline de três agentes (working-backwards-designer →
> working-backwards-analyst → senior-functional-analyst-reviewer), condição C2.
> Toda regra de negócio aqui presente foi efetivamente elicitada por meio de perguntas
> bloqueantes respondidas pelo orquestrador do pipeline. Nenhum trecho do gabarito foi
> copiado ou parafraseado em bloco — ver `registro.md` para o rastro completo de
> pergunta → resposta.

## Contrato obrigatório

> Copiado literalmente de `stage4/corpus/UC-15/enunciado.md`.

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão.

```python
class ErroNotificacao(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class Orquestrador:
    def __init__(self, relogio: Callable[[], datetime] | None = None,
                 dormir: Callable[[float], None] | None = None) -> None:
        """`relogio` devolve um `datetime` timezone-aware; `dormir` recebe segundos."""

    def registrar_canal(self, nome: str, enviar: Callable[[str, str], None],
                        prioridade: int) -> None:
        """`enviar(destinatario, mensagem)` retorna `None` em sucesso ou levanta
        qualquer exceção em falha."""

    def configurar(self, config: dict) -> None:
        """`config`: {"tentativas": int, "backoff_base_s": float, "fator": float,
                      "silencio_inicio_h": int, "silencio_fim_h": int}"""

    def enviar(self, notificacao: dict) -> dict:
        """`notificacao`: {"destinatario": str, "mensagem": str,
                           "idempotency_key": str, "urgente": bool,
                           "quando": datetime}
        Retorna {"status": str, "canal": str | None, "tentativas": int,
                 "duplicado": bool}"""

    def dead_letters(self) -> list[dict]: ...

    def reprocessar(self, idempotency_key: str) -> dict:
        """Retorna o mesmo dicionário de `enviar`."""

    def historico(self, idempotency_key: str) -> list[dict]:
        """[{"em": datetime, "canal": str, "tentativa": int,
             "resultado": str, "erro": str | None}]"""
```

### Vocabulário fechado

`ErroNotificacao.code` assume **somente**: `CANAL_DESCONHECIDO`, `DESTINATARIO_INVALIDO`,
`MENSAGEM_INVALIDA`, `CONFIGURACAO_INVALIDA`, `NOTIFICACAO_NAO_ENCONTRADA`,
`ESTADO_INVALIDO`.

O `status` assume **somente**: `ENTREGUE`, `ADIADA`, `DEAD_LETTER`.

O `resultado` do histórico assume **somente**: `SUCESSO`, `FALHA`.

### Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.

---

## Requisitos Funcionais

### RF-01 — Registro de canal
`registrar_canal(nome, enviar, prioridade)` registra um canal de envio associado a uma
prioridade numérica.
- `prioridade < 0`, `nome` vazio, ou `enviar` não-chamável → `ErroNotificacao("CONFIGURACAO_INVALIDA")`.
- Reregistrar um `nome` já existente substitui a função e a prioridade anteriormente
  associadas a ele.

### RF-02 — Configuração
`configurar(config)` define a política operacional: `tentativas` (padrão 3),
`backoff_base_s`, `fator`, `silencio_inicio_h`/`silencio_fim_h` (padrão 22/8).
- `tentativas < 1`, `backoff_base_s <= 0`, `fator < 1`, ou hora de silêncio fora de
  `0..23` → `ErroNotificacao("CONFIGURACAO_INVALIDA")`.
- Chaves ausentes em `config` assumem o valor padrão.
- `silencio_inicio_h == silencio_fim_h` desativa a janela de silêncio.

### RF-03 — Validação da notificação
Ordem de verificação em `enviar(notificacao)`: destinatário → mensagem → demais campos
(`idempotency_key`, `quando`) → existência de canal registrado.
- `destinatario` ausente ou vazio → `DESTINATARIO_INVALIDO`.
- `mensagem` ausente, vazia, ou com mais de 500 caracteres → `MENSAGEM_INVALIDA`.
- `idempotency_key` ausente/vazia, ou `quando` ausente/*naive* (sem tzinfo) →
  `CONFIGURACAO_INVALIDA`. Não há sub-ordem definida entre `idempotency_key` e `quando`:
  ambos produzem o mesmo código de erro, portanto a ordem de checagem entre os dois é
  observacionalmente irrelevante.
- Nenhum canal registrado → `CANAL_DESCONHECIDO`.

### RF-04 — Janela de silêncio
Notificação **não urgente** cujo `quando` caia dentro de `[silencio_inicio_h, silencio_fim_h)`
(janela avaliada na hora do próprio `quando`, timezone-aware; a janela cruza a meia-noite
normalmente) → `status="ADIADA"`, `canal=None`, `tentativas=0`, nenhuma chamada de canal é
feita, nenhuma entrada de histórico é gravada.
`urgente=True` ignora a janela de silêncio integralmente, mesmo dentro do horário
configurado.

**Regra de negócio confirmada (não é lacuna de especificação):** `ADIADA` é um estado
**terminal** do ponto de vista da API pública — ver RF-05 e RF-11. Não existe operação de
retomada automática nem manual para uma notificação `ADIADA`.

### RF-05 — Idempotência
`idempotency_key` já processada anteriormente — **em qualquer status**, incluindo
`ADIADA` — devolve o mesmo resultado anterior com `duplicado=True`, sem disparar novo
envio e sem gravar nova entrada de histórico.

Consequência direta: uma notificação não-urgente que caia na janela de silêncio (RF-04)
recebe `ADIADA` e permanece nesse estado para sempre sob a mesma `idempotency_key` — nova
chamada de `enviar()` com a mesma chave sempre devolve o `ADIADA` original com
`duplicado=True`. O único caminho para reenviar é o chamador usar uma **nova**
`idempotency_key` fora da janela de silêncio.

### RF-06 — Retentativas dentro de um canal
Cada canal recebe até `tentativas` tentativas (padrão 3) antes de ser abandonado.
Entre duas tentativas do **mesmo** canal há uma espera via `dormir`: contando as esperas a
partir de `i = 1`, a i-ésima espera (antes da tentativa `i + 1`) dura
`backoff_base_s × fator ** (i - 1)`, sem jitter. Com os padrões (`base=1`, `fator=2`) as
esperas são `1s, 2s, 4s, ...`; com `tentativas=3` ocorrem exatamente 2 esperas (`1s`, `2s`).
`dormir` nunca é chamado antes da primeira tentativa de um canal, nem depois da última
tentativa de um canal, nem entre um canal e o seguinte.

### RF-07 — Fallback entre canais
Os canais são percorridos por **prioridade crescente** (número menor primeiro); empate é
resolvido pelo nome em ordem lexicográfica. Só se passa ao canal seguinte depois de
esgotar **todas** as tentativas do canal anterior (RF-06). Não há espera entre um canal e
o próximo.

### RF-08 — Sucesso encerra o fluxo
A primeira tentativa bem-sucedida (em qualquer canal) encerra o envio: nenhum canal
posterior é tentado. `status="ENTREGUE"`. `tentativas` no retorno é o **total acumulado**
de tentativas de todos os canais percorridos, incluindo a bem-sucedida.

### RF-09 — Dead letter
Esgotados todos os canais registrados sem sucesso → `status="DEAD_LETTER"`, `canal=None`,
`tentativas` é o total acumulado de tentativas de todos os canais esgotados (mesma regra
de contagem de RF-08), e a notificação passa a constar em `dead_letters()`.

### RF-10 — Consulta de dead letters
`dead_letters()` retorna `[{"idempotency_key", "destinatario", "mensagem", "ultimo_erro"}]`,
ordenado por `idempotency_key` crescente. `ultimo_erro` é `str(exceção)` da **última**
tentativa realizada.

### RF-11 — Reprocessamento
`reprocessar(idempotency_key)`:
- Chave desconhecida → `ErroNotificacao("NOTIFICACAO_NAO_ENCONTRADA")` (verificado antes
  do estado).
- Status atual diferente de `DEAD_LETTER` (incluindo `ENTREGUE` e `ADIADA`) →
  `ErroNotificacao("ESTADO_INVALIDO")`.
- Sobre uma notificação em `DEAD_LETTER`: repete o **ciclo completo** de canais e
  tentativas desde o início (não soma às tentativas do episódio anterior — a numeração de
  tentativa dentro de cada canal reinicia em 1 para este novo ciclo). Em caso de sucesso,
  a notificação sai de `dead_letters()`. O histórico deste novo ciclo é **acrescentado**
  ao histórico já existente (não o substitui). Retorna o mesmo formato de `enviar`.

### RF-12 — Histórico
`historico(idempotency_key)` é *append-only*, em ordem cronológica, com **uma entrada por
tentativa** (bem-sucedida ou não): `{"em": datetime, "canal": str, "tentativa": int,
"resultado": "SUCESSO"|"FALHA", "erro": str | None}`. `tentativa` é numerada **dentro
daquele canal**, começando em 1 a cada canal (e reiniciando a cada novo ciclo de
`reprocessar`, ver RF-11). `erro` é `str(exceção)` na falha, `None` no sucesso.
Notificação `ADIADA` não gera entrada de histórico.

### RF-13 — Captura de exceção do canal
Qualquer exceção levantada pelo callable `enviar` de um canal é tratada como falha
**daquela tentativa** — não propaga para fora de `Orquestrador.enviar()` e não interrompe
o processamento — e seu texto (`str(e)`) é capturado no campo `erro` do histórico.

---

## Requisitos Não Funcionais

### RNF-01 — Runtime
Python 3.12, apenas biblioteca padrão, sem dependências externas. Arquivo único
`solucao.py`.

### RNF-02 — Testabilidade / determinismo — **avanço sob risco**
`relogio` e `dormir` são injetáveis via `__init__` para permitir testes determinísticos
(sem relógio real, sem espera real). **Sem resposta registrada** para o comportamento
padrão quando `relogio=None` e/ou `dormir=None` são passados (uso "real", fora de teste).
Registrado como avanço sob risco (opção B do SFAR) — ver `registro.md`. A implementação
deve adotar um default explícito e documentá-lo, mas essa escolha não foi validada por
nenhum dos três agentes do pipeline.

### RNF-03 — Isolamento multitenancy — **avanço sob risco**
Sem resposta registrada sobre isolamento de `idempotency_key` entre múltiplos
times/tenants compartilhando a mesma instância de `Orquestrador`. Assume-se, sob risco,
que cada instância atende um único domínio (sem namespace automático de chave).

### RNF-04 — Persistência de estado — **avanço sob risco**
Sem resposta registrada sobre persistência entre reinícios do processo. O contrato
("apenas biblioteca padrão") é consistente com estado mantido inteiramente em memória do
processo (histórico, dead-letters, contadores de tentativa), sem durabilidade entre
reinícios e sem política de retenção/expurgo definida. Assumido sob risco.

### RNF-05 — Concorrência / thread-safety — **avanço sob risco**
Sem resposta registrada sobre comportamento de `Orquestrador` sob chamadas concorrentes a
`enviar()`/`reprocessar()`. Assume-se, sob risco, uso single-threaded; nenhuma garantia de
atomicidade é firmada para acesso concorrente ao histórico, dead-letters ou contadores
internos.

---

## Regras de negócio (resumo consolidado)

1. Backoff exponencial sem jitter, por canal: `backoff_base_s × fator ** (i - 1)`.
2. `tentativas` é contado por canal (não é dividido/somado entre canais na config).
3. Fallback entre canais segue prioridade crescente, esgotando cada canal antes de
   avançar; sem espera entre canais.
4. Primeira tentativa bem-sucedida encerra o fluxo (`ENTREGUE`); `tentativas` no retorno
   é sempre o acumulado de todos os canais percorridos até esse ponto (ou até o
   esgotamento total, para `DEAD_LETTER`).
5. Janela de silêncio aplica-se somente a notificações não urgentes; cruza meia-noite; é
   avaliada na hora do próprio campo `quando`.
6. `ADIADA` é terminal: sem retomada automática, e `reprocessar()` rejeita qualquer status
   que não seja `DEAD_LETTER`.
7. Idempotência cobre **qualquer** status anterior, incluindo `ADIADA`.
8. `reprocessar()` reinicia o ciclo completo (canais + tentativas) do zero; histórico é
   cumulativo entre ciclos, mas a numeração de tentativa por canal reinicia a cada ciclo.
9. Exceções do canal nunca propagam para fora de `enviar()`/`reprocessar()`; são sempre
   tratadas como falha de tentativa.

---

## Critérios de aceite (Gherkin)

```gherkin
Funcionalidade: Envio com retry e fallback entre canais

  Cenário: Sucesso na primeira tentativa do canal de maior prioridade
    Dado um Orquestrador configurado com tentativas=3, backoff_base_s=1, fator=2
    E um canal "push" registrado com prioridade 1 que sempre tem sucesso
    E um canal "sms" registrado com prioridade 2
    Quando uma notificação não urgente é enviada fora da janela de silêncio
    Então o status retornado é "ENTREGUE"
    E o canal retornado é "push"
    E o total de tentativas retornado é 1
    E o canal "sms" nunca é chamado

  Cenário: Fallback para o próximo canal após esgotar as tentativas do primeiro
    Dado um Orquestrador configurado com tentativas=2, backoff_base_s=1, fator=2
    E um canal "push" registrado com prioridade 1 que sempre falha
    E um canal "sms" registrado com prioridade 2 que sempre tem sucesso
    Quando uma notificação não urgente é enviada fora da janela de silêncio
    Então o canal "push" é chamado exatamente 2 vezes
    E entre as duas chamadas de "push" o `dormir` é chamado uma vez com 1.0 segundo
    E o canal "sms" é chamado e tem sucesso na primeira tentativa
    E o status retornado é "ENTREGUE" com canal "sms"
    E o total de tentativas retornado é 3

  Cenário: Todos os canais esgotados geram dead letter
    Dado um Orquestrador configurado com tentativas=1
    E os únicos canais registrados sempre falham
    Quando uma notificação não urgente é enviada fora da janela de silêncio
    Então o status retornado é "DEAD_LETTER"
    E o canal retornado é nulo
    E a notificação passa a aparecer em dead_letters()

Funcionalidade: Janela de silêncio

  Cenário: Notificação não urgente dentro da janela de silêncio é adiada
    Dado um Orquestrador com silencio_inicio_h=22 e silencio_fim_h=8
    Quando uma notificação não urgente com quando=23:00 é enviada
    Então o status retornado é "ADIADA"
    E o canal retornado é nulo
    E o total de tentativas retornado é 0
    E nenhum canal é chamado
    E historico() para essa chave está vazio

  Cenário: Notificação urgente ignora a janela de silêncio
    Dado um Orquestrador com silencio_inicio_h=22 e silencio_fim_h=8
    E um canal registrado que sempre tem sucesso
    Quando uma notificação urgente com quando=23:00 é enviada
    Então o status retornado é "ENTREGUE"

  Cenário: Notificação ADIADA nunca sai desse estado pela mesma chave
    Dado uma notificação não urgente enviada às 23h que retornou "ADIADA"
    Quando enviar() é chamado novamente com a MESMA idempotency_key às 9h
    Então o status retornado ainda é "ADIADA"
    E duplicado é verdadeiro
    E nenhum canal é chamado

Funcionalidade: Idempotência

  Cenário: Reenvio com a mesma chave após entrega não duplica
    Dado uma notificação enviada com sucesso e idempotency_key "K1"
    Quando enviar() é chamado novamente com idempotency_key "K1"
    Então o resultado retornado é idêntico ao primeiro envio
    E duplicado é verdadeiro
    E nenhum canal é chamado novamente
    E nenhuma nova entrada é adicionada ao historico("K1")

Funcionalidade: Dead letter e reprocessamento

  Cenário: Reprocessar uma notificação em dead letter reinicia o ciclo completo
    Dado uma notificação em DEAD_LETTER com histórico de 2 tentativas no canal "push"
    E o canal "push" agora tem sucesso
    Quando reprocessar(idempotency_key) é chamado
    Então o status retornado é "ENTREGUE"
    E a notificação não aparece mais em dead_letters()
    E historico(idempotency_key) contém as 2 entradas antigas mais uma nova entrada
    E a nova entrada tem "tentativa" igual a 1 para o canal "push"

  Cenário: Reprocessar uma notificação que não está em dead letter é inválido
    Dado uma notificação com status "ENTREGUE"
    Quando reprocessar(idempotency_key) é chamado
    Então é levantada ErroNotificacao com code "ESTADO_INVALIDO"

  Cenário: Reprocessar uma chave desconhecida
    Quando reprocessar("chave-inexistente") é chamado
    Então é levantada ErroNotificacao com code "NOTIFICACAO_NAO_ENCONTRADA"

Funcionalidade: Validação de entrada

  Cenário: Destinatário ausente
    Quando enviar() é chamado com destinatario vazio
    Então é levantada ErroNotificacao com code "DESTINATARIO_INVALIDO"

  Cenário: Mensagem excede o limite de 500 caracteres
    Quando enviar() é chamado com mensagem de 501 caracteres
    Então é levantada ErroNotificacao com code "MENSAGEM_INVALIDA"

  Cenário: Nenhum canal registrado
    Dado um Orquestrador sem nenhum canal registrado
    Quando enviar() é chamado com dados válidos
    Então é levantada ErroNotificacao com code "CANAL_DESCONHECIDO"

  Cenário: Configuração inválida
    Quando configurar() é chamado com tentativas=0
    Então é levantada ErroNotificacao com code "CONFIGURACAO_INVALIDA"
```

---

## Riscos e premissas assumidas (avanço sob risco — opção B do SFAR)

Ver `registro.md` para o detalhamento completo de cada pergunta bloqueante, sua origem
(qual agente formulou) e se foi respondida pelo gabarito ou registrada como avanço sob
risco. Resumo dos itens sem resposta registrada:

- Comportamento padrão de `relogio`/`dormir` quando `None` (RNF-02).
- Isolamento de `idempotency_key` entre tenants/times na mesma instância (RNF-03).
- Persistência de estado entre reinícios do processo (RNF-04).
- Thread-safety sob chamadas concorrentes (RNF-05).
- Cancelamento de notificação pendente (`ADIADA`/`DEAD_LETTER`) antes de reprocessamento —
  não há operação equivalente no contrato; ausência de menção nas respostas de negócio
  tratada como exclusão de escopo não confirmada positivamente.
