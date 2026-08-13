"""UC-03 - Motor de precificacao e promocoes."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Callable

TWOPLACES = Decimal("0.01")


def _quant(valor: Decimal) -> Decimal:
    return valor.quantize(TWOPLACES, rounding=ROUND_HALF_EVEN)


def _to_decimal(valor) -> Decimal:
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, int):
        return Decimal(valor)
    if isinstance(valor, str):
        return Decimal(valor)
    if isinstance(valor, float):
        return Decimal(str(valor))
    raise TypeError(f"valor monetario invalido: {valor!r}")


class ErroPrecificacao(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


class MotorPrecificacao:
    def __init__(self, agora: Callable[[], datetime] | None = None) -> None:
        self._agora = agora or datetime.now
        self._campanhas: list[dict] = []
        self._cupons: dict[str, dict] = {}
        self._campanha_seq = 0

    # ------------------------------------------------------------------
    # Registro
    # ------------------------------------------------------------------

    def registrar_campanha(self, campanha: dict) -> str:
        percentual = _to_decimal(campanha["percentual"])
        if percentual <= 0 or percentual > 1:
            raise ErroPrecificacao("CAMPANHA_INVALIDA")
        inicio = campanha["inicio"]
        fim = campanha["fim"]
        if inicio > fim:
            raise ErroPrecificacao("CAMPANHA_INVALIDA")
        categoria = campanha.get("categoria") or ""
        if not categoria:
            raise ErroPrecificacao("CAMPANHA_INVALIDA")

        self._campanha_seq += 1
        identificador = f"CAMP{self._campanha_seq}"
        self._campanhas.append({
            "id": identificador,
            "nome": campanha["nome"],
            "categoria": categoria,
            "percentual": percentual,
            "inicio": inicio,
            "fim": fim,
        })
        return identificador

    def registrar_cupom(self, cupom: dict) -> str:
        tipo = cupom.get("tipo")
        if tipo not in {"PERCENTUAL", "FIXO", "FRETE_GRATIS"}:
            raise ErroPrecificacao("CUPOM_INVALIDO")
        valor = _to_decimal(cupom.get("valor"))
        if valor < 0:
            raise ErroPrecificacao("CUPOM_INVALIDO")
        if tipo == "PERCENTUAL" and valor > 1:
            raise ErroPrecificacao("CUPOM_INVALIDO")
        codigo = cupom["codigo"]
        if codigo in self._cupons:
            raise ErroPrecificacao("CUPOM_INVALIDO")

        pedido_minimo = cupom.get("pedido_minimo")
        self._cupons[codigo] = {
            "codigo": codigo,
            "tipo": tipo,
            "valor": valor,
            "acumulavel": bool(cupom.get("acumulavel", False)),
            "validade": cupom["validade"],
            "pedido_minimo": _to_decimal(pedido_minimo) if pedido_minimo is not None else None,
            "categorias": cupom.get("categorias"),
        }
        return codigo

    # ------------------------------------------------------------------
    # Cotacao / explicacao
    # ------------------------------------------------------------------

    def cotar(self, pedido: dict, cupons: list[str], data: date) -> dict:
        quote, _trilha = self._processar(pedido, cupons, data)
        return quote

    def explicar(self, pedido: dict, cupons: list[str], data: date) -> list[dict]:
        _quote, trilha = self._processar(pedido, cupons, data)
        return trilha

    # ------------------------------------------------------------------
    # Implementacao
    # ------------------------------------------------------------------

    def _processar(self, pedido: dict, cupons: list[str], data: date):
        itens, frete = self._validar_itens(pedido)
        cupom_objs = self._validar_cupons(cupons)

        subtotal_original = sum((it["preco_bruto"] for it in itens), Decimal("0.00"))

        # G-06/G-17: validade (inclusiva) e' verificada antes do pedido minimo
        for c in cupom_objs:
            if data > c["validade"]:
                raise ErroPrecificacao("CUPOM_EXPIRADO")

        for c in cupom_objs:
            if c["pedido_minimo"] is not None and subtotal_original < c["pedido_minimo"]:
                raise ErroPrecificacao("PEDIDO_MINIMO")

        trilha: list[dict] = []

        desconto_campanhas, remaining_by_cat = self._aplicar_campanhas(itens, data, trilha)

        percentuais = [c for c in cupom_objs if c["tipo"] == "PERCENTUAL"]
        fixos = [c for c in cupom_objs if c["tipo"] == "FIXO"]
        frete_gratis = [c for c in cupom_objs if c["tipo"] == "FRETE_GRATIS"]

        desconto_cupons = self._aplicar_cupons(percentuais + fixos, remaining_by_cat, trilha)

        frete_final = self._aplicar_frete_gratis(frete_gratis, frete, trilha)

        raw_total = desconto_campanhas + desconto_cupons
        teto_max = _quant(subtotal_original * Decimal("0.5"))
        if raw_total > teto_max:
            desconto_total = teto_max
            trilha.append({
                "origem": "TETO",
                "referencia": "TETO",
                "base": raw_total,
                "valor": _quant(raw_total - teto_max),
            })
        else:
            desconto_total = raw_total

        total = subtotal_original - desconto_total + frete_final
        if total < 0:
            total = Decimal("0.00")
        total = _quant(total)

        itens_out = self._ratear(itens, desconto_total)

        quote = {
            "subtotal": _quant(subtotal_original),
            "desconto_campanhas": _quant(desconto_campanhas),
            "desconto_cupons": _quant(desconto_cupons),
            "desconto_total": _quant(desconto_total),
            "frete": _quant(frete_final),
            "total": total,
            "itens": itens_out,
        }
        return quote, trilha

    # -- validacao --------------------------------------------------

    def _validar_itens(self, pedido: dict):
        itens = pedido.get("itens")
        if not itens:
            raise ErroPrecificacao("ITEM_INVALIDO")

        vistos: set[str] = set()
        resultado = []
        for item in itens:
            sku = item.get("sku") or ""
            if not sku:
                raise ErroPrecificacao("ITEM_INVALIDO")
            if sku in vistos:
                raise ErroPrecificacao("ITEM_INVALIDO")
            vistos.add(sku)

            quantidade = item.get("quantidade")
            if quantidade is None or quantidade < 1:
                raise ErroPrecificacao("ITEM_INVALIDO")

            preco_unitario = _to_decimal(item.get("preco_unitario"))
            if preco_unitario < 0:
                raise ErroPrecificacao("ITEM_INVALIDO")

            categoria = item.get("categoria") or ""
            preco_bruto = _quant(preco_unitario * quantidade)
            resultado.append({"sku": sku, "categoria": categoria, "preco_bruto": preco_bruto})

        frete = _to_decimal(pedido.get("frete", 0))
        if frete < 0:
            raise ErroPrecificacao("ITEM_INVALIDO")

        return resultado, frete

    def _validar_cupons(self, cupons: list[str]) -> list[dict]:
        vistos: set[str] = set()
        for codigo in cupons:
            if codigo in vistos:
                raise ErroPrecificacao("CUPOM_INVALIDO")
            vistos.add(codigo)
            if codigo not in self._cupons:
                raise ErroPrecificacao("CUPOM_INVALIDO")

        objs = [self._cupons[c] for c in cupons]

        if len(objs) > 1 and any(not c["acumulavel"] for c in objs):
            raise ErroPrecificacao("CUPOM_NAO_ACUMULAVEL")

        return objs

    # -- campanhas ----------------------------------------------------

    def _melhor_campanha(self, categoria: str, data: date) -> dict | None:
        melhor = None
        for c in self._campanhas:
            if c["categoria"] != categoria:
                continue
            if not (c["inicio"] <= data <= c["fim"]):
                continue
            if melhor is None or c["percentual"] > melhor["percentual"]:
                melhor = c
        return melhor

    def _aplicar_campanhas(self, itens: list[dict], data: date, trilha: list[dict]):
        by_cat: dict[str, list[dict]] = {}
        for it in itens:
            by_cat.setdefault(it["categoria"], []).append(it)

        total_desconto = Decimal("0.00")
        remaining_by_cat: dict[str, Decimal] = {}

        for categoria, itens_cat in by_cat.items():
            base = sum((it["preco_bruto"] for it in itens_cat), Decimal("0.00"))
            campanha = self._melhor_campanha(categoria, data)
            if campanha is not None:
                valor = _quant(base * campanha["percentual"])
                if valor > 0:
                    trilha.append({
                        "origem": "CAMPANHA",
                        "referencia": campanha["nome"],
                        "base": base,
                        "valor": valor,
                    })
                total_desconto += valor
                remaining_by_cat[categoria] = base - valor
            else:
                remaining_by_cat[categoria] = base

        return total_desconto, remaining_by_cat

    # -- cupons ---------------------------------------------------------

    def _distribuir(self, remaining_by_cat: dict[str, Decimal], categorias: list[str], valor: Decimal) -> None:
        total = sum((remaining_by_cat[c] for c in categorias), Decimal("0.00"))
        if total <= 0:
            return
        ordenadas = sorted(categorias, key=lambda c: (-remaining_by_cat[c], c))
        acumulado = Decimal("0.00")
        for i, categoria in enumerate(ordenadas):
            if i == len(ordenadas) - 1:
                parcela = valor - acumulado
            else:
                parcela = _quant(valor * remaining_by_cat[categoria] / total)
                acumulado += parcela
            remaining_by_cat[categoria] -= parcela

    def _aplicar_cupons(self, cupons_ordenados: list[dict], remaining_by_cat: dict[str, Decimal],
                         trilha: list[dict]) -> Decimal:
        total_desconto = Decimal("0.00")

        for c in cupons_ordenados:
            categorias = c["categorias"]
            if categorias is None:
                aplicaveis = list(remaining_by_cat.keys())
            else:
                aplicaveis = [cat for cat in categorias if cat in remaining_by_cat]

            base = sum((remaining_by_cat[cat] for cat in aplicaveis), Decimal("0.00"))

            if c["tipo"] == "PERCENTUAL":
                valor = _quant(base * c["valor"])
            else:
                valor = min(_quant(c["valor"]), base) if base > 0 else Decimal("0.00")
                if valor < 0:
                    valor = Decimal("0.00")

            if valor > 0:
                trilha.append({
                    "origem": "CUPOM",
                    "referencia": c["codigo"],
                    "base": base,
                    "valor": valor,
                })
                if aplicaveis:
                    self._distribuir(remaining_by_cat, aplicaveis, valor)

            total_desconto += valor

        return total_desconto

    def _aplicar_frete_gratis(self, frete_gratis: list[dict], frete: Decimal, trilha: list[dict]) -> Decimal:
        if not frete_gratis:
            return frete
        if frete > 0:
            trilha.append({
                "origem": "FRETE",
                "referencia": frete_gratis[0]["codigo"],
                "base": frete,
                "valor": frete,
            })
        return Decimal("0.00")

    # -- rateio -----------------------------------------------------------

    def _ratear(self, itens: list[dict], desconto_total: Decimal) -> list[dict]:
        if desconto_total <= 0:
            return [{
                "sku": it["sku"],
                "preco_bruto": it["preco_bruto"],
                "desconto_rateado": Decimal("0.00"),
                "preco_liquido": it["preco_bruto"],
            } for it in itens]

        total_bruto = sum((it["preco_bruto"] for it in itens), Decimal("0.00"))
        if total_bruto <= 0:
            return [{
                "sku": it["sku"],
                "preco_bruto": it["preco_bruto"],
                "desconto_rateado": Decimal("0.00"),
                "preco_liquido": it["preco_bruto"],
            } for it in itens]

        shares: dict[str, Decimal] = {}
        acumulado = Decimal("0.00")
        for it in itens:
            parcela = _quant(desconto_total * it["preco_bruto"] / total_bruto)
            shares[it["sku"]] = parcela
            acumulado += parcela

        residuo = desconto_total - acumulado
        if residuo != 0:
            alvo = sorted(itens, key=lambda it: (-it["preco_bruto"], it["sku"]))[0]
            shares[alvo["sku"]] += residuo

        resultado = []
        for it in itens:
            desconto_rateado = shares[it["sku"]]
            resultado.append({
                "sku": it["sku"],
                "preco_bruto": it["preco_bruto"],
                "desconto_rateado": desconto_rateado,
                "preco_liquido": it["preco_bruto"] - desconto_rateado,
            })
        return resultado
