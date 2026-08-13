# UC-12 — Serviço de conversão de moedas resiliente — Especificação Técnica Consolidada

> Produzida pelo pipeline de 3 agentes (working-backwards-designer → working-backwards-analyst →
> senior-functional-analyst-reviewer). Lacunas sem resposta disponível na fonte de negócio foram
> registradas como "avanço sob risco" (ver `registro.md`) e estão sinalizadas abaixo com 🟠.

## Contrato obrigatório

> Copiado literalmente de `stage4/corpus/UC-12/enunciado.md`.

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão. Valores monetários e
taxas são `decimal.Decimal`.

```python
class ErroCambio(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class ServicoCambio:
    def __init__(self, provedor: Callable[[str], Decimal],
                 relogio: Callable[[], float] | None = None,
                 config: dict | None = None) -> None:
        """`provedor` recebe um par no formato "USD/BRL" e devolve a taxa, ou levanta
        qualquer exceção quando indisponível. `relogio` devolve segundos monotônicos.
        `config`: {"ttl_s": float, "stale_max_s": float,
                   "falhas_para_abrir": int, "tempo_aberto_s": float}"""

    def registrar_moeda(self, codigo: str, casas: int) -> None: ...

    def cotacao(self, de: str, para: str) -> dict:
        """Retorna {"taxa": Decimal, "stale": bool, "idade_s": float}"""

    def converter(self, valor, de: str, para: str) -> dict:
        """Retorna {"valor_convertido": Decimal, "taxa": Decimal,
                    "stale": bool, "idade_s": float}"""

    def estado_circuito(self) -> str: ...

    def estatisticas(self) -> dict:
        """Retorna {"chamadas_provedor": int, "acertos_cache": int,
                    "falhas_consecutivas": int, "usos_stale": int}"""
```

### Vocabulário fechado

`ErroCambio.code` assume **somente**: `MOEDA_NAO_SUPORTADA`, `COTACAO_INDISPONIVEL`,
`PROVEDOR_INDISPONIVEL`, `VALOR_INVALIDO`, `CONFIGURACAO_INVALIDA`.

`estado_circuito()` retorna **somente**: `FECHADO`, `ABERTO`, `MEIO_ABERTO`.

### Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.

---

## Requisitos Funcionais

