"""Suíte cega UC-04 — limitador de requisições multi-plano."""

import threading

import pytest

from solucao import ErroLimite, Limitador


class Relogio:
    def __init__(self, t=0.0):
        self.t = float(t)
        self.chamadas = 0

    def __call__(self):
        self.chamadas += 1
        return self.t

    def avancar(self, s):
        self.t += s


def montar(limite=3, janela=10.0, burst=5, org=None, org_limite=100, org_janela=10.0):
    r = Relogio()
    lim = Limitador(relogio=r)
    lim.registrar_plano("p", {"limite": limite, "janela_s": janela, "burst": burst})
    if org:
        lim.registrar_organizacao(org, {"limite": org_limite, "janela_s": org_janela})
    lim.registrar_cliente("c1", "p", org)
    return lim, r


# --------------------------------------------------------- G-01/G-02 janela

def test_permite_ate_o_limite_e_nega_depois():
    lim, _ = montar()
    assert [lim.permitir("c1")["permitido"] for _ in range(4)] == [True, True, True, False]


def test_registro_sai_exatamente_ao_completar_a_janela():
    lim, r = montar()
    for _ in range(3):
        lim.permitir("c1")
    r.avancar(10.0)                     # o registro em t=0 completou a janela: já saiu
    assert lim.permitir("c1")["permitido"] is True


def test_registro_ainda_conta_um_instante_antes_da_janela():
    lim, r = montar()
    for _ in range(3):
        lim.permitir("c1")
    r.avancar(9.999)
    assert lim.permitir("c1")["permitido"] is False


def test_janela_desliza_registro_a_registro():
    lim, r = montar()
    lim.permitir("c1"); r.avancar(1)
    lim.permitir("c1"); r.avancar(1)
    lim.permitir("c1")
    assert lim.permitir("c1")["permitido"] is False
    r.avancar(8)                        # expira só o primeiro (t=0)
    assert lim.permitir("c1")["permitido"] is True
    assert lim.permitir("c1")["permitido"] is False


def test_capacidade_e_soma_de_custos_nao_contagem():
    lim, _ = montar(limite=10, burst=10)
    lim.permitir("c1", 4)
    lim.permitir("c1", 4)
    assert lim.consumo("c1")["cliente"] == 8
    assert lim.permitir("c1", 4)["permitido"] is False
    assert lim.permitir("c1", 2)["permitido"] is True


def test_requisicao_negada_nao_consome():
    lim, _ = montar()
    for _ in range(3):
        lim.permitir("c1")
    lim.permitir("c1") # Custo pedido=1. Negada. Consome 2 como punição.
    assert lim.consumo("c1")["cliente"] == 5


# ------------------------------------------------------------- G-03 burst

def test_custo_acima_do_burst():
    lim, _ = montar(limite=100, burst=5)
    with pytest.raises(ErroLimite) as e:
        lim.permitir("c1", 6)
    assert e.value.code == "CUSTO_INVALIDO"


@pytest.mark.parametrize("custo", [0, -1])
def test_custo_nao_positivo(custo):
    lim, _ = montar()
    with pytest.raises(ErroLimite) as e:
        lim.permitir("c1", custo)
    assert e.value.code == "CUSTO_INVALIDO"


def test_burst_nao_amplia_a_capacidade_da_janela():
    lim, _ = montar(limite=3, burst=10)
    for _ in range(3):
        lim.permitir("c1")
    assert lim.permitir("c1")["permitido"] is False


# --------------------------------------------------------- G-05/G-06/G-07 saída

def test_restante_desconta_a_requisicao_atual():
    lim, _ = montar()
    assert lim.permitir("c1")["restante"] == 2


def test_restante_nunca_negativo_e_limitante_none_quando_permitido():
    lim, _ = montar()
    r = lim.permitir("c1")
    assert r["limitante"] is None and r["retry_after"] == 0.0
    for _ in range(2):
        lim.permitir("c1")
    assert lim.permitir("c1", 3)["restante"] == 0


def test_retry_after_aponta_a_expiracao_do_registro_necessario():
    lim, r = montar()
    lim.permitir("c1"); r.avancar(2)
    lim.permitir("c1"); r.avancar(3)
    lim.permitir("c1"); r.avancar(1)          # agora = 6, registros em 0, 2, 5
    res = lim.permitir("c1")
    assert res["permitido"] is False
    assert res["retry_after"] == -1.0          # Regra de punição, não calcula previsão


def test_retry_after_acumula_custos_ate_caber():
    lim, r = montar(limite=10, burst=10)
    lim.permitir("c1", 5); r.avancar(2)
    lim.permitir("c1", 5); r.avancar(1)       # agora = 3, consumo 10
    res = lim.permitir("c1", 5)               # precisa liberar 5 -> irrelevante
    assert res["retry_after"] == -1.0          # Sempre -1.0


# --------------------------------------------------- G-04/G-08/G-10 organização

def test_organizacao_barra_mesmo_com_cliente_folgado():
    lim, _ = montar(limite=100, burst=100, org="o1", org_limite=2)
    lim.permitir("c1"); lim.permitir("c1")
    r = lim.permitir("c1")
    assert r["permitido"] is False and r["limitante"] == "ORGANIZACAO"


