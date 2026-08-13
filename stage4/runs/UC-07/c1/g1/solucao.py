"""UC-07 — Motor de cotação de frete multi-transportadora."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_EVEN

_MONEY_Q = Decimal("0.01")
_PESO_Q = Decimal("0.001")
_STEP = Decimal("0.5")

_CODES = {
    "REGIAO_NAO_ATENDIDA",
    "TRANSPORTADORA_DESCONHECIDA",
    "DIMENSOES_INVALIDAS",
    "TABELA_INVALIDA",
    "PEDIDO_INVALIDO",
    "SEM_COTACAO",
}


class ErroFrete(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise InvalidOperation("bool não é numérico")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        return Decimal(value.strip())
    raise InvalidOperation(f"tipo inválido: {type(value)!r}")


def _quantize_money(valor: Decimal) -> Decimal:
    return valor.quantize(_MONEY_Q, rounding=ROUND_HALF_EVEN)


def _quantize_peso(valor: Decimal) -> Decimal:
    return valor.quantize(_PESO_Q, rounding=ROUND_HALF_EVEN)


def _arredondar_meio_kg_acima(valor: Decimal) -> Decimal:
    quociente = (valor / _STEP).to_integral_value(rounding=ROUND_CEILING)
    return _quantize_peso(quociente * _STEP)


def _somente_digitos(texto: str) -> str:
    return "".join(ch for ch in str(texto) if ch.isdigit())


class MotorFrete:
    def __init__(self) -> None:
        self._transportadoras: dict[str, dict] = {}
        self._restricoes: dict[str, list[str]] = {}

    # ------------------------------------------------------------------
    def registrar_transportadora(self, nome: str, config: dict) -> None:
        normalizado = self._validar_e_normalizar_tabela(config)
        self._transportadoras[nome] = normalizado
        self._restricoes.setdefault(nome, [])

    def _validar_e_normalizar_tabela(self, config: dict) -> dict:
        try:
            faixas_in = config.get("faixas")
            if not faixas_in:
                raise ErroFrete("TABELA_INVALIDA")

            faixas = []
            ate_anterior = None
            for faixa in faixas_in:
                ate_kg = _to_decimal(faixa["ate_kg"])
                preco = _to_decimal(faixa["preco"])
                prazo_dias = int(_to_decimal(faixa["prazo_dias"]))

                if preco < 0:
                    raise ErroFrete("TABELA_INVALIDA")
                if prazo_dias < 1:
                    raise ErroFrete("TABELA_INVALIDA")
                if ate_anterior is not None and not (ate_kg > ate_anterior):
                    raise ErroFrete("TABELA_INVALIDA")
                ate_anterior = ate_kg

                faixas.append({"ate_kg": ate_kg, "preco": preco, "prazo_dias": prazo_dias})

            regioes = config.get("regioes")
            if not regioes:
                raise ErroFrete("TABELA_INVALIDA")

            fator_cubagem = _to_decimal(config.get("fator_cubagem"))
            if fator_cubagem <= 0:
                raise ErroFrete("TABELA_INVALIDA")

            peso_maximo_kg = _to_decimal(config.get("peso_maximo_kg"))
            if peso_maximo_kg <= 0:
                raise ErroFrete("TABELA_INVALIDA")

            ad_valorem_in = config.get("ad_valorem")
            if ad_valorem_in is None:
                ad_valorem = None
            else:
                ad_valorem = _to_decimal(ad_valorem_in)
                if ad_valorem < 0:
                    raise ErroFrete("TABELA_INVALIDA")
        except ErroFrete:
            raise
        except (InvalidOperation, TypeError, KeyError, ValueError, ArithmeticError):
            raise ErroFrete("TABELA_INVALIDA")

        return {
            "faixas": faixas,
            "regioes": list(regioes),
            "fator_cubagem": fator_cubagem,
            "peso_maximo_kg": peso_maximo_kg,
            "ad_valorem": ad_valorem,
        }

    # ------------------------------------------------------------------
    def registrar_restricao(self, transportadora: str, prefixo_cep: str) -> None:
        if transportadora not in self._transportadoras:
            raise ErroFrete("TRANSPORTADORA_DESCONHECIDA")
        self._restricoes.setdefault(transportadora, []).append(_somente_digitos(prefixo_cep))

    # ------------------------------------------------------------------
    def cotar(self, pedido: dict) -> list[dict]:
        # G-17 (1): validação do pedido
        itens_in = pedido.get("itens")
        uf_destino = pedido.get("uf_destino")
        cep_destino = pedido.get("cep_destino")
        if not itens_in or not uf_destino or not cep_destino:
            raise ErroFrete("PEDIDO_INVALIDO")

        # G-17 (2): validação de dimensões dos itens
        itens = []
        try:
            for item in itens_in:
                peso_kg = _to_decimal(item["peso_kg"])
                altura_cm = _to_decimal(item["altura_cm"])
                largura_cm = _to_decimal(item["largura_cm"])
                comprimento_cm = _to_decimal(item["comprimento_cm"])
                quantidade = _to_decimal(item["quantidade"])
                valor = _to_decimal(item["valor"])

                if (peso_kg <= 0 or altura_cm <= 0 or largura_cm <= 0
                        or comprimento_cm <= 0 or quantidade < 1 or valor < 0):
                    raise ErroFrete("DIMENSOES_INVALIDAS")

                itens.append({
                    "peso_kg": peso_kg, "altura_cm": altura_cm, "largura_cm": largura_cm,
                    "comprimento_cm": comprimento_cm, "quantidade": quantidade, "valor": valor,
                })
        except ErroFrete:
            raise
        except (InvalidOperation, TypeError, KeyError, ValueError, ArithmeticError):
            raise ErroFrete("DIMENSOES_INVALIDAS")

        # G-17 (3): região
        candidatas = {
            nome: cfg for nome, cfg in self._transportadoras.items()
            if uf_destino in cfg["regioes"]
        }
        if not candidatas:
            raise ErroFrete("REGIAO_NAO_ATENDIDA")

        # G-17 (4): disponibilidade de cotação
        cep_digitos = _somente_digitos(cep_destino)
        peso_real = sum((item["peso_kg"] * item["quantidade"] for item in itens), Decimal(0))
        valor_total = sum((item["valor"] * item["quantidade"] for item in itens), Decimal(0))

        resultados = []
        for nome, cfg in candidatas.items():
            prefixos = self._restricoes.get(nome, [])
            if any(cep_digitos.startswith(p) for p in prefixos):
                continue

            peso_cubado = sum(
                ((item["altura_cm"] * item["largura_cm"] * item["comprimento_cm"])
                 / cfg["fator_cubagem"]) * item["quantidade"]
                for item in itens
            )
            peso_bruto = max(peso_real, peso_cubado)
            peso_cobrado = _arredondar_meio_kg_acima(peso_bruto)

            if peso_cobrado > cfg["peso_maximo_kg"]:
                continue

            faixa = next((f for f in cfg["faixas"] if f["ate_kg"] >= peso_cobrado), None)
            if faixa is None:
                continue

            frete = _quantize_money(faixa["preco"])
            ad_valorem = cfg["ad_valorem"]
            if ad_valorem is None:
                seguro = _quantize_money(Decimal(0))
            else:
                seguro = _quantize_money(ad_valorem * valor_total)
            total = _quantize_money(frete + seguro)

            resultados.append({
                "transportadora": nome,
                "peso_cobrado_kg": peso_cobrado,
                "frete": frete,
                "seguro": seguro,
                "prazo_dias": faixa["prazo_dias"],
                "total": total,
            })

        if not resultados:
            raise ErroFrete("SEM_COTACAO")

        resultados.sort(key=lambda r: (r["total"], r["prazo_dias"], r["transportadora"]))
        return resultados

    # ------------------------------------------------------------------
    def melhor_cotacao(self, pedido: dict, criterio: str) -> dict:
        if criterio not in ("PRECO", "PRAZO"):
            raise ErroFrete("PEDIDO_INVALIDO")

        resultados = self.cotar(pedido)

        if criterio == "PRECO":
            return min(resultados, key=lambda r: (r["total"], r["prazo_dias"], r["transportadora"]))
        return min(resultados, key=lambda r: (r["prazo_dias"], r["total"], r["transportadora"]))
