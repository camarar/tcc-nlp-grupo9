"""UC-12 — Serviço de conversão de moedas resiliente."""

from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Callable, Optional

_CODES = frozenset({
    "MOEDA_NAO_SUPORTADA",
    "COTACAO_INDISPONIVEL",
    "PROVEDOR_INDISPONIVEL",
    "VALOR_INVALIDO",
    "CONFIGURACAO_INVALIDA",
})

_ESTADOS = frozenset({"FECHADO", "ABERTO", "MEIO_ABERTO"})

_DEFAULTS = {
    "ttl_s": 600,
    "stale_max_s": 86400,
    "falhas_para_abrir": 5,
    "tempo_aberto_s": 60,
}

_TAXA_QUANT = Decimal("0.000001")
_TAXA_UNITARIA = Decimal("1.000000")


class ErroCambio(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        assert code in _CODES
        super().__init__(mensagem or code)
        self.code = code
        self.mensagem = mensagem


class ServicoCambio:
    def __init__(self, provedor: Callable[[str], Decimal],
                 relogio: Optional[Callable[[], float]] = None,
                 config: Optional[dict] = None) -> None:
        self._provedor = provedor
        self._relogio = relogio if relogio is not None else time.monotonic

        cfg = config or {}
        try:
            for chave in _DEFAULTS:
                if chave in cfg and cfg[chave] <= 0:
                    raise ErroCambio("CONFIGURACAO_INVALIDA",
                                      f"{chave} deve ser positivo")
        except TypeError:
            raise ErroCambio("CONFIGURACAO_INVALIDA", "config inválida")

        self._ttl_s = cfg.get("ttl_s", _DEFAULTS["ttl_s"])
        self._stale_max_s = cfg.get("stale_max_s", _DEFAULTS["stale_max_s"])
        self._falhas_para_abrir = cfg.get("falhas_para_abrir", _DEFAULTS["falhas_para_abrir"])
        self._tempo_aberto_s = cfg.get("tempo_aberto_s", _DEFAULTS["tempo_aberto_s"])

        self._moedas: dict[str, int] = {}
        self._cache: dict[str, tuple[Decimal, float]] = {}

        self._estado = "FECHADO"
        self._falhas_consecutivas = 0
        self._aberto_desde: Optional[float] = None

        self._chamadas_provedor = 0
        self._acertos_cache = 0
        self._usos_stale = 0

    # ------------------------------------------------------------------ #
    # API pública

    def registrar_moeda(self, codigo: str, casas: int) -> None:
        if not codigo or casas < 0 or casas > 8:
            raise ErroCambio("CONFIGURACAO_INVALIDA", "moeda/casas inválidas")
        self._moedas[codigo] = casas

    def cotacao(self, de: str, para: str) -> dict:
        self._verificar_moedas(de, para)
        if de == para:
            return {"taxa": _TAXA_UNITARIA, "stale": False, "idade_s": 0.0}
        return self._taxa_cruzada(de, para)

    def converter(self, valor, de: str, para: str) -> dict:
        self._verificar_moedas(de, para)
        valor_dec = self._parse_valor(valor)

        if de == para:
            casas = self._moedas[para]
            valor_convertido = self._quantizar(valor_dec, casas)
            return {"valor_convertido": valor_convertido, "taxa": _TAXA_UNITARIA,
                    "stale": False, "idade_s": 0.0}

        resultado = self._taxa_cruzada(de, para)
        casas = self._moedas[para]
        valor_convertido = self._quantizar(valor_dec * resultado["taxa"], casas)
        return {"valor_convertido": valor_convertido, "taxa": resultado["taxa"],
                "stale": resultado["stale"], "idade_s": resultado["idade_s"]}

    def estado_circuito(self) -> str:
        return self._estado_efetivo()

    def estatisticas(self) -> dict:
        return {
            "chamadas_provedor": self._chamadas_provedor,
            "acertos_cache": self._acertos_cache,
            "falhas_consecutivas": self._falhas_consecutivas,
            "usos_stale": self._usos_stale,
        }

    # ------------------------------------------------------------------ #
    # Helpers de validação

    def _verificar_moedas(self, de: str, para: str) -> None:
        if de not in self._moedas or para not in self._moedas:
            raise ErroCambio("MOEDA_NAO_SUPORTADA", f"{de}/{para} não registrada(s)")

    @staticmethod
    def _parse_valor(valor) -> Decimal:
        try:
            if isinstance(valor, Decimal):
                valor_dec = valor
            elif isinstance(valor, float):
                valor_dec = Decimal(str(valor))
            else:
                valor_dec = Decimal(valor)
        except (InvalidOperation, TypeError, ValueError):
            raise ErroCambio("VALOR_INVALIDO", "valor não numérico")
        if valor_dec < 0:
            raise ErroCambio("VALOR_INVALIDO", "valor negativo")
        return valor_dec

    @staticmethod
    def _quantizar(valor: Decimal, casas: int) -> Decimal:
        quantum = Decimal(1).scaleb(-casas)
        return valor.quantize(quantum, rounding=ROUND_HALF_EVEN)

    # ------------------------------------------------------------------ #
    # Núcleo de cotação

    def _taxa_cruzada(self, de: str, para: str) -> dict:
        perna_de = self._resolver_perna(de)
        perna_para = self._resolver_perna(para)

        taxa = (perna_para["taxa"] / perna_de["taxa"]).quantize(
            _TAXA_QUANT, rounding=ROUND_HALF_EVEN)
        idade_s = round(max(perna_de["idade_s"], perna_para["idade_s"]), 3)
        stale = perna_de["stale"] or perna_para["stale"]
        return {"taxa": taxa, "stale": stale, "idade_s": idade_s}

    def _resolver_perna(self, moeda: str) -> dict:
        if moeda == "USD":
            return {"taxa": Decimal(1), "stale": False, "idade_s": 0.0}

        par = f"USD/{moeda}"
        agora = self._relogio()
        entrada = self._cache.get(par)
        idade = (agora - entrada[1]) if entrada is not None else None

        if entrada is not None and idade < self._ttl_s:
            self._acertos_cache += 1
            return {"taxa": entrada[0], "stale": False, "idade_s": round(idade, 3)}

        return self._chamar_ou_fallback(par, entrada, idade)

    def _chamar_ou_fallback(self, par: str, entrada, idade) -> dict:
        estado = self._estado_efetivo()
        pode_chamar = estado in ("FECHADO", "MEIO_ABERTO")

        if pode_chamar:
            try:
                taxa = self._provedor(par)
                self._chamadas_provedor += 1
                timestamp = self._relogio()
                self._cache[par] = (taxa, timestamp)
                self._falhas_consecutivas = 0
                self._estado = "FECHADO"
                self._aberto_desde = None
                return {"taxa": taxa, "stale": False, "idade_s": 0.0}
            except Exception:
                self._chamadas_provedor += 1
                self._falhas_consecutivas += 1
                if self._estado == "MEIO_ABERTO" or \
                        self._falhas_consecutivas >= self._falhas_para_abrir:
                    self._estado = "ABERTO"
                    self._aberto_desde = self._relogio()

        return self._fallback_stale(entrada, idade)

    def _fallback_stale(self, entrada, idade) -> dict:
        if entrada is not None and idade < self._stale_max_s:
            self._usos_stale += 1
            return {"taxa": entrada[0], "stale": True, "idade_s": round(idade, 3)}
        if entrada is not None:
            raise ErroCambio("COTACAO_INDISPONIVEL", "cotação obsoleta demais")
        raise ErroCambio("PROVEDOR_INDISPONIVEL", "sem cotação disponível")

    # ------------------------------------------------------------------ #
    # Circuit breaker

    def _estado_efetivo(self) -> str:
        if self._estado == "ABERTO" and self._aberto_desde is not None:
            if (self._relogio() - self._aberto_desde) >= self._tempo_aberto_s:
                self._estado = "MEIO_ABERTO"
        return self._estado
