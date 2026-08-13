"""Suíte cega UC-15 — orquestrador de notificações com reenvio."""

from datetime import datetime, timezone

import pytest

from solucao import ErroNotificacao, Orquestrador

AGORA = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
MADRUGADA = datetime(2026, 6, 15, 3, 0, tzinfo=timezone.utc)


class Canal:
    def __init__(self, falhas=0, erro="indisponivel"):
        self.falhas = falhas
        self.erro = erro
        self.chamadas = []

    def __call__(self, destinatario, mensagem):
        self.chamadas.append((destinatario, mensagem))
        if len(self.chamadas) <= self.falhas:
            raise RuntimeError(self.erro)


class Sono:
    def __init__(self):
        self.esperas = []

    def __call__(self, s):
        self.esperas.append(s)


def montar(canais=(("push", 0, 1),), config=None):
    sono = Sono()
    o = Orquestrador(relogio=lambda: AGORA, dormir=sono)
    objs = {}
    for nome, falhas, pri in canais:
        c = Canal(falhas)
        objs[nome] = c
        o.registrar_canal(nome, c, pri)
    if config:
        o.configurar(config)
    return o, objs, sono


def notif(**kw):
    n = {"destinatario": "cli", "mensagem": "oi", "idempotency_key": "k1",
         "urgente": False, "quando": AGORA}
    n.update(kw)
    return n


# --------------------------------------------------- G-01/G-02 tentativas

def test_sucesso_na_primeira_tentativa():
    o, c, sono = montar()
    r = o.enviar(notif())
    assert r["status"] == "ENTREGUE" and r["canal"] == "push" and r["tentativas"] == 1
    assert sono.esperas == []


def test_reenvio_ate_o_sucesso():
    o, c, sono = montar(canais=(("push", 2, 1),))
    r = o.enviar(notif())
    assert r["status"] == "ENTREGUE" and r["tentativas"] == 3
    assert len(c["push"].chamadas) == 3


def test_backoff_exponencial_deterministico():
    o, c, sono = montar(canais=(("push", 2, 1),))
    o.enviar(notif())
    assert sono.esperas == [1, 2]


def test_nao_dorme_depois_da_ultima_tentativa():
    o, c, sono = montar(canais=(("push", 3, 1),))
    o.enviar(notif())
    assert sono.esperas == [1, 2]


def test_tentativas_configuraveis():
    o, c, sono = montar(canais=(("push", 10, 1),),
                        config={"tentativas": 2, "backoff_base_s": 5, "fator": 3})
    r = o.enviar(notif())
    assert len(c["push"].chamadas) == 2 and sono.esperas == [5]
    assert r["status"] == "DEAD_LETTER"


# ------------------------------------------------------ G-03/G-04 canais

def test_cai_para_o_proximo_canal_apos_esgotar():
    o, c, _ = montar(canais=(("push", 3, 1), ("sms", 0, 2)))
    r = o.enviar(notif())
    assert r["canal"] == "sms" and r["status"] == "ENTREGUE"
    assert len(c["push"].chamadas) == 3 and len(c["sms"].chamadas) == 1


def test_tentativas_somam_todos_os_canais():
    o, _, _ = montar(canais=(("push", 3, 1), ("sms", 0, 2)))
    assert o.enviar(notif())["tentativas"] == 4


def test_ordem_por_prioridade():
    o, c, _ = montar(canais=(("sms", 0, 2), ("push", 0, 1)))
    assert o.enviar(notif())["canal"] == "push"
    assert c["sms"].chamadas == []


def test_empate_de_prioridade_desempata_por_nome():
    o, c, _ = montar(canais=(("zap", 0, 1), ("email", 0, 1)))
    assert o.enviar(notif())["canal"] == "email"


def test_sucesso_impede_canais_seguintes():
    o, c, _ = montar(canais=(("push", 0, 1), ("sms", 0, 2)))
    o.enviar(notif())
    assert c["sms"].chamadas == []


# --------------------------------------------------------- G-05 dead letter

def test_todos_os_canais_falharam():
    o, _, _ = montar(canais=(("push", 3, 1), ("sms", 3, 2)))
    r = o.enviar(notif())
    assert r["status"] == "DEAD_LETTER" and r["canal"] is None and r["tentativas"] == 6


