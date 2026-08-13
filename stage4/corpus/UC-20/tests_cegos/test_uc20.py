"""Suíte cega UC-20 — gestor de credenciais com política e rotação."""

from datetime import datetime, timedelta, timezone

import pytest

from solucao import ErroCredencial, GestorCredenciais

T0 = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
BOA = "Xk7#mQ2$wLp9"
BOA2 = "Vt5@nRj8&zHw"
BOA3 = "Bp3!yUc6%fKd"


class Relogio:
    def __init__(self):
        self.t = T0

    def __call__(self):
        return self.t

    def avancar(self, **kw):
        self.t += timedelta(**kw)


def montar(politica=None):
    r = Relogio()
    g = GestorCredenciais(relogio=r)
    g.definir_politica("padrao", politica or {})
    g.criar_usuario("ana", "padrao")
    return g, r


# ------------------------------------------------------- G-01/G-02 avaliação

def test_senha_boa_nao_tem_violacoes():
    g, _ = montar()
    assert g.avaliar(BOA, "padrao") == []


def test_avaliacao_devolve_todas_as_violacoes():
    g, _ = montar()
    assert g.avaliar("password", "padrao") == ["COMPRIMENTO", "CLASSES", "COMUM"]


def test_ordem_das_violacoes_e_fixa():
    g, _ = montar()
    assert g.avaliar("aaaabbbbcccc", "padrao") == ["CLASSES", "REPETICAO"]


# --------------------------------------------------------- G-03..G-07 regras

def test_comprimento_minimo():
    g, _ = montar()
    assert g.avaliar("Xk7#mQ2$wLp", "padrao") == ["COMPRIMENTO"]


def test_comprimento_exato_e_aceito():
    g, _ = montar()
    assert "COMPRIMENTO" not in g.avaliar(BOA, "padrao")


def test_duas_classes_nao_bastam():
    g, _ = montar()
    assert g.avaliar("XKMQWLPRVT2N", "padrao") == ["CLASSES"]


def test_tres_classes_bastam():
    g, _ = montar()
    assert g.avaliar("XkmQwLpRvT2n", "padrao") == []


def test_senha_comum_sem_diferenciar_maiusculas():
    g, _ = montar({"min_caracteres": 8, "classes_minimas": 1})
    assert g.avaliar("PassWord", "padrao") == ["COMUM"]


def test_repeticao_de_quatro():
    g, _ = montar()
    assert g.avaliar("Xk7#mQaaaa$9", "padrao") == ["REPETICAO"]


def test_repeticao_de_tres_e_aceita():
    g, _ = montar()
    assert g.avaliar("Xk7#mQaaa$92", "padrao") == []


def test_sequencia_crescente():
    g, _ = montar()
    assert g.avaliar("Xk7#mQabcd$9", "padrao") == ["SEQUENCIA"]


def test_sequencia_decrescente():
    g, _ = montar()
    assert g.avaliar("Xk#mQ4321$9w", "padrao") == ["SEQUENCIA"]


def test_sequencia_de_tres_e_aceita():
    g, _ = montar()
    assert g.avaliar("Xk7#mQabc$92", "padrao") == []


def test_politica_configuravel():
    g, _ = montar({"min_caracteres": 20})
    assert g.avaliar(BOA, "padrao") == ["COMPRIMENTO"]


def test_classes_minimas_configuravel():
    g, _ = montar({"classes_minimas": 4})
    assert g.avaliar("XkmQwLpRvT2n", "padrao") == ["CLASSES"]


def test_comuns_configuravel():
    g, _ = montar({"comuns": [BOA]})
    assert g.avaliar(BOA, "padrao") == ["COMUM"]


# ------------------------------------------------------ G-08/G-09 troca

def test_definir_senha_boa():
    g, _ = montar()
    r = g.definir_senha("ana", BOA)
    assert r == {"expira_em": T0 + timedelta(days=90), "trocas": 1}


def test_senha_fraca_e_recusada():
    g, _ = montar()
    with pytest.raises(ErroCredencial) as e:
        g.definir_senha("ana", "password")
    assert e.value.code == "SENHA_FRACA"


def test_reutilizacao_da_senha_atual():
    g, _ = montar()
    g.definir_senha("ana", BOA)
    with pytest.raises(ErroCredencial) as e:
        g.definir_senha("ana", BOA)
    assert e.value.code == "SENHA_REUTILIZADA"


def test_reutilizacao_dentro_do_historico():
    g, _ = montar({"historico": 3})
    g.definir_senha("ana", BOA)
    g.definir_senha("ana", BOA2)
    with pytest.raises(ErroCredencial) as e:
        g.definir_senha("ana", BOA)
    assert e.value.code == "SENHA_REUTILIZADA"


def test_senha_fora_do_historico_pode_voltar():
    g, _ = montar({"historico": 2})
    g.definir_senha("ana", BOA)
    g.definir_senha("ana", BOA2)
    g.definir_senha("ana", BOA3)
    assert g.definir_senha("ana", BOA)["trocas"] == 4


def test_forca_precede_reutilizacao():
    g, _ = montar()
    g.definir_senha("ana", BOA)
    with pytest.raises(ErroCredencial) as e:
        g.definir_senha("ana", "password")
    assert e.value.code == "SENHA_FRACA"


def test_contador_de_trocas():
    g, _ = montar()
    g.definir_senha("ana", BOA)
    assert g.definir_senha("ana", BOA2)["trocas"] == 2


# ------------------------------------------------- G-11..G-15 rotação e login

