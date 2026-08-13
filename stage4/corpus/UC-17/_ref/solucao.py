"""UC-17 — Serviço de ingestão de arquivos."""

from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Callable

_VOCAB_TIPOS = ("PNG", "JPEG", "PDF")

_ASSINATURAS = (
    (b"\x89PNG\r\n\x1a\n", "PNG", "png"),
    (b"\xff\xd8\xff", "JPEG", "jpg"),
    (b"%PDF", "PDF", "pdf"),
)

_CONFIG_PADRAO = {
    "tamanho_maximo_bytes": 5 * 1024 * 1024,
    "tipos_permitidos": ["PNG", "JPEG"],
    "ttl_sessao_s": 3600.0,
}


class ErroUpload(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


class ServicoUpload:
    def __init__(self, relogio: Callable[[], float] | None = None) -> None:
        self._relogio = relogio if relogio is not None else time.monotonic
        self._config = {
            "tamanho_maximo_bytes": _CONFIG_PADRAO["tamanho_maximo_bytes"],
            "tipos_permitidos": list(_CONFIG_PADRAO["tipos_permitidos"]),
            "ttl_sessao_s": _CONFIG_PADRAO["ttl_sessao_s"],
        }
        self._sessoes: dict[str, dict] = {}
        self._armazenados: dict[str, dict] = {}

    def configurar(self, config: dict) -> None:
        tamanho_maximo_bytes = config.get(
            "tamanho_maximo_bytes", _CONFIG_PADRAO["tamanho_maximo_bytes"]
        )
        tipos_permitidos = config.get(
            "tipos_permitidos", list(_CONFIG_PADRAO["tipos_permitidos"])
        )
        ttl_sessao_s = config.get("ttl_sessao_s", _CONFIG_PADRAO["ttl_sessao_s"])

        if tamanho_maximo_bytes < 1:
            raise ErroUpload("DADOS_INVALIDOS")
        if ttl_sessao_s <= 0:
            raise ErroUpload("DADOS_INVALIDOS")
        if not tipos_permitidos or any(t not in _VOCAB_TIPOS for t in tipos_permitidos):
            raise ErroUpload("DADOS_INVALIDOS")

        self._config = {
            "tamanho_maximo_bytes": tamanho_maximo_bytes,
            "tipos_permitidos": list(tipos_permitidos),
            "ttl_sessao_s": ttl_sessao_s,
        }

    def iniciar(self, nome_original: str, tamanho_declarado: int) -> str:
        if not nome_original or tamanho_declarado < 1:
            raise ErroUpload("DADOS_INVALIDOS")
        if tamanho_declarado > self._config["tamanho_maximo_bytes"]:
            raise ErroUpload("TAMANHO_EXCEDIDO")

        upload_id = str(uuid.uuid4())
        self._sessoes[upload_id] = {
            "iniciada_em": self._relogio(),
            "partes": {},
            "situacao": "EM_ANDAMENTO",
        }
        return upload_id

    def enviar_parte(self, upload_id: str, indice: int, dados: bytes) -> dict:
        sessao = self._sessao_ativa(upload_id)

        if indice < 0 or not isinstance(dados, bytes) or len(dados) == 0:
            raise ErroUpload("DADOS_INVALIDOS")

        partes = sessao["partes"]
        duplicada = indice in partes
        outros = sum(len(v) for k, v in partes.items() if k != indice)
        total = outros + len(dados)
        if total > self._config["tamanho_maximo_bytes"]:
            raise ErroUpload("TAMANHO_EXCEDIDO")

        partes[indice] = dados
        return {
            "recebidas": len(partes),
            "bytes_recebidos": total,
            "duplicada": duplicada,
        }

    def concluir(self, upload_id: str) -> dict:
        sessao = self._sessao_ativa(upload_id)

        partes = sessao["partes"]
        if not partes:
            raise ErroUpload("DADOS_INVALIDOS")
        indices = sorted(partes.keys())
        if indices != list(range(len(indices))):
            raise ErroUpload("DADOS_INVALIDOS")

        conteudo = b"".join(partes[i] for i in indices)

        if len(conteudo) > self._config["tamanho_maximo_bytes"]:
            raise ErroUpload("TAMANHO_EXCEDIDO")

        tipo, ext = self._detectar_tipo(conteudo)
        if tipo not in self._config["tipos_permitidos"]:
            raise ErroUpload("TIPO_NAO_PERMITIDO")

        hash_ = hashlib.sha256(conteudo).hexdigest()
        sessao["situacao"] = "CONCLUIDO"

        existente = self._armazenados.get(hash_)
        if existente is not None:
            return {
                "nome_armazenado": existente["nome_armazenado"],
                "tipo": existente["tipo"],
                "tamanho": existente["tamanho"],
                "hash": hash_,
                "duplicado_de": existente["nome_armazenado"],
            }

        nome_armazenado = f"{uuid.uuid4()}.{ext}"
        registro = {
            "nome_armazenado": nome_armazenado,
            "tipo": tipo,
            "tamanho": len(conteudo),
            "hash": hash_,
        }
        self._armazenados[hash_] = registro
        return {
            "nome_armazenado": nome_armazenado,
            "tipo": tipo,
            "tamanho": len(conteudo),
            "hash": hash_,
            "duplicado_de": None,
        }

    def cancelar(self, upload_id: str) -> None:
        sessao = self._sessao_ativa(upload_id)
        sessao["situacao"] = "CANCELADO"
        return None

    def situacao(self, upload_id: str) -> str:
        sessao = self._sessoes.get(upload_id)
        if sessao is None:
            raise ErroUpload("UPLOAD_NAO_ENCONTRADO")
        self._aplicar_expiracao(sessao)
        return sessao["situacao"]

    def listar(self) -> list[dict]:
        itens = sorted(self._armazenados.values(), key=lambda r: r["nome_armazenado"])
        return [
            {
                "nome_armazenado": r["nome_armazenado"],
                "tipo": r["tipo"],
                "tamanho": r["tamanho"],
                "hash": r["hash"],
            }
            for r in itens
        ]

    def _sessao_ativa(self, upload_id: str) -> dict:
        sessao = self._sessoes.get(upload_id)
        if sessao is None:
            raise ErroUpload("UPLOAD_NAO_ENCONTRADO")
        self._aplicar_expiracao(sessao)
        if sessao["situacao"] != "EM_ANDAMENTO":
            raise ErroUpload("ESTADO_INVALIDO")
        return sessao

    def _aplicar_expiracao(self, sessao: dict) -> None:
        if sessao["situacao"] == "EM_ANDAMENTO":
            agora = self._relogio()
            if agora - sessao["iniciada_em"] >= self._config["ttl_sessao_s"]:
                sessao["situacao"] = "EXPIRADO"

    def _detectar_tipo(self, conteudo: bytes) -> tuple[str, str]:
        for assinatura, tipo, ext in _ASSINATURAS:
            if conteudo.startswith(assinatura):
                return tipo, ext
        raise ErroUpload("ARQUIVO_CORROMPIDO")
