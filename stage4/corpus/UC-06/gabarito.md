# UC-06 — Gabarito de Decisões (pré-registrado)

> USO RESTRITO: responde exclusivamente às perguntas dos agentes na condição C2.
> NUNCA fornecer este arquivo ao gerador de código nem à condição C1.

- **G-01 — Intervalos semiabertos.** A consulta ocupa `[inicio, fim)`. Duas consultas
  **adjacentes** (o fim de uma igual ao início da outra) **não** conflitam. Qualquer
  sobreposição parcial conflita.

- **G-02 — Duração padrão.** `duracao_min` ausente ou `None` → **30 minutos**.
  `duracao_min <= 0` ou não múltiplo de 5 → `ErroAgenda("DADOS_INVALIDOS")`.

- **G-03 — Fuso horário.** `inicio` **precisa** ser `datetime` *timezone-aware*; entrada
  *naive* → `ErroAgenda("DADOS_INVALIDOS")`. Internamente tudo é normalizado para UTC,
  mas os `datetime` devolvidos por `disponibilidade` e `agenda_do_dia` estão no fuso da
  clínica (`FUSO`).

- **G-04 — Conflito multi-recurso.** O horário só é aceito se **profissional, sala e
  equipamento** (quando informado) estiverem simultaneamente livres. Conflito em qualquer
  um deles → `ErroAgenda("HORARIO_INDISPONIVEL")`. Agendamentos em situação `CANCELADO`,
  `REMARCADO` e `FALTA` **não** ocupam o recurso; `AGENDADO` e `REALIZADO` ocupam.

- **G-05 — Janela de atendimento.** O intervalo `[inicio, fim)` precisa caber inteiramente
  dentro da janela de **todos** os recursos envolvidos, avaliada no dia da semana
  correspondente **no fuso da clínica**. Fim exatamente igual ao fim da janela é aceito.
  Fora da janela, ou em dia não atendido → `ErroAgenda("FORA_DA_JANELA")`.

- **G-06 — Recursos desconhecidos.** Profissional, sala ou equipamento não registrado →
  `ErroAgenda("RECURSO_DESCONHECIDO")`. O recurso precisa ter sido registrado com o `tipo`
  correspondente ao papel que ocupa; papel trocado (ex.: uma `SALA` informada como
  profissional) também é `RECURSO_DESCONHECIDO`.

- **G-07 — Ordem de validação.** Nesta sequência: (1) dados (campos obrigatórios, duração,
  *timezone*), (2) existência e tipo dos recursos, (3) janela de atendimento,
  (4) conflito de horário.

- **G-08 — Cancelamento e multa.** `cancelar` leva a `CANCELADO`. Há **multa** quando o
  cancelamento ocorre a **menos de 24 horas** do início da consulta (`multa=True`);
  exatamente 24 horas antes ainda é sem multa. Cancelar depois do início da consulta é
  permitido e sempre gera multa.

- **G-09 — Estados terminais.** `CANCELADO`, `REMARCADO`, `REALIZADO` e `FALTA` recusam
  `cancelar`, `remarcar` e `registrar_comparecimento` com `ErroAgenda("ESTADO_INVALIDO")`.
  Só `AGENDADO` aceita operações.

- **G-10 — Remarcação.** Cria um **novo** agendamento, com novo identificador, mantendo
  paciente e os mesmos recursos; o original passa a `REMARCADO`. O novo horário passa por
  todas as validações de `agendar`. Se o novo horário for inválido, **nada muda**: o
  original permanece `AGENDADO` e o erro é propagado. O agendamento original não ocupa mais
  o recurso, então remarcar para um horário sobreposto ao próprio horário original é
  permitido.

- **G-11 — Comparecimento.** `compareceu=True` → `REALIZADO`; `False` → `FALTA`. Só pode
  ser registrado a partir do início da consulta: `quando < inicio` →
  `ErroAgenda("ESTADO_INVALIDO")`. Retorna a nova situação.

- **G-12 — Disponibilidade.** Blocos livres do **profissional** no dia informado, dentro da
  janela dele, descontados os agendamentos que ocupam o recurso (G-04), mesclando blocos
  contíguos e devolvendo em ordem cronológica. Blocos de duração zero não aparecem. Dia sem
  janela para aquele profissional → lista vazia.

- **G-13 — Agenda do dia.** Todos os agendamentos do profissional cujo **início**, no fuso
  da clínica, cai no dia informado — inclusive os `CANCELADO`, `REMARCADO`, `REALIZADO` e
  `FALTA` —, ordenados por `inicio` e, no empate, por `agendamento_id`.

- **G-14 — Campos obrigatórios.** `paciente`, `profissional`, `sala` e `inicio` são
  obrigatórios; ausentes ou vazios → `ErroAgenda("DADOS_INVALIDOS")`. `equipamento` aceita
  `None`.

- **G-15 — Registro de recurso.** `tipo` fora do vocabulário, `janela` com `inicio >= fim`,
  `dias` vazio ou com valor fora de `0..6` → `ErroAgenda("DADOS_INVALIDOS")`. Registrar
  novamente um `recurso_id` existente substitui a janela e mantém os agendamentos.

- **G-16 — Referências inválidas.** `agendamento_id` desconhecido →
  `ErroAgenda("AGENDAMENTO_NAO_ENCONTRADO")`, verificado antes do estado. `profissional`
  desconhecido em `disponibilidade` e `agenda_do_dia` → `ErroAgenda("RECURSO_DESCONHECIDO")`.
