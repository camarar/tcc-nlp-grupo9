# UC-16 — Serviço de consulta paginada com escopo por perfil

## Contexto de negócio

O backoffice lista pedidos para times diferentes. Cada perfil enxerga um recorte diferente
dos dados: o time de atendimento não pode ver a margem, o time regional só vê a própria
região. As listas são grandes e precisam ser paginadas sem pular nem repetir registros
quando alguém cadastra algo no meio da navegação. Os usuários filtram e ordenam por vários
campos.

## Contrato obrigatório

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão.

```python
class ErroConsulta(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class ServicoConsulta:
    def __init__(self, registros: list[dict]) -> None:
        """Todo registro tem, no mínimo, a chave `id` (int)."""

    def definir_perfil(self, perfil: str, campos_visiveis: list[str],
                       filtro_fixo: dict | None = None) -> None: ...

    def inserir(self, registro: dict) -> None: ...

    def consultar(self, perfil: str, params: dict) -> dict:
        """`params`: {"cursor": str | None, "tamanho": int | None,
                      "ordenar_por": list[list] | None,
                      "filtros": dict | None}
        `ordenar_por` é uma lista de pares `[campo, direcao]`.
        `filtros` mapeia campo -> {"op": str, "valor": Any}.
        Retorna {"itens": list[dict], "proximo_cursor": str | None,
                 "tem_proxima": bool, "total": int}"""
```

### Vocabulário fechado

`ErroConsulta.code` assume **somente**: `CURSOR_INVALIDO`, `CAMPO_INVALIDO`,
`PARAMETRO_INVALIDO`, `PERFIL_DESCONHECIDO`, `FILTRO_INVALIDO`.

A `direcao` assume **somente**: `asc`, `desc`.

O `op` do filtro assume **somente**: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`,
`contains`.

> Este enunciado define o vocabulário, não a regra: como o cursor é construído, o que
> acontece com registros inseridos entre páginas, e em que circunstância cada código se
> aplica faz parte do que precisa ser decidido.

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
