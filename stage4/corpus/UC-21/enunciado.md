# UC-21 — Orquestrador de estornos e chargebacks

## Contexto de negócio

Uma plataforma de pagamentos precisa controlar o ciclo de vida de cobranças já
autorizadas. O componente deve capturar valores, realizar estornos totais ou parciais,
registrar chargebacks, proteger requisições repetidas e fornecer saldo e histórico
auditável. Operações incompatíveis não podem corromper os totais financeiros.

## Contrato obrigatório

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão. Valores monetários
trafegam como `decimal.Decimal`. Entradas monetárias podem chegar como `str`, `int`,
`float` ou `Decimal`. Datas e instantes usam `datetime` timezone-aware.

```python
class ErroPagamento(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class OrquestradorPagamentos:
    def __init__(self, agora: Callable[[], datetime] | None = None) -> None:
        """`agora` é um relógio injetável; quando ausente, usar o relógio do sistema."""

    def registrar(self, pagamento_id: str, valor, moeda: str,
                  criado_em: datetime) -> dict:
        """Retorna {"pagamento_id": str, "estado": str, "valor": Decimal}."""

    def capturar(self, pagamento_id: str, operacao_id: str, valor=None) -> dict:
        """Retorna {"duplicado": bool, "capturado": Decimal,
                    "saldo_disponivel": Decimal, "estado": str}."""

    def estornar(self, pagamento_id: str, operacao_id: str, valor,
                 motivo: str = "") -> dict:
        """Retorna {"duplicado": bool, "estornado": Decimal,
                    "saldo_disponivel": Decimal, "estado": str}."""

    def registrar_chargeback(self, pagamento_id: str, operacao_id: str,
                             valor, ocorrido_em: datetime) -> dict:
        """Retorna {"duplicado": bool, "chargeback": Decimal,
                    "saldo_disponivel": Decimal, "estado": str}."""

    def consultar(self, pagamento_id: str) -> dict:
        """Retorna exatamente {"pagamento_id": str, "moeda": str,
        "valor_autorizado": Decimal, "valor_capturado": Decimal,
        "valor_estornado": Decimal, "valor_chargeback": Decimal,
        "saldo_disponivel": Decimal, "estado": str}."""

    def historico(self, pagamento_id: str) -> list[dict]:
        """Cada item tem exatamente {"sequencia": int, "tipo": str,
        "operacao_id": str | None, "valor": Decimal, "instante": datetime}."""
```

### Vocabulário fechado

`ErroPagamento.code` assume **somente** um destes valores:

`PAGAMENTO_INVALIDO`, `PAGAMENTO_NAO_ENCONTRADO`, `ESTADO_INVALIDO`,
`VALOR_INVALIDO`, `MOEDA_INVALIDA`, `IDEMPOTENCIA_CONFLITANTE`,
`DATA_INVALIDA`.

O campo `estado` assume **somente** um destes valores:

`AUTORIZADO`, `CAPTURADO_PARCIAL`, `CAPTURADO`, `ESTORNADO_PARCIAL`,
`ESTORNADO`, `CHARGEBACK_PARCIAL`, `CHARGEBACK`.

O campo `tipo` do histórico assume **somente**: `REGISTRO`, `CAPTURA`, `ESTORNO`,
`CHARGEBACK`.

> Este enunciado define o vocabulário, não as regras de transição, arredondamento,
> idempotência, precedência, limites ou composição dos saldos. Essas decisões fazem
> parte do que precisa ser esclarecido.

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.