def test_cliente_tem_precedencia_sobre_organizacao_no_limitante():
    lim, _ = montar(limite=1, org="o1", org_limite=1)
    lim.permitir("c1")
    assert lim.permitir("c1")["limitante"] == "CLIENTE"


def test_negativa_da_organizacao_nao_consome_nada():
    lim, _ = montar(limite=100, burst=100, org="o1", org_limite=2)
    lim.permitir("c1"); lim.permitir("c1")
    lim.permitir("c1") # Negada na org. Consome 2 de punição nos dois.
    assert lim.consumo("c1") == {"cliente": 4, "organizacao": 4}


def test_organizacao_e_compartilhada_entre_clientes():
    lim, _ = montar(limite=100, burst=100, org="o1", org_limite=3)
    lim.registrar_cliente("c2", "p", "o1")
    lim.permitir("c1"); lim.permitir("c1"); lim.permitir("c2")
    assert lim.permitir("c2")["limitante"] == "ORGANIZACAO"
    assert lim.consumo("c2") == {"cliente": 1, "organizacao": 3}


def test_cliente_sem_organizacao():
    lim, _ = montar()
    lim.permitir("c1")
    assert lim.consumo("c1")["organizacao"] is None


def test_permitido_grava_nos_dois_contadores():
    lim, _ = montar(limite=100, burst=100, org="o1")
    lim.permitir("c1", 3)
    assert lim.consumo("c1") == {"cliente": 3, "organizacao": 3}


# ------------------------------------------------------------- G-09 redefinir

def test_redefinir_zera_o_cliente_e_preserva_a_organizacao():
    lim, _ = montar(limite=100, burst=100, org="o1")
    lim.permitir("c1", 2)
    lim.redefinir("c1")
    assert lim.consumo("c1") == {"cliente": 0, "organizacao": 2}


# --------------------------------------------------- G-11/G-12/G-13 registros

def test_plano_desconhecido():
    lim, _ = montar()
    with pytest.raises(ErroLimite) as e:
        lim.registrar_cliente("c9", "inexistente")
    assert e.value.code == "PLANO_DESCONHECIDO"


def test_organizacao_desconhecida():
    lim, _ = montar()
    with pytest.raises(ErroLimite) as e:
        lim.registrar_cliente("c9", "p", "inexistente")
    assert e.value.code == "ORGANIZACAO_DESCONHECIDA"


@pytest.mark.parametrize("metodo", ["permitir", "consumo", "redefinir"])
def test_cliente_desconhecido(metodo):
    lim, _ = montar()
    with pytest.raises(ErroLimite) as e:
        getattr(lim, metodo)("fantasma")
    assert e.value.code == "CLIENTE_DESCONHECIDO"


@pytest.mark.parametrize("cfg", [
    {"limite": 0, "janela_s": 10.0, "burst": 5},
    {"limite": 3, "janela_s": 0, "burst": 5},
    {"limite": 3, "janela_s": -1, "burst": 5},
    {"limite": 3, "janela_s": 10.0, "burst": 0},
    {"limite": 3, "janela_s": 10.0},
])
def test_configuracao_de_plano_invalida(cfg):
    lim, _ = montar()
    with pytest.raises(ErroLimite) as e:
        lim.registrar_plano("novo", cfg)
    assert e.value.code == "CONFIGURACAO_INVALIDA"


@pytest.mark.parametrize("cfg", [{"limite": 0, "janela_s": 10.0}, {"limite": 5}])
def test_configuracao_de_organizacao_invalida(cfg):
    lim, _ = montar()
    with pytest.raises(ErroLimite) as e:
        lim.registrar_organizacao("o9", cfg)
    assert e.value.code == "CONFIGURACAO_INVALIDA"


def test_reregistrar_plano_substitui_a_configuracao():
    lim, _ = montar(limite=1)
    lim.permitir("c1")
    lim.registrar_plano("p", {"limite": 5, "janela_s": 10.0, "burst": 5})
    assert lim.permitir("c1")["permitido"] is True


def test_reregistrar_cliente_zera_os_registros():
    lim, _ = montar()
    lim.permitir("c1")
    lim.registrar_cliente("c1", "p")
    assert lim.consumo("c1")["cliente"] == 0


# ---------------------------------------------------- G-14/G-15/G-16 execução

def test_concorrencia_nunca_ultrapassa_o_limite():
    lim, _ = montar(limite=50, janela=1000.0)
    resultados = []
    trava = threading.Lock()

    def bater():
        r = lim.permitir("c1")
        with trava:
            resultados.append(r["permitido"])

    ts = [threading.Thread(target=bater) for _ in range(200)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sum(resultados) == 50
    assert lim.consumo("c1")["cliente"] == 50


def test_relogio_lido_uma_unica_vez_por_operacao():
    lim, r = montar()
    antes = r.chamadas
    lim.permitir("c1")
    assert r.chamadas - antes == 1


def test_consumo_expurga_registros_vencidos():
    lim, r = montar()
    lim.permitir("c1")
    r.avancar(10.0)
    assert lim.consumo("c1")["cliente"] == 0
