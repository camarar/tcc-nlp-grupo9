"""UC-20 — Gestor de credenciais com política e rotação."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Callable

_ORDEM_VIOLACOES = ("COMPRIMENTO", "CLASSES", "COMUM", "REPETICAO", "SEQUENCIA")

_POLITICA_PADRAO = {
    "min_caracteres": 12,
    "classes_minimas": 3,
    "historico": 5,
    "rotacao_dias": 90,
    "tolerancia_dias": 7,
    "comuns": ["senha123", "password", "123456", "qwerty", "admin"],
}


class ErroCredencial(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


def _tem_repeticao(senha: str) -> bool:
    corrida = 1
    for i in range(1, len(senha)):
        if senha[i] == senha[i - 1]:
            corrida += 1
            if corrida >= 4:
                return True
        else:
            corrida = 1
    return False


def _tem_sequencia(senha: str) -> bool:
    crescente = 1
    decrescente = 1
    for i in range(1, len(senha)):
        delta = ord(senha[i]) - ord(senha[i - 1])
        if delta == 1:
            crescente += 1
            decrescente = 1
        elif delta == -1:
            decrescente += 1
            crescente = 1
        else:
            crescente = 1
            decrescente = 1
        if crescente >= 4 or decrescente >= 4:
            return True
    return False


def _contar_classes(senha: str) -> int:
    tem_minuscula = tem_maiuscula = tem_digito = tem_simbolo = False
    for c in senha:
        if c.isdigit():
            tem_digito = True
        elif c.isalpha():
            if c.islower():
                tem_minuscula = True
            else:
                tem_maiuscula = True
        else:
            tem_simbolo = True
    return sum((tem_minuscula, tem_maiuscula, tem_digito, tem_simbolo))


class GestorCredenciais:
    def __init__(self, relogio: Callable[[], datetime] | None = None) -> None:
        self._relogio = relogio or (lambda: datetime.now(timezone.utc))
        self._politicas: dict[str, dict] = {}
        self._usuarios: dict[str, dict] = {}

    def definir_politica(self, perfil: str, politica: dict) -> None:
        if not perfil:
            raise ErroCredencial("POLITICA_INVALIDA", "perfil vazio")

        mesclada = {**_POLITICA_PADRAO, **politica}

        if mesclada["min_caracteres"] < 8:
            raise ErroCredencial("POLITICA_INVALIDA", "min_caracteres menor que 8")
        if mesclada["classes_minimas"] not in (1, 2, 3, 4):
            raise ErroCredencial("POLITICA_INVALIDA", "classes_minimas fora de 1..4")
        if mesclada["historico"] < 1:
            raise ErroCredencial("POLITICA_INVALIDA", "historico menor que 1")
        if mesclada["rotacao_dias"] < 1:
            raise ErroCredencial("POLITICA_INVALIDA", "rotacao_dias menor que 1")
        if mesclada["tolerancia_dias"] < 0:
            raise ErroCredencial("POLITICA_INVALIDA", "tolerancia_dias negativo")
        comuns = mesclada["comuns"]
        if not isinstance(comuns, list) or not all(isinstance(x, str) for x in comuns):
            raise ErroCredencial("POLITICA_INVALIDA", "comuns deve ser lista de strings")

        mesclada["comuns"] = list(comuns)
        self._politicas[perfil] = mesclada

    def criar_usuario(self, login: str, perfil: str) -> None:
        if not login or login in self._usuarios:
            raise ErroCredencial("USUARIO_INVALIDO", "login vazio ou já existente")
        if perfil not in self._politicas:
            raise ErroCredencial("USUARIO_INVALIDO", "perfil sem política definida")

        self._usuarios[login] = {
            "perfil": perfil,
            "senha_hash": None,
            "historico_hashes": [],
            "definida_em": None,
            "expira_em": None,
            "trocas": 0,
            "tolerancia_dias": None,
        }

    def avaliar(self, senha: str, perfil: str) -> list[str]:
        politica = self._politicas.get(perfil)
        if politica is None:
            raise ErroCredencial("POLITICA_INVALIDA", "perfil sem política definida")

        violacoes = set()
        if len(senha) < politica["min_caracteres"]:
            violacoes.add("COMPRIMENTO")
        if _contar_classes(senha) < politica["classes_minimas"]:
            violacoes.add("CLASSES")
        if senha.lower() in {c.lower() for c in politica["comuns"]}:
            violacoes.add("COMUM")
        if _tem_repeticao(senha):
            violacoes.add("REPETICAO")
        if _tem_sequencia(senha):
            violacoes.add("SEQUENCIA")

        return [v for v in _ORDEM_VIOLACOES if v in violacoes]

    def _hash(self, login: str, senha: str) -> str:
        salt = hashlib.sha256(login.encode()).hexdigest()[:16].encode()
        return hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, 100000).hex()

    def _usuario(self, login: str) -> dict:
        usuario = self._usuarios.get(login)
        if usuario is None:
            raise ErroCredencial("USUARIO_INVALIDO", "login inexistente")
        return usuario

    def definir_senha(self, login: str, senha: str) -> dict:
        usuario = self._usuario(login)
        perfil = usuario["perfil"]
        politica = self._politicas[perfil]

        violacoes = self.avaliar(senha, perfil)
        if violacoes:
            raise ErroCredencial("SENHA_FRACA", "senha não atende à política")

        hash_ = self._hash(login, senha)
        if hash_ in usuario["historico_hashes"]:
            raise ErroCredencial("SENHA_REUTILIZADA", "senha já usada recentemente")

        historico = usuario["historico_hashes"] + [hash_]
        usuario["historico_hashes"] = historico[-politica["historico"]:]

        agora = self._relogio()
        usuario["senha_hash"] = hash_
        usuario["definida_em"] = agora
        usuario["expira_em"] = agora + timedelta(days=politica["rotacao_dias"])
        usuario["tolerancia_dias"] = politica["tolerancia_dias"]
        usuario["trocas"] += 1

        return {"expira_em": usuario["expira_em"], "trocas": usuario["trocas"]}

    def autenticar(self, login: str, senha: str) -> dict:
        usuario = self._usuario(login)
        if usuario["senha_hash"] is None:
            raise ErroCredencial("ESTADO_INVALIDO", "usuário sem senha definida")

        agora = self._relogio()
        expira_em = usuario["expira_em"]
        fim_tolerancia = expira_em + timedelta(days=usuario["tolerancia_dias"])

        expirada = agora >= expira_em
        em_tolerancia = expirada and agora < fim_tolerancia
        dias_para_expirar = (expira_em - agora).days

        senha_correta = self._hash(login, senha) == usuario["senha_hash"]
        if not expirada:
            autenticado = senha_correta
        elif em_tolerancia:
            autenticado = senha_correta
        else:
            autenticado = False

        return {
            "autenticado": autenticado,
            "expirada": expirada,
            "em_tolerancia": em_tolerancia,
            "dias_para_expirar": dias_para_expirar,
        }

    def situacao(self, login: str) -> dict:
        usuario = self._usuario(login)

        if usuario["senha_hash"] is None:
            return {
                "perfil": usuario["perfil"],
                "definida_em": None,
                "expira_em": None,
                "trocas": 0,
                "expirada": False,
                "em_tolerancia": False,
            }

        agora = self._relogio()
        expira_em = usuario["expira_em"]
        fim_tolerancia = expira_em + timedelta(days=usuario["tolerancia_dias"])
        expirada = agora >= expira_em
        em_tolerancia = expirada and agora < fim_tolerancia

        return {
            "perfil": usuario["perfil"],
            "definida_em": usuario["definida_em"],
            "expira_em": expira_em,
            "trocas": usuario["trocas"],
            "expirada": expirada,
            "em_tolerancia": em_tolerancia,
        }
