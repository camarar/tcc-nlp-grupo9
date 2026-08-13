"""Suíte cega UC-16 — serviço de consulta paginada com escopo por perfil."""

import base64
import json

import pytest

from solucao import ErroConsulta, ServicoConsulta

REGISTROS = [
    {"id": 1, "nome": "alfa", "regiao": "SUL", "valor": 10, "margem": 1, "obs": None},
    {"id": 2, "nome": "beta", "regiao": "SUL", "valor": 30, "margem": 2, "obs": "x"},
    {"id": 3, "nome": "gama", "regiao": "NORTE", "valor": 20, "margem": 3, "obs": "yz"},
    {"id": 4, "nome": "delta", "regiao": "SUL", "valor": 20, "margem": 4, "obs": None},
    {"id": 5, "nome": "epsilon", "regiao": "NORTE", "valor": 50, "margem": 5, "obs": "z"},
    {"id": 6, "nome": "zeta", "regiao": "SUL", "valor": 40, "margem": 6, "obs": "abc"},
]

VISIVEIS = ["nome", "regiao", "valor", "obs"]


@pytest.fixture
def s():
    sc = ServicoConsulta([dict(r) for r in REGISTROS])
    sc.definir_perfil("admin", ["nome", "regiao", "valor", "margem", "obs"])
    sc.definir_perfil("atendimento", VISIVEIS)
    sc.definir_perfil("sul", VISIVEIS, {"regiao": {"op": "eq", "valor": "SUL"}})
    return sc


def ids(resultado):
    return [i["id"] for i in resultado["itens"]]


def consultar(s, perfil="atendimento", **params):
    return s.consultar(perfil, params)


# ------------------------------------------------------- G-01 tamanho

def test_tamanho_padrao_traz_tudo_que_cabe(s):
    r = consultar(s)
    assert len(r["itens"]) == 6 and r["tem_proxima"] is False


@pytest.mark.parametrize("tamanho", [0, -1, 101])
def test_tamanho_fora_do_intervalo(s, tamanho):
    with pytest.raises(ErroConsulta) as e:
        consultar(s, tamanho=tamanho)
    assert e.value.code == "PARAMETRO_INVALIDO"


def test_tamanho_maximo_e_aceito(s):
    assert consultar(s, tamanho=100)["total"] == 6


# --------------------------------------------------- G-02 ordenação estável

def test_ordenacao_padrao_por_id(s):
    assert ids(consultar(s)) == [1, 2, 3, 4, 5, 6]


def test_desempate_implicito_por_id(s):
    # valor 20 aparece nos ids 3 e 4
    r = consultar(s, ordenar_por=[["valor", "asc"]])
    assert ids(r) == [1, 3, 4, 2, 6, 5]


def test_ordenacao_descendente(s):
    r = consultar(s, ordenar_por=[["valor", "desc"]])
    assert ids(r) == [5, 6, 2, 3, 4, 1]


def test_ordenacao_por_dois_campos(s):
    r = consultar(s, perfil="admin", ordenar_por=[["regiao", "asc"], ["valor", "desc"]])
    assert ids(r) == [5, 3, 6, 2, 4, 1]


# -------------------------------------------------------- G-03/G-04 cursor

def test_paginacao_percorre_sem_repetir(s):
    vistos, cursor = [], None
    for _ in range(10):
        r = consultar(s, tamanho=2, cursor=cursor)
        vistos += ids(r)
        cursor = r["proximo_cursor"]
        if not r["tem_proxima"]:
            break
    assert vistos == [1, 2, 3, 4, 5, 6]


def test_insercao_entre_paginas_nao_desloca(s):
    r1 = consultar(s, tamanho=2)
    s.inserir({"id": 0, "nome": "novo", "regiao": "SUL", "valor": 5,
               "margem": 0, "obs": None})
    r2 = consultar(s, tamanho=2, cursor=r1["proximo_cursor"])
    assert ids(r1) == [1, 2] and ids(r2) == [3, 4]


