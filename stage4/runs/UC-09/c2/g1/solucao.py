"""UC-09 — Central de chamados com SLA."""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta
from typing import Callable, Optional
from zoneinfo import ZoneInfo

_SEVERIDADES = {"CRITICA", "ALTA", "MEDIA", "BAIXA"}
_SEVERIDADE_RANK = {"CRITICA": 0, "ALTA": 1, "MEDIA": 2, "BAIXA": 3}
_SITUACOES_ATIVAS = {"ABERTO", "ATRIBUIDO", "REABERTO"}

_ABERTURA_COMERCIAL = time(9, 0)
_FECHAMENTO_COMERCIAL = time(18, 0)


class ErroChamado(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code
        self.mensagem = mensagem


class _Chamado:
    __slots__ = (
        "id", "cliente", "severidade", "assunto", "aberto_em",
        "sla_minutos", "horario_comercial", "situacao", "atendente",
        "consumido_min", "ativo_desde", "suspenso_desde", "resolvido_em",
        "estado_antes_pausa", "prazo_atual", "ordem",
    )

    def __init__(self, id, cliente, severidade, assunto, aberto_em,
                 sla_minutos, horario_comercial, prazo_inicial, ordem):
        self.id = id
        self.cliente = cliente
        self.severidade = severidade
        self.assunto = assunto
        self.aberto_em = aberto_em
        self.sla_minutos = sla_minutos
        self.horario_comercial = horario_comercial
        self.situacao = "ABERTO"
        self.atendente = None
        self.consumido_min = 0.0
        self.ativo_desde = aberto_em
        self.suspenso_desde = None
        self.resolvido_em = None
        self.estado_antes_pausa = None
        self.prazo_atual = prazo_inicial
        self.ordem = ordem


class CentralChamados:
    FUSO = "America/Sao_Paulo"

    def __init__(self, relogio: Optional[Callable[[], datetime]] = None) -> None:
        self._relogio = relogio
        self._politicas: dict[str, tuple[int, bool]] = {}
        self._chamados: dict[str, _Chamado] = {}
        self._ordem = 0
        self._tz = ZoneInfo(self.FUSO)

    # ------------------------------------------------------------------ #
    # Tempo útil
    # ------------------------------------------------------------------ #

    def _snap_para_util(self, dt: datetime) -> datetime:
        dt = dt.astimezone(self._tz)
        while True:
            if dt.weekday() >= 5:
                dt = datetime.combine(dt.date() + timedelta(days=1), time(0, 0), tzinfo=self._tz)
                continue
            if dt.time() < _ABERTURA_COMERCIAL:
                return datetime.combine(dt.date(), _ABERTURA_COMERCIAL, tzinfo=self._tz)
            if dt.time() >= _FECHAMENTO_COMERCIAL:
                dt = datetime.combine(dt.date() + timedelta(days=1), time(0, 0), tzinfo=self._tz)
                continue
            return dt

    def _tempo_util(self, inicio: datetime, fim: datetime, horario_comercial: bool) -> float:
        if fim <= inicio:
            return 0.0
        if not horario_comercial:
            return (fim - inicio).total_seconds() / 60

        inicio = inicio.astimezone(self._tz)
        fim = fim.astimezone(self._tz)
        total = 0.0
        cur = inicio
        while cur.date() <= fim.date():
            if cur.weekday() < 5:
                abertura = datetime.combine(cur.date(), _ABERTURA_COMERCIAL, tzinfo=self._tz)
                fechamento = datetime.combine(cur.date(), _FECHAMENTO_COMERCIAL, tzinfo=self._tz)
                seg_inicio = max(cur, abertura)
                seg_fim = min(fim, fechamento)
                if seg_fim > seg_inicio:
                    total += (seg_fim - seg_inicio).total_seconds() / 60
            proximo_dia = datetime.combine(cur.date() + timedelta(days=1), time(0, 0), tzinfo=self._tz)
            if proximo_dia > fim:
                break
            cur = proximo_dia
        return total

    def _avancar_util(self, inicio: datetime, minutos: float, horario_comercial: bool) -> datetime:
        if minutos <= 0:
            return inicio
        if not horario_comercial:
            return inicio + timedelta(minutes=minutos)

        cur = self._snap_para_util(inicio)
        restante = minutos
        while restante > 1e-9:
            fechamento = datetime.combine(cur.date(), _FECHAMENTO_COMERCIAL, tzinfo=self._tz)
            disponivel = (fechamento - cur).total_seconds() / 60
            if restante <= disponivel:
                cur = cur + timedelta(minutes=restante)
                restante = 0.0
            else:
                restante -= disponivel
                proximo_dia = datetime.combine(cur.date() + timedelta(days=1), time(0, 0), tzinfo=self._tz)
                cur = self._snap_para_util(proximo_dia)
        return cur

    # ------------------------------------------------------------------ #
    # Auxiliares
    # ------------------------------------------------------------------ #

    def _get(self, chamado_id: str) -> _Chamado:
        chamado = self._chamados.get(chamado_id)
        if chamado is None:
            raise ErroChamado("CHAMADO_NAO_ENCONTRADO")
        return chamado

    @staticmethod
    def _aware(dt) -> bool:
        return isinstance(dt, datetime) and dt.tzinfo is not None and dt.utcoffset() is not None

    # ------------------------------------------------------------------ #
    # API pública
    # ------------------------------------------------------------------ #

    def configurar_sla(self, severidade: str, minutos: int, horario_comercial: bool) -> None:
        if severidade not in _SEVERIDADES or minutos is None or minutos <= 0:
            raise ErroChamado("POLITICA_INVALIDA")
        self._politicas[severidade] = (minutos, horario_comercial)

    def abrir(self, dados: dict) -> str:
        cliente = dados.get("cliente")
        assunto = dados.get("assunto")
        severidade = dados.get("severidade")
        aberto_em = dados.get("aberto_em")

        if not cliente or not assunto:
            raise ErroChamado("DADOS_INVALIDOS")
        if severidade not in _SEVERIDADES:
            raise ErroChamado("DADOS_INVALIDOS")
        if not self._aware(aberto_em):
            raise ErroChamado("DADOS_INVALIDOS")
        if severidade not in self._politicas:
            raise ErroChamado("DADOS_INVALIDOS")

        sla_minutos, horario_comercial = self._politicas[severidade]
        prazo_inicial = self._avancar_util(aberto_em, sla_minutos, horario_comercial)

        chamado_id = str(uuid.uuid4())
        self._ordem += 1
        chamado = _Chamado(
            chamado_id, cliente, severidade, assunto, aberto_em,
            sla_minutos, horario_comercial, prazo_inicial, self._ordem,
        )
        self._chamados[chamado_id] = chamado
        return chamado_id

    def atribuir(self, chamado_id: str, atendente: str, quando: datetime) -> None:
        chamado = self._get(chamado_id)
        if chamado.situacao not in _SITUACOES_ATIVAS:
            raise ErroChamado("ESTADO_INVALIDO")
        if not atendente:
            raise ErroChamado("ATRIBUICAO_INVALIDA")
        chamado.atendente = atendente
        chamado.situacao = "ATRIBUIDO"

    def pausar(self, chamado_id: str, motivo: str, quando: datetime) -> None:
        chamado = self._get(chamado_id)
        if chamado.situacao not in _SITUACOES_ATIVAS:
            raise ErroChamado("ESTADO_INVALIDO")
        if not motivo:
            raise ErroChamado("DADOS_INVALIDOS")

        elapsed = self._tempo_util(chamado.ativo_desde, quando, chamado.horario_comercial)
        chamado.consumido_min += elapsed
        chamado.estado_antes_pausa = chamado.situacao
        chamado.situacao = "PAUSADO"
        chamado.suspenso_desde = quando
        chamado.ativo_desde = None

    def retomar(self, chamado_id: str, quando: datetime) -> None:
        chamado = self._get(chamado_id)
        if chamado.situacao != "PAUSADO":
            raise ErroChamado("ESTADO_INVALIDO")

        duracao = self._tempo_util(chamado.suspenso_desde, quando, chamado.horario_comercial)
        chamado.prazo_atual = self._avancar_util(chamado.prazo_atual, duracao, chamado.horario_comercial)
        chamado.situacao = chamado.estado_antes_pausa
        chamado.estado_antes_pausa = None
        chamado.suspenso_desde = None
        chamado.ativo_desde = quando

    def resolver(self, chamado_id: str, quando: datetime) -> dict:
        chamado = self._get(chamado_id)
        if chamado.situacao in {"PAUSADO", "RESOLVIDO"}:
            raise ErroChamado("ESTADO_INVALIDO")

        elapsed = self._tempo_util(chamado.ativo_desde, quando, chamado.horario_comercial)
        chamado.consumido_min += elapsed
        chamado.situacao = "RESOLVIDO"
        chamado.ativo_desde = None
        chamado.resolvido_em = quando

        tempo_util_min = int(chamado.consumido_min)
        cumpriu_sla = tempo_util_min <= chamado.sla_minutos
        return {"cumpriu_sla": cumpriu_sla, "tempo_util_min": tempo_util_min}

    def reabrir(self, chamado_id: str, quando: datetime) -> None:
        chamado = self._get(chamado_id)
        if chamado.situacao != "RESOLVIDO":
            raise ErroChamado("ESTADO_INVALIDO")

        duracao = self._tempo_util(chamado.resolvido_em, quando, chamado.horario_comercial)
        chamado.prazo_atual = self._avancar_util(chamado.prazo_atual, duracao, chamado.horario_comercial)
        chamado.situacao = "REABERTO"
        chamado.resolvido_em = None
        chamado.ativo_desde = quando

    def prazo(self, chamado_id: str) -> datetime:
        chamado = self._get(chamado_id)
        return chamado.prazo_atual

    def _fila_ordenada(self, quando: datetime) -> list[_Chamado]:
        elegiveis = [c for c in self._chamados.values() if c.situacao in _SITUACOES_ATIVAS]

        def chave(c: _Chamado):
            estourado = quando > c.prazo_atual
            return (
                _SEVERIDADE_RANK[c.severidade],
                not estourado,
                c.prazo_atual,
                c.aberto_em,
                c.ordem,
            )

        elegiveis.sort(key=chave)
        return elegiveis

    def fila(self, quando: datetime) -> list[dict]:
        return [
            {
                "chamado_id": c.id,
                "severidade": c.severidade,
                "situacao": c.situacao,
                "prazo": c.prazo_atual,
                "estourado": quando > c.prazo_atual,
            }
            for c in self._fila_ordenada(quando)
        ]

    def proximo(self, quando: datetime) -> str:
        elegiveis = self._fila_ordenada(quando)
        if not elegiveis:
            raise ErroChamado("FILA_VAZIA")
        return elegiveis[0].id
