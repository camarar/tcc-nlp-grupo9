"""UC-06 — Agenda clinica com multiplos recursos."""

from __future__ import annotations

import itertools
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo


class ErroAgenda(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


class _Recurso:
    __slots__ = ("recurso_id", "tipo", "janela")

    def __init__(self, recurso_id: str, tipo: str, janela: dict) -> None:
        self.recurso_id = recurso_id
        self.tipo = tipo
        self.janela = janela


class _Agendamento:
    __slots__ = ("agendamento_id", "paciente", "profissional", "sala",
                 "equipamento", "inicio", "fim", "situacao")

    def __init__(self, agendamento_id: str, paciente: str, profissional: str,
                 sala: str, equipamento: str | None, inicio: datetime,
                 fim: datetime, situacao: str) -> None:
        self.agendamento_id = agendamento_id
        self.paciente = paciente
        self.profissional = profissional
        self.sala = sala
        self.equipamento = equipamento
        self.inicio = inicio
        self.fim = fim
        self.situacao = situacao


_OCUPA = {"AGENDADO", "REALIZADO"}
_TIPOS_VALIDOS = {"PROFISSIONAL", "SALA", "EQUIPAMENTO"}
_DIAS_VALIDOS = set(range(7))


class Agenda:
    FUSO = "America/Sao_Paulo"

    def __init__(self, agora: Callable[[], datetime] | None = None) -> None:
        self._agora = agora or (lambda: datetime.now(timezone.utc))
        self._recursos: dict[str, _Recurso] = {}
        self._agendamentos: dict[str, _Agendamento] = {}
        self._contador = itertools.count(1)
        self._tz = ZoneInfo(self.FUSO)

    # ------------------------------------------------------------------
    # RF-01
    # ------------------------------------------------------------------
    def registrar_recurso(self, recurso_id: str, tipo: str, janela: dict) -> None:
        if not recurso_id or tipo not in _TIPOS_VALIDOS:
            raise ErroAgenda("DADOS_INVALIDOS", "tipo invalido")
        if not isinstance(janela, dict):
            raise ErroAgenda("DADOS_INVALIDOS", "janela invalida")
        inicio = janela.get("inicio")
        fim = janela.get("fim")
        dias = janela.get("dias")
        if not isinstance(inicio, time) or not isinstance(fim, time):
            raise ErroAgenda("DADOS_INVALIDOS", "janela invalida")
        if inicio >= fim:
            raise ErroAgenda("DADOS_INVALIDOS", "inicio >= fim")
        if not dias or not isinstance(dias, list) or any(
            d not in _DIAS_VALIDOS for d in dias
        ):
            raise ErroAgenda("DADOS_INVALIDOS", "dias invalidos")
        self._recursos[recurso_id] = _Recurso(
            recurso_id, tipo,
            {"inicio": inicio, "fim": fim, "dias": list(dias)},
        )

    # ------------------------------------------------------------------
    # RF-02
    # ------------------------------------------------------------------
    def agendar(self, dados: dict) -> str:
        inicio, fim, papeis = self._validar_dados_agendamento(dados)
        self._validar_recursos(papeis)
        self._validar_janela(papeis, inicio, fim)
        self._validar_conflito(papeis, inicio, fim, ignorar_id=None)

        agendamento_id = f"AG{next(self._contador)}"
        agendamento = _Agendamento(
            agendamento_id=agendamento_id,
            paciente=dados["paciente"],
            profissional=papeis["PROFISSIONAL"],
            sala=papeis["SALA"],
            equipamento=papeis.get("EQUIPAMENTO"),
            inicio=inicio,
            fim=fim,
            situacao="AGENDADO",
        )
        self._agendamentos[agendamento_id] = agendamento
        return agendamento_id

    def _validar_dados_agendamento(self, dados: dict):
        if not isinstance(dados, dict):
            raise ErroAgenda("DADOS_INVALIDOS", "dados invalidos")

        paciente = dados.get("paciente")
        profissional = dados.get("profissional")
        sala = dados.get("sala")
        equipamento = dados.get("equipamento")
        inicio = dados.get("inicio")
        duracao_min = dados.get("duracao_min")

        if not paciente or not profissional or not sala:
            raise ErroAgenda("DADOS_INVALIDOS", "campos obrigatorios ausentes")

        if duracao_min is None:
            duracao_min = 30
        if not isinstance(duracao_min, int) or isinstance(duracao_min, bool) \
                or duracao_min <= 0 or duracao_min % 5 != 0:
            raise ErroAgenda("DADOS_INVALIDOS", "duracao invalida")

        if not isinstance(inicio, datetime) or inicio.tzinfo is None \
                or inicio.tzinfo.utcoffset(inicio) is None:
            raise ErroAgenda("DADOS_INVALIDOS", "inicio deve ser timezone-aware")

        inicio_utc = inicio.astimezone(timezone.utc)
        fim_utc = inicio_utc + timedelta(minutes=duracao_min)

        papeis = {
            "PROFISSIONAL": profissional,
            "SALA": sala,
        }
        if equipamento:
            papeis["EQUIPAMENTO"] = equipamento

        return inicio_utc, fim_utc, papeis

    def _validar_recursos(self, papeis: dict[str, str]) -> None:
        for papel, recurso_id in papeis.items():
            recurso = self._recursos.get(recurso_id)
            if recurso is None or recurso.tipo != papel:
                raise ErroAgenda("RECURSO_DESCONHECIDO", recurso_id)

    def _validar_janela(self, papeis: dict[str, str], inicio_utc: datetime,
                         fim_utc: datetime) -> None:
        inicio_local = inicio_utc.astimezone(self._tz)
        fim_local = fim_utc.astimezone(self._tz)
        dia_semana = inicio_local.weekday()

        for recurso_id in papeis.values():
            recurso = self._recursos[recurso_id]
            janela = recurso.janela
            if dia_semana not in janela["dias"]:
                raise ErroAgenda("FORA_DA_JANELA", recurso_id)
            if inicio_local.date() != fim_local.date():
                raise ErroAgenda("FORA_DA_JANELA", recurso_id)
            if inicio_local.time() < janela["inicio"] or fim_local.time() > janela["fim"]:
                raise ErroAgenda("FORA_DA_JANELA", recurso_id)

    def _validar_conflito(self, papeis: dict[str, str], inicio_utc: datetime,
                           fim_utc: datetime, ignorar_id: str | None) -> None:
        recursos_ids = set(papeis.values())
        for agendamento in self._agendamentos.values():
            if agendamento.agendamento_id == ignorar_id:
                continue
            if agendamento.situacao not in _OCUPA:
                continue
            ocupados = {agendamento.profissional, agendamento.sala}
            if agendamento.equipamento:
                ocupados.add(agendamento.equipamento)
            if not (ocupados & recursos_ids):
                continue
            if inicio_utc < agendamento.fim and agendamento.inicio < fim_utc:
                raise ErroAgenda("HORARIO_INDISPONIVEL",
                                  ocupados.intersection(recursos_ids).pop())

    # ------------------------------------------------------------------
    # RF-03
    # ------------------------------------------------------------------
    def cancelar(self, agendamento_id: str, quando: datetime) -> dict:
        agendamento = self._buscar(agendamento_id)
        if agendamento.situacao != "AGENDADO":
            raise ErroAgenda("ESTADO_INVALIDO", agendamento.situacao)

        quando_utc = self._to_utc_valido(quando)
        antecedencia = agendamento.inicio - quando_utc
        multa = antecedencia < timedelta(hours=24)

        agendamento.situacao = "CANCELADO"
        return {"multa": multa, "situacao": "CANCELADO"}

    # ------------------------------------------------------------------
    # RF-04
    # ------------------------------------------------------------------
    def remarcar(self, agendamento_id: str, novo_inicio: datetime) -> str:
        agendamento = self._buscar(agendamento_id)
        if agendamento.situacao != "AGENDADO":
            raise ErroAgenda("ESTADO_INVALIDO", agendamento.situacao)

        dados = {
            "paciente": agendamento.paciente,
            "profissional": agendamento.profissional,
            "sala": agendamento.sala,
            "equipamento": agendamento.equipamento,
            "inicio": novo_inicio,
            "duracao_min": int((agendamento.fim - agendamento.inicio).total_seconds() // 60),
        }
        inicio, fim, papeis = self._validar_dados_agendamento(dados)
        self._validar_recursos(papeis)
        self._validar_janela(papeis, inicio, fim)
        self._validar_conflito(papeis, inicio, fim, ignorar_id=agendamento.agendamento_id)

        novo_id = f"AG{next(self._contador)}"
        novo_agendamento = _Agendamento(
            agendamento_id=novo_id,
            paciente=agendamento.paciente,
            profissional=agendamento.profissional,
            sala=agendamento.sala,
            equipamento=agendamento.equipamento,
            inicio=inicio,
            fim=fim,
            situacao="AGENDADO",
        )
        self._agendamentos[novo_id] = novo_agendamento
        agendamento.situacao = "REMARCADO"
        return novo_id

    # ------------------------------------------------------------------
    # RF-05
    # ------------------------------------------------------------------
    def registrar_comparecimento(self, agendamento_id: str,
                                  compareceu: bool, quando: datetime) -> str:
        agendamento = self._buscar(agendamento_id)
        if agendamento.situacao != "AGENDADO":
            raise ErroAgenda("ESTADO_INVALIDO", agendamento.situacao)

        quando_utc = self._to_utc_valido(quando)
        if quando_utc < agendamento.inicio:
            raise ErroAgenda("ESTADO_INVALIDO", "antes do inicio")

        agendamento.situacao = "REALIZADO" if compareceu else "FALTA"
        return agendamento.situacao

    # ------------------------------------------------------------------
    # RF-06
    # ------------------------------------------------------------------
    def disponibilidade(self, profissional: str, dia: date) -> list[dict]:
        recurso = self._recursos.get(profissional)
        if recurso is None or recurso.tipo != "PROFISSIONAL":
            raise ErroAgenda("RECURSO_DESCONHECIDO", profissional)

        dia_semana = dia.weekday()
        if dia_semana not in recurso.janela["dias"]:
            return []

        janela_inicio = datetime.combine(dia, recurso.janela["inicio"], tzinfo=self._tz)
        janela_fim = datetime.combine(dia, recurso.janela["fim"], tzinfo=self._tz)

        ocupados = []
        for agendamento in self._agendamentos.values():
            if agendamento.profissional != profissional:
                continue
            if agendamento.situacao not in _OCUPA:
                continue
            inicio_local = agendamento.inicio.astimezone(self._tz)
            fim_local = agendamento.fim.astimezone(self._tz)
            inicio_corte = max(inicio_local, janela_inicio)
            fim_corte = min(fim_local, janela_fim)
            if inicio_corte < fim_corte:
                ocupados.append((inicio_corte, fim_corte))

        ocupados.sort(key=lambda par: par[0])

        livres = []
        cursor = janela_inicio
        for inicio_ocupado, fim_ocupado in ocupados:
            if inicio_ocupado > cursor:
                livres.append({"inicio": cursor, "fim": inicio_ocupado})
            if fim_ocupado > cursor:
                cursor = fim_ocupado
        if cursor < janela_fim:
            livres.append({"inicio": cursor, "fim": janela_fim})

        return livres

    # ------------------------------------------------------------------
    # RF-07
    # ------------------------------------------------------------------
    def agenda_do_dia(self, profissional: str, dia: date) -> list[dict]:
        recurso = self._recursos.get(profissional)
        if recurso is None or recurso.tipo != "PROFISSIONAL":
            raise ErroAgenda("RECURSO_DESCONHECIDO", profissional)

        itens = []
        for agendamento in self._agendamentos.values():
            if agendamento.profissional != profissional:
                continue
            inicio_local = agendamento.inicio.astimezone(self._tz)
            if inicio_local.date() != dia:
                continue
            itens.append({
                "agendamento_id": agendamento.agendamento_id,
                "inicio": inicio_local,
                "fim": agendamento.fim.astimezone(self._tz),
                "paciente": agendamento.paciente,
                "situacao": agendamento.situacao,
            })

        itens.sort(key=lambda item: (item["inicio"], item["agendamento_id"]))
        return itens

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _buscar(self, agendamento_id: str) -> _Agendamento:
        agendamento = self._agendamentos.get(agendamento_id)
        if agendamento is None:
            raise ErroAgenda("AGENDAMENTO_NAO_ENCONTRADO", agendamento_id)
        return agendamento

    @staticmethod
    def _to_utc_valido(quando: datetime) -> datetime:
        if not isinstance(quando, datetime) or quando.tzinfo is None \
                or quando.tzinfo.utcoffset(quando) is None:
            raise ErroAgenda("DADOS_INVALIDOS", "quando deve ser timezone-aware")
        return quando.astimezone(timezone.utc)
