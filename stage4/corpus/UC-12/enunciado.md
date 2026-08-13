# UC-12 — Serviço de conversão de moedas resiliente

## Contexto de negócio

Uma fintech converte valores entre moedas usando as cotações de um provedor externo que
cobra por chamada e cai com alguma frequência. O serviço não pode ficar indisponível
quando o provedor cai, nem pode martelar um provedor que está fora do ar. Nem todo par de
moedas é cotado diretamente. Moedas diferentes têm número diferente de casas decimais.

## Contrato obrigatório

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão. Valores monetários e
taxas são `decimal.Decimal`.

```python
class ErroCambio(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class ServicoCambio:
    def __init__(self, provedor: Callable[[str], Decimal],
                 relogio: Callable[[], float] | None = None,
                 config: dict | None = None) -> None:
        """`provedor` recebe um par no formato "USD/BRL" e devolve a taxa, ou levanta
        qualquer exceção quando indisponível. `relogio` devolve segundos monotônicos.
        `config`: {"ttl_s": float, "stale_max_s": float,
                   "falhas_para_abrir": int, "tempo_aberto_s": float}"""

    def registrar_moeda(self, codigo: str, casas: int) -> None: ...

    def cotacao(self, de: str, para: str) -> dict:
        """Retorna {"taxa": Decimal, "stale": bool, "idade_s": float}"""

    def converter(self, valor, de: str, para: str) -> dict:
        """Retorna {"valor_convertido": Decimal, "taxa": Decimal,
                    "stale": bool, "idade_s": float}"""

    def estado_circuito(self) -> str: ...

    def estatisticas(self) -> dict:
        """Retorna {"chamadas_provedor": int, "acertos_cache": int,
                    "falhas_consecutivas": int, "usos_stale": int}"""
```

### Vocabulário fechado

`ErroCambio.code` assume **somente**: `MOEDA_NAO_SUPORTADA`, `COTACAO_INDISPONIVEL`,
`PROVEDOR_INDISPONIVEL`, `VALOR_INVALIDO`, `CONFIGURACAO_INVALIDA`.

`estado_circuito()` retorna **somente**: `FECHADO`, `ABERTO`, `MEIO_ABERTO`.

> Este enunciado define o vocabulário, não a regra: em que circunstância cada código e
> cada estado se aplica faz parte do que precisa ser decidido.

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
