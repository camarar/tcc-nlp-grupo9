# UC-06 — Agenda clínica com múltiplos recursos — Especificação técnica consolidada

> Produzida pelo pipeline `working-backwards-designer` → `working-backwards-analyst` →
> `senior-functional-analyst-reviewer` (condição C2). As regras de negócio abaixo refletem
> exclusivamente o que os agentes elicitaram por meio de perguntas `[BLOQUEANTE]`
> respondidas pelo orquestrador. Ver `registro.md` para o detalhe das iterações e
> `captura.json` para a lista literal das perguntas.

## Requisitos Funcionais

**RF-01 — `registrar_recurso`**
Registra ou re-registra um recurso (`PROFISSIONAL`, `SALA` ou `EQUIPAMENTO`) com sua janela
de atendimento (`dias`, `inicio`, `fim`).
- Re-registrar um `recurso_id` já existente **substitui** a janela de atendimento e
  **preserva** os agendamentos já existentes contra esse recurso — mesmo que, após a
  substituição, um agendamento futuro `AGENDADO` caia fora da nova janela. Não há
  revalidação retroativa nem novo código de erro para esse caso; a nova janela só se aplica
  à validação de agendamentos criados a partir do re-registro.

**RF-02 — `agendar`**
Cria um agendamento em estado `AGENDADO`, retornando seu identificador.
- `duracao_min` ausente ou `None` → duração padrão de 30 minutos. `duracao_min <= 0` ou não
  múltiplo de 5 → `DADOS_INVALIDOS`.
- `inicio` precisa ser `datetime` *timezone-aware*; entrada *naive* → `DADOS_INVALIDOS`, sem
  fallback assumindo o fuso da clínica. Entradas *aware* em qualquer fuso são aceitas e
  normalizadas internamente para UTC antes de qualquer comparação.
- Validação em pipeline **fail-fast**, nesta ordem fixa (o primeiro problema encontrado
  determina o único `ErroAgenda.code` retornado — a exceção expõe apenas um `.code` por
  chamada, não há relato agregado de múltiplas causas):
  1. `DADOS_INVALIDOS` — campos obrigatórios ausentes/vazios, duração inválida, `inicio` naive.
  2. `RECURSO_DESCONHECIDO` — profissional, sala ou equipamento não registrado, ou registrado
     com `tipo` diferente do papel que ocupa (ex.: uma `SALA` informada como profissional).
  3. `FORA_DA_JANELA` — o intervalo `[inicio, fim)` não cabe inteiramente dentro da janela de
     atendimento de **todos** os recursos envolvidos, no dia da semana correspondente no fuso
     da clínica.
  4. `HORARIO_INDISPONIVEL` — sobreposição do intervalo semiaberto `[inicio, fim)` com
     agendamento existente em estado `AGENDADO` ou `REALIZADO` para qualquer um dos recursos
     envolvidos. Agendamentos adjacentes (fim de um == início do outro) **não** conflitam.
- Agendamentos em `CANCELADO`, `REMARCADO` ou `FALTA` **não** ocupam o recurso.

**RF-03 — `cancelar`**
Recebe `agendamento_id` e `quando`; retorna `{"multa": bool, "situacao": str}`.
- `agendamento_id` desconhecido → `AGENDAMENTO_NAO_ENCONTRADO`, verificado **antes** de
  qualquer checagem de estado.
- Só é permitido a partir do estado `AGENDADO`; qualquer outro estado → `ESTADO_INVALIDO`.
- `multa = True` quando o cancelamento ocorre a **menos de 24 horas** do `inicio` da
  consulta; exatamente 24 horas antes é considerado sem multa. Cancelar após o início da
  consulta é permitido e sempre gera `multa = True`.
- Transição: `AGENDADO → CANCELADO`.

**RF-04 — `remarcar`**
Recebe `agendamento_id` e `novo_inicio`; retorna o identificador do agendamento vigente.
- `agendamento_id` desconhecido → `AGENDAMENTO_NAO_ENCONTRADO`, verificado antes do estado.
- Só é permitido a partir do estado `AGENDADO`; qualquer outro estado → `ESTADO_INVALIDO`.
- Cria **sempre** um **novo** agendamento com novo `agendamento_id`, mantendo paciente e os
  mesmos recursos do agendamento original. O original transiciona para `REMARCADO`.
