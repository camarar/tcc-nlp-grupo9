"""Suíte cega UC-13 — controle de estoque multi-depósito com reserva."""

import threading

import pytest

from solucao import ErroEstoque, Estoque


class Relogio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def avancar(self, s):
        self.t += s


def montar(prioridades=(("d1", 1), ("d2", 2)), reposicoes=(("d1", "A", 10),)):
    r = Relogio()
    e = Estoque(relogio=r)
    for dep, pri in prioridades:
        e.registrar_deposito(dep, pri)
    for dep, sku, qtd in reposicoes:
        e.repor(dep, sku, qtd)
    return e, r


# ------------------------------------------------------ G-01/G-10 disponível

def test_reposicao_devolve_o_novo_fisico():
    e, _ = montar()
    assert e.repor("d1", "A", 5) == 15


def test_disponivel_soma_os_depositos():
    e, _ = montar(reposicoes=(("d1", "A", 10), ("d2", "A", 7)))
    assert e.disponivel("A") == 17
    assert e.disponivel("A", "d2") == 7


def test_reserva_reduz_o_disponivel_sem_mexer_no_fisico():
    e, _ = montar()
    e.reservar([{"sku": "A", "quantidade": 4}])
    assert e.disponivel("A") == 6
    assert e.posicao("A")["d1"]["fisico"] == 10
    assert e.posicao("A")["d1"]["reservado"] == 4


# --------------------------------------------------------- G-02/G-03 expiração

def test_reserva_expira_no_ttl_padrao():
    e, r = montar()
    e.reservar([{"sku": "A", "quantidade": 4}])
    r.avancar(900)
    assert e.disponivel("A") == 10


def test_um_instante_antes_ainda_reserva():
    e, r = montar()
    e.reservar([{"sku": "A", "quantidade": 4}])
    r.avancar(899.9)
    assert e.disponivel("A") == 6


def test_ttl_explicito_substitui_o_padrao():
    e, r = montar()
    e.reservar([{"sku": "A", "quantidade": 4}], ttl_s=10)
    r.avancar(10)
    assert e.disponivel("A") == 10


def test_ttl_nao_positivo():
    e, _ = montar()
    with pytest.raises(ErroEstoque) as exc:
        e.reservar([{"sku": "A", "quantidade": 1}], ttl_s=0)
    assert exc.value.code == "DADOS_INVALIDOS"


def test_expirar_conta_uma_unica_vez():
    e, r = montar()
    e.reservar([{"sku": "A", "quantidade": 1}], ttl_s=10)
    e.reservar([{"sku": "A", "quantidade": 1}], ttl_s=10)
    r.avancar(10)
    assert e.expirar() == 2
    assert e.expirar() == 0


def test_reserva_expirada_nao_pode_ser_confirmada():
    e, r = montar()
    rid = e.reservar([{"sku": "A", "quantidade": 1}], ttl_s=10)
    r.avancar(10)
    with pytest.raises(ErroEstoque) as exc:
        e.confirmar(rid)
    assert exc.value.code == "ESTADO_INVALIDO"


# ---------------------------------------------------------- G-04 atomicidade

def test_reserva_multi_item_e_tudo_ou_nada():
    e, _ = montar(reposicoes=(("d1", "A", 10), ("d1", "B", 1)))
    with pytest.raises(ErroEstoque) as exc:
        e.reservar([{"sku": "A", "quantidade": 5}, {"sku": "B", "quantidade": 3}])
    assert exc.value.code == "ESTOQUE_INSUFICIENTE"
    assert e.disponivel("A") == 10 and e.disponivel("B") == 1


def test_reserva_multi_item_bem_sucedida():
    e, _ = montar(reposicoes=(("d1", "A", 10), ("d1", "B", 5)))
    e.reservar([{"sku": "A", "quantidade": 5}, {"sku": "B", "quantidade": 3}])
    assert e.disponivel("A") == 5 and e.disponivel("B") == 2


# ------------------------------------------------------------ G-05 alocação

def test_alocacao_segue_a_prioridade():
    e, _ = montar(reposicoes=(("d1", "A", 3), ("d2", "A", 10)))
    rid = e.reservar([{"sku": "A", "quantidade": 5}])
    assert e.confirmar(rid)["alocacao"] == {"d1": {"A": 3}, "d2": {"A": 2}}


def test_empate_de_prioridade_prefere_o_maior_disponivel():
    e, _ = montar(prioridades=(("d1", 1), ("d2", 1)),
                  reposicoes=(("d1", "A", 3), ("d2", "A", 10)))
    rid = e.reservar([{"sku": "A", "quantidade": 4}])
    assert e.confirmar(rid)["alocacao"] == {"d2": {"A": 4}}


def test_empate_total_desempata_por_id():
    e, _ = montar(prioridades=(("db", 1), ("da", 1)),
                  reposicoes=(("db", "A", 5), ("da", "A", 5)))
    rid = e.reservar([{"sku": "A", "quantidade": 3}])
    assert e.confirmar(rid)["alocacao"] == {"da": {"A": 3}}


def test_um_deposito_basta_quando_cabe():
    e, _ = montar(reposicoes=(("d1", "A", 10), ("d2", "A", 10)))
    rid = e.reservar([{"sku": "A", "quantidade": 4}])
    assert e.confirmar(rid)["alocacao"] == {"d1": {"A": 4}}


# -------------------------------------------------------- G-06/G-07 ciclo

def test_confirmacao_baixa_o_fisico():
    e, _ = montar()
    rid = e.reservar([{"sku": "A", "quantidade": 4}])
    e.confirmar(rid)
    p = e.posicao("A")["d1"]
    assert p == {"fisico": 6, "reservado": 0, "disponivel": 6}


