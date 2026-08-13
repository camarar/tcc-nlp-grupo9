# UC-15 — Orquestrador de notificações com reenvio

## Contexto de negócio

Uma plataforma avisa seus clientes por vários canais — push, SMS, e-mail. Os canais falham
com frequência e de forma intermitente, então vale a pena tentar de novo antes de desistir,
e vale a pena cair para outro canal quando um deles não responde. Ninguém quer receber SMS
de cobrança às três da manhã, exceto quando o aviso é crítico. O mesmo evento não pode
gerar duas notificações. O que não foi entregue de jeito nenhum precisa ficar registrado
para tratamento manual.

## Contrato obrigatório

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

> Este enunciado define o vocabulário, não a regra: quantas tentativas, com que intervalo,
> em que ordem os canais são usados e em que circunstância cada status se aplica faz parte
> do que precisa ser decidido.

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
