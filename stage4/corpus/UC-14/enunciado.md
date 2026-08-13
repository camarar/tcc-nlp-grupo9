# UC-14 — Motor de cálculo tributário por UF e NCM

## Contexto de negócio

Uma distribuidora emite notas para todo o país e precisa calcular o imposto de cada item.
A alíquota depende do estado de destino e da classificação fiscal do produto (NCM). A
tabela de alíquotas é mantida pelo time fiscal e **está incompleta** — nem todo par
UF/NCM está cadastrado. Alguns produtos são isentos, alguns têm substituição tributária, e
empresas no Simples calculam diferente. O fiscal precisa auditar como cada número saiu.

## Contrato obrigatório

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão. Valores monetários e
alíquotas são `decimal.Decimal`; entradas numéricas podem chegar como `str`, `int`,
`float` ou `Decimal`.

```python
class ErroTributario(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class MotorTributario:
    def registrar_aliquota(self, uf: str, ncm: str, aliquota,
                           mva=None) -> None: ...

    def registrar_isencao(self, uf: str, ncm: str) -> None: ...

    def registrar_regime(self, cnpj: str, regime: str) -> None: ...

    def calcular(self, nota: dict) -> dict:
        """`nota`: {"cnpj_emitente": str, "uf_destino": str, "frete": <monetário>,
                    "itens": [{"ncm": str, "valor": <monetário>,
                               "quantidade": int, "desconto": <monetário>}]}
        Retorna {"base_calculo": Decimal, "icms": Decimal, "icms_st": Decimal,
                 "total_tributos": Decimal, "total_nota": Decimal}"""

    def memoria_calculo(self, nota: dict) -> list[dict]:
        """[{"ncm": str, "ncm_aplicado": str | None, "aliquota": Decimal | None,
             "base": Decimal, "icms": Decimal, "icms_st": Decimal,
             "isento": bool}]"""
```

### Vocabulário fechado

`ErroTributario.code` assume **somente**: `ALIQUOTA_NAO_CADASTRADA`, `TABELA_INVALIDA`,
`NOTA_INVALIDA`, `ITEM_INVALIDO`, `REGIME_DESCONHECIDO`.

O `regime` assume **somente**: `SIMPLES`, `NORMAL`.

> Este enunciado define o vocabulário, não a regra: o que fazer quando o par UF/NCM não
> está na tabela, o que entra na base de cálculo e como cada regime altera o resultado faz
> parte do que precisa ser decidido.

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
