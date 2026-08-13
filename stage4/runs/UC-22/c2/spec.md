# Especificação Consolidada - UC-22 Motor de Pontuação e Resgate de Milhas

## 1. Requisitos Funcionais (RF) e Regras de Negócio (RN)

- **RF-01**: O sistema deve registrar um cliente com CPF e categoria. Categorias aceitas: 'BASIC', 'SILVER', 'GOLD', 'BLACK'.
- **RF-02**: O sistema deve acumular milhas em voos adicionados, considerando multiplicadores por categoria.
  - **RN-01 (Conversão base e exceção de Terça-feira)**: A conversão é de 1 milha por KM. A categoria 'GOLD' ganha 50% de bônus sobre a conversão de distância e a 'BLACK' 100%. No entanto, voos na terça-feira (dia_da_semana == 2) não usam regra de distância ou bônus de categoria: geram um valor absoluto e fixo de 500 milhas para qualquer cliente.
- **RF-03**: O sistema deve aplicar bônus por valor pago.
  - **RN-02 (Bônus financeiro)**: Se o valor_pago for > 1000.00, soma-se 200 milhas fixas. Essa regra não se aplica (é bloqueada) se o cliente for 'BASIC'.
- **RF-04**: O sistema deve tratar resgates de milhas com cobrança de taxas.
  - **RN-03 (Taxa de Resgate)**: Todo resgate debita o valor solicitado (milhas_necessarias) + uma taxa fixa de sistema de 100 milhas. Exceção: clientes 'BLACK' são isentos desta taxa.
  - **RN-04 (Múltiplos Resgates)**: Clientes podem resgatar quantas vezes quiserem.
- **RF-05**: Validações e arredondamentos.
  - **RN-05 (Arredondamento truncado)**: Sempre que houver cálculos gerando frações de milha, o valor deve ser truncado para baixo (ex: 1507.5 vira 1507).
  - **RN-06 (Restrições Iniciais)**: Se cpf não encontrado, lançar `ErroMilhas("CLIENTE_NAO_ENCONTRADO")`. Categoria inválida lança `ErroMilhas("CATEGORIA_INVALIDA")`. Valores negativos ou dia fora do padrão (1..7) levantam `ErroMilhas("VALORES_INVALIDOS")`. Falta de saldo total levanta `ErroMilhas("SALDO_INSUFICIENTE")`.

## 2. Contrato obrigatório

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão. 

```python
class ErroMilhas(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...

class MotorMilhas:
    def __init__(self) -> None: ...
    def registrar_cliente(self, cpf: str, categoria: str) -> None: ...
    def adicionar_voo(self, cpf: str, distancia_km: float, valor_pago: float, dia_da_semana: int) -> str: ...
    def saldo_milhas(self, cpf: str) -> int: ...
    def resgatar_milhas(self, cpf: str, milhas_necessarias: int) -> bool: ...
```

### Vocabulário fechado

`ErroMilhas.code` assume **somente** um destes valores:
`CLIENTE_NAO_ENCONTRADO`, `SALDO_INSUFICIENTE`, `CATEGORIA_INVALIDA`, `VALORES_INVALIDOS`.
