"""UC-13 — Controle de estoque multi-depósito com reserva."""

from __future__ import annotations

import itertools
import threading
import time
import uuid
from typing import Callable


class ErroEstoque(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


_TTL_PADRAO = 900.0


class _Deposito:
    __slots__ = ("deposito_id", "prioridade", "fisico")

    def __init__(self, deposito_id: str, prioridade: int) -> None:
        self.deposito_id = deposito_id
        self.prioridade = prioridade
        self.fisico: dict[str, int] = {}


class _Reserva:
    __slots__ = ("reserva_id", "criada_em", "ttl", "estado", "alocacao")

    def __init__(self, reserva_id: str, criada_em: float, ttl: float,
                 alocacao: dict[str, dict[str, int]]) -> None:
        self.reserva_id = reserva_id
        self.criada_em = criada_em
        self.ttl = ttl
        self.estado = "ativa"
        self.alocacao = alocacao


class Estoque:
    def __init__(self, relogio: Callable[[], float] | None = None) -> None:
        self._relogio = relogio if relogio is not None else time.monotonic
        self._lock = threading.Lock()
        self._depositos: dict[str, _Deposito] = {}
        self._skus_conhecidos: set[str] = set()
        self._reservas: dict[str, _Reserva] = {}
        self._contador = itertools.count(1)

    # ------------------------------------------------------------------
    # Internos (chamados sempre dentro do lock)
    # ------------------------------------------------------------------

    def _expirar_vencidas(self, agora: float) -> int:
        count = 0
        for reserva in self._reservas.values():
            if reserva.estado == "ativa" and agora - reserva.criada_em >= reserva.ttl:
                reserva.estado = "expirada"
                count += 1
        return count

    def _reservado_total(self, sku: str, deposito_id: str) -> int:
        total = 0
        for reserva in self._reservas.values():
            if reserva.estado != "ativa":
                continue
            total += reserva.alocacao.get(deposito_id, {}).get(sku, 0)
        return total

    def _disponivel_deposito(self, sku: str, deposito_id: str) -> int:
        dep = self._depositos[deposito_id]
        fisico = dep.fisico.get(sku, 0)
        reservado = self._reservado_total(sku, deposito_id)
        return fisico - reservado

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def registrar_deposito(self, deposito_id: str, prioridade: int) -> None:
        with self._lock:
            self._expirar_vencidas(self._relogio())
            if not deposito_id or prioridade < 0:
                raise ErroEstoque("DADOS_INVALIDOS")
            existente = self._depositos.get(deposito_id)
            if existente is not None:
                existente.prioridade = prioridade
            else:
                self._depositos[deposito_id] = _Deposito(deposito_id, prioridade)

    def repor(self, deposito_id: str, sku: str, quantidade: int) -> int:
        with self._lock:
            self._expirar_vencidas(self._relogio())
            if quantidade < 1:
                raise ErroEstoque("DADOS_INVALIDOS")
            dep = self._depositos.get(deposito_id)
            if dep is None:
                raise ErroEstoque("DEPOSITO_DESCONHECIDO")
            dep.fisico[sku] = dep.fisico.get(sku, 0) + quantidade
            self._skus_conhecidos.add(sku)
            return dep.fisico[sku]

    def disponivel(self, sku: str, deposito_id: str | None = None) -> int:
        with self._lock:
            self._expirar_vencidas(self._relogio())
            if sku not in self._skus_conhecidos:
                raise ErroEstoque("SKU_DESCONHECIDO")
            if deposito_id is None:
                return sum(
                    self._disponivel_deposito(sku, dep_id)
                    for dep_id in self._depositos
                )
            if deposito_id not in self._depositos:
                return 0
            return self._disponivel_deposito(sku, deposito_id)

    def posicao(self, sku: str) -> dict:
        with self._lock:
            self._expirar_vencidas(self._relogio())
            if sku not in self._skus_conhecidos:
                raise ErroEstoque("SKU_DESCONHECIDO")
            resultado = {}
            for dep_id, dep in self._depositos.items():
                fisico = dep.fisico.get(sku, 0)
                reservado = self._reservado_total(sku, dep_id)
                resultado[dep_id] = {
                    "fisico": fisico,
                    "reservado": reservado,
                    "disponivel": fisico - reservado,
                }
            return resultado

    def reservar(self, itens: list[dict], ttl_s: float | None = None) -> str:
        with self._lock:
            agora = self._relogio()
            self._expirar_vencidas(agora)

            # Categoria 1: DADOS_INVALIDOS
            if not itens:
                raise ErroEstoque("DADOS_INVALIDOS")
            vistos: set[str] = set()
            for item in itens:
                sku = item.get("sku")
                quantidade = item.get("quantidade")
                if not sku or quantidade is None or quantidade < 1:
                    raise ErroEstoque("DADOS_INVALIDOS")
                if sku in vistos:
                    raise ErroEstoque("DADOS_INVALIDOS")
                vistos.add(sku)
            if ttl_s is not None and ttl_s <= 0:
                raise ErroEstoque("DADOS_INVALIDOS")

            # Categoria 2: SKU_DESCONHECIDO
            for item in itens:
                if item["sku"] not in self._skus_conhecidos:
                    raise ErroEstoque("SKU_DESCONHECIDO")

            # Categoria 3: ESTOQUE_INSUFICIENTE (agregado por sku)
            depositos_ordenados = sorted(
                self._depositos.values(),
                key=lambda d: d.prioridade,
            )
            alocacao_planejada: dict[str, dict[str, int]] = {}
            for item in itens:
                sku = item["sku"]
                quantidade_restante = item["quantidade"]
                disponiveis = sorted(
                    depositos_ordenados,
                    key=lambda d: (
                        d.prioridade,
                        -self._disponivel_deposito(sku, d.deposito_id),
                        d.deposito_id,
                    ),
                )
                for dep in disponiveis:
                    if quantidade_restante <= 0:
                        break
                    disp = self._disponivel_deposito(sku, dep.deposito_id)
                    if disp <= 0:
                        continue
                    usado = min(disp, quantidade_restante)
                    alocacao_planejada.setdefault(dep.deposito_id, {})[sku] = (
                        alocacao_planejada.setdefault(dep.deposito_id, {}).get(sku, 0) + usado
                    )
                    quantidade_restante -= usado
                if quantidade_restante > 0:
                    raise ErroEstoque("ESTOQUE_INSUFICIENTE")

            ttl = ttl_s if ttl_s is not None else _TTL_PADRAO
            reserva_id = f"r{next(self._contador)}-{uuid.uuid4().hex}"
            self._reservas[reserva_id] = _Reserva(reserva_id, agora, ttl, alocacao_planejada)
            return reserva_id

    def confirmar(self, reserva_id: str) -> dict:
        with self._lock:
            self._expirar_vencidas(self._relogio())
            reserva = self._reservas.get(reserva_id)
            if reserva is None:
                raise ErroEstoque("RESERVA_NAO_ENCONTRADA")
            if reserva.estado != "ativa":
                raise ErroEstoque("ESTADO_INVALIDO")
            for dep_id, skus in reserva.alocacao.items():
                dep = self._depositos[dep_id]
                for sku, quantidade in skus.items():
                    dep.fisico[sku] = dep.fisico.get(sku, 0) - quantidade
            reserva.estado = "confirmada"
            return {"alocacao": {d: dict(s) for d, s in reserva.alocacao.items()}}

    def cancelar(self, reserva_id: str) -> None:
        with self._lock:
            self._expirar_vencidas(self._relogio())
            reserva = self._reservas.get(reserva_id)
            if reserva is None:
                raise ErroEstoque("RESERVA_NAO_ENCONTRADA")
            if reserva.estado != "ativa":
                raise ErroEstoque("ESTADO_INVALIDO")
            reserva.estado = "cancelada"

    def transferir(self, sku: str, origem: str, destino: str, quantidade: int) -> None:
        with self._lock:
            self._expirar_vencidas(self._relogio())
            if origem == destino:
                raise ErroEstoque("DADOS_INVALIDOS")
            if quantidade < 1:
                raise ErroEstoque("DADOS_INVALIDOS")
            if origem not in self._depositos or destino not in self._depositos:
                raise ErroEstoque("DEPOSITO_DESCONHECIDO")
            if sku not in self._skus_conhecidos:
                raise ErroEstoque("SKU_DESCONHECIDO")
            disp_origem = self._disponivel_deposito(sku, origem)
            if quantidade > disp_origem:
                raise ErroEstoque("ESTOQUE_INSUFICIENTE")
            dep_origem = self._depositos[origem]
            dep_destino = self._depositos[destino]
            dep_origem.fisico[sku] = dep_origem.fisico.get(sku, 0) - quantidade
            dep_destino.fisico[sku] = dep_destino.fisico.get(sku, 0) + quantidade

    def expirar(self) -> int:
        with self._lock:
            return self._expirar_vencidas(self._relogio())
