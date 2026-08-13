"""UC-05 — Motor de split e liquidação de recebíveis."""

from __future__ import annotations

import itertools
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Callable, Optional

_DOIS_CASAS = Decimal("0.01")
_TAXA_ANTECIPACAO_MENSAL = Decimal("0.015")
_DIAS_MES = Decimal("30")


def _quant(valor: Decimal) -> Decimal:
    return valor.quantize(_DOIS_CASAS, rounding=ROUND_HALF_EVEN)


def _to_decimal(valor) -> Decimal:
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, bool):
        raise ValueError("bool não é um valor monetário válido")
    if isinstance(valor, int):
        return Decimal(valor)
    if isinstance(valor, float):
        return Decimal(str(valor))
    if isinstance(valor, str):
        return Decimal(valor)
    raise ValueError("valor não conversível para Decimal")


class ErroRecebivel(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


class MotorRecebiveis:
    def __init__(self, agora: Optional[Callable[[], datetime]] = None) -> None:
        self._agora = agora or datetime.now
        self._transacoes: dict[str, dict] = {}
        self._recebiveis: dict[str, list[dict]] = {}
        self._seq = itertools.count(1)

    # ------------------------------------------------------------------ #
    # API pública
    # ------------------------------------------------------------------ #

    def registrar_transacao(self, dados: dict) -> str:
        valor_raw = dados.get("valor")
        parcelas = dados.get("parcelas")
        mdr_raw = dados.get("mdr")
        data_transacao = dados.get("data")
        split = dados.get("split")

        try:
            valor_dec = _to_decimal(valor_raw)
        except Exception:
            raise ErroRecebivel("TRANSACAO_INVALIDA", "valor inválido")
        if valor_dec <= 0:
            raise ErroRecebivel("TRANSACAO_INVALIDA", "valor deve ser positivo")

        if not isinstance(parcelas, int) or isinstance(parcelas, bool) or parcelas < 1 or parcelas > 12:
            raise ErroRecebivel("TRANSACAO_INVALIDA", "parcelas fora do intervalo permitido")

        try:
            mdr_dec = _to_decimal(mdr_raw)
        except Exception:
            raise ErroRecebivel("TRANSACAO_INVALIDA", "mdr inválido")
        if mdr_dec < 0 or mdr_dec >= 1:
            raise ErroRecebivel("TRANSACAO_INVALIDA", "mdr fora do intervalo permitido")

        if not isinstance(data_transacao, date):
            raise ErroRecebivel("TRANSACAO_INVALIDA", "data ausente ou inválida")

        if not split or not isinstance(split, list):
            raise ErroRecebivel("SPLIT_INVALIDO", "split vazio ou ausente")

        nomes = [item.get("participante") for item in split]
        if len(nomes) != len(set(nomes)):
            raise ErroRecebivel("SPLIT_INVALIDO", "participante repetido")

        split_convertido = []
        soma_percentuais = Decimal("0")
        for item in split:
            try:
                percentual = _to_decimal(item.get("percentual"))
            except Exception:
                raise ErroRecebivel("SPLIT_INVALIDO", "percentual inválido")
            if percentual <= 0:
                raise ErroRecebivel("SPLIT_INVALIDO", "percentual deve ser positivo")
            soma_percentuais += percentual
            split_convertido.append({"participante": item.get("participante"), "percentual": percentual})
        if soma_percentuais != Decimal("1"):
            raise ErroRecebivel("SPLIT_INVALIDO", "soma dos percentuais diferente de 1")

        tid = self._novo_id()
        valores_parcela = self._dividir_parcelas(valor_dec, parcelas)

        recs: list[dict] = []
        for n in range(1, parcelas + 1):
            bruto_parcela = valores_parcela[n - 1]
            vencimento = data_transacao + timedelta(days=30 * n)
            partes = self._ratear_split(bruto_parcela, split_convertido)
            for item in split_convertido:
                nome = item["participante"]
                valor_bruto = partes[nome]
                taxa = _quant(valor_bruto * mdr_dec)
                valor_liquido = valor_bruto - taxa
                recs.append({
                    "participante": nome,
                    "parcela": n,
                    "vencimento": vencimento,
                    "valor_bruto": valor_bruto,
                    "taxa": taxa,
                    "valor_liquido": valor_liquido,
                    "valor_liquido_original": valor_liquido,
                    "situacao": "A_RECEBER",
                    "eventos": [],
                })

        self._transacoes[tid] = {
            "valor": valor_dec,
            "parcelas": parcelas,
            "mdr": mdr_dec,
            "data": data_transacao,
            "split": split_convertido,
        }
        self._recebiveis[tid] = recs
        return tid

    def recebiveis(self, transacao_id: str) -> list[dict]:
        recs = self._obter_recebiveis(transacao_id)
        ordenados = sorted(recs, key=lambda r: (r["parcela"], r["participante"]))
        return [{
            "participante": r["participante"],
            "parcela": r["parcela"],
            "vencimento": r["vencimento"],
            "valor_bruto": r["valor_bruto"],
            "taxa": r["taxa"],
            "valor_liquido": r["valor_liquido"],
            "situacao": r["situacao"],
        } for r in ordenados]

    def antecipar(self, transacao_id: str, participante: str, ate_parcela: int, data: date) -> dict:
        recs = self._obter_recebiveis(transacao_id)
        tx = self._transacoes[transacao_id]

        nomes_split = {item["participante"] for item in tx["split"]}
        if participante not in nomes_split:
            raise ErroRecebivel("PARTICIPANTE_INVALIDO", "participante fora do split")

        if not isinstance(ate_parcela, int) or isinstance(ate_parcela, bool) or not (1 <= ate_parcela <= tx["parcelas"]):
            raise ErroRecebivel("PARCELA_INVALIDA", "ate_parcela fora do intervalo da transação")

        elegiveis = [r for r in recs
                     if r["participante"] == participante
                     and r["situacao"] == "A_RECEBER"
                     and r["parcela"] <= ate_parcela]
        if not elegiveis:
            raise ErroRecebivel("ESTADO_INVALIDO", "nenhum recebível elegível para antecipação")

        desagio_total = Decimal("0.00")
        valor_bruto_total = Decimal("0.00")
        valor_liquido_total = Decimal("0.00")
        parcelas_afetadas = []

        for r in elegiveis:
            dias = (r["vencimento"] - data).days
            if dias <= 0:
                desagio = Decimal("0.00")
            else:
                desagio = _quant(r["valor_liquido"] * _TAXA_ANTECIPACAO_MENSAL * Decimal(dias) / _DIAS_MES)
            desagio_total += desagio
            valor_bruto_total += r["valor_bruto"]
            valor_liquido_total += r["valor_liquido"]
            r["situacao"] = "ANTECIPADO"
            r["eventos"].append({"tipo": "ANTECIPADO", "data": data, "valor": r["valor_liquido"]})
            parcelas_afetadas.append(r["parcela"])

        return {
            "valor_bruto": valor_bruto_total,
            "desagio": desagio_total,
            "valor_liquido": valor_liquido_total - desagio_total,
            "parcelas": sorted(set(parcelas_afetadas)),
        }

    def estornar(self, transacao_id: str, valor, data: date) -> dict:
        recs = self._obter_recebiveis(transacao_id)

        a_receber = [r for r in recs if r["situacao"] == "A_RECEBER"]
        if not a_receber:
            raise ErroRecebivel("ESTADO_INVALIDO", "não há recebíveis a receber nesta transação")

        try:
            valor_dec = _to_decimal(valor)
        except Exception:
            raise ErroRecebivel("VALOR_INVALIDO", "valor inválido")

        soma_bruto = sum((r["valor_bruto"] for r in a_receber), Decimal("0.00"))
        if valor_dec <= 0 or valor_dec > soma_bruto:
            raise ErroRecebivel("VALOR_INVALIDO", "valor de estorno fora do intervalo permitido")

        partes: dict[int, Decimal] = {}
        soma_rateio = Decimal("0.00")
        for r in a_receber:
            v = _quant(valor_dec * r["valor_bruto"] / soma_bruto)
            partes[id(r)] = v
            soma_rateio += v

        residuo = valor_dec - soma_rateio
        if residuo != 0:
            alvo = sorted(a_receber, key=lambda r: (-r["valor_bruto"], r["parcela"], r["participante"]))[0]
            partes[id(alvo)] += residuo

        por_participante: dict[str, Decimal] = {}
        mdr = self._transacoes[transacao_id]["mdr"]
        for r in a_receber:
            v = partes[id(r)]
            r["valor_bruto"] -= v
            r["taxa"] = _quant(r["valor_bruto"] * mdr)
            r["valor_liquido"] = r["valor_bruto"] - r["taxa"]
            if r["valor_bruto"] == Decimal("0.00"):
                r["situacao"] = "ESTORNADO"
            r["eventos"].append({"tipo": "ESTORNO", "data": data, "valor": v})
            por_participante[r["participante"]] = por_participante.get(r["participante"], Decimal("0.00")) + v

        return {"estornado": valor_dec, "por_participante": por_participante}

    def liquidar(self, data: date) -> list[dict]:
        resultado = []
        for tid, recs in self._recebiveis.items():
            for r in recs:
                if r["situacao"] == "A_RECEBER" and r["vencimento"] <= data:
                    r["situacao"] = "LIQUIDADO"
                    r["eventos"].append({"tipo": "LIQUIDADO", "data": data, "valor": r["valor_liquido"]})
                    resultado.append({
                        "transacao_id": tid,
                        "participante": r["participante"],
                        "parcela": r["parcela"],
                        "valor_liquido": r["valor_liquido"],
                    })
        resultado.sort(key=lambda x: (x["transacao_id"], x["parcela"], x["participante"]))
        return resultado

    def posicao(self, participante: str, data: date) -> dict:
        a_receber = Decimal("0.00")
        antecipado = Decimal("0.00")
        liquidado = Decimal("0.00")
        estornado = Decimal("0.00")

        for recs in self._recebiveis.values():
            for r in recs:
                if r["participante"] != participante:
                    continue
                eventos_ate = [e for e in r["eventos"] if e["data"] <= data]
                if not eventos_ate:
                    a_receber += r["valor_liquido_original"]
                    continue
                for e in eventos_ate:
                    if e["tipo"] == "ANTECIPADO":
                        antecipado += e["valor"]
                    elif e["tipo"] == "LIQUIDADO":
                        liquidado += e["valor"]
                    elif e["tipo"] == "ESTORNO":
                        estornado += e["valor"]

        return {
            "a_receber": a_receber,
            "antecipado": antecipado,
            "liquidado": liquidado,
            "estornado": estornado,
        }

    # ------------------------------------------------------------------ #
    # Auxiliares internos
    # ------------------------------------------------------------------ #

    def _novo_id(self) -> str:
        return f"TX{next(self._seq):06d}"

    def _obter_recebiveis(self, transacao_id: str) -> list[dict]:
        recs = self._recebiveis.get(transacao_id)
        if recs is None:
            raise ErroRecebivel("TRANSACAO_NAO_ENCONTRADA", "transação inexistente")
        return recs

    @staticmethod
    def _dividir_parcelas(valor: Decimal, parcelas: int) -> list[Decimal]:
        base = _quant(valor / parcelas)
        valores = [base] * parcelas
        valores[0] = valor - base * (parcelas - 1)
        return valores

    @staticmethod
    def _ratear_split(valor_total: Decimal, split: list[dict]) -> dict[str, Decimal]:
        partes: dict[str, Decimal] = {}
        soma = Decimal("0.00")
        for item in split:
            v = _quant(valor_total * item["percentual"])
            partes[item["participante"]] = v
            soma += v

        residuo = valor_total - soma
        if residuo != 0:
            alvo = sorted(split, key=lambda s: (-s["percentual"], s["participante"]))[0]["participante"]
            partes[alvo] += residuo
        return partes