| ID | Requisito |
|---|---|
| RF-01 | `registrar_moeda(codigo, casas)` registra uma moeda com seu número de casas decimais. Nenhuma moeda vem pré-registrada (nem USD). `casas < 0`, `casas > 8`, ou `codigo` vazio → `ErroCambio(code="CONFIGURACAO_INVALIDA")`. Reregistrar uma moeda já registrada substitui as casas decimais e não invalida/limpa o cache existente para essa moeda. |
| RF-02 | `cotacao(de, para)` e `converter(valor, de, para)` verificam a existência de registro para `de` e `para` **antes** de qualquer consulta ao provedor ou ao cache. Se qualquer uma não estiver registrada → `ErroCambio(code="MOEDA_NAO_SUPORTADA")`. |
| RF-03 | Caso `de == para`: retorno imediato com `taxa=Decimal("1.000000")`, `stale=False`, `idade_s=0.0`; em `converter()`, `valor_convertido` é o `valor` quantizado nas casas decimais da moeda, sem chamar o provedor e sem incrementar `acertos_cache`. |
| RF-04 | Toda cotação é resolvida via moeda-ponte fixa USD: o provedor é consultado exclusivamente no formato `"USD/<MOEDA>"`; `USD/USD` vale `1` por definição e nunca é consultado ao provedor. Não existe consulta de par direto que não passe pelo dólar. Taxa cruzada: `taxa(A→B) = taxa(USD/B) / taxa(USD/A)`. |
| RF-05 | A taxa cruzada é quantizada em 6 casas decimais com `ROUND_HALF_EVEN` antes de ser retornada ou usada em cálculo subsequente. `cotacao()`/`converter()` sempre retornam `taxa` com 6 casas decimais. |
| RF-06 | `valor_convertido = valor × taxa`, quantizado nas casas decimais registradas para a moeda de **destino** (`para`), usando `ROUND_HALF_EVEN`. |
| RF-07 | Cache por perna `USD/<MOEDA>` com janela de frescor `ttl_s`. Enquanto `idade_s < ttl_s`, a cotação em cache é servida diretamente (`stale=False`), incrementando `acertos_cache`, sem chamar o provedor. A cotação expira quando `idade_s >= ttl_s`. |
| RF-08 | Quando `idade_s >= ttl_s`, o serviço **sempre** tenta chamar o provedor antes de qualquer fallback (não há atalho para servir stale sem tentativa prévia). Se a chamada tiver sucesso, o cache é atualizado e a cotação é servida fresca (`stale=False`, `idade_s=0.0`), incrementando `chamadas_provedor`. |
| RF-09 | Se a chamada ao provedor falhar: (a) se existe cotação em cache para aquele par com `idade_s < stale_max_s`, ela é servida com `stale=True`, incrementando `chamadas_provedor` (pela tentativa) e `usos_stale`; (b) se a cotação em cache tem `idade_s >= stale_max_s`, levanta `ErroCambio(code="COTACAO_INDISPONIVEL")`; (c) se não existe nenhuma cotação em cache para o par, levanta `ErroCambio(code="PROVEDOR_INDISPONIVEL")`. 🟠 *Precedência entre (b) e (c) quando as duas pernas de uma conversão cruzada divergem nesse resultado não está definida — ver avanço sob risco AR-01 em `registro.md`.* |
| RF-10 | Circuit breaker de 3 estados (`FECHADO`, `ABERTO`, `MEIO_ABERTO`), **global** à instância de `ServicoCambio` (não por par), exposto via `estado_circuito()` sem parâmetros. `FECHADO`: chamadas ao provedor ocorrem normalmente; cada falha incrementa `falhas_consecutivas`; qualquer sucesso zera o contador; ao atingir `falhas_para_abrir` → `ABERTO` (inicia timer de `tempo_aberto_s`). `ABERTO`: nenhuma chamada ao provedor é tentada; serve-se cache/stale (RF-09b/c) até decorrer `tempo_aberto_s`, quando transiciona para `MEIO_ABERTO`. `MEIO_ABERTO`: permite exatamente **uma** chamada de sondagem ao provedor; sucesso → `FECHADO` e zera `falhas_consecutivas`; falha → volta a `ABERTO`, reiniciando o timer de `tempo_aberto_s`. 🟠 *Semântica de transição de estado **dentro** de uma mesma chamada que resolve duas pernas (cruzada) não está definida — ver AR-02 e AR-03 em `registro.md`.* |
| RF-11 | Em conversão cruzada, cada perna (`USD/A`, `USD/B`) é resolvida de forma independente segundo RF-07–RF-10, compartilhando o estado do circuito global. `idade_s` final é a idade da mais antiga das duas pernas; `stale` final é verdadeiro se qualquer uma das duas pernas for `stale`. 🟠 *Herda as lacunas de RF-09 e RF-10 (AR-01, AR-02, AR-03).* |
| RF-12 | `converter(valor, de, para)` com `valor < 0` levanta `ErroCambio(code="VALOR_INVALIDO")`. `valor == 0` é válido e produz `valor_convertido` igual a zero (quantizado nas casas da moeda destino), sem erro. |
| RF-13 | `config` inválido — qualquer uma das chaves `ttl_s`, `stale_max_s`, `falhas_para_abrir`, `tempo_aberto_s` com valor `<= 0` — levanta `ErroCambio(code="CONFIGURACAO_INVALIDA")`. Chaves ausentes assumem individualmente os defaults (config parcial é permitido): `ttl_s=600`, `stale_max_s=86400`, `falhas_para_abrir=5`, `tempo_aberto_s=60`. |
| RF-14 | `estatisticas()` retorna contadores cumulativos desde a criação da instância, com granularidade **por cotação resolvida** (por perna, em conversões cruzadas): `chamadas_provedor` (toda invocação efetiva ao provedor, sucesso ou falha, uma por perna que efetivamente chamou o provedor); `acertos_cache` (uma por perna servida do cache dentro do TTL; não conta stale nem o atalho `de==para`); `usos_stale` (uma por perna que usou cotação obsoleta); `falhas_consecutivas` (contador corrente do disjuntor, refletindo o estado presente). |

