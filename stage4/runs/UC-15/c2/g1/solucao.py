"""UC-15 — Orquestrador de notificações com reenvio."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional


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


class _Notificacao:
    __slots__ = ("destinatario", "mensagem", "resultado", "historico")

    def __init__(self, destinatario: str, mensagem: str, resultado: dict) -> None:
        self.destinatario = destinatario
        self.mensagem = mensagem
        self.resultado = resultado
        self.historico: list[dict] = []


class Orquestrador:
    def __init__(self, relogio: Optional[Callable[[], datetime]] = None,
                 dormir: Optional[Callable[[float], None]] = None) -> None:
        self._relogio = relogio if relogio is not None else (lambda: datetime.now(timezone.utc))
        self._dormir = dormir if dormir is not None else (lambda s: None)
        self._canais: dict[str, _Canal] = {}
        self._config = {
            "tentativas": 3,
            "backoff_base_s": 1.0,
            "fator": 2.0,
            "silencio_inicio_h": 22,
            "silencio_fim_h": 8,
        }
        self._notificacoes: dict[str, _Notificacao] = {}

    def registrar_canal(self, nome: str, enviar: Callable[[str, str], None],
                         prioridade: int) -> None:
        if not nome or not callable(enviar) or prioridade < 0:
            raise ErroNotificacao("CONFIGURACAO_INVALIDA")
        self._canais[nome] = _Canal(nome, enviar, prioridade)

    def configurar(self, config: dict) -> None:
        tentativas = config.get("tentativas", 3)
        backoff_base_s = config.get("backoff_base_s", 1.0)
        fator = config.get("fator", 2.0)
        silencio_inicio_h = config.get("silencio_inicio_h", 22)
        silencio_fim_h = config.get("silencio_fim_h", 8)

        if tentativas < 1 or backoff_base_s <= 0 or fator < 1:
            raise ErroNotificacao("CONFIGURACAO_INVALIDA")
        if not (0 <= silencio_inicio_h <= 23) or not (0 <= silencio_fim_h <= 23):
            raise ErroNotificacao("CONFIGURACAO_INVALIDA")

        self._config = {
            "tentativas": tentativas,
            "backoff_base_s": backoff_base_s,
            "fator": fator,
            "silencio_inicio_h": silencio_inicio_h,
            "silencio_fim_h": silencio_fim_h,
        }

    def _em_silencio(self, quando: datetime) -> bool:
        inicio = self._config["silencio_inicio_h"]
        fim = self._config["silencio_fim_h"]
        if inicio == fim:
            return False
        hora = quando.hour
        if inicio < fim:
            return inicio <= hora < fim
        return hora >= inicio or hora < fim

    def _validar(self, notificacao: dict) -> None:
        destinatario = notificacao.get("destinatario")
        if not destinatario:
            raise ErroNotificacao("DESTINATARIO_INVALIDO")

        mensagem = notificacao.get("mensagem")
        if not mensagem or len(mensagem) > 500:
            raise ErroNotificacao("MENSAGEM_INVALIDA")

        idempotency_key = notificacao.get("idempotency_key")
        quando = notificacao.get("quando")
        if not idempotency_key or quando is None or quando.tzinfo is None:
            raise ErroNotificacao("CONFIGURACAO_INVALIDA")

        if not self._canais:
            raise ErroNotificacao("CANAL_DESCONHECIDO")

    def _canais_ordenados(self) -> list[_Canal]:
        return sorted(self._canais.values(), key=lambda c: (c.prioridade, c.nome))

    def _executar_ciclo(self, notif: _Notificacao, idempotency_key: str) -> dict:
        tentativas_config = self._config["tentativas"]
        base = self._config["backoff_base_s"]
        fator = self._config["fator"]

        total_tentativas = 0
        ultimo_erro: Optional[str] = None

        for canal in self._canais_ordenados():
            for i in range(1, tentativas_config + 1):
                if i > 1:
                    self._dormir(base * (fator ** (i - 2)))

                total_tentativas += 1
                try:
                    canal.enviar(notif.destinatario, notif.mensagem)
                except Exception as e:
                    erro_str = str(e)
                    ultimo_erro = erro_str
                    notif.historico.append({
                        "em": self._relogio(),
                        "canal": canal.nome,
                        "tentativa": i,
                        "resultado": "FALHA",
                        "erro": erro_str,
                    })
                else:
                    notif.historico.append({
                        "em": self._relogio(),
                        "canal": canal.nome,
                        "tentativa": i,
                        "resultado": "SUCESSO",
                        "erro": None,
                    })
                    resultado = {
                        "status": "ENTREGUE",
                        "canal": canal.nome,
                        "tentativas": total_tentativas,
                        "duplicado": False,
                    }
                    return resultado

        resultado = {
            "status": "DEAD_LETTER",
            "canal": None,
            "tentativas": total_tentativas,
            "duplicado": False,
        }
        self._dead_letters_erro = getattr(self, "_dead_letters_erro", {})
        self._dead_letters_erro[idempotency_key] = ultimo_erro
        return resultado

    def enviar(self, notificacao: dict) -> dict:
        self._validar(notificacao)

        idempotency_key = notificacao["idempotency_key"]

        if idempotency_key in self._notificacoes:
            anterior = self._notificacoes[idempotency_key].resultado
            return dict(anterior, duplicado=True)

        destinatario = notificacao["destinatario"]
        mensagem = notificacao["mensagem"]
        quando = notificacao["quando"]
        urgente = notificacao.get("urgente", False)

        if not urgente and self._em_silencio(quando):
            resultado = {
                "status": "ADIADA",
                "canal": None,
                "tentativas": 0,
                "duplicado": False,
            }
            notif = _Notificacao(destinatario, mensagem, resultado)
            self._notificacoes[idempotency_key] = notif
            return dict(resultado)

        notif = _Notificacao(destinatario, mensagem, {})
        self._notificacoes[idempotency_key] = notif
        resultado = self._executar_ciclo(notif, idempotency_key)
        notif.resultado = resultado
        return dict(resultado)

    def dead_letters(self) -> list[dict]:
        erros = getattr(self, "_dead_letters_erro", {})
        saida = []
        for chave, notif in self._notificacoes.items():
            if notif.resultado.get("status") == "DEAD_LETTER":
                saida.append({
                    "idempotency_key": chave,
                    "destinatario": notif.destinatario,
                    "mensagem": notif.mensagem,
                    "ultimo_erro": erros.get(chave),
                })
        saida.sort(key=lambda d: d["idempotency_key"])
        return saida

    def reprocessar(self, idempotency_key: str) -> dict:
        notif = self._notificacoes.get(idempotency_key)
        if notif is None:
            raise ErroNotificacao("NOTIFICACAO_NAO_ENCONTRADA")
        if notif.resultado.get("status") != "DEAD_LETTER":
            raise ErroNotificacao("ESTADO_INVALIDO")

        resultado = self._executar_ciclo(notif, idempotency_key)
        notif.resultado = resultado
        if resultado["status"] != "DEAD_LETTER":
            erros = getattr(self, "_dead_letters_erro", {})
            erros.pop(idempotency_key, None)
        return dict(resultado)

    def historico(self, idempotency_key: str) -> list[dict]:
        notif = self._notificacoes.get(idempotency_key)
        if notif is None:
            return []
        return list(notif.historico)
