# UC-17 — Serviço de ingestão de arquivos

## Contexto de negócio

Uma plataforma recebe documentos e imagens enviados pelos usuários. O envio é feito em
partes, porque a conexão cai e o cliente precisa poder retomar de onde parou. O que chega
não é confiável: usuários renomeiam arquivos, enviam coisas maiores do que declararam e
tentam escapar do diretório de destino pelo nome. O mesmo arquivo enviado duas vezes não
deve ocupar espaço duas vezes.

## Contrato obrigatório

Arquivo único `solucao.py`, Python 3.12, apenas biblioteca padrão.

```python
class ErroUpload(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None: ...
    # expõe o atributo público .code


class ServicoUpload:
    def __init__(self, relogio: Callable[[], float] | None = None) -> None:
        """`relogio` devolve segundos monotônicos como float."""

    def configurar(self, config: dict) -> None:
        """`config`: {"tamanho_maximo_bytes": int, "tipos_permitidos": list[str],
                      "ttl_sessao_s": float}"""

    def iniciar(self, nome_original: str, tamanho_declarado: int) -> str: ...

    def enviar_parte(self, upload_id: str, indice: int, dados: bytes) -> dict:
        """Retorna {"recebidas": int, "bytes_recebidos": int, "duplicada": bool}"""

    def concluir(self, upload_id: str) -> dict:
        """Retorna {"nome_armazenado": str, "tipo": str, "tamanho": int,
                    "hash": str, "duplicado_de": str | None}"""

    def cancelar(self, upload_id: str) -> None: ...

    def situacao(self, upload_id: str) -> str: ...

    def listar(self) -> list[dict]:
        """[{"nome_armazenado": str, "tipo": str, "tamanho": int, "hash": str}]"""
```

### Vocabulário fechado

`ErroUpload.code` assume **somente**: `TIPO_NAO_PERMITIDO`, `TAMANHO_EXCEDIDO`,
`ARQUIVO_CORROMPIDO`, `UPLOAD_NAO_ENCONTRADO`, `ESTADO_INVALIDO`, `DADOS_INVALIDOS`.

A situação assume **somente**: `EM_ANDAMENTO`, `CONCLUIDO`, `CANCELADO`, `EXPIRADO`.

O `tipo` assume **somente**: `PNG`, `JPEG`, `PDF`.

> Este enunciado define o vocabulário, não a regra: como o tipo é determinado, como o nome
> de destino é formado e em que circunstância cada código se aplica faz parte do que
> precisa ser decidido.

## Entrega

- Implementar em `solucao.py`. Os testes em `tests_visiveis/` devem passar.