## Requisitos Não Funcionais

| ID | Requisito |
|---|---|
| RNF-01 | **Determinismo.** Dado o mesmo `provedor`, `relogio`, `config` e sequência de chamadas, a saída (valores, códigos de erro, estado do circuito, estatísticas) deve ser idêntica em qualquer execução, dentro dos limites das lacunas registradas como avanço sob risco. |
| RNF-02 | **Precisão numérica.** Toda manipulação de taxa e valor monetário usa `Decimal`, nunca `float`. Todas as quantizações usam exclusivamente `ROUND_HALF_EVEN`: 6 casas para taxa cruzada, casas registradas da moeda de destino para `valor_convertido`. |
| RNF-03 | **Isolamento de configuração.** Parâmetros de `config` são por instância, sem estado global compartilhado entre instâncias distintas de `ServicoCambio`. |
| RNF-04 | **Fail-safe de vocabulário.** Nenhuma exceção nativa do Python deve escapar da API pública; toda falha de negócio esperada é traduzida para `ErroCambio` com `.code` pertencente estritamente ao vocabulário fechado. |
| RNF-05 | **Resiliência a falha de dependência externa.** O serviço degrada graciosamente para dados stale dentro do teto `stale_max_s` antes de propagar erro, e usa o circuit breaker para evitar chamadas repetidas a um provedor já conhecido como indisponível durante a janela `tempo_aberto_s`. |
| RNF-06 | **Sem efeitos colaterais globais.** Cache e estado do circuito residem em memória, por instância, sem persistência externa. |
| RNF-07 🟠 | **Risco aceito — concorrência.** Não há garantia de thread-safety/atomicidade entre chamadas concorrentes a uma mesma instância; não há fonte de negócio confirmando requisito de concorrência para esta versão. Avanço sob risco (ver `registro.md`). |
| RNF-08 🟠 | **Risco aceito — sanidade de taxa do provedor.** Não há validação de razoabilidade da taxa retornada pelo `provedor` (valores `<= 0` são aceitos como estão); não há fonte de negócio confirmando essa regra para esta versão. Avanço sob risco (ver `registro.md`). |

## Regras de negócio