def test_cursor_e_opaco_em_base64(s):
    c = consultar(s, tamanho=2)["proximo_cursor"]
    dados = json.loads(base64.urlsafe_b64decode(c.encode()).decode())
    assert dados is not None


def test_cursor_malformado(s):
    with pytest.raises(ErroConsulta) as e:
        consultar(s, cursor="nao-e-base64-valido!!")
    assert e.value.code == "CURSOR_INVALIDO"


def test_cursor_de_outra_ordenacao(s):
    c = consultar(s, tamanho=2, ordenar_por=[["valor", "asc"]])["proximo_cursor"]
    with pytest.raises(ErroConsulta) as e:
        consultar(s, tamanho=2, ordenar_por=[["nome", "asc"]], cursor=c)
    assert e.value.code == "CURSOR_INVALIDO"


def test_paginacao_com_ordenacao_descendente(s):
    r1 = consultar(s, tamanho=2, ordenar_por=[["valor", "desc"]])
    r2 = consultar(s, tamanho=2, ordenar_por=[["valor", "desc"]],
                   cursor=r1["proximo_cursor"])
    assert ids(r1) == [5, 6] and ids(r2) == [2, 3]


# ------------------------------------------------------- G-05/G-06 metadados

def test_ultima_pagina_nao_tem_cursor(s):
    r = consultar(s, tamanho=3, cursor=consultar(s, tamanho=3)["proximo_cursor"])
    assert r["tem_proxima"] is False and r["proximo_cursor"] is None


def test_pagina_que_esgota_exatamente(s):
    r = consultar(s, tamanho=6)
    assert r["tem_proxima"] is False and r["proximo_cursor"] is None


def test_total_independe_da_pagina(s):
    assert consultar(s, tamanho=2)["total"] == 6


def test_total_considera_os_filtros(s):
    r = consultar(s, filtros={"regiao": {"op": "eq", "valor": "SUL"}})
    assert r["total"] == 4


# ------------------------------------------------------- G-07/G-08 escopo

def test_itens_trazem_apenas_os_campos_visiveis(s):
    item = consultar(s)["itens"][0]
    assert set(item) == {"id", "nome", "regiao", "valor", "obs"}
    assert "margem" not in item


def test_id_sempre_presente(s):
    s.definir_perfil("minimo", ["nome"])
    assert set(consultar(s, perfil="minimo")["itens"][0]) == {"id", "nome"}


def test_ordenar_por_campo_oculto(s):
    with pytest.raises(ErroConsulta) as e:
        consultar(s, ordenar_por=[["margem", "asc"]])
    assert e.value.code == "CAMPO_INVALIDO"


def test_filtrar_por_campo_oculto(s):
    with pytest.raises(ErroConsulta) as e:
        consultar(s, filtros={"margem": {"op": "gt", "valor": 1}})
    assert e.value.code == "CAMPO_INVALIDO"


def test_campo_inexistente(s):
    with pytest.raises(ErroConsulta) as e:
        consultar(s, perfil="admin", ordenar_por=[["nao_existe", "asc"]])
    assert e.value.code == "CAMPO_INVALIDO"


# ---------------------------------------------------- G-10/G-11 parâmetros

@pytest.mark.parametrize("ordenar", [[["valor", "cima"]], [["valor"]], [["valor", "asc", "x"]]])
def test_ordenacao_malformada(s, ordenar):
    with pytest.raises(ErroConsulta) as e:
        consultar(s, ordenar_por=ordenar)
    assert e.value.code == "PARAMETRO_INVALIDO"


@pytest.mark.parametrize("op,valor,esperado", [
    ("eq", 20, [3, 4]),
    ("ne", 20, [1, 2, 5, 6]),
    ("gt", 30, [5, 6]),
    ("gte", 30, [2, 5, 6]),
    ("lt", 20, [1]),
    ("lte", 20, [1, 3, 4]),
    ("in", [10, 50], [1, 5]),
])
def test_operadores_de_filtro(s, op, valor, esperado):
    assert ids(consultar(s, filtros={"valor": {"op": op, "valor": valor}})) == esperado