def test_dead_letters_lista_a_notificacao():
    o, _, _ = montar(canais=(("push", 3, 1),))
    o.enviar(notif())
    dl = o.dead_letters()
    assert len(dl) == 1
    assert dl[0]["idempotency_key"] == "k1" and dl[0]["ultimo_erro"] == "indisponivel"


def test_dead_letters_ordenado_por_chave():
    o, _, _ = montar(canais=(("push", 99, 1),))
    o.enviar(notif(idempotency_key="kb"))
    o.enviar(notif(idempotency_key="ka"))
    assert [d["idempotency_key"] for d in o.dead_letters()] == ["ka", "kb"]


# ------------------------------------------------------ G-06 janela de silêncio

def test_nao_urgente_na_madrugada_e_enviada():
    o, c, _ = montar()
    r = o.enviar(notif(quando=MADRUGADA))
    assert r["status"] == "ENTREGUE"
    assert len(c["push"].chamadas) == 1


def test_urgente_atravessa_a_janela_e_adiada():
    o, c, _ = montar()
    r = o.enviar(notif(quando=MADRUGADA, urgente=True))
    assert r == {"status": "ADIADA", "canal": None, "tentativas": 0, "duplicado": False}
    assert c["push"].chamadas == []


def test_fora_da_janela_envia_normalmente():
    o, _, _ = montar()
    assert o.enviar(notif(quando=AGORA))["status"] == "ENTREGUE"


def test_fronteira_de_abertura_da_janela():
    o, _, _ = montar()
    inicio = datetime(2026, 6, 15, 22, 0, tzinfo=timezone.utc)
    fim = datetime(2026, 6, 15, 8, 0, tzinfo=timezone.utc)
    # urgente é quem sofre a janela anômala
    assert o.enviar(notif(idempotency_key="a", quando=inicio, urgente=True))["status"] == "ADIADA"
    assert o.enviar(notif(idempotency_key="b", quando=fim, urgente=True))["status"] == "ENTREGUE"


def test_janela_desativada_quando_inicio_igual_fim():
    o, _, _ = montar(config={"silencio_inicio_h": 0, "silencio_fim_h": 0})
    assert o.enviar(notif(quando=MADRUGADA))["status"] == "ENTREGUE"


def test_adiada_nao_gera_historico():
    o, _, _ = montar()
    o.enviar(notif(quando=MADRUGADA, urgente=True))
    assert o.historico("k1") == []


# ---------------------------------------------------------- G-07 idempotência

def test_chave_repetida_reenvia_tudo():
    o, c, _ = montar()
    o.enviar(notif())
    r = o.enviar(notif())
    assert r["duplicado"] is False and r["status"] == "ENTREGUE"
    assert len(c["push"].chamadas) == 2


def test_chave_repetida_de_dead_letter():
    o, c, _ = montar(canais=(("push", 99, 1),))
    o.enviar(notif())
    n = len(c["push"].chamadas)
    r = o.enviar(notif())
    assert r["duplicado"] is False and r["status"] == "DEAD_LETTER"
    assert len(c["push"].chamadas) == n * 2


def test_chaves_diferentes_enviam_separado():
    o, c, _ = montar()
    o.enviar(notif(idempotency_key="k1"))
    o.enviar(notif(idempotency_key="k2"))
    assert len(c["push"].chamadas) == 2


# ------------------------------------------------------- G-08 reprocessamento

def test_reprocessar_dead_letter_com_sucesso():
    sono = Sono()
    o = Orquestrador(relogio=lambda: AGORA, dormir=sono)
    canal = Canal(falhas=3)
    o.registrar_canal("push", canal, 1)
    o.enviar(notif())
    r = o.reprocessar("k1")
    assert r["status"] == "ENTREGUE"
    assert o.dead_letters() == []


def test_reprocessar_notificacao_entregue():
    o, _, _ = montar()
    o.enviar(notif())
    with pytest.raises(ErroNotificacao) as e:
        o.reprocessar("k1")
    assert e.value.code == "ESTADO_INVALIDO"


def test_reprocessar_chave_desconhecida():
    o, _, _ = montar()
    with pytest.raises(ErroNotificacao) as e:
        o.reprocessar("nao-existe")
    assert e.value.code == "NOTIFICACAO_NAO_ENCONTRADA"


def test_inexistente_precede_estado():
    o, _, _ = montar()
    o.enviar(notif())
    with pytest.raises(ErroNotificacao) as e:
        o.reprocessar("outra-chave")
    assert e.value.code == "NOTIFICACAO_NAO_ENCONTRADA"


