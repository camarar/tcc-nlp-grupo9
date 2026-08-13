"""UC-08 — Controle de acesso com bloqueio e segundo fator."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable


class ErroAcesso(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


class _Usuario:
    def __init__(self, login: str, senha_hash: str, mfa_segredo: str | None) -> None:
        self.login = login
        self.senha_hash = senha_hash
        self.mfa_segredo = mfa_segredo or None
        self.falhas: list[datetime] = []
        self.bloqueado_ate: datetime | None = None
        self.dispositivos_conhecidos: set[str] = set()
        self.eventos: list[dict] = []


class _Desafio:
    def __init__(self, desafio_id: str, login: str, ip: str, dispositivo: str,
                 criado_em: datetime) -> None:
        self.desafio_id = desafio_id
        self.login = login
        self.ip = ip
        self.dispositivo = dispositivo
        self.criado_em = criado_em
        self.usado = False


class _Sessao:
    def __init__(self, sessao_id: str, login: str, expira_em: datetime) -> None:
        self.sessao_id = sessao_id
        self.login = login
        self.expira_em = expira_em
        self.revogada = False


_POLITICA_PADRAO = {
    "max_falhas": 5,
    "janela_falhas_min": 15,
    "bloqueio_min": 30,
    "sessao_min": 60,
    "exigir_mfa_novo_dispositivo": True,
}

_CHAVES_POLITICA_INT = ("max_falhas", "janela_falhas_min", "bloqueio_min", "sessao_min")


class ControleAcesso:
    def __init__(self, relogio: Callable[[], datetime] | None = None) -> None:
        self._relogio = relogio or (lambda: datetime.now(timezone.utc))
        self._politica = dict(_POLITICA_PADRAO)
        self._usuarios: dict[str, _Usuario] = {}
        self._desafios: dict[str, _Desafio] = {}
        self._sessoes: dict[str, _Sessao] = {}

    def _agora(self) -> datetime:
        return self._relogio()

    def configurar_politica(self, politica: dict) -> None:
        nova = {}
        for chave in ("max_falhas", "janela_falhas_min", "bloqueio_min",
                      "sessao_min", "exigir_mfa_novo_dispositivo"):
            if chave not in politica:
                raise ErroAcesso("POLITICA_INVALIDA", f"chave ausente: {chave}")
            nova[chave] = politica[chave]
        for chave in _CHAVES_POLITICA_INT:
            valor = nova[chave]
            if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
                raise ErroAcesso("POLITICA_INVALIDA", f"valor invalido: {chave}")
        self._politica = nova

    def registrar_usuario(self, login: str, senha_hash: str,
                          mfa_segredo: str | None = None) -> None:
        if login in self._usuarios:
            raise ErroAcesso("USUARIO_INVALIDO", "login ja registrado")
        if not senha_hash:
            raise ErroAcesso("USUARIO_INVALIDO", "senha_hash vazio")
        self._usuarios[login] = _Usuario(login, senha_hash, mfa_segredo)

    def _limpar_falhas_expiradas(self, usuario: _Usuario) -> None:
        limite = self._agora() - timedelta(minutes=self._politica["janela_falhas_min"])
        usuario.falhas = [f for f in usuario.falhas if f > limite]

    def _observar_desbloqueio(self, usuario: _Usuario, registrar_evento: bool) -> None:
        if usuario.bloqueado_ate is not None and self._agora() >= usuario.bloqueado_ate:
            usuario.bloqueado_ate = None
            usuario.falhas = []
            if registrar_evento:
                self._registrar_evento(usuario, "DESBLOQUEIO", None, None)

    def _registrar_evento(self, usuario: _Usuario, tipo: str,
                           ip: str | None, dispositivo: str | None) -> None:
        usuario.eventos.append({
            "em": self._agora(),
            "tipo": tipo,
            "ip": ip,
            "dispositivo": dispositivo,
        })

    def _registrar_falha(self, usuario: _Usuario, tipo_evento: str,
                          ip: str | None, dispositivo: str | None) -> bool:
        """Registra falha e evento correspondente. Retorna True se bloqueou agora."""
        agora = self._agora()
        usuario.falhas.append(agora)
        self._limpar_falhas_expiradas(usuario)
        self._registrar_evento(usuario, tipo_evento, ip, dispositivo)
        bloqueou = False
        if len(usuario.falhas) >= self._politica["max_falhas"]:
            usuario.bloqueado_ate = agora + timedelta(minutes=self._politica["bloqueio_min"])
            self._registrar_evento(usuario, "BLOQUEIO", ip, dispositivo)
            bloqueou = True
        return bloqueou

    def autenticar(self, login: str, senha_hash: str,
                   ip: str, dispositivo: str) -> dict:
        usuario = self._usuarios.get(login)
        if usuario is None:
            raise ErroAcesso("CREDENCIAL_INVALIDA", "credenciais invalidas")

        self._observar_desbloqueio(usuario, registrar_evento=True)

        if usuario.bloqueado_ate is not None:
            raise ErroAcesso("CONTA_BLOQUEADA", "conta bloqueada")

        senha_ok = hmac.compare_digest(usuario.senha_hash, senha_hash)
        if not senha_ok:
            self._registrar_falha(usuario, "LOGIN_FALHA", ip, dispositivo)
            raise ErroAcesso("CREDENCIAL_INVALIDA", "credenciais invalidas")

        exige_mfa = (
            usuario.mfa_segredo is not None
            and self._politica["exigir_mfa_novo_dispositivo"]
            and bool(dispositivo)
            and dispositivo not in usuario.dispositivos_conhecidos
        )

        if exige_mfa:
            desafio_id = secrets.token_hex(16)
            for d in self._desafios.values():
                if d.login == login and not d.usado:
                    d.usado = True
            self._desafios[desafio_id] = _Desafio(desafio_id, login, ip, dispositivo,
                                                    self._agora())
            return {
                "status": "MFA_REQUERIDO",
                "sessao_id": None,
                "desafio_id": desafio_id,
                "expira_em": None,
            }

        usuario.falhas = []
        usuario.dispositivos_conhecidos.add(dispositivo)
        self._registrar_evento(usuario, "LOGIN_SUCESSO", ip, dispositivo)
        sessao = self._criar_sessao(login)
        return {
            "status": "AUTENTICADO",
            "sessao_id": sessao.sessao_id,
            "desafio_id": None,
            "expira_em": sessao.expira_em,
        }

    def _criar_sessao(self, login: str) -> _Sessao:
        sessao_id = secrets.token_hex(16)
        expira_em = self._agora() + timedelta(minutes=self._politica["sessao_min"])
        sessao = _Sessao(sessao_id, login, expira_em)
        self._sessoes[sessao_id] = sessao
        return sessao

    def responder_mfa(self, desafio_id: str, codigo: str) -> dict:
        desafio = self._desafios.get(desafio_id)
        if desafio is None:
            raise ErroAcesso("MFA_INVALIDO", "desafio invalido")

        usuario = self._usuarios.get(desafio.login)
        agora = self._agora()
        expirado = agora - desafio.criado_em >= timedelta(minutes=5)

        if desafio.usado or expirado or usuario is None:
            raise ErroAcesso("MFA_INVALIDO", "desafio invalido")

        codigo_esperado = hashlib.sha256(
            (usuario.mfa_segredo + desafio_id).encode()
        ).hexdigest()[-6:]

        if not hmac.compare_digest(codigo_esperado, codigo):
            desafio.usado = True
            self._registrar_falha(usuario, "MFA_FALHA", desafio.ip, desafio.dispositivo)
            raise ErroAcesso("MFA_INVALIDO", "codigo invalido")

        desafio.usado = True
        usuario.falhas = []
        usuario.dispositivos_conhecidos.add(desafio.dispositivo)
        self._registrar_evento(usuario, "MFA_SUCESSO", desafio.ip, desafio.dispositivo)
        self._registrar_evento(usuario, "LOGIN_SUCESSO", desafio.ip, desafio.dispositivo)
        sessao = self._criar_sessao(usuario.login)
        return {
            "status": "AUTENTICADO",
            "sessao_id": sessao.sessao_id,
            "desafio_id": None,
            "expira_em": sessao.expira_em,
        }

    def validar_sessao(self, sessao_id: str) -> dict:
        sessao = self._sessoes.get(sessao_id)
        if sessao is None or sessao.revogada:
            raise ErroAcesso("SESSAO_INVALIDA", "sessao invalida")
        if self._agora() >= sessao.expira_em:
            del self._sessoes[sessao_id]
            raise ErroAcesso("SESSAO_INVALIDA", "sessao expirada")
        return {"login": sessao.login, "expira_em": sessao.expira_em}

    def revogar_sessao(self, sessao_id: str) -> None:
        sessao = self._sessoes.get(sessao_id)
        if sessao is None or sessao.revogada or self._agora() >= sessao.expira_em:
            raise ErroAcesso("SESSAO_INVALIDA", "sessao invalida")
        sessao.revogada = True
        usuario = self._usuarios.get(sessao.login)
        if usuario is not None:
            self._registrar_evento(usuario, "SESSAO_REVOGADA", None, None)

    def revogar_todas(self, login: str) -> int:
        usuario = self._usuarios.get(login)
        if usuario is None:
            raise ErroAcesso("USUARIO_INVALIDO", "usuario inexistente")
        agora = self._agora()
        count = 0
        for sessao in self._sessoes.values():
            if sessao.login == login and not sessao.revogada and agora < sessao.expira_em:
                sessao.revogada = True
                count += 1
                self._registrar_evento(usuario, "SESSAO_REVOGADA", None, None)
        return count

    def situacao(self, login: str) -> dict:
        usuario = self._usuarios.get(login)
        if usuario is None:
            raise ErroAcesso("USUARIO_INVALIDO", "usuario inexistente")
        self._observar_desbloqueio(usuario, registrar_evento=False)
        self._limpar_falhas_expiradas(usuario)
        agora = self._agora()
        sessoes_ativas = sum(
            1 for s in self._sessoes.values()
            if s.login == login and not s.revogada and agora < s.expira_em
        )
        bloqueado = usuario.bloqueado_ate is not None and agora < usuario.bloqueado_ate
        return {
            "bloqueado": bloqueado,
            "falhas": len(usuario.falhas),
            "bloqueado_ate": usuario.bloqueado_ate if bloqueado else None,
            "sessoes_ativas": sessoes_ativas,
        }

    def eventos(self, login: str) -> list[dict]:
        usuario = self._usuarios.get(login)
        if usuario is None:
            raise ErroAcesso("USUARIO_INVALIDO", "usuario inexistente")
        return list(usuario.eventos)
