"""UC-10 — Motor de conciliação de pagamentos."""

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN

_STATUS_VALIDOS = ("APROVADA", "CANCELADA", "ESTORNADA")
_TIPO_VALIDOS = ("VENDA", "ESTORNO")
_CATEGORIAS = ("CONCILIADA", "DIVERGENTE", "DUPLICADA", "SOMENTE_INTERNA", "SOMENTE_EXTRATO")
_STATUS_PARTICIPANTES = ("APROVADA", "ESTORNADA")
_STATUS_PARA_TIPO = {"APROVADA": "VENDA", "ESTORNADA": "ESTORNO"}
_DOIS_CENTAVOS = Decimal("0.01")


class ErroConciliacao(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


def _to_decimal(valor):
    if isinstance(valor, bool):
        raise ValueError("tipo inválido para valor monetário")
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, int):
        return Decimal(valor)
    if isinstance(valor, float):
        return Decimal(str(valor))
    if isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            raise ValueError("valor monetário vazio")
        return Decimal(texto)
    raise ValueError("tipo inválido para valor monetário")


class MotorConciliacao:
    def __init__(self) -> None:
        self._internas: dict[str, dict] = {}
        self._extrato: dict[str, list[dict]] = {}
        self._categorias: dict[str, dict] = {}
        self._counts: dict[str, int] = {c: 0 for c in _CATEGORIAS}
        self._total_liquido = Decimal("0.00")
        self._conciliado = False
        self._resolvidas: set[str] = set()

    # ------------------------------------------------------------------ #
    # Carga
    # ------------------------------------------------------------------ #
    def carregar_internas(self, registros: list[dict]) -> int:
        novos: dict[str, dict] = {}
        for registro in registros:
            transacao_id = registro.get("transacao_id")
            if not transacao_id or not isinstance(transacao_id, str):
                raise ErroConciliacao("REGISTRO_INVALIDO", "transacao_id vazio ou ausente")

            try:
                valor = _to_decimal(registro.get("valor"))
            except (InvalidOperation, ValueError, TypeError):
                raise ErroConciliacao("REGISTRO_INVALIDO", "valor inválido")
            if valor <= 0:
                raise ErroConciliacao("REGISTRO_INVALIDO", "valor deve ser positivo")

            data = registro.get("data")
            if not isinstance(data, date):
                raise ErroConciliacao("REGISTRO_INVALIDO", "data ausente ou inválida")

            status = registro.get("status")
            if status not in _STATUS_VALIDOS:
                raise ErroConciliacao("REGISTRO_INVALIDO", "status fora do vocabulário")

            if transacao_id in self._internas or transacao_id in novos:
                raise ErroConciliacao("REGISTRO_INVALIDO", "transacao_id repetido nas internas")

            novos[transacao_id] = {"valor": valor, "data": data, "status": status}

        self._internas.update(novos)
        return len(novos)

    def carregar_extrato(self, registros: list[dict]) -> int:
        novos: list[tuple[str, dict]] = []
        for registro in registros:
            transacao_id = registro.get("transacao_id")
            if not transacao_id or not isinstance(transacao_id, str):
                raise ErroConciliacao("REGISTRO_INVALIDO", "transacao_id vazio ou ausente")

            try:
                valor_bruto = _to_decimal(registro.get("valor_bruto"))
                taxa = _to_decimal(registro.get("taxa"))
            except (InvalidOperation, ValueError, TypeError):
                raise ErroConciliacao("REGISTRO_INVALIDO", "valor inválido")

            if valor_bruto <= 0:
                raise ErroConciliacao("REGISTRO_INVALIDO", "valor_bruto deve ser positivo")
            if taxa < 0:
                raise ErroConciliacao("REGISTRO_INVALIDO", "taxa não pode ser negativa")
            if taxa > valor_bruto:
                raise ErroConciliacao("REGISTRO_INVALIDO", "taxa maior que valor_bruto")

            data = registro.get("data")
            if not isinstance(data, date):
                raise ErroConciliacao("REGISTRO_INVALIDO", "data ausente ou inválida")

            tipo = registro.get("tipo")
            if tipo not in _TIPO_VALIDOS:
                raise ErroConciliacao("REGISTRO_INVALIDO", "tipo fora do vocabulário")

            novos.append((transacao_id, {
                "valor_bruto": valor_bruto, "taxa": taxa, "data": data, "tipo": tipo,
            }))

        for transacao_id, registro in novos:
            self._extrato.setdefault(transacao_id, []).append(registro)
        return len(novos)

    # ------------------------------------------------------------------ #
    # Conciliação
    # ------------------------------------------------------------------ #
    def conciliar(self, data_corte: date) -> dict:
        internas_participantes = {
            tid: reg for tid, reg in self._internas.items()
            if reg["status"] in _STATUS_PARTICIPANTES and reg["data"] <= data_corte
        }

        limite_extrato = data_corte + timedelta(days=2)
        extrato_participante: dict[str, list[dict]] = {}
        for tid, registros in self._extrato.items():
            filtrados = [r for r in registros if r["data"] <= limite_extrato]
            if filtrados:
                extrato_participante[tid] = filtrados

        categorias: dict[str, dict] = {}
        total_liquido = Decimal("0")

        duplicadas_ids = {tid for tid, regs in extrato_participante.items() if len(regs) >= 2}
        for tid in duplicadas_ids:
            primeira = extrato_participante[tid][0]
            interna = internas_participantes.get(tid)
            categorias[tid] = {
                "categoria": "DUPLICADA",
                "motivo": None,
                "valor_interno": interna["valor"] if interna else None,
                "valor_extrato": primeira["valor_bruto"],
            }

        pareadas_ids: set[str] = set()
        for tid, registros in extrato_participante.items():
            if tid in duplicadas_ids:
                continue
            registro_extrato = registros[0]
            interna = internas_participantes.get(tid)
            if interna is None:
                categorias[tid] = {
                    "categoria": "SOMENTE_EXTRATO",
                    "motivo": None,
                    "valor_interno": None,
                    "valor_extrato": registro_extrato["valor_bruto"],
                }
                continue

            pareadas_ids.add(tid)
            tipo_esperado = _STATUS_PARA_TIPO[interna["status"]]
            if registro_extrato["tipo"] != tipo_esperado:
                categorias[tid] = {
                    "categoria": "DIVERGENTE", "motivo": "TIPO_DIVERGENTE",
                    "valor_interno": interna["valor"], "valor_extrato": registro_extrato["valor_bruto"],
                }
            elif interna["valor"] != registro_extrato["valor_bruto"]:
                categorias[tid] = {
                    "categoria": "DIVERGENTE", "motivo": "VALOR_DIVERGENTE",
                    "valor_interno": interna["valor"], "valor_extrato": registro_extrato["valor_bruto"],
                }
            elif not (interna["data"] <= registro_extrato["data"] <= interna["data"] + timedelta(days=2)):
                categorias[tid] = {
                    "categoria": "DIVERGENTE", "motivo": "FORA_DA_JANELA",
                    "valor_interno": interna["valor"], "valor_extrato": registro_extrato["valor_bruto"],
                }
            else:
                categorias[tid] = {
                    "categoria": "CONCILIADA", "motivo": None,
                    "valor_interno": interna["valor"], "valor_extrato": registro_extrato["valor_bruto"],
                }
                liquido = registro_extrato["valor_bruto"] - registro_extrato["taxa"]
                if registro_extrato["tipo"] == "VENDA":
                    total_liquido += liquido
                else:
                    total_liquido -= liquido

        for tid, interna in internas_participantes.items():
            if tid in duplicadas_ids or tid in pareadas_ids:
                continue
            categorias[tid] = {
                "categoria": "SOMENTE_INTERNA",
                "motivo": None,
                "valor_interno": interna["valor"],
                "valor_extrato": None,
            }

        counts = {c: 0 for c in _CATEGORIAS}
        for item in categorias.values():
            counts[item["categoria"]] += 1

        self._categorias = categorias
        self._counts = counts
        self._total_liquido = total_liquido.quantize(_DOIS_CENTAVOS, rounding=ROUND_HALF_EVEN)
        self._conciliado = True

        return {
            "conciliadas": counts["CONCILIADA"],
            "divergentes": counts["DIVERGENTE"],
            "duplicadas": counts["DUPLICADA"],
            "somente_interna": counts["SOMENTE_INTERNA"],
            "somente_extrato": counts["SOMENTE_EXTRATO"],
            "total_liquido": self._total_liquido,
        }

    # ------------------------------------------------------------------ #
    # Consultas
    # ------------------------------------------------------------------ #
    def itens(self, categoria: str) -> list[dict]:
        if not self._conciliado:
            raise ErroConciliacao("CONCILIACAO_NAO_EXECUTADA", "conciliar ainda não foi chamado")
        if categoria not in _CATEGORIAS:
            raise ErroConciliacao("CATEGORIA_INVALIDA", "categoria fora do vocabulário")

        resultado = [
            {
                "transacao_id": tid,
                "categoria": item["categoria"],
                "motivo": item["motivo"],
                "valor_interno": item["valor_interno"],
                "valor_extrato": item["valor_extrato"],
                "resolvida": item["categoria"] == "DIVERGENTE" and tid in self._resolvidas,
            }
            for tid, item in self._categorias.items()
            if item["categoria"] == categoria
        ]
        resultado.sort(key=lambda item: item["transacao_id"])
        return resultado

    def resolver(self, transacao_id: str, ator: str, observacao: str) -> None:
        # G-11: existência -> categoria/estado -> argumentos
        item = self._categorias.get(transacao_id)
        if item is None:
            raise ErroConciliacao("TRANSACAO_NAO_ENCONTRADA", "transacao não está na conciliação")

        if item["categoria"] != "DIVERGENTE" or transacao_id in self._resolvidas:
            raise ErroConciliacao("ESTADO_INVALIDO", "transacao não está divergente pendente")

        if not ator or not observacao:
            raise ErroConciliacao("REGISTRO_INVALIDO", "ator ou observacao vazios")

        self._resolvidas.add(transacao_id)

    def relatorio(self) -> dict:
        if not self._conciliado:
            raise ErroConciliacao("CONCILIACAO_NAO_EXECUTADA", "conciliar ainda não foi chamado")

        pendentes = 0
        resolvidas = 0
        for tid, item in self._categorias.items():
            if item["categoria"] != "DIVERGENTE":
                continue
            if tid in self._resolvidas:
                resolvidas += 1
            else:
                pendentes += 1

        return {
            "por_categoria": dict(self._counts),
            "pendentes": pendentes,
            "resolvidas": resolvidas,
            "total_liquido": self._total_liquido,
        }
