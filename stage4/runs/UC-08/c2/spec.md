# UC-08 — Especificação Técnica Consolidada
## Controle de acesso com bloqueio e segundo fator

> Produzida pelo pipeline de três agentes: `working-backwards-designer` (PR/FAQ) →
> `working-backwards-analyst` (revisão de arquitetura) → `senior-functional-analyst-reviewer`
> (validação de requisitos). Perguntas `[BLOQUEANTE]` foram respondidas exclusivamente com base
> em `stage4/corpus/UC-08/gabarito.md`; o que não constava no gabarito foi registrado como
> **avanço sob risco** (opção B do SFAR) em `registro.md`, nunca inventado.

---

## 1. Contrato obrigatório

> Copiado literalmente de `stage4/corpus/UC-08/enunciado.md`.

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão.

```python
class ErroAcesso(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class ControleAcesso:
    def __init__(self, relogio: Callable[[], datetime] | None = None) -> None:
        """`relogio` devolve um `datetime` timezone-aware em UTC."""

    def configurar_politica(self, politica: dict) -> None:
        """`politica`: {"max_falhas": int, "janela_falhas_min": int,
                        "bloqueio_min": int, "sessao_min": int,
                        "exigir_mfa_novo_dispositivo": bool}"""

    def registrar_usuario(self, login: str, senha_hash: str,
                          mfa_segredo: str | None = None) -> None: ...

    def autenticar(self, login: str, senha_hash: str,
                   ip: str, dispositivo: str) -> dict:
        """Retorna {"status": str, "sessao_id": str | None,
                    "desafio_id": str | None, "expira_em": datetime | None}"""

    def responder_mfa(self, desafio_id: str, codigo: str) -> dict:
        """Retorna o mesmo dicionário de `autenticar`."""

    def validar_sessao(self, sessao_id: str) -> dict:
        """Retorna {"login": str, "expira_em": datetime}"""

    def revogar_sessao(self, sessao_id: str) -> None: ...

    def revogar_todas(self, login: str) -> int:
        """Retorna a quantidade de sessões revogadas."""

    def situacao(self, login: str) -> dict:
        """Retorna {"bloqueado": bool, "falhas": int,
                    "bloqueado_ate": datetime | None, "sessoes_ativas": int}"""

    def eventos(self, login: str) -> list[dict]:
        """[{"em": datetime, "tipo": str, "ip": str | None,
             "dispositivo": str | None}]"""
```

### Vocabulário fechado

`ErroAcesso.code` assume **somente**: `CREDENCIAL_INVALIDA`, `CONTA_BLOQUEADA`,
`SESSAO_INVALIDA`, `MFA_INVALIDO`, `USUARIO_INVALIDO`, `POLITICA_INVALIDA`.

O campo `status` assume **somente**: `AUTENTICADO`, `MFA_REQUERIDO`.

O campo `tipo` do evento assume **somente**: `LOGIN_SUCESSO`, `LOGIN_FALHA`, `BLOQUEIO`,
`DESBLOQUEIO`, `MFA_SUCESSO`, `MFA_FALHA`, `SESSAO_REVOGADA`.

> Este enunciado define o vocabulário, não a regra: em que circunstância cada código,
> status e tipo de evento se aplica faz parte do que precisa ser decidido.

---

## 2. Requisitos Funcionais (RF)

