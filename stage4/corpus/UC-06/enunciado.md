# UC-06 — Agenda clínica com múltiplos recursos

## Contexto de negócio

Uma clínica precisa agendar consultas sem gerar conflito. Cada consulta ocupa ao mesmo
tempo um profissional, uma sala e, em alguns casos, um equipamento — todos precisam estar
livres. A clínica atende em janelas de horário que variam por recurso e dia da semana. Os
pacientes cancelam, remarcam e às vezes não aparecem, e a recepção precisa ver os horários
livres de cada profissional.

## Contrato obrigatório

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão (`zoneinfo` incluído).

```python
class ErroAgenda(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class Agenda:
    FUSO = "America/Sao_Paulo"

    def __init__(self, agora: Callable[[], datetime] | None = None) -> None: ...

    def registrar_recurso(self, recurso_id: str, tipo: str, janela: dict) -> None:
        """`janela`: {"inicio": time, "fim": time, "dias": list[int]}
        onde `dias` usa 0=segunda .. 6=domingo, no fuso da clínica."""

    def agendar(self, dados: dict) -> str:
        """`dados`: {"paciente": str, "profissional": str, "sala": str,
                     "equipamento": str | None, "inicio": datetime,
                     "duracao_min": int | None}
        Retorna o identificador do agendamento."""

    def cancelar(self, agendamento_id: str, quando: datetime) -> dict:
        """Retorna {"multa": bool, "situacao": str}"""

    def remarcar(self, agendamento_id: str, novo_inicio: datetime) -> str:
        """Retorna o identificador do agendamento vigente após a remarcação."""

    def registrar_comparecimento(self, agendamento_id: str,
                                 compareceu: bool, quando: datetime) -> str:
        """Retorna a nova situação do agendamento."""

    def disponibilidade(self, profissional: str, dia: date) -> list[dict]:
        """[{"inicio": datetime, "fim": datetime}] — blocos livres, no fuso da clínica."""

    def agenda_do_dia(self, profissional: str, dia: date) -> list[dict]:
        """[{"agendamento_id": str, "inicio": datetime, "fim": datetime,
             "paciente": str, "situacao": str}]"""
```

### Vocabulário fechado

`ErroAgenda.code` assume **somente**: `HORARIO_INDISPONIVEL`, `FORA_DA_JANELA`,
`RECURSO_DESCONHECIDO`, `AGENDAMENTO_NAO_ENCONTRADO`, `ESTADO_INVALIDO`,
`DADOS_INVALIDOS`.

A situação de um agendamento assume **somente**: `AGENDADO`, `CANCELADO`, `REMARCADO`,
`REALIZADO`, `FALTA`.

O `tipo` de recurso assume **somente**: `PROFISSIONAL`, `SALA`, `EQUIPAMENTO`.

> Este enunciado define o vocabulário, não a regra: em que circunstância cada código,
> situação e tipo se aplica faz parte do que precisa ser decidido.

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
