"""Suíte cega UC-08 — controle de acesso com bloqueio e segundo fator."""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from solucao import ControleAcesso, ErroAcesso

SENHA = "hash-correto"
OUTRA = "hash-errado"
SEGREDO = "s3gr3d0"


class Relogio:
    INICIO = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)

    def __init__(self):
        self.t = self.INICIO

    def __call__(self):
        return self.t

    def avancar(self, **kw):
        self.t += timedelta(**kw)

    def reiniciar(self):
        self.t = self.INICIO


RELOGIO = Relogio()


def codigo(desafio_id, segredo=SEGREDO):
    return hashlib.sha256((segredo + desafio_id).encode()).hexdigest()[-6:]


@pytest.fixture
def ca():
    RELOGIO.reiniciar()
    c = ControleAcesso(relogio=RELOGIO)
    c.registrar_usuario("ana", SENHA)
    return c


@pytest.fixture
def mfa():
    RELOGIO.reiniciar()
    c = ControleAcesso(relogio=RELOGIO)
    c.registrar_usuario("bia", SENHA, SEGREDO)
    return c


def falhar(c, n, login="ana"):
    for _ in range(n):
        with pytest.raises(ErroAcesso):
            c.autenticar(login, OUTRA, "1.1.1.1", "d1")


# ------------------------------------------------------ G-01/G-07 enumeração

def test_login_inexistente_e_senha_errada_dao_o_mesmo_erro(ca):
    with pytest.raises(ErroAcesso) as e1:
        ca.autenticar("ana", OUTRA, "1.1.1.1", "d1")
    with pytest.raises(ErroAcesso) as e2:
        ca.autenticar("fantasma", SENHA, "1.1.1.1", "d1")
    assert e1.value.code == e2.value.code == "CREDENCIAL_INVALIDA"


def test_tentativa_contra_login_inexistente_nao_cria_estado(ca):
    for _ in range(10):
        with pytest.raises(ErroAcesso):
            ca.autenticar("fantasma", OUTRA, "1.1.1.1", "d1")
    with pytest.raises(ErroAcesso) as e:
        ca.situacao("fantasma")
    assert e.value.code == "USUARIO_INVALIDO"


# ----------------------------------------------------- G-03..G-06 bloqueio

def test_bloqueia_na_quinta_falha(ca):
    falhar(ca, 4)
    assert ca.situacao("ana")["bloqueado"] is False
    falhar(ca, 1)
    assert ca.situacao("ana")["bloqueado"] is True


def test_bloqueado_recusa_ate_a_senha_correta(ca):
    falhar(ca, 5)
    with pytest.raises(ErroAcesso) as e:
        ca.autenticar("ana", SENHA, "1.1.1.1", "d1")
    assert e.value.code == "CONTA_BLOQUEADA"


def test_tentativa_durante_bloqueio_nao_prorroga(ca):
    falhar(ca, 5)
    ate = ca.situacao("ana")["bloqueado_ate"]
    RELOGIO.avancar(minutes=10)
    with pytest.raises(ErroAcesso):
        ca.autenticar("ana", SENHA, "1.1.1.1", "d1")
    assert ca.situacao("ana")["bloqueado_ate"] == ate


def test_falhas_fora_da_janela_nao_somam(ca):
    falhar(ca, 4)
    RELOGIO.avancar(minutes=16)
    falhar(ca, 4)
    assert ca.situacao("ana")["bloqueado"] is False
    assert ca.situacao("ana")["falhas"] == 4


def test_sucesso_nao_zera_o_contador(ca):
    falhar(ca, 4)
    ca.autenticar("ana", SENHA, "1.1.1.1", "d1")
    assert ca.situacao("ana")["falhas"] == 4
    # Mais uma falha e vai bloquear
    with pytest.raises(ErroAcesso):
        ca.autenticar("ana", OUTRA, "1.1.1.1", "d1")
    assert ca.situacao("ana")["bloqueado"] is True


def test_bloqueio_expira_e_zera_o_contador(ca):
    falhar(ca, 5)
    RELOGIO.avancar(minutes=30)
    assert ca.autenticar("ana", SENHA, "1.1.1.1", "d1")["status"] == "AUTENTICADO"
    assert ca.situacao("ana")["falhas"] == 0
    assert ca.situacao("ana")["bloqueado_ate"] is None


def test_evento_de_desbloqueio_registrado(ca):
    falhar(ca, 5)
    RELOGIO.avancar(minutes=31)
    ca.autenticar("ana", SENHA, "1.1.1.1", "d1")
    tipos = [e["tipo"] for e in ca.eventos("ana")]
    assert "BLOQUEIO" in tipos and "DESBLOQUEIO" in tipos
    assert tipos.index("BLOQUEIO") < tipos.index("DESBLOQUEIO")


# --------------------------------------------------------- G-08 quando exigir