| ID | Requisito | Status |
|---|---|---|
| RF-01 | A comparação de `senha_hash` e do código MFA com o valor esperado usa `hmac.compare_digest` (tempo constante); nunca `==`. | 🟢 Confirmado (gabarito) |
| RF-02 | Login inexistente e senha incorreta produzem exatamente o mesmo erro `ErroAcesso("CREDENCIAL_INVALIDA")` em `autenticar`. `autenticar` **nunca** levanta `USUARIO_INVALIDO` (anti-enumeração de contas). | 🟢 Confirmado (gabarito) |
| RF-03 | Tentativa de `autenticar` contra `login` inexistente **não cria** usuário, **não acumula** falhas e **não gera evento**. | 🟢 Confirmado (gabarito) |
| RF-04 | `max_falhas` falhas de senha/MFA dentro de uma janela deslizante de `janela_falhas_min` minutos bloqueiam a conta por `bloqueio_min` minutos. Contam apenas as falhas cujo instante esteja **a menos de** `janela_falhas_min` minutos do momento atual (limite exclusivo: falha com idade exatamente igual a `janela_falhas_min` já não conta). | 🟢 Confirmado (gabarito) |
| RF-05 | Autenticação bem-sucedida (senha, ou senha+MFA quando exigido) zera o contador de falhas do login. | 🟢 Confirmado (gabarito) |
| RF-06 | Enquanto bloqueada, `autenticar` levanta `ErroAcesso("CONTA_BLOQUEADA")` mesmo com senha correta. A tentativa **não** incrementa o contador de falhas, **não** prorroga o bloqueio, e **não gera evento algum** de auditoria (nem `LOGIN_FALHA`). | 🟢 Confirmado (gabarito) |
| RF-07 | O bloqueio termina quando `agora >= bloqueado_ate` — no instante exato do vencimento a conta já está liberada, com o contador de falhas zerado. O evento `DESBLOQUEIO` é gravado na primeira operação de **autenticação** (`autenticar`) após o vencimento — não em consultas puras (`situacao`, `eventos`). | 🟢 Confirmado (gabarito) |
| RF-08 | `status="MFA_REQUERIDO"` (com `desafio_id` novo e `sessao_id=None`) é retornado quando, após senha correta e conta não bloqueada: o usuário possui `mfa_segredo` configurado, `exigir_mfa_novo_dispositivo=True` na política, **e** o `dispositivo` informado nunca teve um `LOGIN_SUCESSO` registrado anteriormente para aquele `login`. Caso contrário, `status="AUTENTICADO"` direto. | 🟢 Confirmado (gabarito) |
| RF-09 | Código de MFA válido: `hashlib.sha256((mfa_segredo + desafio_id).encode()).hexdigest()[-6:]`. | 🟢 Confirmado (gabarito) |
| RF-10 | O `desafio_id` expira em 5 minutos e é de uso único. Desafio expirado, já respondido, ou inexistente → `ErroAcesso("MFA_INVALIDO")`. | 🟢 Confirmado (gabarito) |
| RF-11 | Resposta de MFA com código incorreto incrementa o **mesmo** contador de falhas de `RF-04` (pode bloquear a conta) e grava evento `MFA_FALHA`. | 🟢 Confirmado (gabarito) |
| RF-12 | Sessão é criada na autenticação bem-sucedida (após MFA, quando exigido), com expiração **absoluta** de `sessao_min` minutos a partir da criação. `validar_sessao` não estende o prazo. Sessão expirada, revogada ou inexistente → `ErroAcesso("SESSAO_INVALIDA")`; sessão expirada é descartada. | 🟢 Confirmado (gabarito) |
| RF-13 | `revogar_sessao` sobre sessão inexistente ou já revogada → `ErroAcesso("SESSAO_INVALIDA")`. `revogar_todas` devolve a quantidade de sessões **ativas** revogadas (sessões já expiradas não contam) e grava um evento `SESSAO_REVOGADA` por sessão revogada. | 🟢 Confirmado (gabarito) |
| RF-14 | Eventos são *append-only*, devolvidos em ordem cronológica, e nunca contêm `senha_hash`, `mfa_segredo` ou o código de MFA digitado. | 🟢 Confirmado (gabarito) |
| RF-15 | `configurar_politica`: qualquer valor inteiro `<= 0`, ou chave obrigatória ausente, → `ErroAcesso("POLITICA_INVALIDA")`. Enquanto não configurada, vale a política padrão: `max_falhas=5`, `janela_falhas_min=15`, `bloqueio_min=30`, `sessao_min=60`, `exigir_mfa_novo_dispositivo=True`. Reconfigurar a política **não** reseta contadores, bloqueios nem sessões existentes. | 🟢 Confirmado (gabarito) |
| RF-16 | `registrar_usuario`: `login` já registrado, ou `senha_hash` vazio, → `ErroAcesso("USUARIO_INVALIDO")`. | 🟢 Confirmado (gabarito) |
| RF-17 | `situacao`, `eventos` e `revogar_todas` sobre `login` inexistente → `ErroAcesso("USUARIO_INVALIDO")` (diferente de `autenticar`, que nunca revela existência — assimetria intencional: `autenticar` protege contra enumeração por um chamador anônimo; estas três operações são de natureza administrativa e revelam existência do login). | 🟢 Confirmado (gabarito) |
| RF-18 | Campo `falhas` de `situacao()` conta apenas as falhas dentro da janela deslizante vigente (mesma regra de RF-04). `bloqueado_ate` é `None` quando a conta não está bloqueada. | 🟢 Confirmado (gabarito) |
| RF-19 | A exceção lançada na chamada que **atinge** `max_falhas` (a falha que dispara o bloqueio) é `ErroAcesso("CREDENCIAL_INVALIDA")` referente à própria falha; o evento `BLOQUEIO` é gravado na mesma operação, em adição ao `LOGIN_FALHA`/`MFA_FALHA` dessa tentativa. Chamadas **subsequentes** já recebem `CONTA_BLOQUEADA` (RF-06). | 🟡 Avanço sob risco — sem confirmação no gabarito |
| RF-20 | Uma nova chamada a `autenticar` que dispara novo desafio MFA para o mesmo `login` invalida qualquer desafio anterior ainda pendente daquele login (não coexistem desafios simultâneos válidos). | 🟡 Avanço sob risco — sem confirmação no gabarito |
| RF-21 | `dispositivo` vazio ou não informado é tratado como "sempre novo" (nunca reconhecido) para fins da regra RF-08. | 🟡 Avanço sob risco — sem confirmação no gabarito |
| RF-22 | Desafio MFA que expira sem que `responder_mfa` seja chamado nenhuma vez não gera evento nem incrementa o contador de falhas (comportamento silencioso; consequência só existe quando há uma tentativa efetiva de resposta). | 🟡 Avanço sob risco — sem confirmação no gabarito |
| RF-23 | Não há política de expurgo/retenção de `eventos()`: o histórico cresce sem limite durante a vida da instância. `mfa_segredo=""` (string vazia) é tratado como equivalente a `None` (usuário sem MFA configurado), não como erro. | 🟡 Avanço sob risco — sem confirmação no gabarito |