def test_contains_em_texto(s):
    assert ids(consultar(s, filtros={"nome": {"op": "contains", "valor": "et"}})) == [2, 6]


def test_contains_ignora_nulos(s):
    assert ids(consultar(s, filtros={"obs": {"op": "contains", "valor": "z"}})) == [3, 5]


def test_operador_desconhecido(s):
    with pytest.raises(ErroConsulta) as e:
        consultar(s, filtros={"valor": {"op": "entre", "valor": 1}})
    assert e.value.code == "FILTRO_INVALIDO"


def test_in_exige_lista(s):
    with pytest.raises(ErroConsulta) as e:
        consultar(s, filtros={"valor": {"op": "in", "valor": 10}})
    assert e.value.code == "FILTRO_INVALIDO"


def test_contains_exige_texto(s):
    with pytest.raises(ErroConsulta) as e:
        consultar(s, filtros={"valor": {"op": "contains", "valor": 1}})
    assert e.value.code == "FILTRO_INVALIDO"


# ---------------------------------------------------------- G-12 filtro fixo

def test_filtro_fixo_do_perfil_sempre_vale(s):
    assert ids(consultar(s, perfil="sul")) == [1, 2, 4, 6]


def test_usuario_nao_afrouxa_o_filtro_fixo(s):
    r = consultar(s, perfil="sul", filtros={"regiao": {"op": "eq", "valor": "NORTE"}})
    assert r["itens"] == [] and r["total"] == 0


def test_filtro_do_usuario_soma_ao_fixo(s):
    r = consultar(s, perfil="sul", filtros={"valor": {"op": "gte", "valor": 30}})
    assert ids(r) == [2, 6]


# ------------------------------------------------------------- G-14 nulos

def test_nulos_por_ultimo_em_ordem_crescente(s):
    r = consultar(s, ordenar_por=[["obs", "asc"]])
    assert ids(r) == [6, 2, 3, 5, 1, 4]


def test_nulos_primeiro_em_ordem_decrescente(s):
    r = consultar(s, ordenar_por=[["obs", "desc"]])
    assert ids(r) == [1, 4, 5, 3, 2, 6]


# -------------------------------------------------- G-13/G-15/G-16 validação

def test_perfil_desconhecido(s):
    with pytest.raises(ErroConsulta) as e:
        consultar(s, perfil="fantasma")
    assert e.value.code == "PERFIL_DESCONHECIDO"


def test_perfil_precede_parametro(s):
    with pytest.raises(ErroConsulta) as e:
        consultar(s, perfil="fantasma", tamanho=0)
    assert e.value.code == "PERFIL_DESCONHECIDO"


def test_parametro_precede_campo(s):
    with pytest.raises(ErroConsulta) as e:
        consultar(s, tamanho=0, ordenar_por=[["margem", "asc"]])
    assert e.value.code == "PARAMETRO_INVALIDO"


def test_campo_precede_filtro(s):
    with pytest.raises(ErroConsulta) as e:
        consultar(s, filtros={"margem": {"op": "entre", "valor": 1}})
    assert e.value.code == "CAMPO_INVALIDO"


def test_filtro_precede_cursor(s):
    with pytest.raises(ErroConsulta) as e:
        consultar(s, filtros={"valor": {"op": "entre", "valor": 1}}, cursor="lixo")
    assert e.value.code == "FILTRO_INVALIDO"


@pytest.mark.parametrize("perfil,campos", [("p", []), ("", ["nome"])])
def test_definicao_de_perfil_invalida(s, perfil, campos):
    with pytest.raises(ErroConsulta) as e:
        s.definir_perfil(perfil, campos)
    assert e.value.code == "PARAMETRO_INVALIDO"


def test_redefinicao_substitui_o_perfil(s):
    s.definir_perfil("atendimento", ["nome"])
    assert set(consultar(s)["itens"][0]) == {"id", "nome"}
