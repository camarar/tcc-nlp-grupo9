# UC-11 — Gabarito de Decisões (pré-registrado)

> USO RESTRITO: responde exclusivamente às perguntas dos agentes na condição C2.
> NUNCA fornecer este arquivo ao gerador de código nem à condição C1.

- **G-01 — Política é uma lista de permissões (*allowlist*).** Campo **escalar** não
  declarado na política da finalidade é **removido** do resultado. O padrão é a
  privacidade: nenhum valor passa sem regra explícita. Por isso `MANTER` existe — é a única
  forma de preservar um valor.

- **G-02 — Percurso recursivo.** Campos cujo valor é `dict` ou **lista de `dict`** são
  sempre **percorridos**, estejam ou não declarados na política — a *allowlist* de G-01
  vale para os valores escalares que estão dentro deles. As regras são aplicadas **pelo
  nome do campo, em qualquer profundidade**. Um contêiner que fique sem nenhum campo
  permitido é mantido no resultado, vazio. Listas de valores simples são tratadas como
  escalares: só sobrevivem se o campo estiver declarado.

- **G-03 — `MASCARA`.** Preserva os **dois últimos caracteres** e substitui todos os
  demais por `*`, mantendo o comprimento original (inclusive separadores):
  `"12345678909"` → `"*********09"`.

- **G-04 — `HASH`.** `hashlib.sha256((salt + str(valor)).encode()).hexdigest()`, hexadecimal
  completo em minúsculas.

- **G-05 — `INICIAIS`.** A primeira letra de **cada palavra**, em maiúscula, cada uma
  seguida de ponto: `"Maria da Silva"` → `"M.D.S."`. Espaços múltiplos são colapsados.

- **G-06 — `DOMINIO`.** Preserva apenas o domínio do e-mail, prefixado por `*@`:
  `"maria@x.com"` → `"*@x.com"`. Valor sem `@` → `ErroAnonimizacao("REGISTRO_INVALIDO")`.

- **G-07 — `GENERALIZAR`.** Sobre `datetime.date`, devolve apenas o **ano** como `int`.
  Sobre `int`, devolve a faixa de dez em dez como texto: `37` → `"30-39"`. Qualquer outro
  tipo → `ErroAnonimizacao("REGISTRO_INVALIDO")`.

- **G-08 — `REMOVER` e `MANTER`.** `REMOVER` exclui a chave do resultado (não a define como
  `None`). `MANTER` copia o valor sem alteração.

- **G-09 — Valores nulos.** `None` atravessa `MASCARA`, `HASH`, `INICIAIS`, `DOMINIO` e
  `GENERALIZAR` **sem alteração** e sem erro; continua `None` no resultado.

- **G-10 — Não destrutivo.** O registro de entrada **nunca** é modificado: o resultado é
  sempre uma estrutura nova.

- **G-11 — Determinismo.** A mesma entrada, com o mesmo `salt` e a mesma finalidade, produz
  **exatamente** a mesma saída em execuções diferentes. Não há aleatoriedade.

- **G-12 — Chave de junção.** `hashlib.sha256((salt + cpf_somente_digitos).encode()).hexdigest()`,
  onde `cpf_somente_digitos` descarta qualquer caractere não numérico do campo `cpf` do
  **nível raiz**. É **independente da finalidade**, o que permite cruzar relatórios
  diferentes. Registro sem `cpf`, com `cpf` vazio ou sem nenhum dígito →
  `ErroAnonimizacao("CHAVE_INVALIDA")`.

- **G-13 — Campos sensíveis.** A denylist fixa é `{cpf, cnpj, email, telefone, nome,
  endereco, cep, rg, data_nascimento}`. `campos_sensiveis` devolve os nomes encontrados em
  **qualquer profundidade**, sem repetição, em ordem alfabética.

- **G-14 — Finalidade.** Finalidade não registrada em `anonimizar` ou `anonimizar_lote` →
  `ErroAnonimizacao("FINALIDADE_INVALIDA")`. Registrar novamente a mesma finalidade
  **substitui** as regras anteriores.

- **G-15 — Política inválida.** `ErroAnonimizacao("POLITICA_INVALIDA")` quando: `regras`
  vazio ou ausente; alguma estratégia fora do vocabulário; algum nome de campo vazio;
  `finalidade` vazia. `salt` vazio no construtor também é `POLITICA_INVALIDA`.

- **G-16 — Registro inválido.** `ErroAnonimizacao("REGISTRO_INVALIDO")` quando o registro
  não é um `dict`.

- **G-17 — Lote atômico.** `anonimizar_lote` só devolve resultado se **todos** os registros
  puderem ser processados; qualquer erro interrompe a operação e é propagado.
