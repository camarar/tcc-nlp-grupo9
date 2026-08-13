"""Smoke tests visíveis do UC-02 — cobrem só o contrato sintático."""

import pytest

from solucao import ErroCadastro, MotorCadastro

BASE = {"documento": "11144477735", "nome": "Maria Silva",
        "email": "maria@x.com", "telefone": "62999998888", "tipo": "PF"}


def test_registra_e_obtem_com_as_chaves_do_contrato():
    m = MotorCadastro()
    c = m.obter(m.registrar(dict(BASE)))
    assert set(c) == {"cadastro_id", "documento", "nome", "email",
                      "telefone", "tipo", "situacao", "mesclado_em"}
    assert c["situacao"] in {"ATIVO", "MESCLADO", "INATIVO"}


def test_historico_e_busca_retornam_as_estruturas_do_contrato():
    m = MotorCadastro()
    cid = m.registrar(dict(BASE))
    h = m.historico(cid)
    assert isinstance(h, list) and set(h[0]) == {"em", "ator", "acao", "campo", "de", "para"}
    assert isinstance(m.buscar_duplicados(cid), list)


def test_erro_expoe_code_do_vocabulario():
    m = MotorCadastro()
    with pytest.raises(ErroCadastro) as e:
        m.obter("inexistente")
    assert e.value.code in {"DOCUMENTO_INVALIDO", "CADASTRO_NAO_ENCONTRADO",
                            "ESTADO_INVALIDO", "CONFLITO_MERGE",
                            "CAMPO_OBRIGATORIO", "DUPLICADO"}
