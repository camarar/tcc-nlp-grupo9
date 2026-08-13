"""UC-09 — Central de chamados com SLA."""

from __future__ import annotations

import itertools
from datetime import datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

SEVERIDADES = ("CRITICA", "ALTA", "MEDIA", "BAIXA")
_RANK_SEVERIDADE = {sev: i for i, sev in enumerate(SEVERIDADES)}
_ESTADOS_ATIVOS = {"ABERTO", "ATRIBUIDO", "REABERTO"}
_ESTADOS_FILA = {"ABERTO", "ATRIBUIDO", "REABERTO"}


class ErroChamado(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


class _Chamado:
    __slots__ = (
        "id", "cliente", "severidade", "assunto", "aberto_em", "situacao",
        "sla_minutos", "sla_horario_comercial", "prazo", "atendente",
        "excluido_acumulado", "stop_inicio", "estado_antes_pausa",
        "criado_em_index",
    )


class CentralChamados:
    FUSO = "America/Sao_Paulo"

    def __init__(self, relogio: Callable[[], datetime] | None = None) -> None:
        self._relogio = relogio
        self._tz = ZoneInfo(self.FUSO)
        self._sla: dict[str, tuple[int, bool]] = {}
        self._chamados: dict[str, _Chamado] = {}
        self._contador = itertools.count(1)

    # ------------------------------------------------------------------
    # Horário comercial / aritmética de minutos úteis
    # ------------------------------------------------------------------

    def _proximo_instante_util(self, dt: datetime) -> datetime:
        dt = dt.astimezone(self._tz)
        if dt.weekday() < 5:
            inicio = dt.replace(hour=9, minute=0, second=0, microsecond=0)
            fim = dt.replace(hour=18, minute=0, second=0, microsecond=0)
            if dt < inicio:
                return inicio
            if dt < fim:
                return dt
        cur = dt + timedelta(days=1)
        cur = cur.replace(hour=9, minute=0, second=0, microsecond=0)
        while cur.weekday() >= 5:
            cur += timedelta(days=1)
        return cur

    def _somar_minutos_uteis(self, inicio: datetime, minutos: float) -> datetime:
        if minutos <= 0:
            return inicio
        cur = self._proximo_instante_util(inicio)
        restante = minutos
        while True:
            fim_janela = cur.replace(hour=18, minute=0, second=0, microsecond=0)
            disponivel = (fim_janela - cur).total_seconds() / 60
            if restante <= disponivel:
                return cur + timedelta(minutes=restante)
            restante -= disponivel
            cur = self._proximo_instante_util(fim_janela)

    def _minutos_uteis_entre(self, a: datetime, b: datetime) -> float:
        a = a.astimezone(self._tz)
        b = b.astimezone(self._tz)
        if b <= a:
            return 0.0
        total = 0.0
        cur = a
        while cur < b:
            nxt = self._proximo_instante_util(cur)
            if nxt >= b:
                break
            fim_janela = nxt.replace(hour=18, minute=0, second=0, microsecond=0)
            fim_trecho = min(b, fim_janela)
            total += (fim_trecho - nxt).total_seconds() / 60
            cur = fim_trecho
        return total

    def _metrica(self, chamado: _Chamado, a: datetime, b: datetime) -> float:
        if chamado.sla_horario_comercial:
            return self._minutos_uteis_entre(a, b)
        return (b - a).total_seconds() / 60

    def _empurra_prazo(self, chamado: _Chamado, delta: float) -> datetime:
        if delta <= 0:
            return chamado.prazo
        if chamado.sla_horario_comercial:
            return self._somar_minutos_uteis(chamado.prazo, delta)
        return chamado.prazo + timedelta(minutes=delta)

    # ------------------------------------------------------------------
    # Utilidades internas
    # ------------------------------------------------------------------

    def _obter(self, chamado_id: str) -> _Chamado:
        chamado = self._chamados.get(chamado_id)
        if chamado is None:
            raise ErroChamado("CHAMADO_NAO_ENCONTRADO")
        return chamado

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def configurar_sla(self, severidade: str, minutos: int, horario_comercial: bool) -> None:
        if minutos <= 0 or severidade not in SEVERIDADES:
            raise ErroChamado("POLITICA_INVALIDA")
        self._sla[severidade] = (minutos, horario_comercial)

    def abrir(self, dados: dict) -> str:
        cliente = dados.get("cliente")
        assunto = dados.get("assunto")
        severidade = dados.get("severidade")
        aberto_em = dados.get("aberto_em")

        if not cliente or not assunto:
            raise ErroChamado("DADOS_INVALIDOS")
        if severidade not in SEVERIDADES:
            raise ErroChamado("DADOS_INVALIDOS")
        if not isinstance(aberto_em, datetime) or aberto_em.tzinfo is None \
                or aberto_em.tzinfo.utcoffset(aberto_em) is None:
            raise ErroChamado("DADOS_INVALIDOS")

        sla = self._sla.get(severidade)
        if sla is None:
            raise ErroChamado("DADOS_INVALIDOS")
        minutos, horario_comercial = sla

        if horario_comercial:
            prazo = self._somar_minutos_uteis(aberto_em, minutos)
        else:
            prazo = aberto_em + timedelta(minutes=minutos)

        chamado_id = f"CH-{next(self._contador):06d}"
        chamado = _Chamado()
        chamado.id = chamado_id
        chamado.cliente = cliente
        chamado.severidade = severidade
        chamado.assunto = assunto
        chamado.aberto_em = aberto_em
        chamado.situacao = "ABERTO"
        chamado.sla_minutos = minutos
        chamado.sla_horario_comercial = horario_comercial
        chamado.prazo = prazo
        chamado.atendente = None
        chamado.excluido_acumulado = 0.0
        chamado.stop_inicio = None
        chamado.estado_antes_pausa = None
        chamado.criado_em_index = next(self._contador)

        self._chamados[chamado_id] = chamado
        return chamado_id

    def atribuir(self, chamado_id: str, atendente: str, quando: datetime) -> None:
        chamado = self._obter(chamado_id)
        if chamado.situacao not in ("ABERTO", "REABERTO", "ATRIBUIDO"):
            raise ErroChamado("ESTADO_INVALIDO")
        if not atendente:
            raise ErroChamado("ATRIBUICAO_INVALIDA")
        chamado.situacao = "ATRIBUIDO"
        chamado.atendente = atendente

    def pausar(self, chamado_id: str, motivo: str, quando: datetime) -> None:
        chamado = self._obter(chamado_id)
        if chamado.situacao not in _ESTADOS_ATIVOS:
            raise ErroChamado("ESTADO_INVALIDO")
        if not motivo:
            raise ErroChamado("DADOS_INVALIDOS")
        chamado.estado_antes_pausa = chamado.situacao
        chamado.situacao = "PAUSADO"
        chamado.stop_inicio = quando

    def retomar(self, chamado_id: str, quando: datetime) -> None:
        chamado = self._obter(chamado_id)
        if chamado.situacao != "PAUSADO":
            raise ErroChamado("ESTADO_INVALIDO")
        delta = self._metrica(chamado, chamado.stop_inicio, quando)
        chamado.prazo = self._empurra_prazo(chamado, delta)
        chamado.excluido_acumulado += delta
        chamado.situacao = chamado.estado_antes_pausa
        chamado.estado_antes_pausa = None
        chamado.stop_inicio = None

    def resolver(self, chamado_id: str, quando: datetime) -> dict:
        chamado = self._obter(chamado_id)
        if chamado.situacao not in _ESTADOS_ATIVOS:
            raise ErroChamado("ESTADO_INVALIDO")
        total = self._metrica(chamado, chamado.aberto_em, quando)
        tempo_util = total - chamado.excluido_acumulado
        tempo_util_min = int(tempo_util)
        cumpriu_sla = tempo_util_min <= chamado.sla_minutos

        chamado.situacao = "RESOLVIDO"
        chamado.stop_inicio = quando

        return {"cumpriu_sla": cumpriu_sla, "tempo_util_min": tempo_util_min}

    def reabrir(self, chamado_id: str, quando: datetime) -> None:
        chamado = self._obter(chamado_id)
        if chamado.situacao != "RESOLVIDO":
            raise ErroChamado("ESTADO_INVALIDO")
        delta = self._metrica(chamado, chamado.stop_inicio, quando)
        chamado.prazo = self._empurra_prazo(chamado, delta)
        chamado.excluido_acumulado += delta
        chamado.situacao = "REABERTO"
        chamado.stop_inicio = None

    def prazo(self, chamado_id: str) -> datetime:
        return self._obter(chamado_id).prazo

    def fila(self, quando: datetime) -> list[dict]:
        candidatos = [c for c in self._chamados.values() if c.situacao in _ESTADOS_FILA]

        def chave(c: _Chamado):
            estourado = quando > c.prazo
            return (
                _RANK_SEVERIDADE[c.severidade],
                0 if estourado else 1,
                c.prazo,
                c.aberto_em,
                c.criado_em_index,
            )

        candidatos.sort(key=chave)

        return [
            {
                "chamado_id": c.id,
                "severidade": c.severidade,
                "situacao": c.situacao,
                "prazo": c.prazo,
                "estourado": quando > c.prazo,
            }
            for c in candidatos
        ]

    def proximo(self, quando: datetime) -> str:
        fila = self.fila(quando)
        if not fila:
            raise ErroChamado("FILA_VAZIA")
        return fila[0]["chamado_id"]
