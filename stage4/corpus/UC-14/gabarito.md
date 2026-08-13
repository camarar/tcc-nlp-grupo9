# UC-14 — Gabarito de Decisões (pré-registrado)

> USO RESTRITO: responde exclusivamente às perguntas dos agentes na condição C2.
> NUNCA fornecer este arquivo ao gerador de código nem à condição C1.

- **G-01 — Regra de Ouro.** Par UF/NCM sem alíquota aplicável →
  `ErroTributario("ALIQUOTA_NAO_CADASTRADA")`. **Nunca** se adota alíquota padrão, nem se
  usa a alíquota de outra UF, nem se trata o item como isento por omissão.

- **G-02 — Busca por prefixo de NCM.** Procura-se primeiro o NCM **exato** na UF. Não
  havendo, vale o **prefixo cadastrado mais longo** que case com o início do NCM do item,
  respeitado o mínimo de **4 dígitos**. Nenhum prefixo de 4 ou mais dígitos cadastrado →
  `ALIQUOTA_NAO_CADASTRADA`. A busca **nunca** cruza UFs.

- **G-03 — Base de cálculo.** `Σ (valor × quantidade − desconto)` dos itens **não isentos**.
  O frete **não** entra na base de cálculo.

- **G-04 — Isenção com correspondência exata.** A isenção vale apenas para o NCM **exato**
  cadastrado na UF — **não** há busca por prefixo, ao contrário da alíquota. Item isento
  fica fora da base, tem `icms` e `icms_st` iguais a `0.00`, `aliquota` e `ncm_aplicado`
  iguais a `None`, e **não** exige alíquota cadastrada.

- **G-05 — ICMS.** Por item: `quantize(base_item × aliquota)`, com `ROUND_HALF_EVEN` em
  2 casas. O ICMS da nota é a **soma dos valores já quantizados por item**.

- **G-06 — Substituição tributária.** Só quando o cadastro aplicado tem `mva`:
  `icms_st = quantize(base_item × (1 + mva) × aliquota) − icms_item`, nunca negativo
  (mínimo `0.00`). Sem `mva`, `icms_st` é `0.00`.

- **G-07 — Regime.** `NORMAL` calcula integralmente. `SIMPLES` reduz o ICMS de cada item à
  **metade** (`quantize(icms × 0.5)`) e **zera a substituição tributária**.

- **G-08 — Regime obrigatório.** CNPJ emitente sem regime cadastrado →
  `ErroTributario("REGIME_DESCONHECIDO")`. Não existe regime padrão.

- **G-09 — Totais.** `total_tributos = icms + icms_st`.
  `total_nota = Σ (valor × quantidade − desconto) de TODOS os itens (inclusive isentos)
  + frete + icms_st`. O ICMS é embutido e **não** soma ao total.

- **G-10 — Tabela inválida.** `ErroTributario("TABELA_INVALIDA")` quando: `aliquota <= 0`
  ou `> 1`; `mva < 0`; `ncm` com menos de 4 dígitos, vazio ou não numérico; `uf` com
  tamanho diferente de 2. Vale também para `registrar_isencao` (`ncm` e `uf`) e para
  `registrar_regime` (`regime` fora do vocabulário).

- **G-11 — Item inválido.** `ErroTributario("ITEM_INVALIDO")` quando: `valor < 0`;
  `quantidade < 1`; `desconto < 0`; `desconto > valor × quantidade`; `ncm` ausente, vazio
  ou não numérico.

- **G-12 — Nota inválida.** `ErroTributario("NOTA_INVALIDA")` quando: `itens` vazio ou
  ausente; `frete < 0`; `uf_destino` ausente ou com tamanho diferente de 2;
  `cnpj_emitente` ausente ou vazio.

- **G-13 — Ordem de validação.** Nesta sequência: (1) `NOTA_INVALIDA`, (2) `ITEM_INVALIDO`,
  (3) `REGIME_DESCONHECIDO`, (4) `ALIQUOTA_NAO_CADASTRADA`.

- **G-14 — Memória de cálculo.** Uma entrada **por item**, na ordem da nota, com o
  `ncm_aplicado` mostrando qual chave do cadastro foi efetivamente usada (o NCM exato ou o
  prefixo) — é isso que torna o fallback auditável. `memoria_calculo` aplica exatamente as
  mesmas regras e os mesmos erros de `calcular`.

- **G-15 — Precisão.** Todo valor monetário é `Decimal` quantizado em 2 casas com
  `ROUND_HALF_EVEN`. `aliquota` e `mva` são frações decimais (`0.18` = 18%).

- **G-16 — Reregistro.** Registrar novamente o mesmo par UF/NCM **substitui** alíquota e
  MVA. Registrar novamente um CNPJ substitui o regime. Uma isenção registrada **prevalece**
  sobre a alíquota do mesmo par exato.
