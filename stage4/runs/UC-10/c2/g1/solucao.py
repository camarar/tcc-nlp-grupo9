"""UC-10 — Motor de conciliação de pagamentos."""

from __future__ import annotations

import itertools
import math
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN

STATUS_VALIDOS = {"APROVADA", "CANCELADA", "ESTORNADA"}
TIPOS_VALIDOS = {"VENDA", "ESTORNO"}
CATEGORIAS_VALIDAS = {
    "CONCILIADA", "DIVERGENTE", "DUPLICADA", "SOMENTE_INTERNA", "SOMENTE_EXTRATO",
}
CODES_VALIDOS = {
    "REGISTRO_INVALIDO", "TRANSACAO_NAO_ENCONTRADA", "ESTADO_INVALIDO",
    "CONCILIACAO_NAO_EXECUTADA", "CATEGORIA_INVALIDA",
}

JANELA_DIAS = 2


class ErroConciliacao(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


def _to_decimal(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return Decimal(str(value))
    if isinstance(value, str):
        texto = value.strip()
        if not texto:
            return None
        try:
            return Decimal(texto)
        except InvalidOperation:
            return None
    return None


class MotorConciliacao:
    def __init__(self) -> None:
        self._internas: dict[str, dict] = {}
        self._extrato_all: list[dict] = []
        self._extrato_seq = itertools.count()
        self._resolucoes: set[str] = set()
        self._itens: dict[str, dict] = {}
        self._conciliado = False
        self._ultimo_total = Decimal("0.00")

    # ------------------------------------------------------------------
    # Carga
    # ------------------------------------------------------------------

    def _normaliza_interna(self, registro, ids_no_lote: set[str]) -> dict:
        if not isinstance(registro, dict):
            raise ErroConciliacao("REGISTRO_INVALIDO", "registro interno invalido")
        tid = registro.get("transacao_id")
        if not tid or not isinstance(tid, str):
            raise ErroConciliacao("REGISTRO_INVALIDO", "transacao_id vazio ou ausente")
        status = registro.get("status")
        if status not in STATUS_VALIDOS:
            raise ErroConciliacao("REGISTRO_INVALIDO", "status fora do vocabulario")
        data = registro.get("data")
        if not isinstance(data, date):
            raise ErroConciliacao("REGISTRO_INVALIDO", "data ausente ou invalida")
        valor = _to_decimal(registro.get("valor"))
        if valor is None or valor <= 0:
            raise ErroConciliacao("REGISTRO_INVALIDO", "valor invalido")
        if tid in ids_no_lote or tid in self._internas:
            raise ErroConciliacao("REGISTRO_INVALIDO", "transacao_id repetido nas internas")
        return {"transacao_id": tid, "valor": valor, "data": data, "status": status}

    def _normaliza_extrato(self, registro) -> dict:
        if not isinstance(registro, dict):
            raise ErroConciliacao("REGISTRO_INVALIDO", "registro de extrato invalido")
        tid = registro.get("transacao_id")
        if not tid or not isinstance(tid, str):
            raise ErroConciliacao("REGISTRO_INVALIDO", "transacao_id vazio ou ausente")
        tipo = registro.get("tipo")
        if tipo not in TIPOS_VALIDOS:
            raise ErroConciliacao("REGISTRO_INVALIDO", "tipo fora do vocabulario")
        data = registro.get("data")
        if not isinstance(data, date):
            raise ErroConciliacao("REGISTRO_INVALIDO", "data ausente ou invalida")
        valor_bruto = _to_decimal(registro.get("valor_bruto"))
        if valor_bruto is None or valor_bruto <= 0:
            raise ErroConciliacao("REGISTRO_INVALIDO", "valor_bruto invalido")
        taxa = _to_decimal(registro.get("taxa"))
        if taxa is None or taxa < 0:
            raise ErroConciliacao("REGISTRO_INVALIDO", "taxa invalida")
        if taxa > valor_bruto:
            raise ErroConciliacao("REGISTRO_INVALIDO", "taxa maior que valor_bruto")
        return {
            "transacao_id": tid, "valor_bruto": valor_bruto, "taxa": taxa,
            "data": data, "tipo": tipo,
        }

    def carregar_internas(self, registros: list[dict]) -> int:
        ids_no_lote: set[str] = set()
        novos = []
        for registro in registros:
            item = self._normaliza_interna(registro, ids_no_lote)
            ids_no_lote.add(item["transacao_id"])
            novos.append(item)
        for item in novos:
            self._internas[item["transacao_id"]] = item
        return len(novos)

    def carregar_extrato(self, registros: list[dict]) -> int:
        novos = [self._normaliza_extrato(registro) for registro in registros]
        for item in novos:
            item["seq"] = next(self._extrato_seq)
            self._extrato_all.append(item)
        return len(novos)

    # ------------------------------------------------------------------
    # Conciliação
    # ------------------------------------------------------------------

    @staticmethod
    def _classifica_par(interna: dict, extrato: dict) -> str | None:
        tipo_esperado = "VENDA" if interna["status"] == "APROVADA" else "ESTORNO"
        if extrato["tipo"] != tipo_esperado:
            return "TIPO_DIVERGENTE"
        if interna["valor"] != extrato["valor_bruto"]:
            return "VALOR_DIVERGENTE"
        limite_inferior = interna["data"]
        limite_superior = interna["data"] + timedelta(days=JANELA_DIAS)
        if not (limite_inferior <= extrato["data"] <= limite_superior):
            return "FORA_DA_JANELA"
        return None

    def conciliar(self, data_corte: date) -> dict:
        limite_extrato = data_corte + timedelta(days=JANELA_DIAS)

        participantes_internas = {
            tid: r for tid, r in self._internas.items()
            if r["status"] in ("APROVADA", "ESTORNADA") and r["data"] <= data_corte
        }

        extrato_filtrado = [r for r in self._extrato_all if r["data"] <= limite_extrato]
        grupos: dict[str, list[dict]] = defaultdict(list)
        for registro in extrato_filtrado:
            grupos[registro["transacao_id"]].append(registro)

        itens: dict[str, dict] = {}
        total = Decimal("0")

        for tid in set(participantes_internas) | set(grupos):
            interna = participantes_internas.get(tid)
            grupo = grupos.get(tid, [])

            if len(grupo) >= 2:
                primeira = min(grupo, key=lambda r: r["seq"])
                categoria = "DUPLICADA"
                motivo = None
                valor_interno = interna["valor"] if interna else None
                valor_extrato = primeira["valor_bruto"]
            elif grupo and interna is not None:
                extrato = grupo[0]
                motivo = self._classifica_par(interna, extrato)
                categoria = "DIVERGENTE" if motivo else "CONCILIADA"
                valor_interno = interna["valor"]
                valor_extrato = extrato["valor_bruto"]
                if categoria == "CONCILIADA":
                    liquido = extrato["valor_bruto"] - extrato["taxa"]
                    total += liquido if extrato["tipo"] == "VENDA" else -liquido
            elif grupo and interna is None:
                categoria = "SOMENTE_EXTRATO"
                motivo = None
                valor_interno = None
                valor_extrato = grupo[0]["valor_bruto"]
            else:
                categoria = "SOMENTE_INTERNA"
                motivo = None
                valor_interno = interna["valor"]
                valor_extrato = None

            itens[tid] = {
                "transacao_id": tid,
                "categoria": categoria,
                "motivo": motivo,
                "valor_interno": valor_interno,
                "valor_extrato": valor_extrato,
            }

        total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)

        self._itens = itens
        self._conciliado = True
        self._ultimo_total = total

        contagem = {categoria: 0 for categoria in CATEGORIAS_VALIDAS}
        for item in itens.values():
            contagem[item["categoria"]] += 1

        return {
            "conciliadas": contagem["CONCILIADA"],
            "divergentes": contagem["DIVERGENTE"],
            "duplicadas": contagem["DUPLICADA"],
            "somente_interna": contagem["SOMENTE_INTERNA"],
            "somente_extrato": contagem["SOMENTE_EXTRATO"],
            "total_liquido": total,
        }

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def _exige_conciliado(self) -> None:
        if not self._conciliado:
            raise ErroConciliacao("CONCILIACAO_NAO_EXECUTADA", "conciliar() ainda nao foi executado")

    def itens(self, categoria: str) -> list[dict]:
        self._exige_conciliado()
        if categoria not in CATEGORIAS_VALIDAS:
            raise ErroConciliacao("CATEGORIA_INVALIDA", "categoria fora do vocabulario")

        resultado = []
        for tid in sorted(self._itens):
            item = self._itens[tid]
            if item["categoria"] != categoria:
                continue
            resolvida = item["categoria"] == "DIVERGENTE" and tid in self._resolucoes
            resultado.append({
                "transacao_id": item["transacao_id"],
                "categoria": item["categoria"],
                "motivo": item["motivo"],
                "valor_interno": item["valor_interno"],
                "valor_extrato": item["valor_extrato"],
                "resolvida": resolvida,
            })
        return resultado

    def resolver(self, transacao_id: str, ator: str, observacao: str) -> None:
        item = self._itens.get(transacao_id)
        if item is None:
            raise ErroConciliacao("TRANSACAO_NAO_ENCONTRADA", "transacao nao encontrada na conciliacao")
        if item["categoria"] != "DIVERGENTE" or transacao_id in self._resolucoes:
            raise ErroConciliacao("ESTADO_INVALIDO", "transacao nao esta em estado divergente pendente")
        if not ator or not observacao:
            raise ErroConciliacao("REGISTRO_INVALIDO", "ator e observacao sao obrigatorios")
        self._resolucoes.add(transacao_id)

    def relatorio(self) -> dict:
        self._exige_conciliado()

        por_categoria = {categoria: 0 for categoria in CATEGORIAS_VALIDAS}
        pendentes = 0
        resolvidas = 0
        for tid, item in self._itens.items():
            por_categoria[item["categoria"]] += 1
            if item["categoria"] == "DIVERGENTE":
                if tid in self._resolucoes:
                    resolvidas += 1
                else:
                    pendentes += 1

        return {
            "por_categoria": por_categoria,
            "pendentes": pendentes,
            "resolvidas": resolvidas,
            "total_liquido": self._ultimo_total,
        }
