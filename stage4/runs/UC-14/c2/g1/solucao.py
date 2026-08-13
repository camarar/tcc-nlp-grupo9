"""UC-14 — Motor de cálculo tributário por UF e NCM.

RNF-02 [AVANÇO SOB RISCO — não confirmado pela fonte de negócio]: entradas
monetárias/numéricas (str/int/float/Decimal) não conversíveis de forma
inequívoca para Decimal (strings não numéricas, None, NaN/Infinity, vírgula
decimal, etc.) são tratadas aqui como dado inválido no nível em que o valor é
usado — ou seja, propagam como ITEM_INVALIDO/NOTA_INVALIDA/TABELA_INVALIDA
conforme o campo, em vez de deixar exceções nativas (InvalidOperation,
TypeError) escaparem. Premissa assumida sob risco, sujeita a validação
posterior.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN

DUAS_CASAS = Decimal("0.01")


class ErroTributario(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code
        self.mensagem = mensagem


def _to_decimal(valor):
    """Converte str/int/float/Decimal para Decimal; None em caso de falha/ambiguidade."""
    if isinstance(valor, Decimal):
        if valor.is_nan() or valor.is_infinite():
            return None
        return valor
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return Decimal(valor)
    if isinstance(valor, float):
        if valor != valor or valor in (float("inf"), float("-inf")):
            return None
        return Decimal(str(valor))
    if isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            return None
        try:
            d = Decimal(texto)
        except InvalidOperation:
            return None
        if d.is_nan() or d.is_infinite():
            return None
        return d
    return None


def _quantizar(valor: Decimal) -> Decimal:
    return valor.quantize(DUAS_CASAS, rounding=ROUND_HALF_EVEN)


class _AliquotaCadastro:
    __slots__ = ("aliquota", "mva")

    def __init__(self, aliquota: Decimal, mva):
        self.aliquota = aliquota
        self.mva = mva


class MotorTributario:
    def __init__(self) -> None:
        self._aliquotas: dict[str, dict[str, _AliquotaCadastro]] = {}
        self._isencoes: dict[str, set[str]] = {}
        self._regimes: dict[str, str] = {}

    # ---------------------------------------------------------------- cadastro

    def registrar_aliquota(self, uf: str, ncm: str, aliquota, mva=None) -> None:
        uf_norm = self._validar_uf_tabela(uf)
        ncm_norm = self._validar_ncm_tabela(ncm)

        aliquota_dec = _to_decimal(aliquota)
        if aliquota_dec is None or aliquota_dec <= 0 or aliquota_dec > 1:
            raise ErroTributario("TABELA_INVALIDA", "aliquota fora do intervalo válido")

        mva_dec = None
        if mva is not None:
            mva_dec = _to_decimal(mva)
            if mva_dec is None or mva_dec < 0:
                raise ErroTributario("TABELA_INVALIDA", "mva inválido")

        self._aliquotas.setdefault(uf_norm, {})[ncm_norm] = _AliquotaCadastro(aliquota_dec, mva_dec)

    def registrar_isencao(self, uf: str, ncm: str) -> None:
        uf_norm = self._validar_uf_tabela(uf)
        ncm_norm = self._validar_ncm_tabela(ncm)
        self._isencoes.setdefault(uf_norm, set()).add(ncm_norm)

    def registrar_regime(self, cnpj: str, regime: str) -> None:
        if not cnpj:
            raise ErroTributario("TABELA_INVALIDA", "cnpj ausente")
        if regime not in ("SIMPLES", "NORMAL"):
            raise ErroTributario("TABELA_INVALIDA", "regime fora do vocabulário fechado")
        self._regimes[cnpj] = regime

    @staticmethod
    def _validar_uf_tabela(uf) -> str:
        if not isinstance(uf, str) or len(uf) != 2:
            raise ErroTributario("TABELA_INVALIDA", "uf inválida")
        return uf

    @staticmethod
    def _validar_ncm_tabela(ncm) -> str:
        if not isinstance(ncm, str) or not ncm.isdigit() or len(ncm) < 4:
            raise ErroTributario("TABELA_INVALIDA", "ncm inválido")
        return ncm

    # ----------------------------------------------------------------- cálculo

    def calcular(self, nota: dict) -> dict:
        _, resultado = self._processar(nota)
        return resultado

    def memoria_calculo(self, nota: dict) -> list[dict]:
        memoria, _ = self._processar(nota)
        return memoria

    def _processar(self, nota: dict):
        cnpj, uf, frete, itens = self._validar_nota(nota)
        itens_validados = [self._validar_item(item) for item in itens]

        if cnpj not in self._regimes:
            raise ErroTributario("REGIME_DESCONHECIDO", "cnpj emitente sem regime cadastrado")
        regime = self._regimes[cnpj]

        memoria: list[dict] = []
        base_calculo = Decimal("0.00")
        icms_total = Decimal("0.00")
        icms_st_total = Decimal("0.00")
        total_nota_itens = Decimal("0.00")

        for item in itens_validados:
            ncm = item["ncm"]
            valor = item["valor"]
            quantidade = item["quantidade"]
            desconto = item["desconto"]

            base_item = valor * quantidade - desconto
            total_nota_itens += base_item

            if ncm in self._isencoes.get(uf, ()):
                memoria.append({
                    "ncm": ncm,
                    "ncm_aplicado": None,
                    "aliquota": None,
                    "base": _quantizar(base_item),
                    "icms": Decimal("0.00"),
                    "icms_st": Decimal("0.00"),
                    "isento": True,
                })
                continue

            ncm_aplicado, cadastro = self._resolver_aliquota(uf, ncm)
            if cadastro is None:
                raise ErroTributario("ALIQUOTA_NAO_CADASTRADA",
                                      f"nenhuma aliquota cadastrada para UF={uf} NCM={ncm}")

            base_quant = _quantizar(base_item)
            icms_normal = _quantizar(base_item * cadastro.aliquota)
            if regime == "SIMPLES":
                icms_item = _quantizar(icms_normal * Decimal("0.5"))
            else:
                icms_item = icms_normal

            if regime == "SIMPLES" or cadastro.mva is None:
                icms_st_item = Decimal("0.00")
            else:
                bruto_st = _quantizar(base_item * (1 + cadastro.mva) * cadastro.aliquota)
                icms_st_item = bruto_st - icms_item
                if icms_st_item < 0:
                    icms_st_item = Decimal("0.00")

            base_calculo += base_quant
            icms_total += icms_item
            icms_st_total += icms_st_item

            memoria.append({
                "ncm": ncm,
                "ncm_aplicado": ncm_aplicado,
                "aliquota": cadastro.aliquota,
                "base": base_quant,
                "icms": icms_item,
                "icms_st": icms_st_item,
                "isento": False,
            })

        total_tributos = icms_total + icms_st_total
        total_nota = _quantizar(total_nota_itens) + frete + icms_st_total

        resultado = {
            "base_calculo": base_calculo,
            "icms": icms_total,
            "icms_st": icms_st_total,
            "total_tributos": total_tributos,
            "total_nota": total_nota,
        }
        return memoria, resultado

    def _resolver_aliquota(self, uf: str, ncm: str):
        tabela = self._aliquotas.get(uf, {})
        exato = tabela.get(ncm)
        if exato is not None:
            return ncm, exato

        melhor_prefixo = None
        melhor_cadastro = None
        for chave, cadastro in tabela.items():
            if len(chave) >= 4 and ncm.startswith(chave):
                if melhor_prefixo is None or len(chave) > len(melhor_prefixo):
                    melhor_prefixo = chave
                    melhor_cadastro = cadastro
        if melhor_prefixo is not None:
            return melhor_prefixo, melhor_cadastro
        return None, None

    # -------------------------------------------------------------- validação

    @staticmethod
    def _validar_nota(nota: dict):
        if not isinstance(nota, dict):
            raise ErroTributario("NOTA_INVALIDA", "nota deve ser um dicionário")

        cnpj = nota.get("cnpj_emitente")
        if not cnpj:
            raise ErroTributario("NOTA_INVALIDA", "cnpj_emitente ausente")

        uf = nota.get("uf_destino")
        if not isinstance(uf, str) or len(uf) != 2:
            raise ErroTributario("NOTA_INVALIDA", "uf_destino inválida")

        frete = _to_decimal(nota.get("frete", 0))
        if frete is None or frete < 0:
            raise ErroTributario("NOTA_INVALIDA", "frete inválido")

        itens = nota.get("itens")
        if not itens:
            raise ErroTributario("NOTA_INVALIDA", "itens ausente ou vazio")

        return cnpj, uf, frete, itens

    @staticmethod
    def _validar_item(item: dict) -> dict:
        if not isinstance(item, dict):
            raise ErroTributario("ITEM_INVALIDO", "item deve ser um dicionário")

        ncm = item.get("ncm")
        if not isinstance(ncm, str) or not ncm.isdigit() or not ncm:
            raise ErroTributario("ITEM_INVALIDO", "ncm inválido")

        valor = _to_decimal(item.get("valor"))
        if valor is None or valor < 0:
            raise ErroTributario("ITEM_INVALIDO", "valor inválido")

        quantidade_raw = item.get("quantidade")
        quantidade = _to_decimal(quantidade_raw)
        if quantidade is None or quantidade != quantidade.to_integral_value() or quantidade < 1:
            raise ErroTributario("ITEM_INVALIDO", "quantidade inválida")
        quantidade = int(quantidade)

        desconto = _to_decimal(item.get("desconto", 0))
        if desconto is None or desconto < 0:
            raise ErroTributario("ITEM_INVALIDO", "desconto inválido")
        if desconto > valor * quantidade:
            raise ErroTributario("ITEM_INVALIDO", "desconto maior que valor total")

        return {"ncm": ncm, "valor": valor, "quantidade": quantidade, "desconto": desconto}