---

## 3. Regras de Negócio (consolidação narrativa)

- **RN-01 (Anti-enumeração em `autenticar`):** ver RF-02, RF-03.
- **RN-02 (Força bruta — senha e MFA no mesmo contador):** ver RF-04, RF-11. Falhas de senha e
  falhas de MFA compartilham o mesmo contador e a mesma janela deslizante — não há limite
  dedicado ao segundo fator.
- **RN-03 (Bloqueio é absoluto, não estende):** ver RF-06. Uma tentativa contra conta já
  bloqueada é totalmente transparente à contagem — nem estende o bloqueio, nem é auditada.
- **RN-04 (Desbloqueio é preguiçoso, mas a auditoria não):** ver RF-07. O estado "desbloqueado"
  é válido a partir do instante exato do vencimento (mesmo sem nenhuma chamada), mas o evento
  `DESBLOQUEIO` só é persistido quando uma operação de autenticação "observa" essa transição.
- **RN-05 (MFA condicional a dispositivo, não a todo login):** ver RF-08. MFA só é exigido de
  quem tem `mfa_segredo` configurado, e apenas para dispositivos nunca vistos antes.
- **RN-06 (Sessão de expiração absoluta):** ver RF-12. Não há renovação implícita por uso.
- **RN-07 (Revogação em massa é seletiva):** ver RF-13. Apenas sessões ativas contam para o
  retorno de `revogar_todas`.
- **RN-08 (Auditoria nunca vaza segredo):** ver RF-14.
- **RN-09 (Política tem default seguro e é imutável retroativamente):** ver RF-15.

---

## 4. Requisitos Não Funcionais (RNF)

