"""UC-03 — Motor de precificação e promoções."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Callable, Optional

DUAS_CASAS = Decimal("0.01")

TIPOS_CUPOM = {"PERCENTUAL", "FIXO", "FRETE_GRATIS"}


class ErroPrecificacao(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code
        self.mensagem = mensagem


def _to_decimal(valor) -> Decimal:
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, float):
        return Decimal(str(valor))
    if isinstance(valor, int):
        return Decimal(valor)
    if isinstance(valor, str):
        return Decimal(valor)
    raise ErroPrecificacao("ITEM_INVALIDO", "valor monetário inválido")


def _q(valor: Decimal) -> Decimal:
    return valor.quantize(DUAS_CASAS, rounding=ROUND_HALF_EVEN)


def _ratear(total: Decimal, pesos: dict) -> dict:
    chaves = list(pesos.keys())
    if not chaves:
        return {}
    total = _q(total)
    soma_pesos = sum(pesos.values(), Decimal("0"))
    if soma_pesos <= 0 or total == 0:
        return {chave: Decimal("0.00") for chave in chaves}
    partes = {}
    soma_parcial = Decimal("0.00")
    for chave in chaves:
        parte = _q(total * pesos[chave] / soma_pesos)
        partes[chave] = parte
        soma_parcial += parte
    residuo = total - soma_parcial
    if residuo != 0:
        alvo = sorted(chaves, key=lambda k: (-pesos[k], str(k)))[0]
        partes[alvo] += residuo
    return partes


class MotorPrecificacao:
    def __init__(self, agora: Optional[Callable[[], datetime]] = None) -> None:
        self._agora = agora or datetime.now
        self._campanhas: list[dict] = []
        self._cupons: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Registro
    # ------------------------------------------------------------------
    def registrar_campanha(self, campanha: dict) -> str:
        percentual = _to_decimal(campanha["percentual"])
        if percentual <= 0 or percentual > 1:
            raise ErroPrecificacao("CAMPANHA_INVALIDA", "percentual fora do intervalo (0, 1]")
        inicio = campanha["inicio"]
        fim = campanha["fim"]
        if inicio > fim:
            raise ErroPrecificacao("CAMPANHA_INVALIDA", "inicio posterior a fim")
        categoria = campanha.get("categoria") or ""
        if not categoria:
            raise ErroPrecificacao("CAMPANHA_INVALIDA", "categoria vazia")

        ordem = len(self._campanhas)
        identificador = f"CAMP-{ordem + 1}"
        self._campanhas.append({
            "id": identificador,
            "nome": campanha["nome"],
            "categoria": categoria,
            "percentual": percentual,
            "inicio": inicio,
            "fim": fim,
            "ordem": ordem,
        })
        return identificador

    def registrar_cupom(self, cupom: dict) -> str:
        codigo = cupom["codigo"]
        if codigo in self._cupons:
            raise ErroPrecificacao("CUPOM_INVALIDO", "código já registrado")
        tipo = cupom["tipo"]
        if tipo not in TIPOS_CUPOM:
            raise ErroPrecificacao("CUPOM_INVALIDO", "tipo fora do vocabulário fechado")
        valor = _to_decimal(cupom["valor"])
        if valor < 0:
            raise ErroPrecificacao("CUPOM_INVALIDO", "valor negativo")
        if tipo == "PERCENTUAL" and valor > 1:
            raise ErroPrecificacao("CUPOM_INVALIDO", "percentual maior que 1")

        pedido_minimo = cupom.get("pedido_minimo")
        if pedido_minimo is not None:
            pedido_minimo = _to_decimal(pedido_minimo)

        self._cupons[codigo] = {
            "codigo": codigo,
            "tipo": tipo,
            "valor": valor,
            "acumulavel": bool(cupom.get("acumulavel", False)),
            "validade": cupom["validade"],
            "pedido_minimo": pedido_minimo,
            "categorias": cupom.get("categorias"),
        }
        return codigo

    # ------------------------------------------------------------------
    # Consulta
    # ------------------------------------------------------------------
    def cotar(self, pedido: dict, cupons: list, data: date) -> dict:
        resultado, _ = self._processar(pedido, cupons, data)
        return resultado

    def explicar(self, pedido: dict, cupons: list, data: date) -> list:
        _, trilha = self._processar(pedido, cupons, data)
        return trilha

    # ------------------------------------------------------------------
    # Implementação
    # ------------------------------------------------------------------
    def _melhor_campanha(self, categoria: str, data: date) -> Optional[dict]:
        candidatas = [
            c for c in self._campanhas
            if c["categoria"] == categoria and c["inicio"] <= data <= c["fim"]
        ]
        if not candidatas:
            return None
        candidatas.sort(key=lambda c: (-c["percentual"], c["ordem"]))
        return candidatas[0]

    def _validar_itens(self, pedido: dict) -> list:
        itens = pedido.get("itens")
        if not itens:
            raise ErroPrecificacao("ITEM_INVALIDO", "lista de itens vazia ou ausente")

        vistos = set()
        resultado = []
        for item in itens:
            sku = item.get("sku") or ""
            if not sku:
                raise ErroPrecificacao("ITEM_INVALIDO", "sku vazio")
            if sku in vistos:
                raise ErroPrecificacao("ITEM_INVALIDO", "sku repetido")
            vistos.add(sku)

            quantidade = item["quantidade"]
            if quantidade < 1:
                raise ErroPrecificacao("ITEM_INVALIDO", "quantidade menor que 1")

            preco_unitario = _to_decimal(item["preco_unitario"])
            if preco_unitario < 0:
                raise ErroPrecificacao("ITEM_INVALIDO", "preco_unitario negativo")

            categoria = item.get("categoria") or ""
            preco_bruto = _q(preco_unitario * quantidade)
            resultado.append({"sku": sku, "categoria": categoria, "preco_bruto": preco_bruto})

        frete = _to_decimal(pedido.get("frete", 0))
        if frete < 0:
            raise ErroPrecificacao("ITEM_INVALIDO", "frete negativo")

        return resultado

    def _processar(self, pedido: dict, cupons: list, data: date):
        itens = self._validar_itens(pedido)
        frete_original = _q(_to_decimal(pedido.get("frete", 0)))

        # (2) existência e duplicidade dos cupons
        vistos = set()
        for codigo in cupons:
            if codigo not in self._cupons:
                raise ErroPrecificacao("CUPOM_INVALIDO", "cupom não registrado")
            if codigo in vistos:
                raise ErroPrecificacao("CUPOM_INVALIDO", "cupom duplicado na lista")
            vistos.add(codigo)
        cupons_obj = [self._cupons[codigo] for codigo in cupons]

        # (3) acumulação
        if len(cupons_obj) > 1:
            for cupom in cupons_obj:
                if not cupom["acumulavel"]:
                    raise ErroPrecificacao("CUPOM_NAO_ACUMULAVEL", "cupom não acumulável combinado com outro")

        # (4) validade
        for cupom in cupons_obj:
            if data > cupom["validade"]:
                raise ErroPrecificacao("CUPOM_EXPIRADO", "cupom fora da validade")

        subtotal_original = _q(sum((item["preco_bruto"] for item in itens), Decimal("0.00")))

        # (5) pedido mínimo
        for cupom in cupons_obj:
            minimo = cupom["pedido_minimo"]
            if minimo is not None and subtotal_original < minimo:
                raise ErroPrecificacao("PEDIDO_MINIMO", "subtotal abaixo do pedido mínimo")

        trilha: list[dict] = []

        base_por_categoria: dict[str, Decimal] = {}
        for item in itens:
            base_por_categoria[item["categoria"]] = base_por_categoria.get(
                item["categoria"], Decimal("0.00")
            ) + item["preco_bruto"]
        remanescente_por_categoria = dict(base_por_categoria)

        desconto_campanhas_total = Decimal("0.00")
        for categoria, base in base_por_categoria.items():
            campanha = self._melhor_campanha(categoria, data)
            if campanha is None:
                continue
            valor = _q(base * campanha["percentual"])
            if valor > 0:
                trilha.append({
                    "origem": "CAMPANHA",
                    "referencia": campanha["nome"],
                    "base": base,
                    "valor": valor,
                })
                desconto_campanhas_total += valor
                remanescente_por_categoria[categoria] -= valor

        percentuais = [c for c in cupons_obj if c["tipo"] == "PERCENTUAL"]
        fixos = [c for c in cupons_obj if c["tipo"] == "FIXO"]
        fretes = [c for c in cupons_obj if c["tipo"] == "FRETE_GRATIS"]

        desconto_cupons_total = Decimal("0.00")
        for cupom in percentuais + fixos:
            if cupom["categorias"] is None:
                pesos = dict(remanescente_por_categoria)
            else:
                pesos = {
                    cat: remanescente_por_categoria[cat]
                    for cat in cupom["categorias"]
                    if cat in remanescente_por_categoria
                }
            base = sum(pesos.values(), Decimal("0.00"))
            if base <= 0:
                continue

            if cupom["tipo"] == "PERCENTUAL":
                valor = _q(base * cupom["valor"])
            else:
                valor = min(_q(cupom["valor"]), base)

            if valor <= 0:
                continue

            trilha.append({
                "origem": "CUPOM",
                "referencia": cupom["codigo"],
                "base": _q(base),
                "valor": valor,
            })
            desconto_cupons_total += valor

            reducao = _ratear(valor, pesos)
            for categoria, parte in reducao.items():
                remanescente_por_categoria[categoria] -= parte

        frete_final = frete_original
        for cupom in fretes:
            categorias = cupom["categorias"]
            if categorias is not None and not any(
                cat in base_por_categoria for cat in categorias
            ):
                continue
            if frete_original > 0:
                trilha.append({
                    "origem": "FRETE",
                    "referencia": cupom["codigo"],
                    "base": frete_original,
                    "valor": frete_original,
                })
            frete_final = Decimal("0.00")
            break

        desconto_total = desconto_campanhas_total + desconto_cupons_total
        teto = _q(subtotal_original * Decimal("0.5"))
        if desconto_total > teto:
            corte = _q(desconto_total - teto)
            desconto_total_final = teto
            trilha.append({
                "origem": "TETO",
                "referencia": "TETO",
                "base": subtotal_original,
                "valor": corte,
            })
        else:
            desconto_total_final = _q(desconto_total)

        pesos_itens = {item["sku"]: item["preco_bruto"] for item in itens}
        rateio = _ratear(desconto_total_final, pesos_itens)

        itens_resultado = []
        for item in itens:
            desconto_rateado = rateio.get(item["sku"], Decimal("0.00"))
            itens_resultado.append({
                "sku": item["sku"],
                "preco_bruto": item["preco_bruto"],
                "desconto_rateado": desconto_rateado,
                "preco_liquido": _q(item["preco_bruto"] - desconto_rateado),
            })

        total = _q(subtotal_original - desconto_total_final + frete_final)

        resultado = {
            "subtotal": subtotal_original,
            "desconto_campanhas": _q(desconto_campanhas_total),
            "desconto_cupons": _q(desconto_cupons_total),
            "desconto_total": desconto_total_final,
            "frete": frete_final,
            "total": total,
            "itens": itens_resultado,
        }
        return resultado, trilha
