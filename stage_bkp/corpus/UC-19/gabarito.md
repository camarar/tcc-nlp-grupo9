# UC-19 — Gabarito de Decisões (pré-registrado)

> USO RESTRITO: responde exclusivamente às perguntas dos agentes na condição C2.
> NUNCA fornecer este arquivo ao gerador de código nem à condição C1.

campos fixos {timestamp_utc, actor_id, action, resource, result}; payload filtrado por denylist de PII (cpf, senha, e-mail, telefone); registros encadeados por hash SHA-256 do registro anterior (append-only); verificar_integridade() detecta adulteração.