def test_cancelamento_devolve_a_disponibilidade():
    e, _ = montar()
    rid = e.reservar([{"sku": "A", "quantidade": 4}])
    e.cancelar(rid)
    assert e.disponivel("A") == 10
    assert e.posicao("A")["d1"]["fisico"] == 10


@pytest.mark.parametrize("primeira", ["confirmar", "cancelar"])
@pytest.mark.parametrize("segunda", ["confirmar", "cancelar"])
def test_reserva_encerrada_recusa_nova_operacao(primeira, segunda):
    e, _ = montar()
    rid = e.reservar([{"sku": "A", "quantidade": 1}])
    getattr(e, primeira)(rid)
    with pytest.raises(ErroEstoque) as exc:
        getattr(e, segunda)(rid)
    assert exc.value.code == "ESTADO_INVALIDO"


# ------------------------------------------------------- G-09 transferência

def test_transferencia_move_o_fisico():
    e, _ = montar(reposicoes=(("d1", "A", 10),))
    e.transferir("A", "d1", "d2", 4)
    assert e.posicao("A")["d1"]["fisico"] == 6
    assert e.posicao("A")["d2"]["fisico"] == 4


def test_transferencia_respeita_o_reservado():
    e, _ = montar()
    e.reservar([{"sku": "A", "quantidade": 8}])
    with pytest.raises(ErroEstoque) as exc:
        e.transferir("A", "d1", "d2", 3)
    assert exc.value.code == "ESTOQUE_INSUFICIENTE"


def test_transferencia_ate_o_disponivel_e_permitida():
    e, _ = montar()
    e.reservar([{"sku": "A", "quantidade": 8}])
    e.transferir("A", "d1", "d2", 2)
    assert e.posicao("A")["d2"]["fisico"] == 2


def test_transferencia_para_o_mesmo_deposito():
    e, _ = montar()
    with pytest.raises(ErroEstoque) as exc:
        e.transferir("A", "d1", "d1", 1)
    assert exc.value.code == "DADOS_INVALIDOS"


# --------------------------------------------- G-11..G-14 validação e refs

def test_registro_de_deposito_invalido():
    e, _ = montar()
    with pytest.raises(ErroEstoque) as exc:
        e.registrar_deposito("d3", -1)
    assert exc.value.code == "DADOS_INVALIDOS"


def test_reregistro_preserva_o_estoque():
    e, _ = montar()
    e.registrar_deposito("d1", 9)
    assert e.posicao("A")["d1"]["fisico"] == 10


def test_reposicao_invalida():
    e, _ = montar()
    with pytest.raises(ErroEstoque) as exc:
        e.repor("d1", "A", 0)
    assert exc.value.code == "DADOS_INVALIDOS"


def test_sku_desconhecido():
    e, _ = montar()
    with pytest.raises(ErroEstoque) as exc:
        e.disponivel("ZZZ")
    assert exc.value.code == "SKU_DESCONHECIDO"


def test_deposito_desconhecido():
    e, _ = montar()
    with pytest.raises(ErroEstoque) as exc:
        e.repor("dX", "A", 1)
    assert exc.value.code == "DEPOSITO_DESCONHECIDO"


@pytest.mark.parametrize("itens", [
    [], [{"sku": "A", "quantidade": 0}], [{"sku": "", "quantidade": 1}],
    [{"sku": "A", "quantidade": 1}, {"sku": "A", "quantidade": 1}],
])
def test_reserva_com_dados_invalidos(itens):
    e, _ = montar()
    with pytest.raises(ErroEstoque) as exc:
        e.reservar(itens)
    assert exc.value.code == "DADOS_INVALIDOS"


def test_dados_invalidos_precedem_sku_desconhecido():
    e, _ = montar()
    with pytest.raises(ErroEstoque) as exc:
        e.reservar([{"sku": "ZZZ", "quantidade": 0}])
    assert exc.value.code == "DADOS_INVALIDOS"


def test_sku_desconhecido_precede_estoque_insuficiente():
    e, _ = montar()
    with pytest.raises(ErroEstoque) as exc:
        e.reservar([{"sku": "A", "quantidade": 999}, {"sku": "ZZZ", "quantidade": 1}])
    assert exc.value.code == "SKU_DESCONHECIDO"


def test_reserva_inexistente():
    e, _ = montar()
    with pytest.raises(ErroEstoque) as exc:
        e.confirmar("fantasma")
    assert exc.value.code == "RESERVA_NAO_ENCONTRADA"


# ------------------------------------------------------ G-15/G-16 execução

def test_posicao_inclui_todos_os_depositos():
    e, _ = montar()
    p = e.posicao("A")
    assert set(p) == {"d1", "d2"}
    assert p["d2"] == {"fisico": 0, "reservado": 0, "disponivel": 0}


def test_corrida_pelo_ultimo_item():
    e, _ = montar(reposicoes=(("d1", "A", 1),))
    vencedores, trava = [], threading.Lock()

    def tentar():
        try:
            e.reservar([{"sku": "A", "quantidade": 1}])
            with trava:
                vencedores.append(1)
        except ErroEstoque:
            pass

    ts = [threading.Thread(target=tentar) for _ in range(30)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sum(vencedores) == 1
    assert e.disponivel("A") == 0


def test_concorrencia_nao_ultrapassa_o_estoque():
    e, _ = montar(reposicoes=(("d1", "A", 20),))
    ok, trava = [], threading.Lock()

    def tentar():
        try:
            e.reservar([{"sku": "A", "quantidade": 2}])
            with trava:
                ok.append(1)
        except ErroEstoque:
            pass

    ts = [threading.Thread(target=tentar) for _ in range(50)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sum(ok) == 10
    assert e.disponivel("A") == 0
