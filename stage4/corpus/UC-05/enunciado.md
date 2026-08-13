# UC-05 — Motor de split e liquidação de recebíveis

## Contexto de negócio

Um marketplace processa vendas parceladas no cartão e precisa dividir o dinheiro entre os
participantes de cada venda — lojista, plataforma e, às vezes, um afiliado. Cada parcela
vira um recebível com data futura. O lojista pode antecipar seus recebíveis pagando um
deságio, o cliente pode pedir estorno, e todo dia o motor precisa liquidar o que venceu.
O financeiro precisa saber a posição de cada participante em qualquer data.

## Contrato obrigatório

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão. Valores monetários são
`decimal.Decimal`; entradas monetárias podem chegar como `str`, `int`, `float` ou `Decimal`.

```python
class ErroRecebivel(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class MotorRecebiveis:
    def __init__(self, agora: Callable[[], datetime] | None = None) -> None: ...

    def registrar_transacao(self, dados: dict) -> str:
        """`dados`: {"valor": <monetário>, "parcelas": int, "mdr": <monetário>,
                     "data": date,
                     "split": [{"participante": str, "percentual": <monetário>}]}
        Retorna o identificador da transação."""

    def recebiveis(self, transacao_id: str) -> list[dict]:
        """[{"participante": str, "parcela": int, "vencimento": date,
             "valor_bruto": Decimal, "taxa": Decimal, "valor_liquido": Decimal,
             "situacao": str}]"""

    def antecipar(self, transacao_id: str, participante: str,
                  ate_parcela: int, data: date) -> dict:
        """Retorna {"valor_bruto": Decimal, "desagio": Decimal,
                    "valor_liquido": Decimal, "parcelas": list[int]}"""

    def estornar(self, transacao_id: str, valor, data: date) -> dict:
        """Retorna {"estornado": Decimal,
                    "por_participante": dict[str, Decimal]}"""

    def liquidar(self, data: date) -> list[dict]:
        """[{"transacao_id": str, "participante": str, "parcela": int,
             "valor_liquido": Decimal}]"""

    def posicao(self, participante: str, data: date) -> dict:
        """Retorna {"a_receber": Decimal, "antecipado": Decimal,
                    "liquidado": Decimal, "estornado": Decimal}"""
```

### Vocabulário fechado

`ErroRecebivel.code` assume **somente**: `TRANSACAO_INVALIDA`, `SPLIT_INVALIDO`,
`PARCELA_INVALIDA`, `ESTADO_INVALIDO`, `TRANSACAO_NAO_ENCONTRADA`,
`PARTICIPANTE_INVALIDO`, `VALOR_INVALIDO`.

O campo `situacao` do recebível assume **somente**: `A_RECEBER`, `ANTECIPADO`,
`LIQUIDADO`, `ESTORNADO`.

> Este enunciado define o vocabulário, não a regra: em que circunstância cada código e
> cada situação se aplica faz parte do que precisa ser decidido.

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
