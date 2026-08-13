# UC-02 — Motor de cadastro e deduplicação de clientes

## Contexto de negócio

Uma operação de varejo recebe cadastros de clientes por vários canais e acumulou base
duplicada. É preciso um motor que registre pessoas físicas e jurídicas validando o
documento, encontre cadastros que provavelmente sejam a mesma pessoa, permita mesclar
dois cadastros preservando a informação, e mantenha o histórico auditável de tudo que
mudou em cada cadastro.

## Contrato obrigatório

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão.

```python
class ErroCadastro(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class MotorCadastro:
    def __init__(self, agora: Callable[[], datetime] | None = None) -> None: ...

    def registrar(self, dados: dict) -> str:
        """`dados` tem as chaves: documento (str), nome (str), email (str | None),
        telefone (str | None), tipo (str). Retorna o identificador do cadastro."""

    def obter(self, cadastro_id: str) -> dict:
        """Retorna {"cadastro_id", "documento", "nome", "email", "telefone",
                    "tipo", "situacao", "mesclado_em"}"""

    def atualizar(self, cadastro_id: str, campos: dict, ator: str) -> dict:
        """Retorna o cadastro após a alteração, no formato de `obter`."""

    def buscar_duplicados(self, cadastro_id: str) -> list[dict]:
        """Retorna [{"cadastro_id": str, "score": Decimal, "criterios": list[str]}],
        ordenado do maior para o menor score."""

    def mesclar(self, principal_id: str, secundario_id: str, ator: str) -> str:
        """Retorna o identificador do cadastro sobrevivente."""

    def inativar(self, cadastro_id: str, ator: str) -> None: ...

    def historico(self, cadastro_id: str) -> list[dict]:
        """Retorna [{"em": datetime, "ator": str, "acao": str,
                     "campo": str | None, "de": Any, "para": Any}]"""

    def situacao(self, cadastro_id: str) -> str: ...
```

### Vocabulário fechado

`ErroCadastro.code` assume **somente**: `DOCUMENTO_INVALIDO`, `CADASTRO_NAO_ENCONTRADO`,
`ESTADO_INVALIDO`, `CONFLITO_MERGE`, `CAMPO_OBRIGATORIO`, `DUPLICADO`.

`situacao()` retorna **somente**: `ATIVO`, `MESCLADO`, `INATIVO`.

O campo `tipo` assume **somente**: `PF`, `PJ`.

O campo `acao` do histórico assume **somente**: `REGISTRO`, `ALTERACAO`, `MERGE_ORIGEM`,
`MERGE_DESTINO`, `INATIVACAO`.

Os `criterios` de `buscar_duplicados` assumem **somente**: `DOCUMENTO`, `EMAIL`,
`TELEFONE`, `NOME`.

> Este enunciado define o vocabulário, não a regra: em que circunstância cada código,
> situação, ação e critério se aplica faz parte do que precisa ser decidido.

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
