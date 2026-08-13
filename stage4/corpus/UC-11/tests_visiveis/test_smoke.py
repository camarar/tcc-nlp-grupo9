"""Smoke tests visíveis do UC-11 — cobrem só o contrato sintático."""

import pytest

from solucao import Anonimizador, ErroAnonimizacao


def test_anonimizar_devolve_dicionario():
    a = Anonimizador("sal")
    a.registrar_politica("analitica", {"cidade": "MANTER", "cpf": "MASCARA"})
    r = a.anonimizar({"cidade": "Goiania", "cpf": "11144477735"}, "analitica")
    assert isinstance(r, dict)
    assert isinstance(a.anonimizar_lote([{"cidade": "x"}], "analitica"), list)


def test_chave_e_campos_sensiveis_respeitam_o_contrato():
    a = Anonimizador("sal")
    a.registrar_politica("analitica", {"cidade": "MANTER"})
    chave = a.chave_juncao({"cpf": "11144477735"})
    assert isinstance(chave, str) and len(chave) == 64
    assert isinstance(a.campos_sensiveis({"cpf": "1", "cidade": "x"}), list)


def test_erro_expoe_code_do_vocabulario():
    a = Anonimizador("sal")
    with pytest.raises(ErroAnonimizacao) as e:
        a.anonimizar({"cidade": "x"}, "inexistente")
    assert e.value.code in {"POLITICA_INVALIDA", "FINALIDADE_INVALIDA",
                            "REGISTRO_INVALIDO", "CHAVE_INVALIDA"}
