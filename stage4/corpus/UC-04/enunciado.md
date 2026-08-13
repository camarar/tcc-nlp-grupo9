# UC-04 — Limitador de requisições multi-plano

## Contexto de negócio

Uma plataforma de API cobra por plano de assinatura e precisa proteger a infraestrutura.
Cada cliente pertence a um plano, e clientes podem pertencer a uma organização que também
tem um limite próprio, compartilhado entre seus clientes. Requisições diferentes custam
capacidades diferentes. Quando o cliente é barrado, ele precisa saber quanto esperar. O
componente roda em servidor multi-thread.

## Contrato obrigatório

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão.

```python
class ErroLimite(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class Limitador:
    def __init__(self, relogio: Callable[[], float] | None = None) -> None:
        """`relogio` devolve segundos monotônicos como float; quando ausente,
        usar o relógio do sistema."""

    def registrar_plano(self, nome: str, config: dict) -> None:
        """`config`: {"limite": int, "janela_s": float, "burst": int}"""

    def registrar_cliente(self, client_id: str, plano: str,
                          organizacao: str | None = None) -> None: ...

    def registrar_organizacao(self, org_id: str, config: dict) -> None:
        """`config`: {"limite": int, "janela_s": float}"""

    def permitir(self, client_id: str, custo: int = 1) -> dict:
        """Retorna {"permitido": bool, "restante": int, "retry_after": float,
                    "limitante": str | None}"""

    def consumo(self, client_id: str) -> dict:
        """Retorna {"cliente": int, "organizacao": int | None}"""

    def redefinir(self, client_id: str) -> None: ...
```

### Vocabulário fechado

`ErroLimite.code` assume **somente**: `PLANO_DESCONHECIDO`, `CLIENTE_DESCONHECIDO`,
`ORGANIZACAO_DESCONHECIDA`, `CONFIGURACAO_INVALIDA`, `CUSTO_INVALIDO`.

O campo `limitante` assume **somente**: `CLIENTE`, `ORGANIZACAO`, `None`.

> Este enunciado define o vocabulário, não a regra: em que circunstância cada código e
> cada limitante se aplica faz parte do que precisa ser decidido.

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
