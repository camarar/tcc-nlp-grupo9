"""UC-04 — Limitador de requisições multi-plano."""

from __future__ import annotations

import threading
import time
from typing import Callable


class ErroLimite(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


class _Plano:
    __slots__ = ("limite", "janela_s", "burst")

    def __init__(self, limite: int, janela_s: float, burst: int) -> None:
        self.limite = limite
        self.janela_s = janela_s
        self.burst = burst


class _Organizacao:
    __slots__ = ("limite", "janela_s", "registros")

    def __init__(self, limite: int, janela_s: float) -> None:
        self.limite = limite
        self.janela_s = janela_s
        self.registros: list[list[float | int]] = []


class _Cliente:
    __slots__ = ("plano", "organizacao", "registros")

    def __init__(self, plano: str, organizacao: str | None) -> None:
        self.plano = plano
        self.organizacao = organizacao
        self.registros: list[list[float | int]] = []


def _validar_config_plano(config: dict) -> None:
    for chave in ("limite", "janela_s", "burst"):
        if chave not in config:
            raise ErroLimite(code="CONFIGURACAO_INVALIDA",
                              mensagem=f"chave ausente: {chave}")
    if config["limite"] < 1:
        raise ErroLimite(code="CONFIGURACAO_INVALIDA", mensagem="limite < 1")
    if config["janela_s"] <= 0:
        raise ErroLimite(code="CONFIGURACAO_INVALIDA", mensagem="janela_s <= 0")
    if config["burst"] < 1:
        raise ErroLimite(code="CONFIGURACAO_INVALIDA", mensagem="burst < 1")


def _validar_config_organizacao(config: dict) -> None:
    for chave in ("limite", "janela_s"):
        if chave not in config:
            raise ErroLimite(code="CONFIGURACAO_INVALIDA",
                              mensagem=f"chave ausente: {chave}")
    if config["limite"] < 1:
        raise ErroLimite(code="CONFIGURACAO_INVALIDA", mensagem="limite < 1")
    if config["janela_s"] <= 0:
        raise ErroLimite(code="CONFIGURACAO_INVALIDA", mensagem="janela_s <= 0")


def _expurgar(registros: list, agora: float, janela_s: float) -> None:
    while registros and (agora - registros[0][0]) >= janela_s:
        registros.pop(0)


def _consumo_atual(registros: list) -> int:
    return sum(custo for _, custo in registros)


def _retry_after(registros: list, agora: float, janela_s: float,
                  consumo_atual: int, custo: int, limite: int) -> float:
    alvo = consumo_atual + custo - limite
    acumulado = 0
    for instante, c in registros:
        acumulado += c
        if acumulado >= alvo:
            valor = (instante + janela_s) - agora
            return max(0.0, round(valor, 3))
    return 0.0


class Limitador:
    def __init__(self, relogio: Callable[[], float] | None = None) -> None:
        self._relogio = relogio if relogio is not None else time.monotonic
        self._lock = threading.Lock()
        self._planos: dict[str, _Plano] = {}
        self._organizacoes: dict[str, _Organizacao] = {}
        self._clientes: dict[str, _Cliente] = {}

    def registrar_plano(self, nome: str, config: dict) -> None:
        _validar_config_plano(config)
        with self._lock:
            self._planos[nome] = _Plano(config["limite"], config["janela_s"], config["burst"])

    def registrar_organizacao(self, org_id: str, config: dict) -> None:
        _validar_config_organizacao(config)
        with self._lock:
            if org_id in self._organizacoes:
                org = self._organizacoes[org_id]
                org.limite = config["limite"]
                org.janela_s = config["janela_s"]
            else:
                self._organizacoes[org_id] = _Organizacao(config["limite"], config["janela_s"])

    def registrar_cliente(self, client_id: str, plano: str,
                          organizacao: str | None = None) -> None:
        with self._lock:
            if plano not in self._planos:
                raise ErroLimite(code="PLANO_DESCONHECIDO", mensagem=plano)
            if organizacao is not None and organizacao not in self._organizacoes:
                raise ErroLimite(code="ORGANIZACAO_DESCONHECIDA", mensagem=organizacao)
            self._clientes[client_id] = _Cliente(plano, organizacao)

    def permitir(self, client_id: str, custo: int = 1) -> dict:
        with self._lock:
            agora = self._relogio()
            cliente = self._clientes.get(client_id)
            if cliente is None:
                raise ErroLimite(code="CLIENTE_DESCONHECIDO", mensagem=client_id)

            plano = self._planos[cliente.plano]

            if custo > plano.burst or custo < 1:
                raise ErroLimite(code="CUSTO_INVALIDO", mensagem=str(custo))

            _expurgar(cliente.registros, agora, plano.janela_s)
            consumo_cliente = _consumo_atual(cliente.registros)

            org = None
            if cliente.organizacao is not None:
                org = self._organizacoes[cliente.organizacao]
                _expurgar(org.registros, agora, org.janela_s)

            if consumo_cliente + custo > plano.limite:
                restante = max(0, plano.limite - consumo_cliente)
                retry_after = _retry_after(cliente.registros, agora, plano.janela_s,
                                            consumo_cliente, custo, plano.limite)
                return {"permitido": False, "restante": restante,
                        "retry_after": retry_after, "limitante": "CLIENTE"}

            if org is not None:
                consumo_org = _consumo_atual(org.registros)
                if consumo_org + custo > org.limite:
                    restante = max(0, org.limite - consumo_org)
                    retry_after = _retry_after(org.registros, agora, org.janela_s,
                                                consumo_org, custo, org.limite)
                    return {"permitido": False, "restante": restante,
                            "retry_after": retry_after, "limitante": "ORGANIZACAO"}

            cliente.registros.append([agora, custo])
            restante_cliente = max(0, plano.limite - (consumo_cliente + custo))
            restante = restante_cliente
            if org is not None:
                org.registros.append([agora, custo])
                consumo_org = _consumo_atual(org.registros)
                restante_org = max(0, org.limite - consumo_org)
                restante = min(restante_cliente, restante_org)

            return {"permitido": True, "restante": restante,
                    "retry_after": 0.0, "limitante": None}

    def consumo(self, client_id: str) -> dict:
        with self._lock:
            agora = self._relogio()
            cliente = self._clientes.get(client_id)
            if cliente is None:
                raise ErroLimite(code="CLIENTE_DESCONHECIDO", mensagem=client_id)

            plano = self._planos[cliente.plano]
            _expurgar(cliente.registros, agora, plano.janela_s)
            consumo_cliente = _consumo_atual(cliente.registros)

            consumo_org = None
            if cliente.organizacao is not None:
                org = self._organizacoes[cliente.organizacao]
                _expurgar(org.registros, agora, org.janela_s)
                consumo_org = _consumo_atual(org.registros)

            return {"cliente": consumo_cliente, "organizacao": consumo_org}

    def redefinir(self, client_id: str) -> None:
        with self._lock:
            cliente = self._clientes.get(client_id)
            if cliente is None:
                raise ErroLimite(code="CLIENTE_DESCONHECIDO", mensagem=client_id)
            cliente.registros.clear()