# ------------------------------------------------------------ G-09 histórico

def test_uma_entrada_por_tentativa():
    o, _, _ = montar(canais=(("push", 2, 1),))
    o.enviar(notif())
    h = o.historico("k1")
    assert [x["resultado"] for x in h] == ["FALHA", "FALHA", "SUCESSO"]
    assert [x["tentativa"] for x in h] == [1, 2, 3]
    assert h[0]["erro"] == "indisponivel" and h[-1]["erro"] is None


def test_historico_numera_por_canal():
    o, _, _ = montar(canais=(("push", 3, 1), ("sms", 0, 2)))
    o.enviar(notif())
    h = o.historico("k1")
    assert [(x["canal"], x["tentativa"]) for x in h] == [
        ("push", 1), ("push", 2), ("push", 3), ("sms", 1)]


def test_historico_expoe_as_chaves_do_contrato():
    o, _, _ = montar()
    o.enviar(notif())
    assert set(o.historico("k1")[0]) == {"em", "canal", "tentativa", "resultado", "erro"}


def test_reprocessamento_acrescenta_ao_historico():
    sono = Sono()
    o = Orquestrador(relogio=lambda: AGORA, dormir=sono)
    o.registrar_canal("push", Canal(falhas=3), 1)
    o.enviar(notif())
    antes = len(o.historico("k1"))
    o.reprocessar("k1")
    assert len(o.historico("k1")) > antes


# ---------------------------------------------- G-10..G-13 validação

def test_sem_canal_registrado():
    o = Orquestrador(relogio=lambda: AGORA, dormir=lambda s: None)
    with pytest.raises(ErroNotificacao) as e:
        o.enviar(notif())
    assert e.value.code == "CANAL_DESCONHECIDO"


@pytest.mark.parametrize("kw,code", [
    ({"destinatario": ""}, "DESTINATARIO_INVALIDO"),
    ({"mensagem": ""}, "MENSAGEM_INVALIDA"),
    ({"mensagem": "x" * 501}, "MENSAGEM_INVALIDA"),
    ({"idempotency_key": ""}, "CONFIGURACAO_INVALIDA"),
    ({"quando": datetime(2026, 6, 15, 10, 0)}, "CONFIGURACAO_INVALIDA"),
])
def test_notificacao_invalida(kw, code):
    o, _, _ = montar()
    with pytest.raises(ErroNotificacao) as e:
        o.enviar(notif(**kw))
    assert e.value.code == code


def test_mensagem_de_quinhentos_caracteres_e_valida():
    o, _, _ = montar()
    assert o.enviar(notif(mensagem="x" * 500))["status"] == "ENTREGUE"


def test_destinatario_precede_mensagem():
    o, _, _ = montar()
    with pytest.raises(ErroNotificacao) as e:
        o.enviar(notif(destinatario="", mensagem=""))
    assert e.value.code == "DESTINATARIO_INVALIDO"


def test_validacao_precede_canal_desconhecido():
    o = Orquestrador(relogio=lambda: AGORA, dormir=lambda s: None)
    with pytest.raises(ErroNotificacao) as e:
        o.enviar(notif(destinatario=""))
    assert e.value.code == "DESTINATARIO_INVALIDO"


@pytest.mark.parametrize("cfg", [
    {"tentativas": 0}, {"backoff_base_s": 0}, {"fator": 0.5},
    {"silencio_inicio_h": 24}, {"silencio_fim_h": -1},
])
def test_configuracao_invalida(cfg):
    o, _, _ = montar()
    with pytest.raises(ErroNotificacao) as e:
        o.configurar(cfg)
    assert e.value.code == "CONFIGURACAO_INVALIDA"


@pytest.mark.parametrize("nome,fn,pri", [
    ("", Canal(), 1), ("x", "nao-chamavel", 1), ("x", Canal(), -1),
])
def test_registro_de_canal_invalido(nome, fn, pri):
    o, _, _ = montar()
    with pytest.raises(ErroNotificacao) as e:
        o.registrar_canal(nome, fn, pri)
    assert e.value.code == "CONFIGURACAO_INVALIDA"


def test_reregistro_substitui_o_canal():
    o, c, _ = montar(canais=(("push", 99, 1),))
    novo = Canal(0)
    o.registrar_canal("push", novo, 1)
    assert o.enviar(notif())["status"] == "ENTREGUE"
    assert len(novo.chamadas) == 1