- `novo_inicio` passa pela mesma pipeline de 4 fases de RF-02. Como o agendamento original
  deixa de ocupar o recurso ao virar `REMARCADO`, é permitido remarcar para um horário
  sobreposto ao próprio horário original.
- Se o novo horário for inválido em qualquer fase da pipeline, **nada muda**: o original
  permanece `AGENDADO` e o erro correspondente é propagado.

**RF-05 — `registrar_comparecimento`**
Recebe `agendamento_id`, `compareceu` e `quando`; retorna a nova situação.
- `agendamento_id` desconhecido → `AGENDAMENTO_NAO_ENCONTRADO`, verificado antes do estado.
- Só é permitido a partir do estado `AGENDADO`; qualquer outro estado (inclusive uma segunda
  chamada sobre o mesmo agendamento, já não idempotente) → `ESTADO_INVALIDO`.
- Só pode ser registrado a partir do início da consulta: `quando < inicio` →
  `ESTADO_INVALIDO`.
- `compareceu = True` → `REALIZADO`; `compareceu = False` → `FALTA`.

**RF-06 — `disponibilidade`**
Recebe `profissional` e `dia`; retorna blocos livres `[{"inicio": datetime, "fim": datetime}]`.
- `profissional` desconhecido → `RECURSO_DESCONHECIDO` (não retorna lista vazia
  silenciosamente).
- Escopo restrito à agenda e à janela do **profissional** informado — não cruza com
  disponibilidade de sala/equipamento.
- Blocos livres dentro da janela do profissional naquele dia, descontados os agendamentos
  que ocupam o recurso (RF-02), mesclando blocos contíguos e devolvidos em ordem
  cronológica. Blocos de duração zero não aparecem. Dia sem janela cadastrada para o
  profissional → lista vazia.

**RF-07 — `agenda_do_dia`**
Recebe `profissional` e `dia`; retorna a lista de agendamentos do dia.
- `profissional` desconhecido → `RECURSO_DESCONHECIDO`.
- Lista **todos** os agendamentos do profissional cujo `inicio`, no fuso da clínica, cai no
  dia informado — inclusive `CANCELADO`, `REMARCADO`, `REALIZADO` e `FALTA` — ordenados por
  `inicio` e, em caso de empate, por `agendamento_id`.
- Um agendamento remarcado continua aparecendo, com situação `REMARCADO`, no dia do seu
  `inicio` **original**; o novo agendamento criado pela remarcação aparece separadamente, no
  dia correspondente ao `novo_inicio`.

**RF-08 — `ErroAgenda`**
Exceção com atributo público único `.code`, restrito ao vocabulário fechado:
`HORARIO_INDISPONIVEL`, `FORA_DA_JANELA`, `RECURSO_DESCONHECIDO`,
`AGENDAMENTO_NAO_ENCONTRADO`, `ESTADO_INVALIDO`, `DADOS_INVALIDOS`. Cada chamada que falha
reporta exatamente um `.code`, correspondente à primeira violação encontrada segundo a
ordem de validação do método — não há relato agregado de múltiplas causas simultâneas.

## Requisitos Não Funcionais

**RNF-01 — Persistência.** Estado mantido inteiramente em memória, usando apenas biblioteca
padrão (`zoneinfo` incluído), em arquivo único `solucao.py` (Python 3.12).

**RNF-02 — Determinismo temporal.** Toda comparação de horários ocorre após normalização
para UTC. Toda saída voltada ao usuário (`disponibilidade`, `agenda_do_dia`) é apresentada
no fuso `Agenda.FUSO` ("America/Sao_Paulo"), independentemente do fuso usado nas chamadas de
escrita.

**RNF-03 — Rejeição estrita de entrada ambígua de tempo.** Nenhum método aceita `datetime`
naive nos campos de horário; não há fallback implícito assumindo o fuso da clínica.

**RNF-04 — Imutabilidade de histórico.** Estados terminais (`CANCELADO`, `REMARCADO`,
`REALIZADO`, `FALTA`) nunca revertem nem reabrem por nenhuma operação — `cancelar`,
`remarcar` e `registrar_comparecimento` recusam com `ESTADO_INVALIDO` fora de `AGENDADO`.

## Regras de negócio (consolidado)

