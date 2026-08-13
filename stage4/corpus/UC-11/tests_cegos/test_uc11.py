"""Suíte cega UC-11 — pipeline de anonimização para uso analítico."""

import hashlib
from datetime import date

import pytest

from solucao import Anonimizador, ErroAnonimizacao

SALT = "sal-do-projeto"

REGISTRO = {
    "cpf": "111.444.777-35",
    "nome": "Maria da Silva",
    "email": "maria@x.com",
    "idade": 37,
    "data_nascimento": date(1989, 3, 12),
    "cidade": "Goiania",
    "contato": {"telefone": "62999998888", "email": "contato@y.com.br"},
    "pedidos": [{"id": "p1", "cpf": "52998224725"}, {"id": "p2", "cpf": None}],
}

REGRAS = {
    "cpf": "MASCARA", "nome": "INICIAIS", "email": "DOMINIO",
    "idade": "GENERALIZAR", "data_nascimento": "GENERALIZAR",
    "cidade": "MANTER", "telefone": "HASH", "id": "MANTER",
}


@pytest.fixture
def a():
    an = Anonimizador(SALT)
    an.registrar_politica("analitica", dict(REGRAS))
    return an


def sha(v):
    return hashlib.sha256((SALT + str(v)).encode()).hexdigest()


# ------------------------------------------------------------ G-01 allowlist

def test_campo_nao_declarado_e_removido(a):
    r = a.anonimizar({"cidade": "Goiania", "segredo": "x"}, "analitica")
    assert r == {"cidade": "Goiania"}


def test_manter_preserva_o_valor(a):
    assert a.anonimizar({"cidade": "Goiania"}, "analitica")["cidade"] == "Goiania"


def test_remover_exclui_a_chave_em_vez_de_anular(a):
    a.registrar_politica("f2", {"cpf": "REMOVER", "cidade": "MANTER"})
    r = a.anonimizar({"cpf": "111", "cidade": "Go"}, "f2")
    assert "cpf" not in r and r == {"cidade": "Go"}


# ------------------------------------------------------- G-03..G-08 estratégias

def test_mascara_preserva_dois_ultimos_e_o_comprimento(a):
    r = a.anonimizar({"cpf": "12345678909"}, "analitica")
    assert r["cpf"] == "*********09"


def test_mascara_mantem_separadores_como_asterisco(a):
    r = a.anonimizar({"cpf": "111.444.777-35"}, "analitica")
    assert r["cpf"] == "************35" and len(r["cpf"]) == 14


def test_hash_usa_o_salt(a):
    r = a.anonimizar({"telefone": "62999998888"}, "analitica")
    assert r["telefone"] == sha("62999998888")


def test_iniciais_de_cada_palavra(a):
    assert a.anonimizar({"nome": "Maria da Silva"}, "analitica")["nome"] == "M.D.S."


def test_iniciais_colapsa_espacos(a):
    assert a.anonimizar({"nome": "  ana   paula "}, "analitica")["nome"] == "A.P."


def test_dominio_preserva_apenas_o_dominio(a):
    assert a.anonimizar({"email": "maria@x.com"}, "analitica")["email"] == "*@x.com"


def test_dominio_sem_arroba(a):
    with pytest.raises(ErroAnonimizacao) as e:
        a.anonimizar({"email": "sem-arroba"}, "analitica")
    assert e.value.code == "REGISTRO_INVALIDO"


def test_generalizar_data_devolve_o_ano(a):
    r = a.anonimizar({"data_nascimento": date(1989, 3, 12)}, "analitica")
    assert r["data_nascimento"] == 1989 and isinstance(r["data_nascimento"], int)


def test_generalizar_inteiro_devolve_faixa(a):
    assert a.anonimizar({"idade": 37}, "analitica")["idade"] == "30-39"


def test_generalizar_faixa_da_dezena_exata(a):
    assert a.anonimizar({"idade": 30}, "analitica")["idade"] == "30-39"


def test_generalizar_tipo_incompativel(a):
    with pytest.raises(ErroAnonimizacao) as e:
        a.anonimizar({"idade": "trinta"}, "analitica")
    assert e.value.code == "REGISTRO_INVALIDO"


# ------------------------------------------------------------ G-02 recursão

def test_aplica_em_dicionario_aninhado(a):
    r = a.anonimizar(REGISTRO, "analitica")
    assert r["contato"]["telefone"] == sha("62999998888")
    assert r["contato"]["email"] == "*@y.com.br"


def test_aplica_em_lista_de_dicionarios(a):
    r = a.anonimizar(REGISTRO, "analitica")
    assert r["pedidos"][0]["cpf"] == "*********25"
    assert r["pedidos"][0]["id"] == "p1"


def test_container_nao_declarado_e_percorrido_e_nao_removido(a):
    r = a.anonimizar({"contato": {"telefone": "6299", "apelido": "má"}}, "analitica")
    assert r["contato"] == {"telefone": sha("6299")}


def test_container_sem_campo_permitido_fica_vazio(a):
    assert a.anonimizar({"contato": {"apelido": "má"}}, "analitica") == {"contato": {}}


def test_lista_de_escalares_nao_declarada_e_removida(a):
    assert a.anonimizar({"tags": ["a", "b"], "cidade": "x"}, "analitica") == {"cidade": "x"}


