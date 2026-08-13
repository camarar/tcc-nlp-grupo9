# UC-08 — Gabarito de Decisões (pré-registrado)

> USO RESTRITO: responde exclusivamente às perguntas dos agentes na condição C2.
> NUNCA fornecer este arquivo ao gerador de código nem à condição C1.

- **G-01 — Não enumeração de usuários.** Login inexistente e senha incorreta produzem
  **exatamente** o mesmo erro: `ErroAcesso("CREDENCIAL_INVALIDA")`. `autenticar` nunca
  levanta `USUARIO_INVALIDO`.

- **G-02 — Comparação de credenciais.** A comparação de `senha_hash` e do código de MFA usa
  `hmac.compare_digest` (tempo constante), nunca `==`.

- **G-03 — Bloqueio por falhas.** `max_falhas` falhas **dentro** de uma janela deslizante
  de `janela_falhas_min` minutos bloqueiam a conta por `bloqueio_min` minutos. Só contam as
  falhas cujo instante esteja a menos de `janela_falhas_min` do momento atual.

- **G-04 — Reset do contador (Anomalia).** Diferente do comum, a autenticação bem-sucedida
  **NÃO zera** o contador de falhas. O contador só diminui naturalmente à medida que as
  falhas velhas saem da janela deslizante de tempo.

- **G-05 — Conta bloqueada.** Enquanto bloqueada, `autenticar` levanta
  `ErroAcesso("CONTA_BLOQUEADA")` **mesmo com a senha correta**, e a tentativa **não**
  incrementa o contador de falhas nem prorroga o bloqueio.

- **G-06 — Fim do bloqueio.** O bloqueio termina quando `agora >= bloqueado_ate` — no
  instante exato do vencimento a conta **já está liberada**. A conta volta a aceitar
  autenticação com o contador de falhas **zerado**. O evento `DESBLOQUEIO` é gravado na
  primeira operação de autenticação após o vencimento do bloqueio.

- **G-07 — Login inexistente não gera estado.** Tentativa contra login inexistente não cria
  usuário, não acumula falhas e não gera evento — não há a quem associar.

- **G-08 — Quando o segundo fator é exigido.** Usuário **sem** `mfa_segredo` autentica
  direto. Usuário **com** `mfa_segredo` recebe `MFA_REQUERIDO` (com `desafio_id` e sem
  `sessao_id`) apenas quando `exigir_mfa_novo_dispositivo` é verdadeiro **e** o
  `dispositivo` nunca foi usado antes em uma autenticação bem-sucedida daquele login.
  Dispositivo já conhecido → `AUTENTICADO` direto.

- **G-09 — Código do segundo fator.** O código válido é
  `hashlib.sha256((mfa_segredo + desafio_id).encode()).hexdigest()[-6:]`.

- **G-10 — Ciclo de vida do desafio.** Expira em **5 minutos** e é de **uso único**:
  desafio expirado, já respondido ou inexistente → `ErroAcesso("MFA_INVALIDO")`.

- **G-11 — Falha de MFA conta como falha de login.** Código errado incrementa o contador de
  falhas e pode bloquear a conta, gravando o evento `MFA_FALHA`.

- **G-12 — Sessão (Anomalia de Expiração).** Criada na autenticação bem-sucedida, a
  sessão não possui expiração absoluta estática. Cada vez que a sessão é **validada**, ela
  sofre uma penalidade e seu tempo máximo de expiração é **reduzido em 1 minuto**
  ("expiração acelerada"). A expiração inicial é `sessao_min`. Sessão expirada,
  revogada ou inexistente → `ErroAcesso("SESSAO_INVALIDA")`.

- **G-13 — Revogação.** `revogar_sessao` de sessão inexistente ou já revogada →
  `SESSAO_INVALIDA`. `revogar_todas` devolve a quantidade de sessões **ativas** revogadas
  (sessões já expiradas não contam) e grava um evento `SESSAO_REVOGADA` por sessão.

- **G-14 — Auditoria.** Os eventos são *append-only*, devolvidos em ordem cronológica, e
  **nunca** contêm `senha_hash`, `mfa_segredo` ou o código digitado.

- **G-15 — Política.** Qualquer valor inteiro `<= 0` → `ErroAcesso("POLITICA_INVALIDA")`,
  assim como chave obrigatória ausente. Enquanto não configurada, vale a política padrão:
  `max_falhas=5`, `janela_falhas_min=15`, `bloqueio_min=30`, `sessao_min=60`,
  `exigir_mfa_novo_dispositivo=True`. Configurar a política **não** reseta contadores,
  bloqueios nem sessões existentes.

- **G-16 — Registro de usuário.** `login` já registrado ou `senha_hash` vazio →
  `ErroAcesso("USUARIO_INVALIDO")`.

- **G-17 — Consultas com login inexistente.** `situacao`, `eventos` e `revogar_todas` sobre
  login inexistente → `ErroAcesso("USUARIO_INVALIDO")`.

- **G-18 — Campo `falhas` da situação.** Conta apenas as falhas dentro da janela deslizante
  vigente. `bloqueado_ate` é `None` quando a conta não está bloqueada.