| ID | Regra |
|----|-------|
| RN-01 | Intervalo de ocupação é semiaberto `[inicio, fim)`; adjacência não é conflito. |
| RN-02 | Só `AGENDADO` e `REALIZADO` ocupam o recurso para fins de conflito. |
| RN-03 | `duracao_min` ausente/`None` → 30 min; inválido (`<=0` ou não múltiplo de 5) → `DADOS_INVALIDOS`. |
| RN-04 | `inicio` deve ser timezone-aware; naive → `DADOS_INVALIDOS`. Aware em qualquer fuso é normalizado para UTC internamente. |
| RN-05 | Saídas de `disponibilidade`/`agenda_do_dia` sempre no fuso da clínica. |
| RN-06 | Ordem de validação em `agendar`/`remarcar`: dados → recursos (existência/tipo) → janela → conflito de horário. |
| RN-07 | Multa de cancelamento: `< 24h` de antecedência → `multa=True`; exatamente 24h → sem multa; após o início → sempre `multa=True`. |
| RN-08 | Apenas `AGENDADO` aceita `cancelar`/`remarcar`/`registrar_comparecimento`; demais estados → `ESTADO_INVALIDO`. |
| RN-09 | `remarcar` sempre cria novo `agendamento_id`; original vira `REMARCADO` e libera o recurso, permitindo sobreposição com o próprio horário anterior. |
| RN-10 | `registrar_comparecimento` só a partir do início (`quando >= inicio`); não idempotente. |
| RN-11 | `disponibilidade` cobre só o profissional informado, não cruza sala/equipamento. |
| RN-12 | `agenda_do_dia` lista todos os estados; agendamento remarcado aparece no dia do início original. |
| RN-13 | `registrar_recurso`: `tipo` fora do vocabulário, janela `inicio >= fim`, ou `dias` vazio/fora de `0..6` → `DADOS_INVALIDOS`. Re-registro substitui a janela e preserva agendamentos existentes, mesmo que passem a cair fora da nova janela. |
| RN-14 | `agendamento_id` desconhecido em `cancelar`/`remarcar`/`registrar_comparecimento` → `AGENDAMENTO_NAO_ENCONTRADO`, checado antes do estado. |
| RN-15 | `profissional` desconhecido em `disponibilidade`/`agenda_do_dia` → `RECURSO_DESCONHECIDO` (nunca lista vazia silenciosa). |

## Critérios de aceite (Gherkin)

