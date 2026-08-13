# UC-22 — Motor de Pontuação e Resgate de Milhas

## Contexto de negócio

Uma companhia aérea, XPTO, possui um sistema de fidelidade. O motor deve registrar os clientes (junto com sua categoria), processar novos voos que eles fazem, converter esses voos em milhas na conta do cliente e, finalmente, permitir o resgate dessas milhas por novas passagens ou benefícios.

O saldo de milhas deve ser mantido de forma precisa e as regras de acúmulo e resgate devem ser aplicadas de acordo com as diretrizes da companhia.

## Contrato obrigatório

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão. 

```python
class ErroMilhas(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class MotorMilhas:
    def __init__(self) -> None:
        """Inicializa o motor, sem estado persistente (em memória)."""

    def registrar_cliente(self, cpf: str, categoria: str) -> None:
        """
        Registra um novo cliente.
        Categorias possíveis: 'BASIC', 'SILVER', 'GOLD', 'BLACK'.
        Se o cliente já existir, atualiza a categoria.
        """

    def adicionar_voo(self, cpf: str, distancia_km: float, valor_pago: float, dia_da_semana: int) -> str:
        """
        Adiciona um voo ao extrato do cliente e computa as milhas ganhas.
        'dia_da_semana' vai de 1 (Segunda-feira) a 7 (Domingo).
        Retorna um identificador único para o voo (string).
        """

    def saldo_milhas(self, cpf: str) -> int:
        """
        Retorna o saldo atual de milhas do cliente.
        """

    def resgatar_milhas(self, cpf: str, milhas_necessarias: int) -> bool:
        """
        Tenta debitar as milhas da conta do cliente para um resgate.
        Retorna True em caso de sucesso.
        """
```

### Vocabulário fechado

`ErroMilhas.code` assume **somente** um destes valores:

`CLIENTE_NAO_ENCONTRADO`, `SALDO_INSUFICIENTE`, `CATEGORIA_INVALIDA`, `VALORES_INVALIDOS`.

> Este enunciado define as entradas e saídas esperadas, mas não as regras completas de negócio. As condições precisas para acúmulo (baseado na categoria, valor pago, dia da semana e distância) e as regras de resgate devem ser descobertas antes da implementação.

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
