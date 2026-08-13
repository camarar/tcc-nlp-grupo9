"""UC-14 — Motor de cálculo tributário por UF e NCM."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN

_CENTAVOS = Decimal("0.01")
_REGIMES_VALIDOS = ("SIMPLES", "NORMAL")


class ErroTributario(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


def _quantiza(valor: Decimal) -> Decimal:
    return valor.quantize(_CENTAVOS, rounding=ROUND_HALF_EVEN)


def _para_decimal(valor) -> Decimal:
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, bool):
        raise ValueError("valor booleano não é numérico")
    if isinstance(valor, int):
        return Decimal(valor)
    if isinstance(valor, float):
        return Decimal(str(valor))
    if isinstance(valor, str):
        return Decimal(valor.strip())
    raise ValueError("valor não conversível para Decimal")


def _para_inteiro(valor) -> int:
    if isinstance(valor, bool):
        raise ValueError("valor booleano não é inteiro")
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float):
        if not valor.is_integer():
            raise ValueError("float não inteiro")
        return int(valor)
    if isinstance(valor, Decimal):
        if valor != valor.to_integral_value():
            raise ValueError("Decimal não inteiro")
        return int(valor)
    if isinstance(valor, str):
        return int(valor.strip())
    raise ValueError("valor não conversível para inteiro")


class MotorTributario:
    def __init__(self) -> None:
        self._aliquotas: dict[tuple[str, str], tuple[Decimal, Decimal | None]] = {}
        self._isencoes: set[tuple[str, str]] = set()
        self._regimes: dict[str, str] = {}

    def _validar_uf_ncm_cadastro(self, uf: str, ncm: str) -> None:
        if not isinstance(uf, str) or len(uf) != 2:
            raise ErroTributario("TABELA_INVALIDA", "uf inválida")
        if not isinstance(ncm, str) or len(ncm) < 4 or not ncm.isdigit():
            raise ErroTributario("TABELA_INVALIDA", "ncm inválido")

    def registrar_aliquota(self, uf: str, ncm: str, aliquota, mva=None) -> None:
        self._validar_uf_ncm_cadastro(uf, ncm)
        try:
            aliquota_d = _para_decimal(aliquota)
        except (InvalidOperation, ValueError, TypeError):
            raise ErroTributario("TABELA_INVALIDA", "aliquota inválida")
        if aliquota_d <= 0 or aliquota_d > 1:
            raise ErroTributario("TABELA_INVALIDA", "aliquota fora do intervalo")
        mva_d = None
        if mva is not None:
            try:
                mva_d = _para_decimal(mva)
            except (InvalidOperation, ValueError, TypeError):
                raise ErroTributario("TABELA_INVALIDA", "mva inválido")
            if mva_d < 0:
                raise ErroTributario("TABELA_INVALIDA", "mva negativo")
        self._aliquotas[(uf, ncm)] = (aliquota_d, mva_d)

    def registrar_isencao(self, uf: str, ncm: str) -> None:
        self._validar_uf_ncm_cadastro(uf, ncm)
        self._isencoes.add((uf, ncm))

    def registrar_regime(self, cnpj: str, regime: str) -> None:
        if regime not in _REGIMES_VALIDOS:
            raise ErroTributario("TABELA_INVALIDA", "regime desconhecido")
        self._regimes[cnpj] = regime

    def _validar_nota(self, nota: dict):
        if not isinstance(nota, dict):
            raise ErroTributario("NOTA_INVALIDA", "nota deve ser um dict")
        itens = nota.get("itens")
        if not itens:
            raise ErroTributario("NOTA_INVALIDA", "itens ausentes")
        try:
            frete = _para_decimal(nota.get("frete"))
        except (InvalidOperation, ValueError, TypeError):
            raise ErroTributario("NOTA_INVALIDA", "frete inválido")
        if frete < 0:
            raise ErroTributario("NOTA_INVALIDA", "frete negativo")
        uf_destino = nota.get("uf_destino")
        if not isinstance(uf_destino, str) or len(uf_destino) != 2:
            raise ErroTributario("NOTA_INVALIDA", "uf_destino inválida")
        cnpj = nota.get("cnpj_emitente")
        if not cnpj or not isinstance(cnpj, str):
            raise ErroTributario("NOTA_INVALIDA", "cnpj_emitente ausente")
        return itens, frete, uf_destino, cnpj

    def _validar_item(self, item: dict) -> dict:
        if not isinstance(item, dict):
            raise ErroTributario("ITEM_INVALIDO", "item deve ser um dict")
        try:
            valor = _para_decimal(item.get("valor"))
        except (InvalidOperation, ValueError, TypeError):
            raise ErroTributario("ITEM_INVALIDO", "valor inválido")
        try:
            quantidade = _para_inteiro(item.get("quantidade"))
        except (InvalidOperation, ValueError, TypeError):
            raise ErroTributario("ITEM_INVALIDO", "quantidade inválida")
        try:
            desconto = _para_decimal(item.get("desconto"))
        except (InvalidOperation, ValueError, TypeError):
            raise ErroTributario("ITEM_INVALIDO", "desconto inválido")
        ncm = item.get("ncm")
        if not ncm or not isinstance(ncm, str) or not ncm.isdigit():
            raise ErroTributario("ITEM_INVALIDO", "ncm inválido")
        if valor < 0:
            raise ErroTributario("ITEM_INVALIDO", "valor negativo")
        if quantidade < 1:
            raise ErroTributario("ITEM_INVALIDO", "quantidade menor que 1")
        if desconto < 0:
            raise ErroTributario("ITEM_INVALIDO", "desconto negativo")
        if desconto > valor * quantidade:
            raise ErroTributario("ITEM_INVALIDO", "desconto maior que o total do item")
        return {"ncm": ncm, "valor": valor, "quantidade": quantidade, "desconto": desconto}

    def _resolver_aliquota(self, uf: str, ncm: str):
        exato = self._aliquotas.get((uf, ncm))
        if exato is not None:
            return ncm, exato[0], exato[1]
        melhor_ncm = None
        melhor_par = None
        for (u, k), par in self._aliquotas.items():
            if u != uf or len(k) < 4:
                continue
            if ncm.startswith(k) and (melhor_ncm is None or len(k) > len(melhor_ncm)):
                melhor_ncm = k
                melhor_par = par
        if melhor_par is None:
            return None
        return melhor_ncm, melhor_par[0], melhor_par[1]

    def _processar(self, nota: dict):
        itens, frete, uf, cnpj = self._validar_nota(nota)
        itens_validados = [self._validar_item(item) for item in itens]

        regime = self._regimes.get(cnpj)
        if regime is None:
            raise ErroTributario("REGIME_DESCONHECIDO", "regime não cadastrado para o cnpj")

        memoria = []
        base_calculo = Decimal("0.00")
        total_bruto_todos = Decimal("0.00")
        icms_total = Decimal("0.00")
        icms_st_total = Decimal("0.00")

        for item in itens_validados:
            bruto = _quantiza(item["valor"] * item["quantidade"] - item["desconto"])
            total_bruto_todos += bruto

            if (uf, item["ncm"]) in self._isencoes:
                memoria.append({
                    "ncm": item["ncm"], "ncm_aplicado": None, "aliquota": None,
                    "base": bruto, "icms": Decimal("0.00"), "icms_st": Decimal("0.00"),
                    "isento": True,
                })
                continue

            resolvido = self._resolver_aliquota(uf, item["ncm"])
            if resolvido is None:
                raise ErroTributario("ALIQUOTA_NAO_CADASTRADA", "par uf/ncm sem alíquota")
            ncm_aplicado, aliquota, mva = resolvido

            base_calculo += bruto
            icms_item = _quantiza(bruto * aliquota)

            if mva is not None:
                icms_st_item = _quantiza(bruto * (1 + mva) * aliquota) - icms_item
                if icms_st_item < 0:
                    icms_st_item = Decimal("0.00")
            else:
                icms_st_item = Decimal("0.00")

            if regime == "SIMPLES":
                icms_item = _quantiza(icms_item * Decimal("0.5"))
                icms_st_item = Decimal("0.00")

            icms_total += icms_item
            icms_st_total += icms_st_item
            memoria.append({
                "ncm": item["ncm"], "ncm_aplicado": ncm_aplicado, "aliquota": aliquota,
                "base": bruto, "icms": icms_item, "icms_st": icms_st_item,
                "isento": False,
            })

        total_tributos = icms_total + icms_st_total
        total_nota = total_bruto_todos + frete + icms_st_total

        resultado = {
            "base_calculo": _quantiza(base_calculo),
            "icms": _quantiza(icms_total),
            "icms_st": _quantiza(icms_st_total),
            "total_tributos": _quantiza(total_tributos),
            "total_nota": _quantiza(total_nota),
        }
        return memoria, resultado

    def calcular(self, nota: dict) -> dict:
        _, resultado = self._processar(nota)
        return resultado

    def memoria_calculo(self, nota: dict) -> list:
        memoria, _ = self._processar(nota)
        return memoria
