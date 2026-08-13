# UC-10 — Motor de conciliação de pagamentos

## Contexto de negócio

O financeiro de uma fintech precisa bater as transações registradas internamente com o
extrato que o gateway de pagamento envia. Os dois lados nem sempre fecham: o gateway
duplica linhas, cobra taxas, lança estornos e às vezes credita com alguns dias de atraso.
O time precisa saber exatamente o que conciliou, o que divergiu e por quê, e poder marcar
divergências já tratadas para não reaparecerem.

## Contrato obrigatório

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão. Valores monetários são
`decimal.Decimal`; entradas monetárias podem chegar como `str`, `int`, `float` ou `Decimal`.

```python
class ErroConciliacao(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class MotorConciliacao:
    def carregar_internas(self, registros: list[dict]) -> int:
        """Cada registro: {"transacao_id": str, "valor": <monetário>,
                           "data": date, "status": str}
        Retorna a quantidade carregada."""

    def carregar_extrato(self, registros: list[dict]) -> int:
        """Cada registro: {"transacao_id": str, "valor_bruto": <monetário>,
                           "taxa": <monetário>, "data": date, "tipo": str}
        Retorna a quantidade carregada."""

    def conciliar(self, data_corte: date) -> dict:
        """Retorna {"conciliadas": int, "divergentes": int, "duplicadas": int,
                    "somente_interna": int, "somente_extrato": int,
                    "total_liquido": Decimal}"""

    def itens(self, categoria: str) -> list[dict]:
        """[{"transacao_id": str, "categoria": str, "motivo": str | None,
             "valor_interno": Decimal | None, "valor_extrato": Decimal | None,
             "resolvida": bool}]"""

    def resolver(self, transacao_id: str, ator: str, observacao: str) -> None: ...

    def relatorio(self) -> dict:
        """Retorna {"por_categoria": dict[str, int], "pendentes": int,
                    "resolvidas": int, "total_liquido": Decimal}"""
```

### Vocabulário fechado

`ErroConciliacao.code` assume **somente**: `REGISTRO_INVALIDO`,
`TRANSACAO_NAO_ENCONTRADA`, `ESTADO_INVALIDO`, `CONCILIACAO_NAO_EXECUTADA`,
`CATEGORIA_INVALIDA`.

A `categoria` assume **somente**: `CONCILIADA`, `DIVERGENTE`, `DUPLICADA`,
`SOMENTE_INTERNA`, `SOMENTE_EXTRATO`.

O `status` do registro interno assume **somente**: `APROVADA`, `CANCELADA`, `ESTORNADA`.

O `tipo` do registro de extrato assume **somente**: `VENDA`, `ESTORNO`.

O `motivo` assume **somente**: `VALOR_DIVERGENTE`, `TIPO_DIVERGENTE`, `FORA_DA_JANELA`,
`None`.

> Este enunciado define o vocabulário, não a regra: em que circunstância cada código,
> categoria, status, tipo e motivo se aplica faz parte do que precisa ser decidido.

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
