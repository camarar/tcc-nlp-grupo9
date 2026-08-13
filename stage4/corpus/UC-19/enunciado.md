# UC-19 — Trilha de auditoria à prova de adulteração

## Contexto de negócio

Um sistema regulado precisa registrar tudo o que os usuários fazem, de forma que um
auditor externo consiga provar que nenhum registro foi apagado ou alterado depois de
gravado. Os eventos carregam um payload livre, vindo de várias partes do sistema, e não
podem levar dado pessoal para a trilha. A regulação também obriga a descartar registros
antigos — o que conflita com a promessa de que nada é apagado, e esse conflito precisa ser
resolvido de forma explícita.

## Contrato obrigatório

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão.

```python
class ErroAuditoria(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class TrilhaAuditoria:
    def __init__(self, relogio: Callable[[], datetime] | None = None) -> None:
        """`relogio` devolve um `datetime` timezone-aware em UTC."""

    def configurar(self, config: dict) -> None:
        """`config`: {"denylist": list[str], "retencao_dias": int}"""

    def registrar(self, evento: dict) -> str:
        """`evento`: {"actor_id": str, "action": str, "resource": str,
                      "result": str, "payload": dict}
        Retorna o hash do registro gravado."""

    def consultar(self, filtros: dict) -> list[dict]:
        """`filtros` aceita as chaves `actor_id`, `action`, `resource`, `result`,
        `desde` e `ate` (`datetime`). Retorna os registros em ordem cronológica."""

    def verificar_integridade(self) -> dict:
        """Retorna {"integra": bool, "total": int,
                    "primeiro_divergente": int | None}"""

    def expurgar(self, quando: datetime) -> int:
        """Retorna a quantidade de registros descartados."""

    def exportar(self) -> list[dict]:
        """[{"indice": int, "timestamp_utc": datetime, "actor_id": str,
             "action": str, "resource": str, "result": str,
             "payload": dict, "hash_anterior": str, "hash": str}]"""
```

### Vocabulário fechado

`ErroAuditoria.code` assume **somente**: `REGISTRO_INVALIDO`, `CONSULTA_INVALIDA`,
`POLITICA_INVALIDA`.

O campo `result` assume **somente**: `SUCESSO`, `FALHA`, `NEGADO`.

> Este enunciado define o vocabulário, não a regra: como os registros são encadeados, o
> que acontece com o payload, e como o expurgo convive com a verificação de integridade
> faz parte do que precisa ser decidido.

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
