# UC-20 — Gestor de credenciais com política e rotação

## Contexto de negócio

Uma empresa precisa impor regras de senha diferentes por perfil de usuário — o
administrador tem exigência maior que o estagiário. As senhas precisam ser trocadas
periodicamente, mas ninguém pode ser trancado para fora do sistema no dia exato do
vencimento. Usuários tentam reciclar as mesmas senhas. Quando uma senha é recusada, o
usuário precisa saber **tudo** o que está errado de uma vez, não um problema por tentativa.

## Contrato obrigatório

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão.

```python
class ErroCredencial(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class GestorCredenciais:
    def __init__(self, relogio: Callable[[], datetime] | None = None) -> None:
        """`relogio` devolve um `datetime` timezone-aware em UTC."""

    def definir_politica(self, perfil: str, politica: dict) -> None:
        """`politica`: {"min_caracteres": int, "classes_minimas": int,
                        "historico": int, "rotacao_dias": int,
                        "tolerancia_dias": int, "comuns": list[str]}"""

    def criar_usuario(self, login: str, perfil: str) -> None: ...

    def avaliar(self, senha: str, perfil: str) -> list[str]:
        """Lista de violações; lista vazia significa senha aceitável."""

    def definir_senha(self, login: str, senha: str) -> dict:
        """Retorna {"expira_em": datetime, "trocas": int}"""

    def autenticar(self, login: str, senha: str) -> dict:
        """Retorna {"autenticado": bool, "expirada": bool,
                    "em_tolerancia": bool, "dias_para_expirar": int}"""

    def situacao(self, login: str) -> dict:
        """Retorna {"perfil": str, "definida_em": datetime | None,
                    "expira_em": datetime | None, "trocas": int,
                    "expirada": bool, "em_tolerancia": bool}"""
```

### Vocabulário fechado

`ErroCredencial.code` assume **somente**: `SENHA_FRACA`, `SENHA_REUTILIZADA`,
`USUARIO_INVALIDO`, `POLITICA_INVALIDA`, `ESTADO_INVALIDO`.

Cada violação devolvida por `avaliar` assume **somente**: `COMPRIMENTO`, `CLASSES`,
`COMUM`, `REPETICAO`, `SEQUENCIA`.

> Este enunciado define o vocabulário, não a regra: o que caracteriza cada violação, em que
> ordem elas aparecem e o que acontece com a senha vencida faz parte do que precisa ser
> decidido.

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