- **RN-01 (moeda de referência):** o provedor é consultado sempre no formato `"USD/<MOEDA>"`; `USD/USD` vale `1` por definição e nunca é perguntado ao provedor.
- **RN-02 (taxa cruzada):** `taxa(A → B) = taxa(USD/B) / taxa(USD/A)`, quantizada em 6 casas com `ROUND_HALF_EVEN`.
- **RN-03 (cache com TTL):** cada perna `USD/<MOEDA>` é cacheada por `ttl_s` (padrão 600 s); dentro do TTL o provedor não é chamado.
- **RN-04 (fallback obsoleto):** falha do provedor com cotação em cache → usa-se a última cotação conhecida com `stale=True`, desde que sua idade seja menor que `stale_max_s` (padrão 86400 s); idade igual ou maior → `COTACAO_INDISPONIVEL`.
- **RN-05 (sem cotação alguma):** provedor falhou e não há nenhuma cotação em cache para aquele par → `PROVEDOR_INDISPONIVEL`.
- **RN-06 (disjuntor):** `falhas_para_abrir` falhas consecutivas do provedor (padrão 5) levam o circuito a `ABERTO` por `tempo_aberto_s` (padrão 60 s); em `ABERTO` o provedor não é chamado.
- **RN-07 (meio aberto):** decorrido `tempo_aberto_s`, o estado passa a `MEIO_ABERTO` e a próxima consulta pode chamar o provedor uma vez: sucesso → `FECHADO` com o contador zerado; falha → `ABERTO` de novo.
- **RN-08 (reset por sucesso):** qualquer sucesso do provedor zera o contador de falhas consecutivas.
- **RN-09 (precisão do resultado):** `valor_convertido = valor × taxa`, quantizado nas casas da moeda de destino, `ROUND_HALF_EVEN`; `taxa` devolvida sempre tem 6 casas.
- **RN-10 (mesma moeda):** `de == para` devolve `taxa = 1.000000`, valor inalterado (quantizado), `stale=False`, `idade_s = 0.0`, sem chamar o provedor e sem contar acerto de cache.
- **RN-11 (moeda não registrada):** origem ou destino não registrados → `MOEDA_NAO_SUPORTADA`, verificado antes de qualquer consulta ao provedor.
- **RN-12 (valor):** `valor < 0` → `VALOR_INVALIDO`; zero é válido e converte para zero.
- **RN-13 (idade):** `idade_s` é o tempo em segundos desde a obtenção da cotação efetivamente usada, com `round(x, 3)`; em taxa cruzada, vale a idade da mais antiga das duas cotações, e `stale` é verdadeiro se qualquer uma delas for obsoleta.
- **RN-14 (configuração):** qualquer valor `<= 0` em `config` → `CONFIGURACAO_INVALIDA`; chaves ausentes assumem os defaults individualmente.
- **RN-15 (registro de moeda):** `casas < 0` ou `> 8`, ou `codigo` vazio → `CONFIGURACAO_INVALIDA`; reregistrar substitui as casas decimais e não invalida o cache.
- **RN-16 (estatísticas):** `chamadas_provedor` conta invocações efetivas (sucesso ou falha); `acertos_cache` conta cotações servidas do cache dentro do TTL; `usos_stale` conta usos de cotação obsoleta; `falhas_consecutivas` é o contador corrente do disjuntor.
- **RN-17 (uma consulta por moeda):** numa mesma chamada de `converter` ou `cotacao`, cada moeda não-dólar é resolvida no máximo uma vez junto ao provedor.

## Critérios de aceite (Gherkin)

