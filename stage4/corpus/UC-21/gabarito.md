# UC-21 — Gabarito de Decisões (pré-registrado)

> USO RESTRITO: responde exclusivamente às perguntas dos agentes na condição C2.
> NUNCA fornecer este arquivo ao gerador de código nem à condição C1.

- **G-01 — Registro e moeda.** `pagamento_id` deve ser string não vazia; `valor` deve ser
  maior que zero; `criado_em` deve ser `datetime` timezone-aware. Moedas aceitas:
  `BRL`, `USD` e `EUR`, normalizadas para maiúsculas. Violação gera, respectivamente,
  `PAGAMENTO_INVALIDO`, `VALOR_INVALIDO`, `DATA_INVALIDA` ou `MOEDA_INVALIDA`.
  Identificador já existente gera `PAGAMENTO_INVALIDO` e não altera o pagamento.

- **G-02 — Precisão monetária.** Converter por `Decimal(str(valor))` e quantizar cada
  entrada para duas casas com `ROUND_HALF_EVEN`. Resultado quantizado menor ou igual a
  zero é inválido. Todos os valores retornados têm expoente de duas casas.

- **G-03 — Captura parcial.** Um pagamento pode receber várias capturas parciais. Captura
  omitida (`valor=None`) usa todo o valor autorizado ainda não capturado. A soma capturada
  nunca pode superar o autorizado; excesso ou ausência de restante → `VALOR_INVALIDO`.

- **G-04 — Estados da captura.** Antes de qualquer captura: `AUTORIZADO`. Capturado menos
  que o autorizado: `CAPTURADO_PARCIAL`. Capturado exatamente o autorizado: `CAPTURADO`.
  Não existe cancelamento de autorização.

- **G-05 — Estorno.** Só pode usar valor já capturado e ainda disponível. É permitido
  acumular vários estornos parciais. Valor superior ao saldo disponível ou operação antes
  de qualquer captura → `VALOR_INVALIDO`. Quando ainda resta saldo, o estado é
  `ESTORNADO_PARCIAL`; quando o saldo chega a zero por estorno, `ESTORNADO`.

- **G-06 — Chargeback.** Só pode consumir saldo capturado ainda disponível. Pode ser
  parcial e acumulado, inclusive depois de estorno parcial. Excesso ou ausência de saldo
  → `VALOR_INVALIDO`. Havendo saldo restante: `CHARGEBACK_PARCIAL`; saldo zero atingido
  por chargeback: `CHARGEBACK`.

- **G-07 — Saldo e conservação.** `saldo_disponivel = valor_capturado -
  valor_estornado - valor_chargeback`, sempre `>= 0.00`. Estorno e chargeback competem
  pelo mesmo saldo; nenhum deles considera o valor meramente autorizado.

- **G-08 — Estado prevalente.** O estado reflete a última classe de evento financeiro:
  uma captura posterior a estorno/chargeback parcial volta a `CAPTURADO_PARCIAL` ou
  `CAPTURADO`; estorno posterior a chargeback parcial resulta em `ESTORNADO_PARCIAL` ou
  `ESTORNADO`; chargeback posterior a estorno parcial resulta em `CHARGEBACK_PARCIAL` ou
  `CHARGEBACK`. Estados de saldo zero são terminais porque não há valor capturável nem
  disponível restante.

- **G-09 — Idempotência bem-sucedida.** `operacao_id` é global por pagamento e por toda
  a vida do objeto. Repetição com mesmo tipo e mesmos argumentos normalizados devolve o
  resultado original com `duplicado=True`, sem novo evento. Isso também vale para captura
  com `valor=None`, comparada pelo valor efetivamente capturado na primeira execução.

- **G-10 — Conflito de idempotência.** Reutilizar `operacao_id` com outro tipo de operação
  ou argumentos normalizados diferentes gera `IDEMPOTENCIA_CONFLITANTE`. A comparação de
  chargeback inclui `ocorrido_em`; a de estorno inclui `motivo`; a de captura inclui o
  valor efetivo.

- **G-11 — Falhas não consomem chave.** Operação rejeitada por qualquer validação não
  reserva `operacao_id` e não entra no histórico. A mesma chave pode ser reutilizada em
  uma tentativa posterior válida.

- **G-12 — Datas de chargeback.** `ocorrido_em` precisa ser timezone-aware, não pode ser
  anterior a `criado_em` nem posterior ao instante fornecido por `agora`; violações geram
  `DATA_INVALIDA`. O evento usa `ocorrido_em`; registro, captura e estorno usam `agora()`.

- **G-13 — Histórico.** O registro gera o primeiro evento, com sequência 1,
  `operacao_id=None` e o valor autorizado. Apenas operações bem-sucedidas inéditas geram
  eventos. A sequência é estritamente crescente, a ordem é de efetivação e a lista e os
  dicionários retornados são cópias defensivas.

- **G-14 — Consultas e referências.** Pagamento desconhecido gera
  `PAGAMENTO_NAO_ENCONTRADO` em qualquer método que recebe `pagamento_id`; essa verificação
  precede validações de valor, data e operação. `consultar` e `historico` não alteram estado.

- **G-15 — Atomicidade.** Toda validação de uma operação ocorre antes de qualquer mutação.
  Uma falha preserva totais, estado, histórico, sequência e chaves idempotentes. Métodos
  públicos mutáveis devem ser serializados por instância para impedir saldo negativo em
  chamadas concorrentes.

