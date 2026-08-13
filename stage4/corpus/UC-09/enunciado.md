# UC-09 — Central de chamados com SLA

## Contexto de negócio

Uma operadora de telecom precisa priorizar o atendimento dos chamados de suporte. Cada
chamado tem uma severidade e um prazo de SLA. Alguns SLAs só correm em horário comercial —
não faz sentido consumir prazo de madrugada. Chamados podem ficar pausados esperando o
cliente, ser reabertos depois de resolvidos, e a fila precisa mostrar sempre quem deve ser
atendido primeiro.

## Contrato obrigatório

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão (`zoneinfo` incluído).

```python
class ErroChamado(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class CentralChamados:
    FUSO = "America/Sao_Paulo"

    def __init__(self, relogio: Callable[[], datetime] | None = None) -> None: ...

    def configurar_sla(self, severidade: str, minutos: int,
                       horario_comercial: bool) -> None: ...

    def abrir(self, dados: dict) -> str:
        """`dados`: {"cliente": str, "severidade": str, "assunto": str,
                     "aberto_em": datetime}"""

    def atribuir(self, chamado_id: str, atendente: str, quando: datetime) -> None: ...

    def pausar(self, chamado_id: str, motivo: str, quando: datetime) -> None: ...

    def retomar(self, chamado_id: str, quando: datetime) -> None: ...

    def resolver(self, chamado_id: str, quando: datetime) -> dict:
        """Retorna {"cumpriu_sla": bool, "tempo_util_min": int}"""

    def reabrir(self, chamado_id: str, quando: datetime) -> None: ...

    def prazo(self, chamado_id: str) -> datetime: ...

    def fila(self, quando: datetime) -> list[dict]:
        """[{"chamado_id": str, "severidade": str, "situacao": str,
             "prazo": datetime, "estourado": bool}]"""

    def proximo(self, quando: datetime) -> str:
        """Identificador do chamado no topo da fila."""
```

### Vocabulário fechado

`ErroChamado.code` assume **somente**: `CHAMADO_NAO_ENCONTRADO`, `ESTADO_INVALIDO`,
`DADOS_INVALIDOS`, `POLITICA_INVALIDA`, `FILA_VAZIA`, `ATRIBUICAO_INVALIDA`.

A `severidade` assume **somente**: `CRITICA`, `ALTA`, `MEDIA`, `BAIXA`.

A `situacao` assume **somente**: `ABERTO`, `ATRIBUIDO`, `PAUSADO`, `RESOLVIDO`,
`REABERTO`.

> Este enunciado define o vocabulário, não a regra: em que circunstância cada código,
> severidade e situação se aplica faz parte do que precisa ser decidido.

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
