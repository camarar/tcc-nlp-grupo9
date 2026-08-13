# UC-08 — Controle de acesso com bloqueio e segundo fator

## Contexto de negócio

Um sistema corporativo precisa do componente que autentica usuários e protege contas
contra tentativa de invasão. Contas sofrem ataque de força bruta e precisam ser bloqueadas
temporariamente. Usuários que ativaram segundo fator precisam confirmá-lo quando entram de
um dispositivo novo. Sessões têm prazo e a segurança precisa poder derrubar todas as
sessões de um usuário. Tudo o que acontece é auditado.

## Contrato obrigatório

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

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
