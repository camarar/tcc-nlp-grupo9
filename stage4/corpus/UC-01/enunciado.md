# UC-01 — Motor de amortização de empréstimo

## Contexto de negócio

Uma fintech de crédito pessoal precisa do motor que controla seus empréstimos. O motor
deve criar contratos, gerar o cronograma de parcelas, receber pagamentos — inclusive
atrasados e parciais —, permitir que o cliente quite o contrato antes do prazo e
renegociar contratos inadimplentes. O saldo devedor precisa poder ser consultado em
qualquer data.

## Contrato obrigatório

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão. Valores monetários
trafegam como `decimal.Decimal`. Entradas monetárias e de taxa podem chegar como `str`,
`int`, `float` ou `Decimal`.

```python
class ErroEmprestimo(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class MotorEmprestimo:
    def __init__(self, agora: Callable[[], datetime] | None = None) -> None:
        """`agora` é um relógio injetável; quando ausente, usar o relógio do sistema."""

    def criar_contrato(self, dados: dict) -> str:
        """`dados` tem as chaves: principal, taxa, prazo_meses, sistema,
        carencia_meses (opcional) e data_inicio (datetime.date).
        Retorna o identificador do contrato."""

    def cronograma(self, contrato_id: str) -> list[dict]:
        """Cada item tem exatamente as chaves:
        {"numero": int, "vencimento": date, "juros": Decimal,
         "amortizacao": Decimal, "valor": Decimal, "saldo_apos": Decimal}"""

    def valor_devido(self, contrato_id: str, numero_parcela: int, data: date) -> dict:
        """Retorna {"principal": Decimal, "juros": Decimal,
                    "encargos": Decimal, "total": Decimal}"""

    def registrar_pagamento(self, contrato_id: str, pagamento_id: str,
                            numero_parcela: int, valor, data: date) -> dict:
        """Retorna {"duplicado": bool, "aplicado_encargos": Decimal,
                    "aplicado_juros": Decimal, "aplicado_principal": Decimal,
                    "parcela_quitada": bool}"""

    def saldo_devedor(self, contrato_id: str, data: date) -> Decimal: ...

    def quitar_antecipado(self, contrato_id: str, data: date) -> dict:
        """Retorna {"valor_quitacao": Decimal, "desconto_juros_futuros": Decimal}"""

    def renegociar(self, contrato_id: str, novo_prazo_meses: int,
                   nova_taxa, data: date) -> str:
        """Retorna o identificador do novo contrato."""

    def situacao(self, contrato_id: str, data: date) -> str: ...
```

### Vocabulário fechado

`ErroEmprestimo.code` assume **somente** um destes valores:

`CONTRATO_INVALIDO`, `CONTRATO_NAO_ENCONTRADO`, `ESTADO_INVALIDO`, `VALOR_INVALIDO`,
`PARCELA_INVALIDA`, `RENEGOCIACAO_NAO_PERMITIDA`.

`situacao()` retorna **somente** um destes valores:

`ATIVO`, `EM_ATRASO`, `QUITADO`, `RENEGOCIADO`.

O campo `sistema` de `dados` assume **somente** um destes valores: `PRICE`, `SAC`.

> Este enunciado define o vocabulário, não a regra: em que circunstância cada código de
> erro, cada situação e cada sistema de amortização se aplica faz parte do que precisa
> ser decidido.

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