```gherkin
Funcionalidade: Registro de moedas

  Cenário: Registrar uma nova moeda com casas decimais válidas
    Dado um ServicoCambio recém-criado
    Quando eu registro a moeda "BRL" com 2 casas decimais
    Então nenhuma exceção é levantada

  Cenário: Rejeitar registro de moeda com casas decimais inválidas
    Dado um ServicoCambio recém-criado
    Quando eu registro a moeda "BRL" com -1 casas decimais
    Então uma ErroCambio com code "CONFIGURACAO_INVALIDA" é levantada

  Cenário: Reregistrar uma moeda não invalida o cache existente
    Dado um ServicoCambio com "BRL" registrada com 2 casas e uma cotação USD/BRL em cache
    Quando eu registro novamente "BRL" com 4 casas decimais
    Então a cotação USD/BRL permanece em cache
    E as próximas conversões para BRL usam 4 casas decimais


Funcionalidade: Validação de moeda e valor

  Cenário: Rejeitar conversão com moeda de origem não registrada
    Dado um ServicoCambio com apenas "BRL" registrada
    Quando eu converto 10 de "XYZ" para "BRL"
    Então uma ErroCambio com code "MOEDA_NAO_SUPORTADA" é levantada
    E o provedor não é chamado

  Cenário: Rejeitar valor negativo em converter
    Dado um ServicoCambio com "USD" e "BRL" registradas
    Quando eu converto -5 de "USD" para "BRL"
    Então uma ErroCambio com code "VALOR_INVALIDO" é levantada

  Cenário: Aceitar valor zero em converter
    Dado um ServicoCambio com "USD" e "BRL" registradas
    Quando eu converto 0 de "USD" para "BRL"
    Então o valor_convertido retornado é 0, quantizado nas casas de "BRL"


Funcionalidade: Mesma moeda

  Cenário: Converter para a mesma moeda não chama o provedor
    Dado um ServicoCambio com "USD" registrada
    Quando eu obtenho a cotação de "USD" para "USD"
    Então a taxa retornada é 1.000000
    E stale é False e idade_s é 0.0
    E o provedor não é chamado
    E acertos_cache não é incrementado


Funcionalidade: Cache e TTL

  Cenário: Servir cotação do cache dentro do TTL
    Dado um ServicoCambio com ttl_s=600 e uma cotação USD/BRL obtida há 100 segundos
    Quando eu obtenho a cotação de "USD" para "BRL"
    Então o provedor não é chamado
    E stale é False
    E acertos_cache é incrementado em 1

  Cenário: Cache expirado aciona nova chamada ao provedor com sucesso
    Dado um ServicoCambio com ttl_s=600 e uma cotação USD/BRL obtida há 700 segundos
    E o provedor responde com sucesso para "USD/BRL"
    Quando eu obtenho a cotação de "USD" para "BRL"
    Então o provedor é chamado
    E a cotação retornada é fresca, com stale False e idade_s 0.0
    E chamadas_provedor é incrementado em 1


Funcionalidade: Degradação por falha do provedor

  Cenário: Provedor falha mas há cache obsoleto dentro do teto tolerado
    Dado um ServicoCambio com ttl_s=600, stale_max_s=86400
    E uma cotação USD/BRL em cache com idade 700 segundos (expirada pelo TTL, dentro do stale_max_s)
    E o provedor levanta exceção para "USD/BRL"
    Quando eu obtenho a cotação de "USD" para "BRL"
    Então a cotação em cache é retornada com stale True
    E usos_stale é incrementado em 1

  Cenário: Provedor falha e cache excede o teto de obsolescência
    Dado um ServicoCambio com stale_max_s=86400
    E uma cotação USD/BRL em cache com idade 90000 segundos
    E o provedor levanta exceção para "USD/BRL"
    Quando eu obtenho a cotação de "USD" para "BRL"
    Então uma ErroCambio com code "COTACAO_INDISPONIVEL" é levantada

  Cenário: Provedor falha e não há nenhum cache para o par
    Dado um ServicoCambio sem nenhuma cotação em cache para "USD/BRL"
    E o provedor levanta exceção para "USD/BRL"
    Quando eu obtenho a cotação de "USD" para "BRL"
    Então uma ErroCambio com code "PROVEDOR_INDISPONIVEL" é levantada


Funcionalidade: Circuit breaker

  Cenário: Falhas consecutivas abrem o circuito
    Dado um ServicoCambio com falhas_para_abrir=5 e circuito FECHADO
    E o provedor falha 5 vezes consecutivas em pares distintos sem cache disponível
    Quando eu consulto o estado do circuito
    Então estado_circuito() retorna "ABERTO"

  Cenário: Circuito aberto não chama o provedor
    Dado um ServicoCambio com circuito ABERTO
    Quando eu obtenho uma cotação para um par com cache obsoleto dentro do stale_max_s
    Então o provedor não é chamado
    E a cotação em cache é retornada com stale True

  Cenário: Circuito transita para meio-aberto após o tempo configurado
    Dado um ServicoCambio com circuito ABERTO e tempo_aberto_s=60
    Quando decorrem 60 segundos ou mais (via relogio)
    E eu faço uma nova consulta
    Então o circuito tenta uma chamada de sondagem ao provedor

  Cenário: Sondagem bem-sucedida em meio-aberto fecha o circuito
    Dado um ServicoCambio com circuito MEIO_ABERTO
    E o provedor responde com sucesso à chamada de sondagem
    Quando eu consulto o estado do circuito após a sondagem
    Então estado_circuito() retorna "FECHADO"
    E falhas_consecutivas é 0

  Cenário: Sondagem malsucedida em meio-aberto reabre o circuito
    Dado um ServicoCambio com circuito MEIO_ABERTO
    E o provedor falha na chamada de sondagem
    Quando eu consulto o estado do circuito após a sondagem
    Então estado_circuito() retorna "ABERTO"

  Cenário: Sucesso do provedor zera o contador de falhas consecutivas
    Dado um ServicoCambio com circuito FECHADO e falhas_consecutivas=3
    E o provedor responde com sucesso na próxima chamada
    Quando eu consulto estatisticas()
    Então falhas_consecutivas é 0


Funcionalidade: Conversão cruzada via moeda-ponte

  Cenário: Converter entre duas moedas não-USD via ponte USD
    Dado um ServicoCambio com "EUR" e "GBP" registradas
    E o provedor responde com sucesso para "USD/EUR" e "USD/GBP"
    Quando eu obtenho a cotação de "EUR" para "GBP"
    Então a taxa retornada é taxa(USD/GBP) dividida por taxa(USD/EUR), quantizada em 6 casas com ROUND_HALF_EVEN
    E o provedor é chamado no máximo uma vez para cada uma das duas moedas


Funcionalidade: Configuração

  Cenário: Rejeitar configuração com valor não positivo
    Quando eu crio um ServicoCambio com config={"ttl_s": 0}
    Então uma ErroCambio com code "CONFIGURACAO_INVALIDA" é levantada

  Cenário: Usar valores padrão quando config é omitido
    Dado um ServicoCambio criado sem o parâmetro config
    Então ttl_s efetivo é 600, stale_max_s é 86400, falhas_para_abrir é 5 e tempo_aberto_s é 60


Funcionalidade: Estatísticas

  Cenário: Estatísticas refletem uso de cache, provedor e staleness
    Dado um ServicoCambio recém-criado
    Quando eu realizo uma sequência de chamadas que resulta em 2 acertos de cache, 1 chamada ao provedor e 1 uso de cotação obsoleta
    Então estatisticas() retorna acertos_cache=2, chamadas_provedor=1, usos_stale=1
```

