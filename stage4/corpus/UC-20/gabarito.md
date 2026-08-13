# UC-20 — Gabarito de Decisões (pré-registrado)

> USO RESTRITO: responde exclusivamente às perguntas dos agentes na condição C2.
> NUNCA fornecer este arquivo ao gerador de código nem à condição C1.

- **G-01 — Retorno estruturado.** `avaliar` devolve a **lista de todas** as violações
  encontradas — nunca um booleano e nunca só a primeira. Lista vazia significa senha
  aceitável.

- **G-02 — Ordem fixa das violações.** Sempre nesta ordem, independentemente da ordem em
  que foram detectadas: `COMPRIMENTO`, `CLASSES`, `COMUM`, `REPETICAO`, `SEQUENCIA`.

- **G-03 — `COMPRIMENTO`.** Senha com menos de `min_caracteres` (padrão **12**).

- **G-04 — `CLASSES`.** As quatro classes são minúscula, maiúscula, dígito e símbolo
  (qualquer caractere que não seja letra nem dígito). A senha precisa ter pelo menos
  `classes_minimas` classes distintas (padrão **3**).

- **G-05 — `COMUM`.** A senha consta da lista `comuns`, comparada **sem diferenciar
  maiúsculas**. Padrão: `["senha123", "password", "123456", "qwerty", "admin"]`.

- **G-06 — `REPETICAO`.** Existe uma corrida de **4 ou mais** caracteres idênticos
  consecutivos.

- **G-07 — `SEQUENCIA`.** Existe uma corrida de **4 ou mais** caracteres consecutivos na
  tabela ASCII, crescente ou decrescente de um em um (`abcd`, `4321`).

- **G-08 — Precedência na troca.** `definir_senha` avalia **primeiro** a força: havendo
  violações → `ErroCredencial("SENHA_FRACA")`. Só depois verifica reutilização.

- **G-09 — Histórico de senhas.** Senha igual a qualquer uma das últimas `historico`
  (padrão **5**, contando a senha atual) → `ErroCredencial("SENHA_REUTILIZADA")`. A
  comparação é feita sobre o hash. Uma senha que saiu da janela do histórico pode ser
  reutilizada.

- **G-10 — Armazenamento.** A senha é guardada como
  `hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, 100000).hex()`, com
  `salt = hashlib.sha256(login.encode()).hexdigest()[:16].encode()`. A senha em claro
  **nunca** é armazenada.

- **G-11 — Rotação.** `expira_em = momento da definição + rotacao_dias` (padrão **90**).
  `trocas` conta quantas vezes a senha foi definida, começando em 1 na primeira definição.

- **G-12 — Tolerância.** Depois de `expira_em`, o usuário ainda autentica por
  `tolerancia_dias` (padrão **7**), com `expirada=True` e `em_tolerancia=True`. Passada a
  tolerância, `autenticado=False`, `expirada=True` e `em_tolerancia=False`, mesmo com a
  senha correta.

- **G-13 — Fronteiras temporais.** A senha está expirada quando `agora >= expira_em`. A
  tolerância acaba quando `agora >= expira_em + tolerancia_dias`.

- **G-14 — `dias_para_expirar`.** Dias inteiros restantes até `expira_em`, truncados para
  baixo; **negativo** depois de vencida, indicando há quantos dias venceu.

- **G-15 — Senha incorreta.** `autenticar` com senha errada devolve `autenticado=False`
  **sem levantar exceção**; os demais campos refletem o estado real da credencial.

- **G-16 — Referências e estado.** `login` inexistente em qualquer método →
  `ErroCredencial("USUARIO_INVALIDO")` — esta é uma API administrativa, não o login
  público, então revelar a inexistência é aceitável. Usuário **sem senha definida** em
  `autenticar` → `ErroCredencial("ESTADO_INVALIDO")`; em `situacao`, os campos
  `definida_em` e `expira_em` vêm `None` e `trocas` vem `0`.

- **G-17 — Usuário e perfil.** `criar_usuario` com login já existente, login vazio, ou
  perfil **sem política definida** → `ErroCredencial("USUARIO_INVALIDO")`. `avaliar` com
  perfil sem política → `ErroCredencial("POLITICA_INVALIDA")`.

- **G-18 — Política.** `POLITICA_INVALIDA` quando: `min_caracteres < 8`;
  `classes_minimas` fora de `1..4`; `historico < 1`; `rotacao_dias < 1`;
  `tolerancia_dias < 0`; `comuns` que não seja lista de strings; `perfil` vazio. Chaves
  ausentes assumem o padrão.

- **G-19 — Mudança de política.** Redefinir a política de um perfil **não** invalida
  senhas já definidas nem altera `expira_em` existente: passa a valer a partir da próxima
  troca.