```gherkin
Funcionalidade: Agendamento com múltiplos recursos

  Cenário: Agendar com sucesso quando todos os recursos estão livres e dentro da janela
    Dado que "dra-ana" (PROFISSIONAL), "sala-1" (SALA) e "raio-x" (EQUIPAMENTO) estão
      registrados com janela que cobre o horário desejado
    Quando agendar for chamado com paciente, profissional, sala e equipamento livres nesse horário
    Então um agendamento_id é retornado e a situação do agendamento é "AGENDADO"

  Cenário: Recusar por conflito de horário em qualquer recurso envolvido
    Dado um agendamento AGENDADO ocupando "sala-1" em [09:00, 10:00) no fuso da clínica
    Quando agendar for chamado para outro paciente na mesma sala em [09:30, 10:30)
    Então ErroAgenda é lançado com code "HORARIO_INDISPONIVEL"

  Cenário: Aceitar agendamento adjacente ao anterior
    Dado um agendamento AGENDADO ocupando "dra-ana" em [09:00, 10:00)
    Quando agendar for chamado para "dra-ana" em [10:00, 10:30)
    Então o agendamento é aceito, pois o fim de um é igual ao início do outro

  Cenário: Rejeitar datetime naive
    Quando agendar for chamado com inicio sem timezone
    Então ErroAgenda é lançado com code "DADOS_INVALIDOS"

  Cenário: Duração padrão de 30 minutos
    Quando agendar for chamado sem duracao_min
    Então o agendamento criado ocupa 30 minutos a partir de inicio

  Cenário: Recusar por recurso desconhecido
    Quando agendar for chamado com profissional não registrado
    Então ErroAgenda é lançado com code "RECURSO_DESCONHECIDO"

  Cenário: Recusar por horário fora da janela de atendimento
    Dado que "dra-ana" atende das 08:00 às 12:00 às segundas-feiras
    Quando agendar for chamado para "dra-ana" numa segunda-feira às 13:00
    Então ErroAgenda é lançado com code "FORA_DA_JANELA"

  Cenário: Cancelamento com multa por antecedência menor que 24 horas
    Dado um agendamento AGENDADO com inicio às 10:00 de amanhã
    Quando cancelar for chamado hoje às 11:00 (23h de antecedência)
    Então o retorno é {"multa": true, "situacao": "CANCELADO"}

  Cenário: Cancelamento sem multa com exatamente 24 horas de antecedência
    Dado um agendamento AGENDADO com inicio às 10:00 de amanhã
    Quando cancelar for chamado hoje às 10:00 (exatamente 24h de antecedência)
    Então o retorno é {"multa": false, "situacao": "CANCELADO"}

  Cenário: Recusar operação sobre estado terminal
    Dado um agendamento em situação "REALIZADO"
    Quando cancelar for chamado sobre esse agendamento
    Então ErroAgenda é lançado com code "ESTADO_INVALIDO"

  Cenário: Recusar operação sobre agendamento inexistente antes de checar estado
    Quando cancelar for chamado com um agendamento_id que não existe
    Então ErroAgenda é lançado com code "AGENDAMENTO_NAO_ENCONTRADO"

  Cenário: Remarcar cria novo agendamento e libera o horário original
    Dado um agendamento AGENDADO "A1" em [09:00, 10:00) para "dra-ana"
    Quando remarcar for chamado com "A1" e novo_inicio igual ao próprio [09:00, 10:00)
    Então um novo agendamento_id "A2" é retornado, "A1" passa a "REMARCADO" e "A2" fica "AGENDADO"

  Cenário: Remarcação inválida não altera o agendamento original
    Dado um agendamento AGENDADO "A1" para "dra-ana"
    Quando remarcar for chamado com novo_inicio em conflito com outro agendamento
    Então ErroAgenda é lançado com code "HORARIO_INDISPONIVEL" e "A1" continua "AGENDADO"

  Cenário: Registrar falta antes do início é recusado
    Dado um agendamento AGENDADO com inicio às 14:00
    Quando registrar_comparecimento for chamado às 13:00 com compareceu=False
    Então ErroAgenda é lançado com code "ESTADO_INVALIDO"

  Cenário: Registrar comparecimento não é idempotente
    Dado um agendamento AGENDADO cujo comparecimento já foi registrado como REALIZADO
    Quando registrar_comparecimento for chamado novamente para o mesmo agendamento
    Então ErroAgenda é lançado com code "ESTADO_INVALIDO"

  Cenário: Disponibilidade não cobre a agenda de sala/equipamento
    Dado que "dra-ana" está livre o dia todo dentro da sua janela, mas "sala-1" está ocupada
    Quando disponibilidade for chamado para "dra-ana" nesse dia
    Então o bloco correspondente ao horário aparece como livre, refletindo apenas a agenda do profissional

  Cenário: Disponibilidade para profissional desconhecido
    Quando disponibilidade for chamado com um profissional não registrado
    Então ErroAgenda é lançado com code "RECURSO_DESCONHECIDO"

  Cenário: Agenda do dia inclui todos os estados
    Dado que "dra-ana" tem agendamentos AGENDADO, CANCELADO, REMARCADO, REALIZADO e FALTA no mesmo dia
    Quando agenda_do_dia for chamado para "dra-ana" nesse dia
    Então todos os cinco agendamentos aparecem na lista, ordenados por inicio e, em empate, por agendamento_id

  Cenário: Re-registro de recurso preserva agendamentos futuros mesmo fora da nova janela
    Dado "sala-1" registrada com uma janela e um agendamento AGENDADO dentro dela
    Quando registrar_recurso for chamado novamente para "sala-1" com uma janela mais restritiva que não cobre mais esse horário
    Então o registro é aceito, a janela é substituída, e o agendamento existente permanece "AGENDADO"

  Cenário: Validação de janela inválida em registrar_recurso
    Quando registrar_recurso for chamado com janela cujo inicio >= fim
    Então ErroAgenda é lançado com code "DADOS_INVALIDOS"
```

## Contrato obrigatório

> Copiado literalmente de `stage4/corpus/UC-06/enunciado.md`.

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