def test_usuario_sem_mfa_autentica_direto(ca):
    r = ca.autenticar("ana", SENHA, "1.1.1.1", "d1")
    assert r["status"] == "AUTENTICADO" and r["sessao_id"] and r["desafio_id"] is None


def test_dispositivo_novo_exige_segundo_fator(mfa):
    r = mfa.autenticar("bia", SENHA, "1.1.1.1", "novo")
    assert r["status"] == "MFA_REQUERIDO"
    assert r["desafio_id"] and r["sessao_id"] is None


def test_dispositivo_conhecido_dispensa_segundo_fator(mfa):
    r = mfa.autenticar("bia", SENHA, "1.1.1.1", "d1")
    mfa.responder_mfa(r["desafio_id"], codigo(r["desafio_id"]))
    r2 = mfa.autenticar("bia", SENHA, "9.9.9.9", "d1")
    assert r2["status"] == "AUTENTICADO"


def test_politica_pode_dispensar_o_segundo_fator(mfa):
    mfa.configurar_politica({"max_falhas": 5, "janela_falhas_min": 15,
                             "bloqueio_min": 30, "sessao_min": 60,
                             "exigir_mfa_novo_dispositivo": False})
    assert mfa.autenticar("bia", SENHA, "1.1.1.1", "zzz")["status"] == "AUTENTICADO"


# ------------------------------------------------------ G-09..G-11 desafio

def test_codigo_correto_conclui_a_autenticacao(mfa):
    r = mfa.autenticar("bia", SENHA, "1.1.1.1", "novo")
    f = mfa.responder_mfa(r["desafio_id"], codigo(r["desafio_id"]))
    assert f["status"] == "AUTENTICADO" and f["sessao_id"]
    assert mfa.validar_sessao(f["sessao_id"])["login"] == "bia"


def test_codigo_errado(mfa):
    r = mfa.autenticar("bia", SENHA, "1.1.1.1", "novo")
    with pytest.raises(ErroAcesso) as e:
        mfa.responder_mfa(r["desafio_id"], "000000")
    assert e.value.code == "MFA_INVALIDO"


def test_desafio_e_de_uso_unico(mfa):
    r = mfa.autenticar("bia", SENHA, "1.1.1.1", "novo")
    mfa.responder_mfa(r["desafio_id"], codigo(r["desafio_id"]))
    with pytest.raises(ErroAcesso) as e:
        mfa.responder_mfa(r["desafio_id"], codigo(r["desafio_id"]))
    assert e.value.code == "MFA_INVALIDO"


def test_desafio_expira_em_cinco_minutos(mfa):
    r = mfa.autenticar("bia", SENHA, "1.1.1.1", "novo")
    RELOGIO.avancar(minutes=5, seconds=1)
    with pytest.raises(ErroAcesso) as e:
        mfa.responder_mfa(r["desafio_id"], codigo(r["desafio_id"]))
    assert e.value.code == "MFA_INVALIDO"


def test_desafio_inexistente(mfa):
    with pytest.raises(ErroAcesso) as e:
        mfa.responder_mfa("nao-existe", "000000")
    assert e.value.code == "MFA_INVALIDO"


def test_falha_de_mfa_conta_para_o_bloqueio(mfa):
    for _ in range(5):
        r = mfa.autenticar("bia", SENHA, "1.1.1.1", "novo")
        with pytest.raises(ErroAcesso):
            mfa.responder_mfa(r["desafio_id"], "000000")
    assert mfa.situacao("bia")["bloqueado"] is True
    assert "MFA_FALHA" in [e["tipo"] for e in mfa.eventos("bia")]


# ---------------------------------------------------------- G-12/G-13 sessão

def test_sessao_reduz_expiracao_a_cada_validacao(ca):
    s = ca.autenticar("ana", SENHA, "1.1.1.1", "d1")["sessao_id"]
    RELOGIO.avancar(minutes=58)
    ca.validar_sessao(s)                      # penalidade de 1 min -> expira no 59
    RELOGIO.avancar(minutes=1)                # agora é 59
    with pytest.raises(ErroAcesso) as e:
        ca.validar_sessao(s)
    assert e.value.code == "SESSAO_INVALIDA"


def test_expira_em_reflete_a_politica(ca):
    r = ca.autenticar("ana", SENHA, "1.1.1.1", "d1")
    assert r["expira_em"] == RELOGIO.t + timedelta(minutes=60)


def test_sessao_revogada_nao_vale_mais(ca):
    s = ca.autenticar("ana", SENHA, "1.1.1.1", "d1")["sessao_id"]
    ca.revogar_sessao(s)
    with pytest.raises(ErroAcesso) as e:
        ca.validar_sessao(s)
    assert e.value.code == "SESSAO_INVALIDA"