def test_autenticacao_com_senha_correta():
    g, _ = montar()
    g.definir_senha("ana", BOA)
    assert g.autenticar("ana", BOA) == {"autenticado": True, "expirada": False,
                                        "em_tolerancia": False,
                                        "dias_para_expirar": 90}


def test_senha_incorreta_nao_levanta_excecao():
    g, _ = montar()
    g.definir_senha("ana", BOA)
    assert g.autenticar("ana", "errada")["autenticado"] is False


def test_senha_expirada_dentro_da_tolerancia():
    g, r = montar()
    g.definir_senha("ana", BOA)
    r.avancar(days=90)
    a = g.autenticar("ana", BOA)
    assert a["autenticado"] is True
    assert a["expirada"] is True and a["em_tolerancia"] is True


def test_um_dia_antes_ainda_nao_expirou():
    g, r = montar()
    g.definir_senha("ana", BOA)
    r.avancar(days=89)
    assert g.autenticar("ana", BOA)["expirada"] is False


def test_fim_da_tolerancia_bloqueia():
    g, r = montar()
    g.definir_senha("ana", BOA)
    r.avancar(days=97)
    a = g.autenticar("ana", BOA)
    assert a["autenticado"] is False
    assert a["expirada"] is True and a["em_tolerancia"] is False


def test_ultimo_dia_da_tolerancia_ainda_autentica():
    g, r = montar()
    g.definir_senha("ana", BOA)
    r.avancar(days=96)
    assert g.autenticar("ana", BOA)["autenticado"] is True


def test_dias_para_expirar_fica_negativo():
    g, r = montar()
    g.definir_senha("ana", BOA)
    r.avancar(days=93)
    assert g.autenticar("ana", BOA)["dias_para_expirar"] == -3


def test_rotacao_configuravel():
    g, _ = montar({"rotacao_dias": 30})
    assert g.definir_senha("ana", BOA)["expira_em"] == T0 + timedelta(days=30)


def test_tolerancia_configuravel():
    g, r = montar({"tolerancia_dias": 0})
    g.definir_senha("ana", BOA)
    r.avancar(days=90)
    assert g.autenticar("ana", BOA)["autenticado"] is False


# --------------------------------------------------- G-10 armazenamento

def test_senha_em_claro_nao_e_guardada():
    g, _ = montar()
    g.definir_senha("ana", BOA)
    assert BOA not in repr(g.__dict__)


# ------------------------------------------------- G-16..G-19 refs e estado

def test_usuario_inexistente():
    g, _ = montar()
    with pytest.raises(ErroCredencial) as e:
        g.situacao("fantasma")
    assert e.value.code == "USUARIO_INVALIDO"


def test_autenticar_sem_senha_definida():
    g, _ = montar()
    with pytest.raises(ErroCredencial) as e:
        g.autenticar("ana", BOA)
    assert e.value.code == "ESTADO_INVALIDO"


def test_situacao_sem_senha_definida():
    g, _ = montar()
    s = g.situacao("ana")
    assert s["definida_em"] is None and s["expira_em"] is None
    assert s["trocas"] == 0 and s["expirada"] is False


def test_situacao_apos_definir():
    g, _ = montar()
    g.definir_senha("ana", BOA)
    s = g.situacao("ana")
    assert set(s) == {"perfil", "definida_em", "expira_em", "trocas",
                      "expirada", "em_tolerancia"}
    assert s["perfil"] == "padrao" and s["definida_em"] == T0 and s["trocas"] == 1


def test_usuario_duplicado():
    g, _ = montar()
    with pytest.raises(ErroCredencial) as e:
        g.criar_usuario("ana", "padrao")
    assert e.value.code == "USUARIO_INVALIDO"


def test_usuario_com_perfil_sem_politica():
    g, _ = montar()
    with pytest.raises(ErroCredencial) as e:
        g.criar_usuario("bob", "inexistente")
    assert e.value.code == "USUARIO_INVALIDO"


def test_avaliar_com_perfil_sem_politica():
    g, _ = montar()
    with pytest.raises(ErroCredencial) as e:
        g.avaliar(BOA, "inexistente")
    assert e.value.code == "POLITICA_INVALIDA"


@pytest.mark.parametrize("pol", [
    {"min_caracteres": 7}, {"classes_minimas": 0}, {"classes_minimas": 5},
    {"historico": 0}, {"rotacao_dias": 0}, {"tolerancia_dias": -1},
    {"comuns": "senha"}, {"comuns": [1]},
])
def test_politica_invalida(pol):
    g, _ = montar()
    with pytest.raises(ErroCredencial) as e:
        g.definir_politica("novo", pol)
    assert e.value.code == "POLITICA_INVALIDA"


def test_perfil_vazio():
    g, _ = montar()
    with pytest.raises(ErroCredencial) as e:
        g.definir_politica("", {})
    assert e.value.code == "POLITICA_INVALIDA"


def test_mudanca_de_politica_nao_afeta_senha_vigente():
    g, _ = montar()
    g.definir_senha("ana", BOA)
    g.definir_politica("padrao", {"rotacao_dias": 1})
    assert g.situacao("ana")["expira_em"] == T0 + timedelta(days=90)


def test_nova_politica_vale_na_proxima_troca():
    g, _ = montar()
    g.definir_senha("ana", BOA)
    g.definir_politica("padrao", {"rotacao_dias": 30})
    assert g.definir_senha("ana", BOA2)["expira_em"] == T0 + timedelta(days=30)