| ID | Requisito | Status |
|---|---|---|
| RNF-01 | O componente mantém estado mutável (usuários, sessões, contadores, eventos) inteiramente em memória, sem persistência externa — coerente com o contrato "arquivo único, stdlib apenas". Reinício do processo hospedeiro perde todo o estado (bloqueios, sessões, contadores), o que é aceito como modo de falha seguro (não autentica indevidamente), porém destrutivo. | 🟢 Derivado do contrato (stdlib only, sem menção a storage) |
| RNF-02 | `mfa_segredo` e `senha_hash` nunca aparecem em nenhuma representação pública da API: nem em `str(ErroAcesso)`/mensagens de exceção, nem em nenhum campo de retorno de método público, nem em `eventos()` (estende RF-14 a toda a superfície pública). | 🟢 Derivado do RF-14 confirmado + boas práticas de segurança já implícitas no gabarito (comparação em tempo constante, hashing) |
| RNF-03 | Thread-safety / concorrência dentro do mesmo processo **não é garantida** pelo contrato: não há menção a locks ou uso concorrente no enunciado. O componente deve ser tratado pelo chamador como não thread-safe — uma instância por worker/processo, ou serialização externa do acesso. | 🟡 Avanço sob risco — sem definição no gabarito nem no contrato; ausência de garantia documentada como restrição de uso, não implementada como lock |
| RNF-04 | `eventos(login)` é O(n) no número de eventos do login, sem paginação no contrato — aceitável para o escopo dado (auditoria pontual por login), mas o histórico cresce sem limite durante a vida da instância. | 🟡 Avanço sob risco — retenção/expurgo não definidos no gabarito |
| RNF-05 | O parâmetro `relogio` injetado deve devolver sempre um `datetime` timezone-aware em UTC (conforme contrato); o componente confia no relógio do host/injetado sem tratar retrocesso de horário (ex.: ajuste de NTP) como caso especial. | 🟡 Avanço sob risco — não tratado no gabarito nem no enunciado |

---

## 5. Critérios de Aceite (Gherkin)

