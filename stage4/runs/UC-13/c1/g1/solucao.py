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


TTL_PADRAO_S = 900.0


class _Deposito:
    __slots__ = ("deposito_id", "prioridade", "fisico", "reservado")

    def __init__(self, deposito_id: str, prioridade: int) -> None:
        self.deposito_id = deposito_id
        self.prioridade = prioridade
        self.fisico: dict[str, int] = {}
        self.reservado: dict[str, int] = {}


class _Reserva:
    __slots__ = ("reserva_id", "itens", "alocacao", "criada_em", "ttl", "estado")

    def __init__(self, reserva_id: str, itens: list[dict], alocacao: dict,
                 criada_em: float, ttl: float) -> None:
        self.reserva_id = reserva_id
        self.itens = itens
        self.alocacao = alocacao  # {deposito_id: {sku: quantidade}}
        self.criada_em = criada_em
        self.ttl = ttl
        self.estado = "ativa"  # ativa | confirmada | cancelada | expirada


class Estoque:
    def __init__(self, relogio: Callable[[], float] | None = None) -> None:
        self._relogio = relogio if relogio is not None else time.monotonic
        self._lock = threading.Lock()
        self._depositos: dict[str, _Deposito] = {}
        self._skus_conhecidos: set[str] = set()
        self._reservas: dict[str, _Reserva] = {}
        self._contador = itertools.count(1)

    # ------------------------------------------------------------------
    # Internos (assumem lock já adquirido)
    # ------------------------------------------------------------------

    def _expirar_vencidas(self) -> int:
        agora = self._relogio()
        n = 0
        for reserva in self._reservas.values():
            if reserva.estado != "ativa":
                continue
            if agora - reserva.criada_em >= reserva.ttl:
                self._liberar_reserva(reserva)
                reserva.estado = "expirada"
                n += 1
        return n

    def _liberar_reserva(self, reserva: _Reserva) -> None:
        for deposito_id, skus in reserva.alocacao.items():
            deposito = self._depositos.get(deposito_id)
            if deposito is None:
                continue
            for sku, quantidade in skus.items():
                deposito.reservado[sku] = deposito.reservado.get(sku, 0) - quantidade

    def _disponivel_deposito(self, deposito: _Deposito, sku: str) -> int:
        fisico = deposito.fisico.get(sku, 0)
        reservado = deposito.reservado.get(sku, 0)
        return fisico - reservado

    def _disponivel_total(self, sku: str) -> int:
        return sum(self._disponivel_deposito(d, sku) for d in self._depositos.values())

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def registrar_deposito(self, deposito_id: str, prioridade: int) -> None:
        with self._lock:
            self._expirar_vencidas()
            if not deposito_id or prioridade < 0:
                raise ErroEstoque("DADOS_INVALIDOS")
            existente = self._depositos.get(deposito_id)
            if existente is None:
                self._depositos[deposito_id] = _Deposito(deposito_id, prioridade)
            else:
                existente.prioridade = prioridade

    def repor(self, deposito_id: str, sku: str, quantidade: int) -> int:
        with self._lock:
            self._expirar_vencidas()
            deposito = self._depositos.get(deposito_id)
            if deposito is None:
                raise ErroEstoque("DEPOSITO_DESCONHECIDO")
            if quantidade < 1:
                raise ErroEstoque("DADOS_INVALIDOS")
            deposito.fisico[sku] = deposito.fisico.get(sku, 0) + quantidade
            self._skus_conhecidos.add(sku)
            return deposito.fisico[sku]

    def disponivel(self, sku: str, deposito_id: str | None = None) -> int:
        with self._lock:
            self._expirar_vencidas()
            if sku not in self._skus_conhecidos:
                raise ErroEstoque("SKU_DESCONHECIDO")
            if deposito_id is None:
                return self._disponivel_total(sku)
            deposito = self._depositos.get(deposito_id)
            if deposito is None:
                raise ErroEstoque("DEPOSITO_DESCONHECIDO")
            return self._disponivel_deposito(deposito, sku)

    def reservar(self, itens: list[dict], ttl_s: float | None = None) -> str:
        with self._lock:
            self._expirar_vencidas()

            # G-14: (1) DADOS_INVALIDOS
            if not itens:
                raise ErroEstoque("DADOS_INVALIDOS")
            if ttl_s is not None and ttl_s <= 0:
                raise ErroEstoque("DADOS_INVALIDOS")
            skus_vistos: set[str] = set()
            for item in itens:
                sku = item.get("sku")
                quantidade = item.get("quantidade")
                if not sku or quantidade is None or quantidade < 1:
                    raise ErroEstoque("DADOS_INVALIDOS")
                if sku in skus_vistos:
                    raise ErroEstoque("DADOS_INVALIDOS")
                skus_vistos.add(sku)

            # (2) SKU_DESCONHECIDO
            for item in itens:
                if item["sku"] not in self._skus_conhecidos:
                    raise ErroEstoque("SKU_DESCONHECIDO")

            # (3) ESTOQUE_INSUFICIENTE
            for item in itens:
                if self._disponivel_total(item["sku"]) < item["quantidade"]:
                    raise ErroEstoque("ESTOQUE_INSUFICIENTE")

            # Alocação (G-05)
            alocacao: dict[str, dict[str, int]] = {}
            depositos_ordenados = sorted(
                self._depositos.values(),
                key=lambda d: d.deposito_id,
            )
            for item in itens:
                sku = item["sku"]
                restante = item["quantidade"]
                ordem = sorted(
                    depositos_ordenados,
                    key=lambda d: (
                        d.prioridade,
                        -self._disponivel_deposito(d, sku),
                        d.deposito_id,
                    ),
                )
                for deposito in ordem:
                    if restante <= 0:
                        break
                    disp = self._disponivel_deposito(deposito, sku)
                    if disp <= 0:
                        continue
                    consumido = min(disp, restante)
                    alocacao.setdefault(deposito.deposito_id, {})
                    alocacao[deposito.deposito_id][sku] = (
                        alocacao[deposito.deposito_id].get(sku, 0) + consumido
                    )
                    deposito.reservado[sku] = deposito.reservado.get(sku, 0) + consumido
                    restante -= consumido

            ttl = ttl_s if ttl_s is not None else TTL_PADRAO_S
            reserva_id = str(uuid.uuid4())
            reserva = _Reserva(
                reserva_id=reserva_id,
                itens=itens,
                alocacao=alocacao,
                criada_em=self._relogio(),
                ttl=ttl,
            )
            self._reservas[reserva_id] = reserva
            return reserva_id

    def confirmar(self, reserva_id: str) -> dict:
        with self._lock:
            self._expirar_vencidas()
            reserva = self._reservas.get(reserva_id)
            if reserva is None:
                raise ErroEstoque("RESERVA_NAO_ENCONTRADA")
            if reserva.estado != "ativa":
                raise ErroEstoque("ESTADO_INVALIDO")

            for deposito_id, skus in reserva.alocacao.items():
                deposito = self._depositos[deposito_id]
                for sku, quantidade in skus.items():
                    deposito.fisico[sku] = deposito.fisico.get(sku, 0) - quantidade
                    deposito.reservado[sku] = deposito.reservado.get(sku, 0) - quantidade

            reserva.estado = "confirmada"
            return {"alocacao": reserva.alocacao}

    def cancelar(self, reserva_id: str) -> None:
        with self._lock:
            self._expirar_vencidas()
            reserva = self._reservas.get(reserva_id)
            if reserva is None:
                raise ErroEstoque("RESERVA_NAO_ENCONTRADA")
            if reserva.estado != "ativa":
                raise ErroEstoque("ESTADO_INVALIDO")

            self._liberar_reserva(reserva)
            reserva.estado = "cancelada"

    def transferir(self, sku: str, origem: str, destino: str, quantidade: int) -> None:
        with self._lock:
            self._expirar_vencidas()
            if origem == destino:
                raise ErroEstoque("DADOS_INVALIDOS")
            deposito_origem = self._depositos.get(origem)
            deposito_destino = self._depositos.get(destino)
            if deposito_origem is None or deposito_destino is None:
                raise ErroEstoque("DEPOSITO_DESCONHECIDO")
            if quantidade < 1:
                raise ErroEstoque("DADOS_INVALIDOS")
            if sku not in self._skus_conhecidos:
                raise ErroEstoque("SKU_DESCONHECIDO")

            disp_origem = self._disponivel_deposito(deposito_origem, sku)
            if quantidade > disp_origem:
                raise ErroEstoque("ESTOQUE_INSUFICIENTE")

            deposito_origem.fisico[sku] = deposito_origem.fisico.get(sku, 0) - quantidade
            deposito_destino.fisico[sku] = deposito_destino.fisico.get(sku, 0) + quantidade

    def posicao(self, sku: str) -> dict:
        with self._lock:
            self._expirar_vencidas()
            if sku not in self._skus_conhecidos:
                raise ErroEstoque("SKU_DESCONHECIDO")
            resultado: dict[str, dict[str, int]] = {}
            for deposito in self._depositos.values():
                fisico = deposito.fisico.get(sku, 0)
                reservado = deposito.reservado.get(sku, 0)
                resultado[deposito.deposito_id] = {
                    "fisico": fisico,
                    "reservado": reservado,
                    "disponivel": fisico - reservado,
                }
            return resultado

    def expirar(self) -> int:
        with self._lock:
            return self._expirar_vencidas()