## Riscos aceitos (avanço sob risco — SFAR opção B)

Ver detalhamento completo em `registro.md`. Resumo:

- 🟠 **AR-01** — Precedência entre `COTACAO_INDISPONIVEL` e `PROVEDOR_INDISPONIVEL` quando, numa conversão cruzada, as duas pernas divergem nesse resultado (uma com cache velho demais, outra sem cache algum). Afeta RF-09, RF-11.
- 🟠 **AR-02** — Se uma falha na primeira perna de uma conversão cruzada abre o circuito (`FECHADO`→`ABERTO`) no meio da mesma chamada, se a segunda perna já é bloqueada por esse circuito recém-aberto dentro da mesma operação. Afeta RF-10, RF-11.
- 🟠 **AR-03** — Simetricamente, se uma sondagem bem-sucedida em `MEIO_ABERTO` durante a primeira perna libera a segunda perna da mesma chamada para chamar o provedor livremente, ou se o limite de "uma sondagem" é por chamada externa (bloqueando a segunda perna). Afeta RF-10, RF-11.
- 🟠 **AR-04 (RNF-07)** — Thread-safety/concorrência entre chamadas simultâneas à mesma instância não é garantida nem exigida nesta versão.
- 🟠 **AR-05 (RNF-08)** — Nenhuma validação de sanidade é aplicada sobre a taxa retornada pelo `provedor` (valores `<= 0` são aceitos como estão).
