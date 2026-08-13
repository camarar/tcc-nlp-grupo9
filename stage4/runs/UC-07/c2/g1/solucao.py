"""UC-07 — Motor de cotação de frete multi-transportadora."""

from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_EVEN

CODES = {"REGIAO_NAO_ATENDIDA", "TRANSPORTADORA_DESCONHECIDA", "DIMENSOES_INVALIDAS",
         "TABELA_INVALIDA", "PEDIDO_INVALIDO", "SEM_COTACAO"}
CRITERIOS = {"PRECO", "PRAZO"}

MONEY_Q = Decimal("0.01")
WEIGHT_Q = Decimal("0.001")
STEP = Decimal("0.5")


class ErroFrete(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


def _to_decimal(value, code):
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise ErroFrete(code, "valor booleano inválido")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation:
            raise ErroFrete(code, f"valor numérico inválido: {value!r}")
    raise ErroFrete(code, f"tipo numérico não suportado: {type(value)!r}")


def _money(value):
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_EVEN)


class MotorFrete:
    def __init__(self):
        self._transportadoras = {}
        self._restricoes = {}

    def registrar_transportadora(self, nome: str, config: dict) -> None:
        faixas_in = config.get("faixas")
        if not faixas_in:
            raise ErroFrete("TABELA_INVALIDA", "faixas ausente ou vazia")

        faixas = []
        ate_anterior = None
        for f in faixas_in:
            ate_kg = _to_decimal(f["ate_kg"], "TABELA_INVALIDA")
            preco = _to_decimal(f["preco"], "TABELA_INVALIDA")
            prazo_dias = f["prazo_dias"]
            if not isinstance(prazo_dias, int) or isinstance(prazo_dias, bool):
                raise ErroFrete("TABELA_INVALIDA", "prazo_dias deve ser int")
            if preco < 0:
                raise ErroFrete("TABELA_INVALIDA", "preco negativo")
            if prazo_dias < 1:
                raise ErroFrete("TABELA_INVALIDA", "prazo_dias < 1")
            if ate_anterior is not None and ate_kg <= ate_anterior:
                raise ErroFrete("TABELA_INVALIDA", "ate_kg não estritamente crescente")
            ate_anterior = ate_kg
            faixas.append({"ate_kg": ate_kg, "preco": preco, "prazo_dias": prazo_dias})

        regioes = config.get("regioes") or []
        if not regioes:
            raise ErroFrete("TABELA_INVALIDA", "regioes vazia")

        fator_cubagem = _to_decimal(config.get("fator_cubagem"), "TABELA_INVALIDA")
        if fator_cubagem <= 0:
            raise ErroFrete("TABELA_INVALIDA", "fator_cubagem <= 0")

        peso_maximo_kg = _to_decimal(config.get("peso_maximo_kg"), "TABELA_INVALIDA")
        if peso_maximo_kg <= 0:
            raise ErroFrete("TABELA_INVALIDA", "peso_maximo_kg <= 0")

        ad_valorem_raw = config.get("ad_valorem")
        if ad_valorem_raw is None:
            ad_valorem = None
        else:
            ad_valorem = _to_decimal(ad_valorem_raw, "TABELA_INVALIDA")
            if ad_valorem < 0:
                raise ErroFrete("TABELA_INVALIDA", "ad_valorem negativo")

        self._transportadoras[nome] = {
            "faixas": faixas,
            "regioes": list(regioes),
            "fator_cubagem": fator_cubagem,
            "peso_maximo_kg": peso_maximo_kg,
            "ad_valorem": ad_valorem,
        }
        self._restricoes.setdefault(nome, [])

    def registrar_restricao(self, transportadora: str, prefixo_cep: str) -> None:
        if transportadora not in self._transportadoras:
            raise ErroFrete("TRANSPORTADORA_DESCONHECIDA",
                             f"transportadora não registrada: {transportadora!r}")
        prefixo_digitos = "".join(ch for ch in str(prefixo_cep) if ch.isdigit())
        self._restricoes[transportadora].append(prefixo_digitos)

    def _validar_pedido_estrutura(self, pedido: dict):
        if not pedido.get("itens"):
            raise ErroFrete("PEDIDO_INVALIDO", "itens ausente/vazio")
        if not pedido.get("uf_destino"):
            raise ErroFrete("PEDIDO_INVALIDO", "uf_destino ausente/vazio")
        if not pedido.get("cep_destino"):
            raise ErroFrete("PEDIDO_INVALIDO", "cep_destino ausente/vazio")

    def _validar_dimensoes(self, itens):
        for item in itens:
            peso_kg = _to_decimal(item["peso_kg"], "DIMENSOES_INVALIDAS")
            altura = _to_decimal(item["altura_cm"], "DIMENSOES_INVALIDAS")
            largura = _to_decimal(item["largura_cm"], "DIMENSOES_INVALIDAS")
            comprimento = _to_decimal(item["comprimento_cm"], "DIMENSOES_INVALIDAS")
            quantidade = item["quantidade"]
            valor = _to_decimal(item["valor"], "DIMENSOES_INVALIDAS")
            if peso_kg <= 0:
                raise ErroFrete("DIMENSOES_INVALIDAS", "peso_kg <= 0")
            if altura <= 0 or largura <= 0 or comprimento <= 0:
                raise ErroFrete("DIMENSOES_INVALIDAS", "dimensão <= 0")
            if not isinstance(quantidade, int) or isinstance(quantidade, bool) or quantidade < 1:
                raise ErroFrete("DIMENSOES_INVALIDAS", "quantidade < 1")
            if valor < 0:
                raise ErroFrete("DIMENSOES_INVALIDAS", "valor < 0")

    def _totais_pedido(self, itens):
        peso_real = Decimal(0)
        volume_total = Decimal(0)
        valor_total = Decimal(0)
        for item in itens:
            peso_kg = _to_decimal(item["peso_kg"], "DIMENSOES_INVALIDAS")
            altura = _to_decimal(item["altura_cm"], "DIMENSOES_INVALIDAS")
            largura = _to_decimal(item["largura_cm"], "DIMENSOES_INVALIDAS")
            comprimento = _to_decimal(item["comprimento_cm"], "DIMENSOES_INVALIDAS")
            quantidade = item["quantidade"]
            valor = _to_decimal(item["valor"], "DIMENSOES_INVALIDAS")

            peso_real += peso_kg * quantidade
            valor_total += valor * quantidade
            volume = altura * largura * comprimento
            volume_total += volume * quantidade
        return peso_real, volume_total, valor_total

    def _peso_cobrado(self, peso_real, volume_total, fator_cubagem):
        peso_cubado = volume_total / fator_cubagem
        peso_base = max(peso_real, peso_cubado)
        peso_cobrado = (peso_base / STEP).to_integral_value(rounding=ROUND_CEILING) * STEP
        return peso_cobrado.quantize(WEIGHT_Q)

    def _cotar_transportadora(self, nome, cfg, peso_real, volume_total, valor_total):
        peso_cobrado = self._peso_cobrado(peso_real, volume_total, cfg["fator_cubagem"])
        if peso_cobrado > cfg["peso_maximo_kg"]:
            return None

        frete = None
        prazo_dias = None
        for faixa in cfg["faixas"]:
            if peso_cobrado <= faixa["ate_kg"]:
                frete = faixa["preco"]
                prazo_dias = faixa["prazo_dias"]
                break
        if frete is None:
            return None

        ad_valorem = cfg["ad_valorem"]
        if ad_valorem is None:
            seguro = Decimal("0.00")
        else:
            seguro = (ad_valorem * valor_total).quantize(MONEY_Q, rounding=ROUND_HALF_EVEN)

        frete = _money(frete)
        total = _money(frete + seguro)

        return {
            "transportadora": nome,
            "peso_cobrado_kg": peso_cobrado,
            "frete": frete,
            "seguro": seguro,
            "prazo_dias": prazo_dias,
            "total": total,
        }

    def cotar(self, pedido: dict) -> list:
        self._validar_pedido_estrutura(pedido)
        itens = pedido["itens"]
        self._validar_dimensoes(itens)

        uf_destino = pedido["uf_destino"]
        cep_destino = pedido["cep_destino"]
        cep_digitos = "".join(ch for ch in str(cep_destino) if ch.isdigit())

        atendem_regiao = {nome: cfg for nome, cfg in self._transportadoras.items()
                           if uf_destino in cfg["regioes"]}
        if not atendem_regiao:
            raise ErroFrete("REGIAO_NAO_ATENDIDA", f"nenhuma transportadora atende {uf_destino!r}")

        peso_real, volume_total, valor_total = self._totais_pedido(itens)

        cotacoes = []
        for nome, cfg in atendem_regiao.items():
            prefixos = self._restricoes.get(nome, [])
            if any(cep_digitos.startswith(p) for p in prefixos if p):
                continue
            cotacao = self._cotar_transportadora(nome, cfg, peso_real, volume_total, valor_total)
            if cotacao is not None:
                cotacoes.append(cotacao)

        if not cotacoes:
            raise ErroFrete("SEM_COTACAO", "nenhuma transportadora viável para o pedido")

        cotacoes.sort(key=lambda c: (c["total"], c["prazo_dias"], c["transportadora"]))
        return cotacoes

    def melhor_cotacao(self, pedido: dict, criterio: str) -> dict:
        if criterio not in CRITERIOS:
            raise ErroFrete("PEDIDO_INVALIDO", f"criterio fora do vocabulário: {criterio!r}")

        cotacoes = self.cotar(pedido)

        if criterio == "PRECO":
            cotacoes.sort(key=lambda c: (c["total"], c["prazo_dias"], c["transportadora"]))
        else:
            cotacoes.sort(key=lambda c: (c["prazo_dias"], c["total"], c["transportadora"]))
        return cotacoes[0]