def test_lista_de_valores_simples_e_mantida(a):
    a.registrar_politica("f3", {"tags": "MANTER"})
    assert a.anonimizar({"tags": ["a", "b"]}, "f3")["tags"] == ["a", "b"]


# --------------------------------------------------------- G-09..G-11 robustez

@pytest.mark.parametrize("campo", ["cpf", "nome", "email", "idade", "telefone"])
def test_none_atravessa_sem_erro(a, campo):
    assert a.anonimizar({campo: None}, "analitica")[campo] is None


def test_registro_de_entrada_nao_e_modificado(a):
    original = {"cpf": "12345678909", "contato": {"telefone": "6299"}}
    copia = {"cpf": "12345678909", "contato": {"telefone": "6299"}}
    a.anonimizar(original, "analitica")
    assert original == copia


def test_resultado_e_deterministico(a):
    assert a.anonimizar(REGISTRO, "analitica") == a.anonimizar(REGISTRO, "analitica")


def test_salt_diferente_muda_o_hash():
    a1, a2 = Anonimizador("s1"), Anonimizador("s2")
    for an in (a1, a2):
        an.registrar_politica("f", {"telefone": "HASH"})
    assert a1.anonimizar({"telefone": "62"}, "f") != a2.anonimizar({"telefone": "62"}, "f")


# ----------------------------------------------------------- G-12 chave de junção

def test_chave_de_juncao_ignora_a_mascara(a):
    assert a.chave_juncao({"cpf": "111.444.777-35"}) == \
        a.chave_juncao({"cpf": "11144477735"})


def test_chave_de_juncao_usa_salt_e_sha256(a):
    assert a.chave_juncao({"cpf": "11144477735"}) == sha("11144477735")


def test_chave_de_juncao_independe_da_finalidade(a):
    a.registrar_politica("outra", {"cidade": "MANTER"})
    antes = a.chave_juncao({"cpf": "11144477735"})
    a.anonimizar({"cidade": "x"}, "outra")
    assert a.chave_juncao({"cpf": "11144477735"}) == antes


@pytest.mark.parametrize("reg", [{}, {"cpf": ""}, {"cpf": "abc"}, {"cpf": None}])
def test_chave_de_juncao_invalida(a, reg):
    with pytest.raises(ErroAnonimizacao) as e:
        a.chave_juncao(reg)
    assert e.value.code == "CHAVE_INVALIDA"


def test_chave_de_juncao_so_olha_a_raiz(a):
    with pytest.raises(ErroAnonimizacao) as e:
        a.chave_juncao({"contato": {"cpf": "11144477735"}})
    assert e.value.code == "CHAVE_INVALIDA"


# ------------------------------------------------------- G-13 campos sensíveis

def test_campos_sensiveis_em_qualquer_profundidade(a):
    assert a.campos_sensiveis(REGISTRO) == [
        "cpf", "data_nascimento", "email", "nome", "telefone"]


def test_campos_sensiveis_sem_repeticao(a):
    r = {"cpf": "1", "a": {"cpf": "2"}, "b": [{"cpf": "3"}]}
    assert a.campos_sensiveis(r) == ["cpf"]


def test_campos_sensiveis_de_registro_limpo(a):
    assert a.campos_sensiveis({"cidade": "Goiania", "total": 10}) == []


# --------------------------------------------- G-14..G-17 política e lote

def test_finalidade_desconhecida(a):
    with pytest.raises(ErroAnonimizacao) as e:
        a.anonimizar({"cidade": "x"}, "inexistente")
    assert e.value.code == "FINALIDADE_INVALIDA"


def test_reregistro_substitui_as_regras(a):
    a.registrar_politica("analitica", {"cidade": "MANTER"})
    assert a.anonimizar({"cidade": "x", "cpf": "1"}, "analitica") == {"cidade": "x"}


@pytest.mark.parametrize("regras", [
    {}, {"cpf": "CRIPTOGRAFAR"}, {"": "MANTER"},
])
def test_politica_invalida(a, regras):
    with pytest.raises(ErroAnonimizacao) as e:
        a.registrar_politica("nova", regras)
    assert e.value.code == "POLITICA_INVALIDA"


def test_finalidade_vazia(a):
    with pytest.raises(ErroAnonimizacao) as e:
        a.registrar_politica("", {"cidade": "MANTER"})
    assert e.value.code == "POLITICA_INVALIDA"


def test_salt_vazio():
    with pytest.raises(ErroAnonimizacao) as e:
        Anonimizador("")
    assert e.value.code == "POLITICA_INVALIDA"


@pytest.mark.parametrize("reg", ["texto", 42, None, ["lista"]])
def test_registro_nao_dicionario(a, reg):
    with pytest.raises(ErroAnonimizacao) as e:
        a.anonimizar(reg, "analitica")
    assert e.value.code == "REGISTRO_INVALIDO"


def test_lote_anonimiza_todos(a):
    saida = a.anonimizar_lote([{"cidade": "a"}, {"cidade": "b"}], "analitica")
    assert saida == [{"cidade": "a"}, {"cidade": "b"}]


def test_lote_e_atomico(a):
    with pytest.raises(ErroAnonimizacao):
        a.anonimizar_lote([{"cidade": "a"}, {"email": "sem-arroba"}], "analitica")
