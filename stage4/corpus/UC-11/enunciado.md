# UC-11 — Pipeline de anonimização para uso analítico (LGPD)

## Contexto de negócio

A área de dados precisa liberar a base de clientes para relatórios e para o time de
ciência de dados sem expor dados pessoais. Cada finalidade de uso tem permissão para ver
coisas diferentes: o relatório financeiro pode precisar do domínio do e-mail, o estudo
demográfico precisa da faixa etária, e nenhum dos dois pode ver o CPF. Ainda assim, é
preciso conseguir cruzar registros da mesma pessoa entre relatórios. Os registros chegam
com estruturas aninhadas vindas de várias origens.

## Contrato obrigatório

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão.

```python
class ErroAnonimizacao(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class Anonimizador:
    def __init__(self, salt: str) -> None: ...

    def registrar_politica(self, finalidade: str, regras: dict) -> None:
        """`regras` mapeia nome de campo -> estratégia."""

    def anonimizar(self, registro: dict, finalidade: str) -> dict: ...

    def anonimizar_lote(self, registros: list[dict], finalidade: str) -> list[dict]: ...

    def chave_juncao(self, registro: dict) -> str: ...

    def campos_sensiveis(self, registro: dict) -> list[str]: ...
```

### Vocabulário fechado

`ErroAnonimizacao.code` assume **somente**: `POLITICA_INVALIDA`, `FINALIDADE_INVALIDA`,
`REGISTRO_INVALIDO`, `CHAVE_INVALIDA`.

A estratégia assume **somente**: `MASCARA`, `HASH`, `INICIAIS`, `DOMINIO`, `GENERALIZAR`,
`REMOVER`, `MANTER`.

> Este enunciado define o vocabulário, não a regra: o que cada estratégia faz, o que
> acontece com campo não declarado e em que circunstância cada código se aplica faz parte
> do que precisa ser decidido.

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