```gherkin
Feature: Autenticação com bloqueio por força bruta e segundo fator

  Background:
    Given uma instância de ControleAcesso com relógio controlável
    And a política padrão está em vigor (max_falhas=5, janela_falhas_min=15, bloqueio_min=30, sessao_min=60, exigir_mfa_novo_dispositivo=True)

  # RF-02, RF-03 — anti-enumeração
  Scenario: Login inexistente produz o mesmo erro que senha incorreta
    When autentico com login "fantasma", senha_hash qualquer, ip e dispositivo quaisquer
    Then é levantado ErroAcesso com code "CREDENCIAL_INVALIDA"
    And nenhum evento é registrado para "fantasma"
    And situacao("fantasma") levanta ErroAcesso com code "USUARIO_INVALIDO"

  # RF-04, RF-19 — bloqueio por falhas dentro da janela
  Scenario: Conta é bloqueada ao atingir max_falhas falhas dentro da janela
    Given o usuário "ana" está registrado com senha_hash "correta"
    When autentico "ana" com senha errada 5 vezes em sequência, todas dentro de 15 minutos
    Then a 5ª tentativa levanta ErroAcesso com code "CREDENCIAL_INVALIDA"
    And um evento "BLOQUEIO" é gravado nessa 5ª tentativa
    And situacao("ana") retorna bloqueado=True e bloqueado_ate no futuro

  # RF-06 — tentativa durante bloqueio não conta nem audita
  Scenario: Tentativa contra conta bloqueada não altera estado nem gera evento
    Given o usuário "ana" está bloqueado até daqui a 10 minutos
    When autentico "ana" com a senha CORRETA
    Then é levantado ErroAcesso com code "CONTA_BLOQUEADA"
    And o contador de falhas de "ana" permanece inalterado
    And bloqueado_ate de "ana" permanece o mesmo
    And nenhum evento novo é registrado para essa tentativa

  # RF-07 — desbloqueio automático e evento tardio
  Scenario: Conta é liberada automaticamente no vencimento do bloqueio
    Given o usuário "ana" está bloqueado até T
    And o relógio avança para exatamente T
    When autentico "ana" com a senha correta
    Then a autenticação é bem-sucedida (status "AUTENTICADO")
    And um evento "DESBLOQUEIO" é gravado nessa chamada
    And situacao("ana") retorna falhas=0

  # RF-08 — MFA exigido para dispositivo novo
  Scenario: Usuário com MFA configurado recebe desafio em dispositivo novo
    Given o usuário "bruno" está registrado com mfa_segredo "segredo123"
    And "bruno" nunca autenticou com sucesso do dispositivo "notebook-novo"
    When autentico "bruno" com senha correta a partir do dispositivo "notebook-novo"
    Then a resposta tem status "MFA_REQUERIDO"
    And a resposta tem desafio_id preenchido e sessao_id nulo

  Scenario: Usuário com MFA configurado autentica direto em dispositivo já conhecido
    Given o usuário "bruno" já teve um LOGIN_SUCESSO a partir do dispositivo "notebook-antigo"
    When autentico "bruno" com senha correta a partir do dispositivo "notebook-antigo"
    Then a resposta tem status "AUTENTICADO"
    And a resposta tem sessao_id preenchido

  Scenario: Usuário sem MFA configurado autentica direto mesmo em dispositivo novo
    Given o usuário "carla" está registrada sem mfa_segredo
    When autentico "carla" com senha correta a partir de um dispositivo nunca usado
    Then a resposta tem status "AUTENTICADO"

  # RF-09, RF-10, RF-11 — resposta ao desafio MFA
  Scenario: Código de MFA correto conclui a autenticação
    Given "bruno" recebeu um desafio_id "d1" para mfa_segredo "segredo123"
    When respondo o MFA com o código hashlib.sha256(("segredo123"+"d1").encode()).hexdigest()[-6:]
    Then a resposta tem status "AUTENTICADO" e sessao_id preenchido
    And um evento "MFA_SUCESSO" é gravado

  Scenario: Código de MFA incorreto conta como falha de login
    Given "bruno" recebeu um desafio_id "d1"
    When respondo o MFA com um código incorreto
    Then é levantado ErroAcesso com code "MFA_INVALIDO"
    And um evento "MFA_FALHA" é gravado
    And o contador de falhas de "bruno" é incrementado

  Scenario: Desafio MFA expirado é rejeitado
    Given "bruno" recebeu um desafio_id "d1" há mais de 5 minutos
    When respondo o MFA com o código correto para "d1"
    Then é levantado ErroAcesso com code "MFA_INVALIDO"

  Scenario: Desafio MFA já respondido não pode ser reutilizado
    Given "bruno" já respondeu com sucesso ao desafio_id "d1"
    When respondo o MFA novamente para "d1" com o mesmo código correto
    Then é levantado ErroAcesso com code "MFA_INVALIDO"

  # RF-12 — sessão
  Scenario: Sessão válida é aceita por validar_sessao
    Given "carla" autenticou com sucesso e recebeu sessao_id "s1" com expira_em em 60 minutos
    When valido a sessão "s1"
    Then é retornado login "carla" e o mesmo expira_em original

  Scenario: Sessão expirada é rejeitada e descartada
    Given "carla" autenticou com sucesso e recebeu sessao_id "s1" com expira_em em 60 minutos
    And o relógio avança 61 minutos
    When valido a sessão "s1"
    Then é levantado ErroAcesso com code "SESSAO_INVALIDA"
    And uma nova chamada a validar_sessao("s1") também levanta "SESSAO_INVALIDA"

  # RF-13 — revogação
  Scenario: Revogar sessão específica
    Given "carla" tem uma sessão ativa "s1"
    When revogo a sessão "s1"
    Then um evento "SESSAO_REVOGADA" é gravado
    And validar_sessao("s1") levanta ErroAcesso com code "SESSAO_INVALIDA"

  Scenario: Revogar todas as sessões conta apenas as ativas
    Given "carla" tem 2 sessões ativas e 1 sessão já expirada
    When revogo todas as sessões de "carla"
    Then o retorno é 2
    And 2 eventos "SESSAO_REVOGADA" são gravados

  # RF-15 — política
  Scenario Outline: Política inválida é rejeitada
    When configuro a política com <campo> igual a 0
    Then é levantado ErroAcesso com code "POLITICA_INVALIDA"

    Examples:
      | campo               |
      | max_falhas           |
      | janela_falhas_min    |
      | bloqueio_min         |
      | sessao_min           |

  # RF-16 — registro
  Scenario: Registrar usuário já existente falha
    Given o usuário "ana" já está registrado
    When registro novamente o login "ana"
    Then é levantado ErroAcesso com code "USUARIO_INVALIDO"

  # RF-14 — auditoria não vaza segredo
  Scenario: Eventos nunca expõem segredos
    Given "bruno" tentou autenticar com senha errada e depois respondeu MFA incorretamente
    When consulto eventos("bruno")
    Then nenhum evento contém o valor de senha_hash, mfa_segredo ou o código MFA digitado
    And os eventos estão em ordem cronológica
```

---

## 6. Fora de escopo confirmado

- Persistência/storage externo (não há contrato de storage; estado é em memória).
- Multi-tenant (isolamento é por `login`, sem conceito de organização/tenant).
- Rotação de senha ou de `mfa_segredo` para usuário já registrado (sem método dedicado no contrato).
- Agregação/observabilidade global entre logins (apenas `eventos(login)` por usuário).
- Paginação de `eventos()`.
- Remoção/desativação de `login` já registrado (contas são permanentes pela vida da instância).
