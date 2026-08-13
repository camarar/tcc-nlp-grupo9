# UC-07 — Gabarito de Decisões (pré-registrado)

> USO RESTRITO: responde exclusivamente às perguntas dos agentes na condição C2.
> NUNCA fornecer este arquivo ao gerador de código nem à condição C1.

- **G-01 — Peso cubado.** Calculado **por item**:
  `(altura_cm × largura_cm × comprimento_cm) / fator_cubagem`, multiplicado pela
  `quantidade`. O peso cubado do pedido é a soma dos itens; o peso real é
  `Σ peso_kg × quantidade`.

- **G-02 — Peso cobrado.** `max(peso_real, peso_cubado)`, **arredondado para cima até o
  próximo múltiplo de 0,5 kg** (um peso que já seja múltiplo de 0,5 permanece). Devolvido
  como `Decimal` quantizado em 3 casas.

- **G-03 — Faixas de peso.** `ate_kg` é limite superior **inclusivo**: peso cobrado igual a
  `ate_kg` ainda pertence àquela faixa. Vale a primeira faixa (na ordem da tabela) cujo
  `ate_kg >= peso_cobrado`.

- **G-04 — Limite de peso.** `peso_cobrado > peso_maximo_kg` **exclui** aquela
  transportadora da cotação — não é erro.

- **G-05 — Região não atendida (Regra de Ouro).** Transportadora cuja lista `regioes` não
  contém a `uf_destino` é **excluída** da cotação; nunca se assume tarifa nem se usa a
  faixa de outra região. Se **nenhuma** transportadora cadastrada atender a UF →
  `ErroFrete("REGIAO_NAO_ATENDIDA")`.

- **G-06 — Restrição por CEP.** A transportadora é excluída quando `cep_destino` **começa**
  com qualquer um de seus prefixos restritos. A comparação usa apenas os dígitos do CEP
  (máscara descartada).

- **G-07 — Seguro.** `seguro = quantize(ad_valorem × Σ (valor × quantidade))`. Quando
  `ad_valorem` é `None` ou ausente, o seguro é `0.00`.

- **G-08 — Total.** `total = frete + seguro`.

- **G-09 — Ordenação de `cotar`.** Por `total` crescente; empate por `prazo_dias`
  crescente; empate final por nome da transportadora em ordem lexicográfica.

- **G-10 — `melhor_cotacao`.** `PRECO` escolhe o menor `total` (empate: menor
  `prazo_dias`, depois nome). `PRAZO` escolhe o menor `prazo_dias` (empate: menor `total`,
  depois nome). `criterio` fora do vocabulário → `ErroFrete("PEDIDO_INVALIDO")`.

- **G-11 — Ausência de cotação.** Se há transportadora que atende a UF, mas todas foram
  excluídas por peso ou por restrição de CEP → `ErroFrete("SEM_COTACAO")`. `cotar` nunca
  devolve lista vazia: ou devolve cotações, ou levanta `REGIAO_NAO_ATENDIDA` / `SEM_COTACAO`.

- **G-12 — Itens inválidos.** `ErroFrete("DIMENSOES_INVALIDAS")` quando, em qualquer item,
  `peso_kg <= 0`, alguma dimensão `<= 0`, `quantidade < 1` ou `valor < 0`.

- **G-13 — Pedido inválido.** `ErroFrete("PEDIDO_INVALIDO")` quando `itens` está vazio ou
  ausente, ou quando `uf_destino` ou `cep_destino` estão ausentes ou vazios.

- **G-14 — Tabela inválida.** `ErroFrete("TABELA_INVALIDA")` quando: `faixas` vazia ou
  ausente; `ate_kg` não estritamente crescente na ordem informada; algum `preco < 0`;
  algum `prazo_dias < 1`; `fator_cubagem <= 0`; `peso_maximo_kg <= 0`; `regioes` vazia;
  `ad_valorem` negativo.

- **G-15 — Restrição sobre transportadora inexistente.** →
  `ErroFrete("TRANSPORTADORA_DESCONHECIDA")`.

- **G-16 — Precisão.** Valores monetários são `Decimal` quantizados em 2 casas com
  `ROUND_HALF_EVEN`; pesos, em 3 casas.

- **G-17 — Ordem de validação.** Nesta sequência: (1) pedido, (2) dimensões dos itens,
  (3) região, (4) disponibilidade de cotação.

- **G-18 — Reregistro.** Registrar novamente uma transportadora **substitui** a
  configuração e **mantém** as restrições de CEP já cadastradas para ela.
