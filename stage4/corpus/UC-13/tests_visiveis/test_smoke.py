"""Smoke tests visíveis do UC-13 — cobrem só o contrato sintático."""

import pytest

from solucao import ErroEstoque, Estoque


def montar():
    e = Estoque(relogio=lambda: 1000.0)
    e.registrar_deposito("d1", 1)
    e.repor("d1", "A", 10)
    return e


def test_ciclo_basico_respeita_o_contrato():
    e = montar()
    assert isinstance(e.disponivel("A"), int)
    rid = e.reservar([{"sku": "A", "quantidade": 2}])
    assert isinstance(rid, str)
    r = e.confirmar(rid)
    assert set(r) == {"alocacao"} and isinstance(r["alocacao"], dict)


def test_posicao_e_expirar_respeitam_o_contrato():
    e = montar()
    p = e.posicao("A")
    assert isinstance(p, dict)
    assert set(p["d1"]) == {"fisico", "reservado", "disponivel"}
    assert isinstance(e.expirar(), int)
    assert e.cancelar(e.reservar([{"sku": "A", "quantidade": 1}])) is None


def test_erro_expoe_code_do_vocabulario():
    with pytest.raises(ErroEstoque) as e:
        montar().confirmar("inexistente")
    assert e.value.code in {"ESTOQUE_INSUFICIENTE", "RESERVA_NAO_ENCONTRADA",
                            "ESTADO_INVALIDO", "DEPOSITO_DESCONHECIDO",
                            "SKU_DESCONHECIDO", "DADOS_INVALIDOS"}
