"""UC-05 — Motor de split e liquidação de recebíveis."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Callable

DUAS_CASAS = Decimal("0.01")


def _quant(valor: Decimal) -> Decimal:
    return valor.quantize(DUAS_CASAS, rounding=ROUND_HALF_EVEN)


def _to_decimal(valor) -> Decimal:
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, bool):
        raise ValueError("bool não é monetário")
    if isinstance(valor, float):
        return Decimal(str(valor))
    if isinstance(valor, (int, str)):
        return Decimal(valor)
    raise ValueError("valor monetário inválido")


def _to_decimal_ou_none(valor):
    try:
        return _to_decimal(valor)
    except Exception:
        return None


class ErroRecebivel(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code
        self.mensagem = mensagem


class MotorRecebiveis:
    def __init__(self, agora: Callable[[], datetime] | None = None) -> None:
        self._agora = agora or (lambda: datetime.now())
        self._transacoes: dict[str, dict] = {}
        self._recebiveis: dict[str, list[dict]] = {}

    # ------------------------------------------------------------------
    def registrar_transacao(self, dados: dict) -> str:
        valor = _to_decimal_ou_none(dados.get("valor"))
        parcelas = dados.get("parcelas")
        mdr = _to_decimal_ou_none(dados.get("mdr"))
        data_transacao = dados.get("data")

        invalido = (
            valor is None or valor <= 0
            or not isinstance(parcelas, int) or isinstance(parcelas, bool)
            or parcelas < 1 or parcelas > 12
            or mdr is None or mdr < 0 or mdr >= 1
            or not isinstance(data_transacao, date)
        )
        if invalido:
            raise ErroRecebivel("TRANSACAO_INVALIDA")

        split_bruto = dados.get("split")
        if not split_bruto:
            raise ErroRecebivel("SPLIT_INVALIDO")

        split: list[dict] = []
        vistos: set[str] = set()
        soma_percentual = Decimal("0")
        for item in split_bruto:
            participante = item.get("participante")
            percentual = _to_decimal_ou_none(item.get("percentual"))
            if not participante or percentual is None or percentual <= 0:
                raise ErroRecebivel("SPLIT_INVALIDO")
            if participante in vistos:
                raise ErroRecebivel("SPLIT_INVALIDO")
            vistos.add(participante)
            soma_percentual += percentual
            split.append({"participante": participante, "percentual": percentual})
        if soma_percentual != Decimal("1"):
            raise ErroRecebivel("SPLIT_INVALIDO")

        transacao_id = uuid.uuid4().hex
        self._transacoes[transacao_id] = {
            "valor": valor, "parcelas": parcelas, "mdr": mdr,
            "data": data_transacao, "split": split,
        }

        base = _quant(valor / parcelas)
        valores_parcela = [base] * parcelas
        residuo_parcelas = valor - base * parcelas
        valores_parcela[0] = _quant(valores_parcela[0] + residuo_parcelas)

        recebiveis: list[dict] = []
        for n in range(1, parcelas + 1):
            parcela_valor = valores_parcela[n - 1]
            vencimento = data_transacao + timedelta(days=30 * n)

            brutos: dict[str, Decimal] = {}
            soma_brutos = Decimal("0.00")
            for it in split:
                b = _quant(parcela_valor * it["percentual"])
                brutos[it["participante"]] = b
                soma_brutos += b
            residuo_split = parcela_valor - soma_brutos
            if residuo_split != 0:
                alvo = sorted(split, key=lambda it: (-it["percentual"], it["participante"]))[0]
                brutos[alvo["participante"]] = _quant(brutos[alvo["participante"]] + residuo_split)

            for it in split:
                participante = it["participante"]
                bruto = brutos[participante]
                taxa = _quant(bruto * mdr)
                liquido = bruto - taxa
                recebiveis.append({
                    "participante": participante,
                    "parcela": n,
                    "vencimento": vencimento,
                    "valor_bruto": bruto,
                    "taxa": taxa,
                    "valor_liquido": liquido,
                    "situacao": "A_RECEBER",
                    "_original_liquido": liquido,
                    "_eventos": [],
                })
        self._recebiveis[transacao_id] = recebiveis
        return transacao_id

    # ------------------------------------------------------------------
    def recebiveis(self, transacao_id: str) -> list[dict]:
        if transacao_id not in self._transacoes:
            raise ErroRecebivel("TRANSACAO_NAO_ENCONTRADA")
        itens = [{
            "participante": r["participante"],
            "parcela": r["parcela"],
            "vencimento": r["vencimento"],
            "valor_bruto": r["valor_bruto"],
            "taxa": r["taxa"],
            "valor_liquido": r["valor_liquido"],
            "situacao": r["situacao"],
        } for r in self._recebiveis[transacao_id]]
        itens.sort(key=lambda x: (x["parcela"], x["participante"]))
        return itens

    # ------------------------------------------------------------------
    def antecipar(self, transacao_id: str, participante: str,
                  ate_parcela: int, data: date) -> dict:
        if transacao_id not in self._transacoes:
            raise ErroRecebivel("TRANSACAO_NAO_ENCONTRADA")
        trans = self._transacoes[transacao_id]
        participantes_validos = {it["participante"] for it in trans["split"]}
        if participante not in participantes_validos:
            raise ErroRecebivel("PARTICIPANTE_INVALIDO")
        if (not isinstance(ate_parcela, int) or isinstance(ate_parcela, bool)
                or ate_parcela < 1 or ate_parcela > trans["parcelas"]):
            raise ErroRecebivel("PARCELA_INVALIDA")

        elegiveis = [r for r in self._recebiveis[transacao_id]
                     if r["participante"] == participante
                     and r["situacao"] == "A_RECEBER"
                     and r["parcela"] <= ate_parcela]
        if not elegiveis:
            raise ErroRecebivel("ESTADO_INVALIDO")

        total_bruto = Decimal("0.00")
        total_liquido = Decimal("0.00")
        total_desagio = Decimal("0.00")
        parcelas_afetadas: list[int] = []
        for r in elegiveis:
            dias = (r["vencimento"] - data).days
            if dias <= 0:
                desagio = Decimal("0.00")
            else:
                desagio = _quant(r["valor_liquido"] * Decimal("0.015") * dias / Decimal("30"))
            total_bruto += r["valor_bruto"]
            total_liquido += r["valor_liquido"]
            total_desagio += desagio
            r["situacao"] = "ANTECIPADO"
            r["_eventos"].append({"tipo": "ANTECIPADO", "data": data, "valor": r["valor_liquido"]})
            parcelas_afetadas.append(r["parcela"])

        return {
            "valor_bruto": total_bruto,
            "desagio": total_desagio,
            "valor_liquido": total_liquido - total_desagio,
            "parcelas": sorted(set(parcelas_afetadas)),
        }

    # ------------------------------------------------------------------
    def estornar(self, transacao_id: str, valor, data: date) -> dict:
        if transacao_id not in self._transacoes:
            raise ErroRecebivel("TRANSACAO_NAO_ENCONTRADA")

        elegiveis = [r for r in self._recebiveis[transacao_id] if r["situacao"] == "A_RECEBER"]
        if not elegiveis:
            raise ErroRecebivel("ESTADO_INVALIDO")

        valor_dec = _to_decimal_ou_none(valor)
        soma_bruto = sum((r["valor_bruto"] for r in elegiveis), Decimal("0.00"))
        if valor_dec is None or valor_dec <= 0 or valor_dec > soma_bruto:
            raise ErroRecebivel("VALOR_INVALIDO")

        mdr = self._transacoes[transacao_id]["mdr"]

        partes = [_quant(valor_dec * r["valor_bruto"] / soma_bruto) for r in elegiveis]
        residuo = valor_dec - sum(partes, Decimal("0.00"))
        if residuo != 0:
            idx_alvo = min(
                range(len(elegiveis)),
                key=lambda i: (-elegiveis[i]["valor_bruto"], elegiveis[i]["parcela"], elegiveis[i]["participante"]),
            )
            partes[idx_alvo] = _quant(partes[idx_alvo] + residuo)

        por_participante: dict[str, Decimal] = {}
        for r, parte in zip(elegiveis, partes):
            novo_bruto = _quant(r["valor_bruto"] - parte)
            r["valor_bruto"] = novo_bruto
            nova_taxa = _quant(novo_bruto * mdr)
            r["taxa"] = nova_taxa
            r["valor_liquido"] = novo_bruto - nova_taxa
            if novo_bruto == Decimal("0.00"):
                r["situacao"] = "ESTORNADO"
            r["_eventos"].append({"tipo": "ESTORNO", "data": data, "valor": parte})
            por_participante[r["participante"]] = por_participante.get(r["participante"], Decimal("0.00")) + parte

        return {"estornado": valor_dec, "por_participante": por_participante}

    # ------------------------------------------------------------------
    def liquidar(self, data: date) -> list[dict]:
        resultado = []
        for transacao_id, recebiveis in self._recebiveis.items():
            for r in recebiveis:
                if r["situacao"] == "A_RECEBER" and r["vencimento"] <= data:
                    r["situacao"] = "LIQUIDADO"
                    r["_eventos"].append({"tipo": "LIQUIDADO", "data": data, "valor": r["valor_liquido"]})
                    resultado.append({
                        "transacao_id": transacao_id,
                        "participante": r["participante"],
                        "parcela": r["parcela"],
                        "valor_liquido": r["valor_liquido"],
                    })
        resultado.sort(key=lambda x: (x["transacao_id"], x["parcela"], x["participante"]))
        return resultado

    # ------------------------------------------------------------------
    def posicao(self, participante: str, data: date) -> dict:
        a_receber = Decimal("0.00")
        antecipado = Decimal("0.00")
        liquidado = Decimal("0.00")
        estornado = Decimal("0.00")

        for recebiveis in self._recebiveis.values():
            for r in recebiveis:
                if r["participante"] != participante:
                    continue
                if not any(ev["data"] <= data for ev in r["_eventos"]):
                    a_receber += r["_original_liquido"]
                for ev in r["_eventos"]:
                    if ev["data"] > data:
                        continue
                    if ev["tipo"] == "ANTECIPADO":
                        antecipado += ev["valor"]
                    elif ev["tipo"] == "LIQUIDADO":
                        liquidado += ev["valor"]
                    elif ev["tipo"] == "ESTORNO":
                        estornado += ev["valor"]

        return {
            "a_receber": a_receber,
            "antecipado": antecipado,
            "liquidado": liquidado,
            "estornado": estornado,
        }
