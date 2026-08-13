# Especificação técnica — UC-02: Validador de documentos (CPF/CNPJ)

> Documento consolidado ao final do ciclo Working Backwards (Designer → Analyst → SFAR) da condição c2.
> Este documento **não contém** o gabarito de decisões — apenas as regras de negócio já resolvidas.

## Interface obrigatória

- Arquivo: `solucao.py`
- Função: `validar_documento(documento) -> bool`
- Python 3.12, sem dependências externas.
- Os testes em `tests_visiveis/` devem passar.

## Requisitos de negócio (RN)

| ID | Requisito | Maturidade |
|---|---|---|
| RN-01 | Validação completa de CPF/CNPJ: formato/comprimento + dígito verificador (algoritmo módulo 11, ver seção "Algoritmo de dígito verificador") + rejeição de sequências de dígitos idênticos (ex.: `"11111111111"`, `"00000000000000"`). | Confirmado |
| RN-02 | Escopo exclusivo: apenas CPF e CNPJ. Nenhum outro tipo de documento é suportado. | Confirmado |
| RN-03 | Após normalização (RN-04/RN-09), contar dígitos: 11 dígitos → tratar como CPF; 14 dígitos → tratar como CNPJ; qualquer outro comprimento → retorna `False`. | Confirmado |
| RN-04 | Aceita entrada com máscara (ex.: `"123.456.789-00"`, `"12.345.678/0001-95"`) ou apenas dígitos. O conjunto fechado de caracteres removidos na normalização é `.` `-` `/` — nenhum outro caractere (incluindo espaços internos entre dígitos) é removido. | Confirmado |
| RN-05 | Entrada vazia (`""`), `None`, ou de tipo não-string (`int`, `list`, `dict`, etc.) retorna `False` diretamente. A função **nunca** lança exceção. | Confirmado |
| RN-06 | O retorno é exclusivamente `bool`. Não há exposição de motivo de falha (formato incorreto, dígito inválido e sequência repetida são todos indistinguíveis externamente — todos retornam `False`). | Confirmado |
| RN-07 | A rejeição por sequência de dígitos idênticos tem prioridade e é aplicada como filtro obrigatório e independente do resultado do cálculo de dígito verificador: uma sequência repetida retorna `False` mesmo que seu dígito verificador calculado seja matematicamente correto para aquela sequência. | Confirmado |
| RN-08 | Trim de espaços em branco nas extremidades da string de entrada, antes de qualquer outra normalização. Espaços internos entre dígitos **não** são removidos e tornam a entrada inválida por comprimento incorreto. | **Avanço sob risco** — sem confirmação de negócio; leitura conservadora adotada. |

## Notas de uso / não-requisitos testáveis

- **NU-01 (LGPD):** `validar_documento` não realiza logging. Recomenda-se que a docstring da função oriente explicitamente os integradores a não logarem o valor bruto de `documento` em texto claro, por se tratar de dado pessoal sob a LGPD. Esta é uma orientação de uso, não um comportamento verificável por teste automatizado. **Avanço sob risco** — sem confirmação de negócio.

## Algoritmo de dígito verificador (módulo 11)

> Definição técnica adotada por ser a leitura matematicamente unívoca do termo "dígito verificador" / "módulo 11" já citado nos requisitos — não constitui invenção de regra de negócio.

**CPF** (após normalização, 11 dígitos `d1 d2 ... d11`):
- 1º dígito verificador (`d10`): `soma = Σ(dígito_i * peso_i)` para `i` de 1 a 9, com pesos `[10, 9, 8, 7, 6, 5, 4, 3, 2]`; `resto = soma % 11`; `d10 = 0` se `resto < 2`, senão `d10 = 11 - resto`.
- 2º dígito verificador (`d11`): mesma fórmula sobre os dígitos 1 a 9 mais `d10` (10 valores), com pesos `[11, 10, 9, 8, 7, 6, 5, 4, 3, 2]`.
- Válido se os dígitos verificadores calculados coincidirem com os dígitos 10 e 11 informados.

**CNPJ** (após normalização, 14 dígitos `d1 d2 ... d14`):
- 1º dígito verificador (`d13`): soma dos dígitos 1 a 12 com pesos `[5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]`; `resto = soma % 11`; `d13 = 0` se `resto < 2`, senão `d13 = 11 - resto`.
- 2º dígito verificador (`d14`): mesma fórmula sobre os dígitos 1 a 12 mais `d13` (13 valores), com pesos `[6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]`.
- Válido se os dígitos verificadores calculados coincidirem com os dígitos 13 e 14 informados.

## Ordem de operações (para eliminar ambiguidade de sequenciamento)

1. Checar tipo e vazio (RN-05) — se não for `str` não vazia, retorna `False`.
2. Trim de espaços nas extremidades (RN-08).
3. Remover máscara — apenas `.` `-` `/` (RN-04).
4. Contar dígitos restantes e classificar CPF (11) / CNPJ (14) / inválido, outro comprimento (RN-03) — se inválido, retorna `False`.
5. Checar sequência de dígitos idênticos (RN-07) — se for, retorna `False` imediatamente, sem calcular dígito verificador.
6. Calcular dígito verificador (RN-01, algoritmo acima) — retorna `True` se coincidir, senão `False`.

## Critérios de aceite (Gherkin)

```gherkin
Funcionalidade: Validação de documentos de identificação (CPF/CNPJ)

  Cenário: CPF válido sem máscara
    Dado documento = "52998224725"
    Quando validar_documento é chamado
    Então o retorno deve ser True

  Cenário: CPF inválido (dígito verificador incorreto)
    Dado documento = "52998224724"
    Quando validar_documento é chamado
    Então o retorno deve ser False

  Cenário: CPF válido conhecido com máscara
    Dado documento = "114.447.777-35"
    Quando validar_documento é chamado
    Então o retorno deve ser True

  Cenário: CNPJ válido conhecido com máscara
    Dado documento = "11.222.333/0001-81"
    Quando validar_documento é chamado
    Então o retorno deve ser True

  Cenário: Sequência de dígitos idênticos é rejeitada mesmo com formato de CPF
    Dado documento = "11111111111"
    Quando validar_documento é chamado
    Então o retorno deve ser False

  Cenário: Sequência de dígitos idênticos é rejeitada mesmo com formato de CNPJ
    Dado documento = "11111111111111"
    Quando validar_documento é chamado
    Então o retorno deve ser False

  Cenário: Comprimento que não corresponde a CPF nem CNPJ é inválido
    Dado documento = "123456789"
    Quando validar_documento é chamado
    Então o retorno deve ser False

  Cenário: Entrada vazia é inválida, sem exceção
    Dado documento = ""
    Quando validar_documento é chamado
    Então o retorno deve ser False

  Cenário: Entrada None é inválida, sem exceção
    Dado documento = None
    Quando validar_documento é chamado
    Então o retorno deve ser False

  Cenário: Entrada de tipo não-string é inválida, sem exceção
    Dado documento = 52998224725 (int)
    Quando validar_documento é chamado
    Então o retorno deve ser False

  Cenário: Espaços nas extremidades são tolerados (trim)
    Dado documento = "  52998224725  "
    Quando validar_documento é chamado
    Então o retorno deve ser True
```

## Restrições técnicas

- Python 3.12, sem dependências externas (apenas stdlib).
- Não criar arquivos além de `solucao.py`.
- A suíte de `tests_visiveis/` deve passar antes da entrega.
