# UC-22 — Gabarito de Decisões (pré-registrado)

> USO RESTRITO: responde exclusivamente às perguntas dos agentes na condição C2.
> NUNCA fornecer este arquivo ao gerador de código nem à condição C1.

- **G-01 — Conversão Base e Terça-feira (Dia 2).** A conversão padrão é de 1 milha para cada 1 km voado (`distancia_km`). A categoria 'GOLD' ganha 50% de bônus sobre as milhas da distância, e a categoria 'BLACK' ganha 100% de bônus (o dobro). Porém, se o voo ocorrer na Terça-feira (`dia_da_semana == 2`), a regra de distância e bônus de categoria é ignorada para a base: o voo rende apenas um valor fixo de 500 milhas (para todas as categorias, independente da distância).

- **G-02 — Bônus de Valor Pago.** Se o `valor_pago` pelo voo for superior a R$ 1000.00, o cliente recebe um bônus adicional fixo de 200 milhas somadas ao resultado final. Entretanto, a categoria 'BASIC' nunca recebe esse bônus, mesmo que pague mais de R$ 1000.00.

- **G-03 — Arredondamento.** Qualquer cálculo que gere frações de milhas deve ser estritamente arredondado para baixo (truncado para inteiro, usando `int()` ou `math.floor()`). Ex: 1200.9 km na categoria BASIC rende 1200 milhas. 1005 km na GOLD rende 1507.5 -> 1507 milhas.

- **G-04 — Taxa Fixa de Resgate.** Ao realizar a operação de `resgatar_milhas`, o sistema deve debitar o valor das `milhas_necessarias` **acrescido** de uma "taxa de sistema" de 100 milhas. Exemplo: Se `milhas_necessarias` for 5000, o saldo do cliente deve cair em 5100. A única exceção é a categoria 'BLACK', que é totalmente isenta dessa taxa (deve descontar apenas as `milhas_necessarias`).

- **G-05 — Saldo Insuficiente.** Se o saldo do cliente for menor do que o custo total do resgate (incluindo a taxa, se aplicável), a função deve levantar `ErroMilhas("SALDO_INSUFICIENTE")`. O saldo não deve ser alterado.

- **G-06 — Validação de Entradas.** Se a categoria informada for diferente de BASIC, SILVER, GOLD ou BLACK, levantar `ErroMilhas("CATEGORIA_INVALIDA")`. Se o `cpf` passado não estiver registrado, em qualquer método, levantar `ErroMilhas("CLIENTE_NAO_ENCONTRADO")`. Se a distância ou valor pago forem negativos, ou dia da semana fora de 1..7, levantar `ErroMilhas("VALORES_INVALIDOS")`.

- **G-07 — Idempotência ou Limites.** O sistema permite múltiplos resgates sem limitação de frequência, desde que o saldo permita.
