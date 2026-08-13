# UC-15 — Gabarito de Decisões (pré-registrado)

> USO RESTRITO: responde exclusivamente às perguntas dos agentes na condição C2.
> NUNCA fornecer este arquivo ao gerador de código nem à condição C1.

3 tentativas; backoff exponencial determinístico 1s/2s/4s (sem jitter — sleep injetável); deduplicação por idempotency_key; falha após 3 tentativas -> registro em dead_letter com o último erro.
