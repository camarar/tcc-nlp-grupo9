"""UC-06 - Agenda clinica com multiplos recursos."""

from __future__ import annotations

import itertools
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_CODIGOS = {
    "HORARIO_INDISPONIVEL",
    "FORA_DA_JANELA",
    "RECURSO_DESCONHECIDO",
    "AGENDAMENTO_NAO_ENCONTRADO",
    "ESTADO_INVALIDO",
    "DADOS_INVALIDOS",
}

_TIPOS = {"PROFISSIONAL", "SALA", "EQUIPAMENTO"}

_OCUPA = {"AGENDADO", "REALIZADO"}


class ErroAgenda(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code
        self.mensagem = mensagem


class Agenda:
    FUSO = "America/Sao_Paulo"

    def __init__(self, agora: Callable[[], datetime] | None = None) -> None:
        self._tz = ZoneInfo(self.FUSO)
        self._agora = agora if agora is not None else (lambda: datetime.now(timezone.utc))
        self._recursos: dict[str, dict] = {}
        self._agendamentos: dict[str, dict] = {}
        self._contador = itertools.count(1)

    # ------------------------------------------------------------------
    # Recursos

    def registrar_recurso(self, recurso_id: str, tipo: str, janela: dict) -> None:
        if tipo not in _TIPOS:
            raise ErroAgenda("DADOS_INVALIDOS")
        inicio = janela.get("inicio")
        fim = janela.get("fim")
        dias = janela.get("dias")
        if inicio is None or fim is None or inicio >= fim:
            raise ErroAgenda("DADOS_INVALIDOS")
        if not dias or any(d < 0 or d > 6 for d in dias):
            raise ErroAgenda("DADOS_INVALIDOS")
        self._recursos[recurso_id] = {
            "tipo": tipo,
            "janela": {"inicio": inicio, "fim": fim, "dias": list(dias)},
        }

    # ------------------------------------------------------------------
    # Agendamento

    def agendar(self, dados: dict) -> str:
        return self._agendar_interno(dados)

    def _agendar_interno(self, dados: dict, excluir_id: str | None = None) -> str:
        # (1) dados
        paciente = dados.get("paciente")
        profissional = dados.get("profissional")
        sala = dados.get("sala")
        if not paciente or not profissional or not sala:
            raise ErroAgenda("DADOS_INVALIDOS")

        inicio = dados.get("inicio")
        if inicio is None:
            raise ErroAgenda("DADOS_INVALIDOS")

        equipamento = dados.get("equipamento")

        dur = dados.get("duracao_min")
        if dur is None:
            dur = 30
        elif dur <= 0 or dur % 5 != 0:
            raise ErroAgenda("DADOS_INVALIDOS")

        if not isinstance(inicio, datetime) or inicio.tzinfo is None or inicio.tzinfo.utcoffset(inicio) is None:
            raise ErroAgenda("DADOS_INVALIDOS")

        inicio_utc = inicio.astimezone(timezone.utc)
        fim_utc = inicio_utc + timedelta(minutes=dur)

        # (2) existencia e tipo dos recursos
        self._checar_recurso(profissional, "PROFISSIONAL")
        self._checar_recurso(sala, "SALA")
        if equipamento is not None:
            self._checar_recurso(equipamento, "EQUIPAMENTO")

        envolvidos = [profissional, sala] + ([equipamento] if equipamento is not None else [])

        # (3) janela de atendimento
        for rid in envolvidos:
            self._verifica_janela(rid, inicio_utc, fim_utc)

        # (4) conflito de horario
        for rid in envolvidos:
            if self._tem_conflito(rid, inicio_utc, fim_utc, excluir_id):
                raise ErroAgenda("HORARIO_INDISPONIVEL")

        aid = self._novo_id()
        self._agendamentos[aid] = {
            "paciente": paciente,
            "profissional": profissional,
            "sala": sala,
            "equipamento": equipamento,
            "inicio": inicio_utc,
            "fim": fim_utc,
            "situacao": "AGENDADO",
        }
        return aid

    def cancelar(self, agendamento_id: str, quando: datetime) -> dict:
        ag = self._buscar(agendamento_id)
        if ag["situacao"] != "AGENDADO":
            raise ErroAgenda("ESTADO_INVALIDO")
        quando_utc = quando.astimezone(timezone.utc)
        inicio = ag["inicio"]
        if quando_utc >= inicio:
            multa = True
        else:
            multa = (inicio - quando_utc) < timedelta(hours=24)
        ag["situacao"] = "CANCELADO"
        return {"multa": multa, "situacao": "CANCELADO"}

    def remarcar(self, agendamento_id: str, novo_inicio: datetime) -> str:
        ag = self._buscar(agendamento_id)
        if ag["situacao"] != "AGENDADO":
            raise ErroAgenda("ESTADO_INVALIDO")
        duracao_min = int((ag["fim"] - ag["inicio"]).total_seconds() // 60)
        dados = {
            "paciente": ag["paciente"],
            "profissional": ag["profissional"],
            "sala": ag["sala"],
            "equipamento": ag["equipamento"],
            "inicio": novo_inicio,
            "duracao_min": duracao_min,
        }
        novo_id = self._agendar_interno(dados, excluir_id=agendamento_id)
        ag["situacao"] = "REMARCADO"
        return novo_id

    def registrar_comparecimento(self, agendamento_id: str, compareceu: bool, quando: datetime) -> str:
        ag = self._buscar(agendamento_id)
        if ag["situacao"] != "AGENDADO":
            raise ErroAgenda("ESTADO_INVALIDO")
        quando_utc = quando.astimezone(timezone.utc)
        if quando_utc < ag["inicio"]:
            raise ErroAgenda("ESTADO_INVALIDO")
        ag["situacao"] = "REALIZADO" if compareceu else "FALTA"
        return ag["situacao"]

    # ------------------------------------------------------------------
    # Consultas

    def disponibilidade(self, profissional: str, dia: date) -> list[dict]:
        self._checar_recurso(profissional, "PROFISSIONAL")
        janela = self._recursos[profissional]["janela"]
        if dia.weekday() not in janela["dias"]:
            return []

        janela_inicio_dt = datetime.combine(dia, janela["inicio"], tzinfo=self._tz)
        janela_fim_dt = datetime.combine(dia, janela["fim"], tzinfo=self._tz)

        ocupados = []
        for ag in self._agendamentos.values():
            if ag["profissional"] != profissional or ag["situacao"] not in _OCUPA:
                continue
            ini = max(ag["inicio"], janela_inicio_dt)
            fim = min(ag["fim"], janela_fim_dt)
            if ini < fim:
                ocupados.append((ini, fim))
        ocupados.sort()

        mesclados: list[list[datetime]] = []
        for ini, fim in ocupados:
            if mesclados and ini <= mesclados[-1][1]:
                mesclados[-1][1] = max(mesclados[-1][1], fim)
            else:
                mesclados.append([ini, fim])

        livres = []
        cursor = janela_inicio_dt
        for ini, fim in mesclados:
            if cursor < ini:
                livres.append((cursor, ini))
            cursor = max(cursor, fim)
        if cursor < janela_fim_dt:
            livres.append((cursor, janela_fim_dt))

        return [
            {"inicio": ini.astimezone(self._tz), "fim": fim.astimezone(self._tz)}
            for ini, fim in livres
        ]

    def agenda_do_dia(self, profissional: str, dia: date) -> list[dict]:
        self._checar_recurso(profissional, "PROFISSIONAL")
        itens = []
        for aid, ag in self._agendamentos.items():
            if ag["profissional"] != profissional:
                continue
            inicio_local = ag["inicio"].astimezone(self._tz)
            if inicio_local.date() != dia:
                continue
            itens.append({
                "agendamento_id": aid,
                "inicio": inicio_local,
                "fim": ag["fim"].astimezone(self._tz),
                "paciente": ag["paciente"],
                "situacao": ag["situacao"],
            })
        itens.sort(key=lambda item: (item["inicio"], item["agendamento_id"]))
        return itens

    # ------------------------------------------------------------------
    # Auxiliares internos

    def _novo_id(self) -> str:
        return f"AG{next(self._contador):06d}"

    def _buscar(self, agendamento_id: str) -> dict:
        ag = self._agendamentos.get(agendamento_id)
        if ag is None:
            raise ErroAgenda("AGENDAMENTO_NAO_ENCONTRADO")
        return ag

    def _checar_recurso(self, recurso_id: str, tipo_esperado: str) -> None:
        recurso = self._recursos.get(recurso_id)
        if recurso is None or recurso["tipo"] != tipo_esperado:
            raise ErroAgenda("RECURSO_DESCONHECIDO")

    def _verifica_janela(self, recurso_id: str, inicio_utc: datetime, fim_utc: datetime) -> None:
        janela = self._recursos[recurso_id]["janela"]
        dia_local = inicio_utc.astimezone(self._tz).date()
        if dia_local.weekday() not in janela["dias"]:
            raise ErroAgenda("FORA_DA_JANELA")
        janela_inicio_dt = datetime.combine(dia_local, janela["inicio"], tzinfo=self._tz)
        janela_fim_dt = datetime.combine(dia_local, janela["fim"], tzinfo=self._tz)
        if inicio_utc < janela_inicio_dt or fim_utc > janela_fim_dt:
            raise ErroAgenda("FORA_DA_JANELA")

    def _tem_conflito(self, recurso_id: str, inicio_utc: datetime, fim_utc: datetime,
                       excluir_id: str | None) -> bool:
        for aid, ag in self._agendamentos.items():
            if aid == excluir_id or ag["situacao"] not in _OCUPA:
                continue
            if recurso_id not in (ag["profissional"], ag["sala"], ag["equipamento"]):
                continue
            if ag["inicio"] < fim_utc and ag["fim"] > inicio_utc:
                return True
        return False
