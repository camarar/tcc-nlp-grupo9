"""UC-12 — Serviço de conversão de moedas resiliente."""

from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Callable, Optional


class ErroCambio(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


_PADROES = {
    "ttl_s": 600.0,
    "stale_max_s": 86400.0,
    "falhas_para_abrir": 5,
    "tempo_aberto_s": 60.0,
}


class ServicoCambio:
    def __init__(
        self,
        provedor: Callable[[str], Decimal],
        relogio: Optional[Callable[[], float]] = None,
        config: Optional[dict] = None,
    ) -> None:
        self._provedor = provedor
        self._relogio = relogio if relogio is not None else time.monotonic

        valores = dict(_PADROES)
        config = config or {}
        for chave in _PADROES:
            if chave in config:
                valor = config[chave]
                if valor <= 0:
                    raise ErroCambio("CONFIGURACAO_INVALIDA")
                valores[chave] = valor
        self.ttl_s = valores["ttl_s"]
        self.stale_max_s = valores["stale_max_s"]
        self.falhas_para_abrir = valores["falhas_para_abrir"]
        self.tempo_aberto_s = valores["tempo_aberto_s"]

        self._moedas: dict[str, int] = {}
        self._cache: dict[str, dict] = {}

        self._estado = "FECHADO"
        self._tempo_abertura: Optional[float] = None
        self._falhas_consecutivas = 0

        self._stats = {"chamadas_provedor": 0, "acertos_cache": 0, "usos_stale": 0}

    def registrar_moeda(self, codigo: str, casas: int) -> None:
        if not codigo or casas < 0 or casas > 8:
            raise ErroCambio("CONFIGURACAO_INVALIDA")
        self._moedas[codigo] = casas

    def cotacao(self, de: str, para: str) -> dict:
        self._checar_moedas(de, para)
        if de == para:
            return {"taxa": Decimal("1.000000"), "stale": False, "idade_s": 0.0}
        taxa, idade, stale = self._taxa_cruzada(de, para)
        return {"taxa": taxa, "stale": stale, "idade_s": round(idade, 3)}

    def converter(self, valor, de: str, para: str) -> dict:
        self._checar_moedas(de, para)
        v = self._para_decimal(valor)
        if v < 0:
            raise ErroCambio("VALOR_INVALIDO")

        if de == para:
            casas = self._moedas[de]
            valor_convertido = v.quantize(self._quantizador(casas), rounding=ROUND_HALF_EVEN)
            return {
                "valor_convertido": valor_convertido,
                "taxa": Decimal("1.000000"),
                "stale": False,
                "idade_s": 0.0,
            }

        taxa, idade, stale = self._taxa_cruzada(de, para)
        casas = self._moedas[para]
        valor_convertido = (v * taxa).quantize(self._quantizador(casas), rounding=ROUND_HALF_EVEN)
        return {
            "valor_convertido": valor_convertido,
            "taxa": taxa,
            "stale": stale,
            "idade_s": round(idade, 3),
        }

    def estado_circuito(self) -> str:
        return self._estado_atual()

    def estatisticas(self) -> dict:
        return {
            "chamadas_provedor": self._stats["chamadas_provedor"],
            "acertos_cache": self._stats["acertos_cache"],
            "falhas_consecutivas": self._falhas_consecutivas,
            "usos_stale": self._stats["usos_stale"],
        }

    # -- internos --------------------------------------------------------

    def _checar_moedas(self, de: str, para: str) -> None:
        if de not in self._moedas or para not in self._moedas:
            raise ErroCambio("MOEDA_NAO_SUPORTADA")

    @staticmethod
    def _para_decimal(valor) -> Decimal:
        if isinstance(valor, Decimal):
            return valor
        try:
            return Decimal(str(valor))
        except (InvalidOperation, ValueError, TypeError):
            raise ErroCambio("VALOR_INVALIDO")

    @staticmethod
    def _quantizador(casas: int) -> Decimal:
        return Decimal(1).scaleb(-casas)

    def _estado_atual(self, agora: Optional[float] = None) -> str:
        if self._estado == "ABERTO" and self._tempo_abertura is not None:
            if agora is None:
                agora = self._relogio()
            if agora - self._tempo_abertura >= self.tempo_aberto_s:
                return "MEIO_ABERTO"
        return self._estado

    def _taxa_cruzada(self, de: str, para: str) -> tuple[Decimal, float, bool]:
        taxa_de, idade_de, stale_de = self._resolver_usd(de)
        taxa_para, idade_para, stale_para = self._resolver_usd(para)
        taxa = (taxa_para / taxa_de).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
        idade = max(idade_de, idade_para)
        stale = stale_de or stale_para
        return taxa, idade, stale

    def _resolver_usd(self, moeda: str) -> tuple[Decimal, float, bool]:
        if moeda == "USD":
            return (Decimal(1), 0.0, False)

        par = f"USD/{moeda}"
        agora = self._relogio()
        cacheado = self._cache.get(par)
        if cacheado is not None:
            idade = agora - cacheado["timestamp"]
            if idade < self.ttl_s:
                self._stats["acertos_cache"] += 1
                return (cacheado["taxa"], idade, False)

        estado = self._estado_atual(agora)
        if estado == "ABERTO":
            return self._usar_stale_ou_erro(par, agora)

        try:
            taxa = self._provedor(par)
        except Exception:
            self._stats["chamadas_provedor"] += 1
            self._falhas_consecutivas += 1
            if self._falhas_consecutivas >= self.falhas_para_abrir:
                self._estado = "ABERTO"
                self._tempo_abertura = agora
            return self._usar_stale_ou_erro(par, agora)
        else:
            self._stats["chamadas_provedor"] += 1
            self._falhas_consecutivas = 0
            self._estado = "FECHADO"
            self._tempo_abertura = None
            self._cache[par] = {"taxa": taxa, "timestamp": agora}
            return (taxa, 0.0, False)

    def _usar_stale_ou_erro(self, par: str, agora: float) -> tuple[Decimal, float, bool]:
        cacheado = self._cache.get(par)
        if cacheado is None:
            raise ErroCambio("PROVEDOR_INDISPONIVEL")
        idade = agora - cacheado["timestamp"]
        if idade < self.stale_max_s:
            self._stats["usos_stale"] += 1
            return (cacheado["taxa"], idade, True)
        raise ErroCambio("COTACAO_INDISPONIVEL")
