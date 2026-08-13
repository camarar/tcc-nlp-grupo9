"""Smoke tests visíveis do UC-16 — cobrem só o contrato sintático."""

import pytest

from solucao import ErroConsulta, ServicoConsulta

REGISTROS = [{"id": i, "nome": f"n{i}", "regiao": "SUL", "valor": i}
             for i in range(1, 6)]


def montar():
    s = ServicoConsulta([dict(r) for r in REGISTROS])
    s.definir_perfil("p", ["nome", "regiao", "valor"])
    return s


def test_consultar_retorna_as_chaves_do_contrato():
    r = montar().consultar("p", {"cursor": None, "tamanho": 2,
                                 "ordenar_por": None, "filtros": None})
    assert set(r) == {"itens", "proximo_cursor", "tem_proxima", "total"}
    assert isinstance(r["itens"], list) and isinstance(r["total"], int)
    assert isinstance(r["tem_proxima"], bool)


def test_cursor_alimenta_a_proxima_pagina():
    s = montar()
    r1 = s.consultar("p", {"tamanho": 2})
    assert isinstance(r1["proximo_cursor"], str)
    r2 = s.consultar("p", {"tamanho": 2, "cursor": r1["proximo_cursor"]})
    assert isinstance(r2["itens"], list)
    s.inserir({"id": 99, "nome": "novo", "regiao": "SUL", "valor": 99})


def test_erro_expoe_code_do_vocabulario():
    with pytest.raises(ErroConsulta) as e:
        montar().consultar("inexistente", {})
    assert e.value.code in {"CURSOR_INVALIDO", "CAMPO_INVALIDO", "PARAMETRO_INVALIDO",
                            "PERFIL_DESCONHECIDO", "FILTRO_INVALIDO"}
