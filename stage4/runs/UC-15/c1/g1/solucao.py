"""UC-15 — Orquestrador de notificações com reenvio."""

from datetime import datetime, timezone
from typing import Callable


class ErroNotificacao(Exception):
    def __init__(self, code: str, mensagem: str = "") -> None:
        super().__init__(mensagem or code)
        self.code = code


class _Canal:
    __slots__ = ("nome", "enviar", "prioridade")

    def __init__(self, nome: str, enviar: Callable[[str, str], None], prioridade: int) -> None:
        self.nome = nome
        self.enviar = enviar
        self.prioridade = prioridade


_CONFIG_PADRAO = {
    "tentativas": 3,
    "backoff_base_s": 1.0,
    "fator": 2.0,
    "silencio_inicio_h": 22,
    "silencio_fim_h": 8,
}


class Orquestrador:
    def __init__(self, relogio: Callable[[], datetime] | None = None,
                 dormir: Callable[[float], None] | None = None) -> None:
        self._relogio = relogio or (lambda: datetime.now(timezone.utc))
        self._dormir = dormir or (lambda s: None)
        self._canais: dict[str, _Canal] = {}
        self._config = dict(_CONFIG_PADRAO)
        self._resultados: dict[str, dict] = {}
        self._registros: dict[str, dict] = {}
        self._historico: dict[str, list[dict]] = {}

    def registrar_canal(self, nome: str, enviar: Callable[[str, str], None],
                         prioridade: int) -> None:
        if prioridade < 0 or not nome or not callable(enviar):
            raise ErroNotificacao("CONFIGURACAO_INVALIDA")
        self._canais[nome] = _Canal(nome, enviar, prioridade)

    def configurar(self, config: dict) -> None:
        nova = dict(_CONFIG_PADRAO)
        for chave in ("tentativas", "backoff_base_s", "fator",
                      "silencio_inicio_h", "silencio_fim_h"):
            if chave in config:
                nova[chave] = config[chave]

        if nova["tentativas"] < 1:
            raise ErroNotificacao("CONFIGURACAO_INVALIDA")
        if nova["backoff_base_s"] <= 0:
            raise ErroNotificacao("CONFIGURACAO_INVALIDA")
        if nova["fator"] < 1:
            raise ErroNotificacao("CONFIGURACAO_INVALIDA")
        if not (0 <= nova["silencio_inicio_h"] <= 23):
            raise ErroNotificacao("CONFIGURACAO_INVALIDA")
        if not (0 <= nova["silencio_fim_h"] <= 23):
            raise ErroNotificacao("CONFIGURACAO_INVALIDA")

        self._config = nova

    def _em_silencio(self, quando: datetime) -> bool:
        inicio = self._config["silencio_inicio_h"]
        fim = self._config["silencio_fim_h"]
        if inicio == fim:
            return False
        hora = quando.hour
        if inicio < fim:
            return inicio <= hora < fim
        return hora >= inicio or hora < fim

    def _canais_ordenados(self) -> list[_Canal]:
        return sorted(self._canais.values(), key=lambda c: (c.prioridade, c.nome))

    def _validar_notificacao(self, notificacao: dict) -> None:
        if not notificacao.get("destinatario"):
            raise ErroNotificacao("DESTINATARIO_INVALIDO")
        mensagem = notificacao.get("mensagem")
        if not mensagem or len(mensagem) > 500:
            raise ErroNotificacao("MENSAGEM_INVALIDA")
        if not notificacao.get("idempotency_key"):
            raise ErroNotificacao("CONFIGURACAO_INVALIDA")
        quando = notificacao.get("quando")
        if quando is None or quando.tzinfo is None:
            raise ErroNotificacao("CONFIGURACAO_INVALIDA")
        if not self._canais:
            raise ErroNotificacao("CANAL_DESCONHECIDO")

    def _executar_ciclo(self, chave: str, destinatario: str, mensagem: str) -> dict:
        tentativas_totais = 0
        for canal in self._canais_ordenados():
            max_tentativas = self._config["tentativas"]
            for tentativa in range(1, max_tentativas + 1):
                if tentativa > 1:
                    # G-02: a i-esima espera (i = tentativa - 1) dura base * fator ** (i - 1)
                    espera = tentativa - 1
                    intervalo = (self._config["backoff_base_s"] *
                                 self._config["fator"] ** (espera - 1))
                    self._dormir(intervalo)
                tentativas_totais += 1
                try:
                    canal.enviar(destinatario, mensagem)
                except Exception as exc:
                    self._historico[chave].append({
                        "em": self._relogio(),
                        "canal": canal.nome,
                        "tentativa": tentativa,
                        "resultado": "FALHA",
                        "erro": str(exc),
                    })
                    continue
                else:
                    self._historico[chave].append({
                        "em": self._relogio(),
                        "canal": canal.nome,
                        "tentativa": tentativa,
                        "resultado": "SUCESSO",
                        "erro": None,
                    })
                    return {"status": "ENTREGUE", "canal": canal.nome,
                            "tentativas": tentativas_totais, "duplicado": False}

        return {"status": "DEAD_LETTER", "canal": None,
                "tentativas": tentativas_totais, "duplicado": False}

    def enviar(self, notificacao: dict) -> dict:
        chave = notificacao.get("idempotency_key")
        if chave and chave in self._resultados:
            resultado = dict(self._resultados[chave])
            resultado["duplicado"] = True
            return resultado

        self._validar_notificacao(notificacao)

        destinatario = notificacao["destinatario"]
        mensagem = notificacao["mensagem"]
        quando = notificacao["quando"]
        urgente = notificacao.get("urgente", False)

        if not urgente and self._em_silencio(quando):
            resultado = {"status": "ADIADA", "canal": None, "tentativas": 0,
                          "duplicado": False}
            self._resultados[chave] = resultado
            self._registros[chave] = {
                "destinatario": destinatario,
                "mensagem": mensagem,
            }
            self._historico.setdefault(chave, [])
            return dict(resultado)

        self._historico.setdefault(chave, [])
        self._registros[chave] = {
            "destinatario": destinatario,
            "mensagem": mensagem,
        }
        resultado = self._executar_ciclo(chave, destinatario, mensagem)
        self._resultados[chave] = resultado
        return dict(resultado)

    def dead_letters(self) -> list[dict]:
        letters = []
        for chave, resultado in self._resultados.items():
            if resultado["status"] != "DEAD_LETTER":
                continue
            registro = self._registros[chave]
            ultimo_erro = None
            for entrada in reversed(self._historico.get(chave, [])):
                ultimo_erro = entrada["erro"]
                break
            letters.append({
                "idempotency_key": chave,
                "destinatario": registro["destinatario"],
                "mensagem": registro["mensagem"],
                "ultimo_erro": ultimo_erro,
            })
        letters.sort(key=lambda d: d["idempotency_key"])
        return letters

    def reprocessar(self, idempotency_key: str) -> dict:
        if idempotency_key not in self._resultados:
            raise ErroNotificacao("NOTIFICACAO_NAO_ENCONTRADA")
        if self._resultados[idempotency_key]["status"] != "DEAD_LETTER":
            raise ErroNotificacao("ESTADO_INVALIDO")

        registro = self._registros[idempotency_key]
        resultado = self._executar_ciclo(idempotency_key, registro["destinatario"],
                                          registro["mensagem"])
        self._resultados[idempotency_key] = resultado
        return dict(resultado)

    def historico(self, idempotency_key: str) -> list[dict]:
        return list(self._historico.get(idempotency_key, []))
