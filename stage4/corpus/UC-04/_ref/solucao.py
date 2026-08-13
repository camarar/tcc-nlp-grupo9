"""UC-04 — Limitador de requisições multi-plano.

Janela deslizante com registro de eventos (sliding window log), por cliente
e por organização, com precedência cliente -> organização e serialização
por um único threading.Lock.
"""

from __future__ import annotations

import threading
import time
from typing import Callable


class ErroLimite(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


class _Contador:
    __slots__ = ("limite", "janela_s", "registros")

    def __init__(self, limite: int, janela_s: float) -> None:
        self.limite = limite
        self.janela_s = janela_s
        self.registros: list[tuple[float, int]] = []

    def purgar(self, agora: float) -> None:
        janela_s = self.janela_s
        self.registros = [
            (instante, custo)
            for instante, custo in self.registros
            if agora - instante < janela_s
        ]

    def consumo(self) -> int:
        return sum(custo for _, custo in self.registros)

    def retry_after(self, consumo_atual: int, custo: int, agora: float) -> float:
        alvo = consumo_atual + custo - self.limite
        acumulado = 0
        for instante, custo_r in self.registros:
            acumulado += custo_r
            if acumulado >= alvo:
                return round(max(0.0, (instante + self.janela_s) - agora), 3)
        return 0.0


class _Cliente:
    __slots__ = ("plano", "organizacao", "contador")

    def __init__(self, plano: str, organizacao: str | None, contador: _Contador) -> None:
        self.plano = plano
        self.organizacao = organizacao
        self.contador = contador


class Limitador:
    def __init__(self, relogio: Callable[[], float] | None = None) -> None:
        self._relogio = relogio or time.monotonic
        self._lock = threading.Lock()
        self._planos: dict[str, dict] = {}
        self._organizacoes: dict[str, _Contador] = {}
        self._clientes: dict[str, _Cliente] = {}

    @staticmethod
    def _validar_config_plano(config: dict) -> None:
        try:
            limite = config["limite"]
            janela_s = config["janela_s"]
            burst = config["burst"]
        except KeyError:
            raise ErroLimite("CONFIGURACAO_INVALIDA", "chave obrigatória ausente")
        if limite < 1 or janela_s <= 0 or burst < 1:
            raise ErroLimite("CONFIGURACAO_INVALIDA")

    @staticmethod
    def _validar_config_organizacao(config: dict) -> None:
        try:
            limite = config["limite"]
            janela_s = config["janela_s"]
        except KeyError:
            raise ErroLimite("CONFIGURACAO_INVALIDA", "chave obrigatória ausente")
        if limite < 1 or janela_s <= 0:
            raise ErroLimite("CONFIGURACAO_INVALIDA")

    def registrar_plano(self, nome: str, config: dict) -> None:
        with self._lock:
            self._validar_config_plano(config)
            self._planos[nome] = dict(config)

    def registrar_organizacao(self, org_id: str, config: dict) -> None:
        with self._lock:
            self._validar_config_organizacao(config)
            existente = self._organizacoes.get(org_id)
            if existente is not None:
                existente.limite = config["limite"]
                existente.janela_s = config["janela_s"]
            else:
                self._organizacoes[org_id] = _Contador(config["limite"], config["janela_s"])

    def registrar_cliente(self, client_id: str, plano: str,
                          organizacao: str | None = None) -> None:
        with self._lock:
            plano_cfg = self._planos.get(plano)
            if plano_cfg is None:
                raise ErroLimite("PLANO_DESCONHECIDO")
            if organizacao is not None and organizacao not in self._organizacoes:
                raise ErroLimite("ORGANIZACAO_DESCONHECIDA")
            contador = _Contador(plano_cfg["limite"], plano_cfg["janela_s"])
            self._clientes[client_id] = _Cliente(plano, organizacao, contador)

    def _obter_cliente(self, client_id: str) -> _Cliente:
        cliente = self._clientes.get(client_id)
        if cliente is None:
            raise ErroLimite("CLIENTE_DESCONHECIDO")
        return cliente

    def permitir(self, client_id: str, custo: int = 1) -> dict:
        with self._lock:
            agora = self._relogio()
            cliente = self._obter_cliente(client_id)
            plano_cfg = self._planos[cliente.plano]
            burst = plano_cfg["burst"]
            if custo < 1 or custo > burst:
                raise ErroLimite("CUSTO_INVALIDO")

            contador_cli = cliente.contador
            contador_cli.limite = plano_cfg["limite"]
            contador_cli.janela_s = plano_cfg["janela_s"]
            contador_cli.purgar(agora)
            consumo_cli = contador_cli.consumo()

            if consumo_cli + custo > contador_cli.limite:
                restante = max(0, contador_cli.limite - consumo_cli)
                retry_after = contador_cli.retry_after(consumo_cli, custo, agora)
                return {
                    "permitido": False,
                    "restante": restante,
                    "retry_after": retry_after,
                    "limitante": "CLIENTE",
                }

            contador_org: _Contador | None = None
            consumo_org = 0
            if cliente.organizacao is not None:
                contador_org = self._organizacoes[cliente.organizacao]
                contador_org.purgar(agora)
                consumo_org = contador_org.consumo()
                if consumo_org + custo > contador_org.limite:
                    restante = max(0, contador_org.limite - consumo_org)
                    retry_after = contador_org.retry_after(consumo_org, custo, agora)
                    return {
                        "permitido": False,
                        "restante": restante,
                        "retry_after": retry_after,
                        "limitante": "ORGANIZACAO",
                    }

            contador_cli.registros.append((agora, custo))
            restante_cli = contador_cli.limite - (consumo_cli + custo)
            restante = restante_cli
            if contador_org is not None:
                contador_org.registros.append((agora, custo))
                restante_org = contador_org.limite - (consumo_org + custo)
                restante = min(restante_cli, restante_org)

            return {
                "permitido": True,
                "restante": max(0, restante),
                "retry_after": 0.0,
                "limitante": None,
            }

    def consumo(self, client_id: str) -> dict:
        with self._lock:
            agora = self._relogio()
            cliente = self._obter_cliente(client_id)
            cliente.contador.purgar(agora)
            resultado_cliente = cliente.contador.consumo()
            resultado_organizacao = None
            if cliente.organizacao is not None:
                contador_org = self._organizacoes[cliente.organizacao]
                contador_org.purgar(agora)
                resultado_organizacao = contador_org.consumo()
            return {"cliente": resultado_cliente, "organizacao": resultado_organizacao}

    def redefinir(self, client_id: str) -> None:
        with self._lock:
            cliente = self._obter_cliente(client_id)
            cliente.contador.registros = []
