# UC-07 — Motor de cotação de frete multi-transportadora

## Contexto de negócio

Um e-commerce trabalha com várias transportadoras e precisa cotar o frete de cada pedido
em todas elas para oferecer opções ao cliente. Cada transportadora tem sua própria tabela
de preço por faixa de peso, atende certas regiões, tem limite de peso e cobra seguro sobre
o valor declarado. Algumas faixas de CEP são bloqueadas por transportadora. Pacotes grandes
e leves são cobrados pelo volume, não pelo peso da balança.

## Contrato obrigatório

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão. Valores monetários e
pesos são `decimal.Decimal`; entradas numéricas podem chegar como `str`, `int`, `float` ou
`Decimal`.

```python
class ErroFrete(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class MotorFrete:
    def registrar_transportadora(self, nome: str, config: dict) -> None:
        """`config`: {"faixas": [{"ate_kg": <num>, "preco": <monetário>,
                                  "prazo_dias": int}],
                      "regioes": list[str], "fator_cubagem": int,
                      "peso_maximo_kg": <num>, "ad_valorem": <monetário> | None}"""

    def registrar_restricao(self, transportadora: str, prefixo_cep: str) -> None: ...

    def cotar(self, pedido: dict) -> list[dict]:
        """`pedido`: {"uf_destino": str, "cep_destino": str,
                      "itens": [{"peso_kg": <num>, "altura_cm": <num>,
                                 "largura_cm": <num>, "comprimento_cm": <num>,
                                 "quantidade": int, "valor": <monetário>}]}
        Retorna [{"transportadora": str, "peso_cobrado_kg": Decimal,
                  "frete": Decimal, "seguro": Decimal, "prazo_dias": int,
                  "total": Decimal}]"""

    def melhor_cotacao(self, pedido: dict, criterio: str) -> dict:
        """Retorna um único item, no mesmo formato de `cotar`."""
```

### Vocabulário fechado

`ErroFrete.code` assume **somente**: `REGIAO_NAO_ATENDIDA`, `TRANSPORTADORA_DESCONHECIDA`,
`DIMENSOES_INVALIDAS`, `TABELA_INVALIDA`, `PEDIDO_INVALIDO`, `SEM_COTACAO`.

O `criterio` de `melhor_cotacao` assume **somente**: `PRECO`, `PRAZO`.

> Este enunciado define o vocabulário, não a regra: em que circunstância cada código e
> cada critério se aplica faz parte do que precisa ser decidido.

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
