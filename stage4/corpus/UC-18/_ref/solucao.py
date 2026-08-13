"""UC-18 — Ciclo de vida de pedido com combos promocionais."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Callable

TWO_PLACES = Decimal("0.01")

ITENS_ATIVOS_NO_TOTAL = ("ATIVO", "DESPACHADO")
ITENS_MORTOS = ("CANCELADO", "DEVOLVIDO")


def _quant(valor: Decimal) -> Decimal:
    return valor.quantize(TWO_PLACES, rounding=ROUND_HALF_EVEN)


def _to_decimal(valor) -> Decimal:
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, float):
        return Decimal(str(valor))
    return Decimal(valor)


def _to_money(valor) -> Decimal:
    return _quant(_to_decimal(valor))


class ErroPedido(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


class Pedidos:
    def __init__(self, relogio: Callable[[], datetime] | None = None) -> None:
        # G-12: `em` nunca e nulo — sem relogio injetado, usa o do sistema
        self._relogio = relogio or (lambda: datetime.now(timezone.utc))
        self._pedidos: dict[str, dict] = {}

    # ------------------------------------------------------------------ #
    # API pública
    # ------------------------------------------------------------------ #

    def criar(self, dados: dict) -> str:
        cliente = dados.get("cliente")
        if not cliente:
            raise ErroPedido("ITEM_INVALIDO", "cliente vazio")

        itens_in = dados.get("itens")
        if not itens_in:
            raise ErroPedido("ITEM_INVALIDO", "itens vazio ou ausente")

        itens: dict[str, dict] = {}
        for it in itens_in:
            item_id = it.get("item_id")
            if not item_id or item_id in itens:
                raise ErroPedido("ITEM_INVALIDO", "item_id vazio ou repetido")
            preco_cheio = _to_money(it["preco_cheio"])
            if preco_cheio <= 0:
                raise ErroPedido("ITEM_INVALIDO", "preco_cheio <= 0")
            itens[item_id] = {
                "item_id": item_id,
                "sku": it.get("sku"),
                "preco_cheio": preco_cheio,
                "combo": it.get("combo"),
                "preco": None,
                "situacao": "ATIVO",
                "despachado_em": None,
            }

        combos_in = dados.get("combos") or []
        combos: dict[str, dict] = {}
        for c in combos_in:
            combo_id = c["combo_id"]
            if combo_id in combos:
                raise ErroPedido("COMBO_INVALIDO", "combo_id repetido")
            combos[combo_id] = {
                "combo_id": combo_id,
                "preco": _to_money(c["preco"]),
                "item_ids": [],
                "desfeito": False,
            }

        for item in itens.values():
            combo_id = item["combo"]
            if combo_id is not None:
                if combo_id not in combos:
                    raise ErroPedido("COMBO_INVALIDO", "combo ausente da lista combos")
                combos[combo_id]["item_ids"].append(item["item_id"])

        for combo in combos.values():
            if not combo["item_ids"]:
                raise ErroPedido("COMBO_INVALIDO", "combo sem nenhum item")
            soma = sum((itens[iid]["preco_cheio"] for iid in combo["item_ids"]), Decimal("0.00"))
            if combo["preco"] <= 0 or combo["preco"] >= soma:
                raise ErroPedido("COMBO_INVALIDO", "preco do combo invalido")

        for item in itens.values():
            if item["combo"] is None:
                item["preco"] = item["preco_cheio"]
        for combo in combos.values():
            self._distribuir_preco_combo(combo, itens)

        pedido_id = uuid.uuid4().hex
        pedido = {
            "pedido_id": pedido_id,
            "cliente": cliente,
            "itens": itens,
            "combos": combos,
            "pago_flag": False,
            "pago_valor": Decimal("0.00"),
            "estornado_total": Decimal("0.00"),
            "historico": [],
        }
        em = self._relogio()
        pedido["historico"].append(
            {"em": em, "evento": "CRIACAO", "item_id": None, "valor": None}
        )
        self._pedidos[pedido_id] = pedido
        return pedido_id

    def pagar(self, pedido_id: str, valor, quando: datetime) -> dict:
        pedido = self._get_pedido(pedido_id)
        situacao = self._situacao(pedido)
        if situacao != "CRIADO":
            raise ErroPedido("ESTADO_INVALIDO", "pagamento só é aceito a partir de CRIADO")

        total = self._total(pedido)
        valor_dec = _to_money(valor)
        if valor_dec != total:
            raise ErroPedido("VALOR_INVALIDO", "valor difere do total vigente")

        pedido["pago_flag"] = True
        pedido["pago_valor"] = valor_dec
        pedido["historico"].append(
            {"em": quando, "evento": "PAGAMENTO", "item_id": None, "valor": valor_dec}
        )
        return {"situacao": self._situacao(pedido), "pago": valor_dec}

    def despachar(self, pedido_id: str, itens: list[str], quando: datetime) -> str:
        pedido = self._get_pedido(pedido_id)
        situacao = self._situacao(pedido)
        if situacao not in ("PAGO", "PARCIALMENTE_DESPACHADO"):
            raise ErroPedido("ESTADO_INVALIDO", "despacho não permitido nesta situação")

        if not itens:
            raise ErroPedido("ITEM_INVALIDO", "lista de itens vazia")

        for item_id in itens:
            item = pedido["itens"].get(item_id)
            if item is None or item["situacao"] != "ATIVO":
                raise ErroPedido("ITEM_INVALIDO", "item inexistente ou não ATIVO")

        for item_id in itens:
            item = pedido["itens"][item_id]
            item["situacao"] = "DESPACHADO"
            item["despachado_em"] = quando
            pedido["historico"].append(
                {"em": quando, "evento": "DESPACHO", "item_id": item_id, "valor": None}
            )

        return self._situacao(pedido)

    def cancelar_item(self, pedido_id: str, item_id: str, quando: datetime) -> dict:
        pedido = self._get_pedido(pedido_id)
        if self._situacao(pedido) == "CANCELADO":
            raise ErroPedido("ESTADO_INVALIDO", "pedido cancelado é terminal")

        item = pedido["itens"].get(item_id)
        if item is None:
            raise ErroPedido("ITEM_INVALIDO", "item inexistente no pedido")

        if item["situacao"] in ("DESPACHADO",) + ITENS_MORTOS:
            raise ErroPedido("OPERACAO_NAO_PERMITIDA", "item não pode ser cancelado")

        return self._processar_saida(pedido, item, quando, "CANCELADO", "CANCELAMENTO_ITEM")

    def devolver(self, pedido_id: str, item_id: str, quando: datetime) -> dict:
        pedido = self._get_pedido(pedido_id)
        if self._situacao(pedido) == "CANCELADO":
            raise ErroPedido("ESTADO_INVALIDO", "pedido cancelado é terminal")

        item = pedido["itens"].get(item_id)
        if item is None:
            raise ErroPedido("ITEM_INVALIDO", "item inexistente no pedido")

        if item["situacao"] != "DESPACHADO":
            raise ErroPedido("OPERACAO_NAO_PERMITIDA", "só item DESPACHADO pode ser devolvido")

        if (quando - item["despachado_em"]).days > 7:
            raise ErroPedido("OPERACAO_NAO_PERMITIDA", "prazo de devolução expirado")

        return self._processar_saida(pedido, item, quando, "DEVOLVIDO", "DEVOLUCAO")

    def resumo(self, pedido_id: str) -> dict:
        pedido = self._get_pedido(pedido_id)
        itens = [
            {
                "item_id": it["item_id"],
                "preco": it["preco"],
                "situacao": it["situacao"],
                "combo": it["combo"],
            }
            for it in pedido["itens"].values()
        ]
        return {
            "situacao": self._situacao(pedido),
            "total": self._total(pedido),
            "pago": pedido["pago_valor"],
            "estornado": pedido["estornado_total"],
            "itens": itens,
        }

    def historico(self, pedido_id: str) -> list[dict]:
        pedido = self._get_pedido(pedido_id)
        return [dict(evento) for evento in pedido["historico"]]

    # ------------------------------------------------------------------ #
    # Internos
    # ------------------------------------------------------------------ #

    def _get_pedido(self, pedido_id: str) -> dict:
        pedido = self._pedidos.get(pedido_id)
        if pedido is None:
            raise ErroPedido("PEDIDO_NAO_ENCONTRADO", "pedido inexistente")
        return pedido

    @staticmethod
    def _distribuir_preco_combo(combo: dict, itens: dict) -> None:
        ids = combo["item_ids"]
        soma = sum((itens[iid]["preco_cheio"] for iid in ids), Decimal("0.00"))
        precos = {}
        for iid in ids:
            item = itens[iid]
            bruto = combo["preco"] * item["preco_cheio"] / soma
            precos[iid] = _quant(bruto)

        residuo = combo["preco"] - sum(precos.values(), Decimal("0.00"))
        if residuo != 0:
            melhor = ids[0]
            for iid in ids[1:]:
                atual = itens[iid]["preco_cheio"]
                campeao = itens[melhor]["preco_cheio"]
                if atual > campeao or (atual == campeao and iid < melhor):
                    melhor = iid
            precos[melhor] = precos[melhor] + residuo

        for iid in ids:
            itens[iid]["preco"] = precos[iid]

    def _processar_saida(
        self,
        pedido: dict,
        item: dict,
        quando: datetime,
        nova_situacao_item: str,
        evento: str,
    ) -> dict:
        item["situacao"] = nova_situacao_item

        reprecificados: list[str] = []
        combo_id = item["combo"]
        if combo_id is not None:
            combo = pedido["combos"][combo_id]
            if not combo["desfeito"]:
                combo["desfeito"] = True
                for iid in combo["item_ids"]:
                    if iid == item["item_id"]:
                        continue
                    outro = pedido["itens"][iid]
                    if outro["situacao"] in ITENS_ATIVOS_NO_TOTAL and outro["preco"] != outro["preco_cheio"]:
                        outro["preco"] = outro["preco_cheio"]
                        reprecificados.append(iid)

        novo_total = self._total(pedido)
        pago = pedido["pago_valor"] if pedido["pago_flag"] else Decimal("0.00")
        estorno = pago - novo_total
        if estorno < 0:
            estorno = Decimal("0.00")
        estorno = _quant(estorno)

        pedido["estornado_total"] = _quant(pedido["estornado_total"] + estorno)
        pedido["historico"].append(
            {"em": quando, "evento": evento, "item_id": item["item_id"], "valor": estorno}
        )
        for iid in reprecificados:
            pedido["historico"].append(
                {
                    "em": quando,
                    "evento": "REPRECIFICACAO",
                    "item_id": iid,
                    "valor": pedido["itens"][iid]["preco"],
                }
            )

        nova_situacao_pedido = self._situacao(pedido)
        if nova_situacao_pedido == "CANCELADO":
            pedido["historico"].append(
                {"em": quando, "evento": "CANCELAMENTO_PEDIDO", "item_id": None, "valor": None}
            )

        return {"estorno": estorno, "novo_total": novo_total, "situacao": nova_situacao_pedido}

    @staticmethod
    def _total(pedido: dict) -> Decimal:
        total = sum(
            (it["preco"] for it in pedido["itens"].values() if it["situacao"] in ITENS_ATIVOS_NO_TOTAL),
            Decimal("0.00"),
        )
        return _quant(total)

    @staticmethod
    def _situacao(pedido: dict) -> str:
        situacoes = [it["situacao"] for it in pedido["itens"].values()]

        if all(s in ITENS_MORTOS for s in situacoes):
            return "CANCELADO"

        if (
            not any(s == "ATIVO" for s in situacoes)
            and any(s == "DESPACHADO" for s in situacoes)
            and any(s in ITENS_MORTOS for s in situacoes)
        ):
            return "CONCLUIDO"

        if all(s == "DESPACHADO" for s in situacoes):
            return "DESPACHADO"

        if any(s == "DESPACHADO" for s in situacoes) and any(s == "ATIVO" for s in situacoes):
            return "PARCIALMENTE_DESPACHADO"

        if pedido["pago_flag"]:
            return "PAGO"

        return "CRIADO"