def test_revogar_duas_vezes(ca):
    s = ca.autenticar("ana", SENHA, "1.1.1.1", "d1")["sessao_id"]
    ca.revogar_sessao(s)
    with pytest.raises(ErroAcesso) as e:
        ca.revogar_sessao(s)
    assert e.value.code == "SESSAO_INVALIDA"


def test_revogar_todas_conta_apenas_as_ativas(ca):
    ca.autenticar("ana", SENHA, "1.1.1.1", "d1")
    ca.autenticar("ana", SENHA, "1.1.1.1", "d2")
    RELOGIO.avancar(minutes=61)      # as duas expiraram
    ca.autenticar("ana", SENHA, "1.1.1.1", "d3")
    assert ca.revogar_todas("ana") == 1


def test_sessoes_ativas_na_situacao(ca):
    ca.autenticar("ana", SENHA, "1.1.1.1", "d1")
    ca.autenticar("ana", SENHA, "1.1.1.1", "d2")
    assert ca.situacao("ana")["sessoes_ativas"] == 2
    ca.revogar_todas("ana")
    assert ca.situacao("ana")["sessoes_ativas"] == 0


def test_sessao_inexistente(ca):
    with pytest.raises(ErroAcesso) as e:
        ca.validar_sessao("nao-existe")
    assert e.value.code == "SESSAO_INVALIDA"


# ------------------------------------------------------------ G-14 auditoria

def test_eventos_em_ordem_cronologica_e_sem_segredos(mfa):
    r = mfa.autenticar("bia", SENHA, "1.1.1.1", "novo")
    mfa.responder_mfa(r["desafio_id"], codigo(r["desafio_id"]))
    evs = mfa.eventos("bia")
    assert [e["em"] for e in evs] == sorted(e["em"] for e in evs)
    assert all(set(e) == {"em", "tipo", "ip", "dispositivo"} for e in evs)
    bruto = repr(evs)
    assert SENHA not in bruto and SEGREDO not in bruto


def test_login_com_sucesso_e_falha_geram_eventos(ca):
    falhar(ca, 1)
    ca.autenticar("ana", SENHA, "2.2.2.2", "d1")
    tipos = [e["tipo"] for e in ca.eventos("ana")]
    assert tipos == ["LOGIN_FALHA", "LOGIN_SUCESSO"]
    assert ca.eventos("ana")[-1]["ip"] == "2.2.2.2"


def test_revogacao_gera_um_evento_por_sessao(ca):
    ca.autenticar("ana", SENHA, "1.1.1.1", "d1")
    ca.autenticar("ana", SENHA, "1.1.1.1", "d2")
    ca.revogar_todas("ana")
    assert [e["tipo"] for e in ca.eventos("ana")].count("SESSAO_REVOGADA") == 2


# ------------------------------------------------- G-15..G-18 política e refs

@pytest.mark.parametrize("chave", ["max_falhas", "janela_falhas_min",
                                   "bloqueio_min", "sessao_min"])
def test_politica_com_valor_nao_positivo(ca, chave):
    pol = {"max_falhas": 5, "janela_falhas_min": 15, "bloqueio_min": 30,
           "sessao_min": 60, "exigir_mfa_novo_dispositivo": True}
    pol[chave] = 0
    with pytest.raises(ErroAcesso) as e:
        ca.configurar_politica(pol)
    assert e.value.code == "POLITICA_INVALIDA"


def test_politica_com_chave_ausente(ca):
    with pytest.raises(ErroAcesso) as e:
        ca.configurar_politica({"max_falhas": 5})
    assert e.value.code == "POLITICA_INVALIDA"


def test_politica_aplicada_muda_o_limite(ca):
    ca.configurar_politica({"max_falhas": 2, "janela_falhas_min": 15,
                            "bloqueio_min": 30, "sessao_min": 60,
                            "exigir_mfa_novo_dispositivo": True})
    falhar(ca, 2)
    assert ca.situacao("ana")["bloqueado"] is True


def test_configurar_politica_nao_reseta_estado(ca):
    falhar(ca, 3)
    ca.configurar_politica({"max_falhas": 5, "janela_falhas_min": 15,
                            "bloqueio_min": 30, "sessao_min": 60,
                            "exigir_mfa_novo_dispositivo": True})
    assert ca.situacao("ana")["falhas"] == 3


def test_registro_duplicado(ca):
    with pytest.raises(ErroAcesso) as e:
        ca.registrar_usuario("ana", SENHA)
    assert e.value.code == "USUARIO_INVALIDO"


def test_registro_com_hash_vazio(ca):
    with pytest.raises(ErroAcesso) as e:
        ca.registrar_usuario("novo", "")
    assert e.value.code == "USUARIO_INVALIDO"


@pytest.mark.parametrize("metodo", ["situacao", "eventos", "revogar_todas"])
def test_consulta_com_login_inexistente(ca, metodo):
    with pytest.raises(ErroAcesso) as e:
        getattr(ca, metodo)("fantasma")
    assert e.value.code == "USUARIO_INVALIDO"
