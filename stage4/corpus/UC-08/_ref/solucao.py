"""UC-08 — Controle de acesso com bloqueio e segundo fator."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable


class ErroAcesso(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code
        self.mensagem = mensagem


_CHAVES_INT = ("max_falhas", "janela_falhas_min", "bloqueio_min", "sessao_min")
_CHAVES_POLITICA = _CHAVES_INT + ("exigir_mfa_novo_dispositivo",)

_POLITICA_PADRAO = {
    "max_falhas": 5,
    "janela_falhas_min": 15,
    "bloqueio_min": 30,
    "sessao_min": 60,
    "exigir_mfa_novo_dispositivo": True,
}

_MINUTOS_EXPIRACAO_DESAFIO = 5


class ControleAcesso:
    def __init__(self, relogio: Callable[[], datetime] | None = None) -> None:
        self._relogio = relogio if relogio is not None else lambda: datetime.now(timezone.utc)
        self._politica = dict(_POLITICA_PADRAO)
        self._usuarios: dict[str, dict] = {}
        self._sessoes: dict[str, dict] = {}
        self._desafios: dict[str, dict] = {}
        self._eventos: dict[str, list[dict]] = {}

    # -- configuração ---------------------------------------------------

    def configurar_politica(self, politica: dict) -> None:
        for chave in _CHAVES_POLITICA:
            if chave not in politica:
                raise ErroAcesso("POLITICA_INVALIDA")
        for chave in _CHAVES_INT:
            valor = politica[chave]
            if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
                raise ErroAcesso("POLITICA_INVALIDA")
        if not isinstance(politica["exigir_mfa_novo_dispositivo"], bool):
            raise ErroAcesso("POLITICA_INVALIDA")
        self._politica = {chave: politica[chave] for chave in _CHAVES_POLITICA}

    def registrar_usuario(self, login: str, senha_hash: str,
                          mfa_segredo: str | None = None) -> None:
        if login in self._usuarios:
            raise ErroAcesso("USUARIO_INVALIDO")
        if not senha_hash:
            raise ErroAcesso("USUARIO_INVALIDO")
        self._usuarios[login] = {
            "senha_hash": senha_hash,
            "mfa_segredo": mfa_segredo,
            "falhas": [],
            "bloqueado_ate": None,
            "dispositivos_conhecidos": set(),
        }

    # -- autenticação -----------------------------------------------------

    def autenticar(self, login: str, senha_hash: str, ip: str, dispositivo: str) -> dict:
        agora = self._relogio()
        usuario = self._usuarios.get(login)
        if usuario is None:
            raise ErroAcesso("CREDENCIAL_INVALIDA")

        if usuario["bloqueado_ate"] is not None:
            if agora < usuario["bloqueado_ate"]:
                raise ErroAcesso("CONTA_BLOQUEADA")
            usuario["bloqueado_ate"] = None
            usuario["falhas"] = []
            self._registrar_evento(login, "DESBLOQUEIO", ip, dispositivo, agora)

        if not hmac.compare_digest(senha_hash, usuario["senha_hash"]):
            self._registrar_falha(login, ip, dispositivo, agora, "LOGIN_FALHA")
            raise ErroAcesso("CREDENCIAL_INVALIDA")

        return self._pos_senha_correta(login, ip, dispositivo, agora)

    def responder_mfa(self, desafio_id: str, codigo: str) -> dict:
        agora = self._relogio()
        desafio = self._desafios.get(desafio_id)
        if desafio is None or desafio["respondido"] or agora >= desafio["expira_em"]:
            raise ErroAcesso("MFA_INVALIDO")

        desafio["respondido"] = True
        login = desafio["login"]
        usuario = self._usuarios[login]
        esperado = hashlib.sha256(
            (usuario["mfa_segredo"] + desafio_id).encode()
        ).hexdigest()[-6:]

        if not hmac.compare_digest(codigo, esperado):
            self._registrar_falha(login, desafio["ip"], desafio["dispositivo"], agora, "MFA_FALHA")
            raise ErroAcesso("MFA_INVALIDO")

        return self._criar_sessao_sucesso(login, desafio["ip"], desafio["dispositivo"],
                                          agora, "MFA_SUCESSO")

    def _pos_senha_correta(self, login: str, ip: str, dispositivo: str, agora: datetime) -> dict:
        usuario = self._usuarios[login]
        precisa_mfa = (
            usuario["mfa_segredo"] is not None
            and self._politica["exigir_mfa_novo_dispositivo"]
            and dispositivo not in usuario["dispositivos_conhecidos"]
        )
        if precisa_mfa:
            desafio_id = uuid.uuid4().hex
            self._desafios[desafio_id] = {
                "login": login,
                "ip": ip,
                "dispositivo": dispositivo,
                "expira_em": agora + timedelta(minutes=_MINUTOS_EXPIRACAO_DESAFIO),
                "respondido": False,
            }
            return {"status": "MFA_REQUERIDO", "sessao_id": None,
                    "desafio_id": desafio_id, "expira_em": None}

        return self._criar_sessao_sucesso(login, ip, dispositivo, agora, "LOGIN_SUCESSO")

    def _criar_sessao_sucesso(self, login: str, ip: str, dispositivo: str,
                              agora: datetime, tipo_evento: str) -> dict:
        usuario = self._usuarios[login]
        usuario["falhas"] = []
        usuario["dispositivos_conhecidos"].add(dispositivo)

        sessao_id = uuid.uuid4().hex
        expira_em = agora + timedelta(minutes=self._politica["sessao_min"])
        self._sessoes[sessao_id] = {"login": login, "expira_em": expira_em, "revogada": False}
        self._registrar_evento(login, tipo_evento, ip, dispositivo, agora)

        return {"status": "AUTENTICADO", "sessao_id": sessao_id,
                "desafio_id": None, "expira_em": expira_em}

    def _registrar_falha(self, login: str, ip: str, dispositivo: str,
                         agora: datetime, tipo_evento: str) -> None:
        usuario = self._usuarios[login]
        usuario["falhas"].append(agora)
        self._registrar_evento(login, tipo_evento, ip, dispositivo, agora)

        janela = timedelta(minutes=self._politica["janela_falhas_min"])
        contagem = sum(1 for ts in usuario["falhas"] if (agora - ts) < janela)
        if contagem >= self._politica["max_falhas"]:
            usuario["bloqueado_ate"] = agora + timedelta(minutes=self._politica["bloqueio_min"])
            self._registrar_evento(login, "BLOQUEIO", ip, dispositivo, agora)

    # -- sessões ----------------------------------------------------------

    def validar_sessao(self, sessao_id: str) -> dict:
        agora = self._relogio()
        sessao = self._sessoes.get(sessao_id)
        if sessao is None or sessao["revogada"]:
            raise ErroAcesso("SESSAO_INVALIDA")
        if agora >= sessao["expira_em"]:
            del self._sessoes[sessao_id]
            raise ErroAcesso("SESSAO_INVALIDA")
        return {"login": sessao["login"], "expira_em": sessao["expira_em"]}

    def revogar_sessao(self, sessao_id: str) -> None:
        agora = self._relogio()
        sessao = self._sessoes.get(sessao_id)
        if sessao is None or sessao["revogada"]:
            raise ErroAcesso("SESSAO_INVALIDA")
        if agora >= sessao["expira_em"]:
            del self._sessoes[sessao_id]
            raise ErroAcesso("SESSAO_INVALIDA")
        sessao["revogada"] = True
        self._registrar_evento(sessao["login"], "SESSAO_REVOGADA", None, None, agora)

    def revogar_todas(self, login: str) -> int:
        agora = self._relogio()
        if login not in self._usuarios:
            raise ErroAcesso("USUARIO_INVALIDO")

        contagem = 0
        for sessao in self._sessoes.values():
            if sessao["login"] == login and not sessao["revogada"] and agora < sessao["expira_em"]:
                sessao["revogada"] = True
                contagem += 1
                self._registrar_evento(login, "SESSAO_REVOGADA", None, None, agora)
        return contagem

    # -- consultas ----------------------------------------------------------

    def situacao(self, login: str) -> dict:
        agora = self._relogio()
        usuario = self._usuarios.get(login)
        if usuario is None:
            raise ErroAcesso("USUARIO_INVALIDO")

        bloqueado = usuario["bloqueado_ate"] is not None and agora < usuario["bloqueado_ate"]
        janela = timedelta(minutes=self._politica["janela_falhas_min"])
        falhas = sum(1 for ts in usuario["falhas"] if (agora - ts) < janela)
        sessoes_ativas = sum(
            1 for s in self._sessoes.values()
            if s["login"] == login and not s["revogada"] and agora < s["expira_em"]
        )
        return {
            "bloqueado": bloqueado,
            "falhas": falhas,
            "bloqueado_ate": usuario["bloqueado_ate"] if bloqueado else None,
            "sessoes_ativas": sessoes_ativas,
        }

    def eventos(self, login: str) -> list[dict]:
        if login not in self._usuarios:
            raise ErroAcesso("USUARIO_INVALIDO")
        return [dict(evento) for evento in self._eventos.get(login, [])]

    def _registrar_evento(self, login: str, tipo: str, ip: str | None,
                          dispositivo: str | None, agora: datetime) -> None:
        self._eventos.setdefault(login, []).append({
            "em": agora,
            "tipo": tipo,
            "ip": ip,
            "dispositivo": dispositivo,
        })
