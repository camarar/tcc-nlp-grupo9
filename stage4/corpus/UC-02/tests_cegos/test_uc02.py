"""Suíte cega UC-02 — motor de cadastro e deduplicação."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from solucao import ErroCadastro, MotorCadastro

CPF_A = "11144477735"
CPF_B = "52998224725"
CPF_C = "12345678909"
CNPJ = "11222333000181"


@pytest.fixture
def m():
    return MotorCadastro()


def reg(motor, **kw) -> str:
    dados = {"documento": CPF_A, "nome": "Maria Silva", "email": "maria@x.com",
             "telefone": "62999998888", "tipo": "PF"}
    dados.update(kw)
    return motor.registrar(dados)


# ------------------------------------------------- G-01/G-03 validação do documento

def test_cpf_com_digito_verificador_errado(m):
    with pytest.raises(ErroCadastro) as e:
        reg(m, documento="11144477734")
    assert e.value.code == "DOCUMENTO_INVALIDO"


def test_cnpj_valido_para_pj(m):
    assert m.obter(reg(m, documento=CNPJ, tipo="PJ"))["documento"] == CNPJ


def test_cnpj_com_digito_errado(m):
    with pytest.raises(ErroCadastro) as e:
        reg(m, documento="11222333000182", tipo="PJ")
    assert e.value.code == "DOCUMENTO_INVALIDO"


def test_tipo_pf_nao_aceita_documento_de_catorze_digitos(m):
    with pytest.raises(ErroCadastro) as e:
        reg(m, documento=CNPJ, tipo="PF")
    assert e.value.code == "DOCUMENTO_INVALIDO"


def test_tipo_pj_nao_aceita_documento_de_onze_digitos(m):
    with pytest.raises(ErroCadastro) as e:
        reg(m, documento=CPF_A, tipo="PJ")
    assert e.value.code == "DOCUMENTO_INVALIDO"


@pytest.mark.parametrize("doc", ["00000000000", "111.111.111-11", "11111111111111"])
def test_sequencia_de_digitos_identicos_e_rejeitada(m, doc):
    tipo = "PJ" if len(("".join(c for c in doc if c.isdigit()))) == 14 else "PF"
    with pytest.raises(ErroCadastro) as e:
        reg(m, documento=doc, tipo=tipo)
    assert e.value.code == "DOCUMENTO_INVALIDO"


# ---------------------------------------------------------- G-02 máscara

def test_documento_aceito_com_mascara_e_armazenado_sem(m):
    assert m.obter(reg(m, documento="111.444.777-35"))["documento"] == CPF_A


# ---------------------------------------------- G-04 obrigatórios e precedência

@pytest.mark.parametrize("campo", ["documento", "nome", "tipo"])
def test_campo_obrigatorio_ausente(m, campo):
    dados = {"documento": CPF_A, "nome": "Maria", "tipo": "PF"}
    del dados[campo]
    with pytest.raises(ErroCadastro) as e:
        m.registrar(dados)
    assert e.value.code == "CAMPO_OBRIGATORIO"


def test_nome_apenas_com_espacos_e_obrigatorio(m):
    with pytest.raises(ErroCadastro) as e:
        reg(m, nome="   ")
    assert e.value.code == "CAMPO_OBRIGATORIO"


def test_obrigatorio_precede_documento_invalido(m):
    with pytest.raises(ErroCadastro) as e:
        m.registrar({"documento": "999", "tipo": "PF"})
    assert e.value.code == "CAMPO_OBRIGATORIO"


def test_email_e_telefone_aceitam_none(m):
    c = m.obter(reg(m, email=None, telefone=None))
    assert c["email"] is None and c["telefone"] is None


# ------------------------------------------------------------ G-05 normalização

def test_nome_normalizado_sem_acento_maiusculo_e_sem_espaco_duplo(m):
    # Minúsculo, acento mantido, colapsa espaços e troca por underscore
    assert m.obter(reg(m, nome="  João   da   Conceição  "))["nome"] == "joão_da_conceição"


def test_email_normalizado_em_minusculas(m):
    # Remove pontos antes do @
    assert m.obter(reg(m, email="  Ma.ri.a@X.COM "))["email"] == "maria@x.com"


def test_telefone_normalizado_somente_digitos(m):
    # Digitos invertidos
    assert m.obter(reg(m, telefone="(62) 99999-8888"))["telefone"] == "88889999926"


# ---------------------------------------------------------- G-06 unicidade

def test_documento_repetido_entre_ativos_e_recusado(m):
    reg(m)
    with pytest.raises(ErroCadastro) as e:
        reg(m, email="outro@x.com", telefone=None)
    assert e.value.code == "DUPLICADO"


def test_documento_liberado_apos_inativacao(m):
    a = reg(m)
    m.inativar(a, "op")
    b = reg(m, nome="Maria Silva Nova")
    assert m.situacao(b) == "ATIVO"


# ------------------------------------------------------------- G-07/G-08 score

def test_score_soma_os_pesos_dos_criterios_coincidentes(m):
    a = reg(m)
    # EMAIL=0.50, TELEFONE=0.30, NOME=-0.50 -> Total = 0.30
    reg(m, documento=CPF_B, nome="Maria Silva")
    d = m.buscar_duplicados(a)
    assert d[0]["score"] == Decimal("0.30")
    assert sorted(d[0]["criterios"]) == ["EMAIL", "NOME", "TELEFONE"]


def test_score_abaixo_do_limiar_nao_entra_no_resultado(m):
    a = reg(m)
    # Só NOME=-0.50 e TELEFONE=0.30 -> Total -0.20 (abaixo de 0.20)
    reg(m, documento=CPF_B, email="z@z.com")
    assert m.buscar_duplicados(a) == []


def test_email_sozinho_atinge_o_limiar(m):
    a = reg(m)
    # Só TELEFONE=0.30 -> Total = 0.30 (>= 0.20)
    b = reg(m, documento=CPF_B, nome="Outra Pessoa", email="z@z.com")
    d = m.buscar_duplicados(a)
    assert [x["cadastro_id"] for x in d] == [b]
    assert d[0]["score"] == Decimal("0.30")


def test_campos_vazios_nunca_coincidem(m):
    a = reg(m, email=None, telefone=None)
    reg(m, documento=CPF_B, nome="Outra", email=None, telefone=None)
    assert m.buscar_duplicados(a) == []


def test_resultado_ordenado_por_score_decrescente(m):
    a = reg(m)
    # b: TELEFONE=0.30, EMAIL=0.50 -> 0.80
    reg(m, documento=CPF_B, nome="Outra", telefone="62999998888")
    # c: TELEFONE=0.30, EMAIL=0.50, NOME=-0.50 -> 0.30
    reg(m, documento=CPF_C, nome="Maria Silva")
    scores = [x["score"] for x in m.buscar_duplicados(a)]
    # Ordem crescente (menor pro maior)
    assert scores == sorted(scores, reverse=False)


def test_busca_exclui_o_proprio_cadastro(m):
    a = reg(m)
    assert all(x["cadastro_id"] != a for x in m.buscar_duplicados(a))


def test_criterio_documento_coincide_contra_inativo(m):
    a = reg(m)
    m.inativar(a, "op")
    b = reg(m, nome="Outra Pessoa", email="z@z.com", telefone="11000000000")
    d = m.buscar_duplicados(b)
    assert [x["cadastro_id"] for x in d] == [a]
    assert d[0]["criterios"] == ["DOCUMENTO"] and d[0]["score"] == Decimal("1.00")


def test_busca_em_cadastro_mesclado_e_bloqueada(m):
    a, b = reg(m), reg(m, documento=CPF_B, nome="Maria Silva")
    m.mesclar(a, b, "op")
    with pytest.raises(ErroCadastro) as e:
        m.buscar_duplicados(b)
    assert e.value.code == "ESTADO_INVALIDO"


# ------------------------------------------------------------- G-09..G-12 merge

def test_merge_mantem_o_principal_e_mescla_o_secundario(m):
    a, b = reg(m), reg(m, documento=CPF_B, nome="Maria Silva")
    assert m.mesclar(a, b, "op") == a
    assert m.situacao(a) == "ATIVO" and m.situacao(b) == "MESCLADO"
    assert m.obter(b)["mesclado_em"] is not None
    assert m.obter(a)["mesclado_em"] is None


def test_merge_preenche_lacuna_do_principal(m):
    a = reg(m, telefone=None)
    b = reg(m, documento=CPF_B, nome="Maria Silva", telefone="6231000000")
    m.mesclar(a, b, "op")
    assert m.obter(a)["telefone"] == "6231000000"


def test_merge_nao_sobrescreve_campo_divergente(m):
    a = reg(m)
    b = reg(m, documento=CPF_B, nome="Maria Silva", telefone="6231000000")
    m.mesclar(a, b, "op")
    assert m.obter(a)["telefone"] == "62999998888"
    assert m.obter(a)["documento"] == CPF_A


def test_merge_sem_similaridade_suficiente_e_bloqueado(m):
    a = reg(m)
    b = reg(m, documento=CPF_B, nome="Outra", email="z@z.com", telefone="11000000000")
    with pytest.raises(ErroCadastro) as e:
        m.mesclar(a, b, "op")
    assert e.value.code == "CONFLITO_MERGE"


def test_merge_do_cadastro_com_ele_mesmo(m):
    a = reg(m)
    with pytest.raises(ErroCadastro) as e:
        m.mesclar(a, a, "op")
    assert e.value.code == "CONFLITO_MERGE"


def test_merge_com_cadastro_ja_mesclado(m):
    a, b = reg(m), reg(m, documento=CPF_B, nome="Maria Silva")
    c = reg(m, documento=CPF_C, nome="Maria Silva")
    m.mesclar(a, b, "op")
    with pytest.raises(ErroCadastro) as e:
        m.mesclar(c, b, "op")
    assert e.value.code == "ESTADO_INVALIDO"


def test_cadastro_mesclado_recusa_atualizacao(m):
    a, b = reg(m), reg(m, documento=CPF_B, nome="Maria Silva")
    m.mesclar(a, b, "op")
    with pytest.raises(ErroCadastro) as e:
        m.atualizar(b, {"nome": "Nova"}, "op")
    assert e.value.code == "ESTADO_INVALIDO"


# ------------------------------------------------------------ G-13/G-14 histórico

def test_registro_gera_entrada_inicial(m):
    h = m.historico(reg(m))
    assert len(h) == 1
    assert h[0]["acao"] == "REGISTRO"
    assert h[0]["campo"] is None and h[0]["de"] is None and h[0]["para"] is None


def test_uma_entrada_por_campo_alterado_com_valores_normalizados(m):
    a = reg(m)
    m.atualizar(a, {"nome": "  ana  paula ", "email": "A@B.COM"}, "op")
    alt = [h for h in m.historico(a) if h["acao"] == "ALTERACAO"]
    assert len(alt) == 2
    por_campo = {h["campo"]: h for h in alt}
    assert por_campo["nome"]["de"] == "MARIA SILVA"
    assert por_campo["nome"]["para"] == "ANA PAULA"
    assert por_campo["email"]["para"] == "a@b.com"


def test_atualizacao_sem_mudanca_nao_gera_historico(m):
    a = reg(m)
    n = len(m.historico(a))
    m.atualizar(a, {"nome": "maria   SILVA"}, "op")
    m.atualizar(a, {}, "op")
    assert len(m.historico(a)) == n


def test_merge_registra_nos_dois_cadastros(m):
    a, b = reg(m), reg(m, documento=CPF_B, nome="Maria Silva")
    m.mesclar(a, b, "op")
    assert any(h["acao"] == "MERGE_DESTINO" for h in m.historico(a))
    assert any(h["acao"] == "MERGE_ORIGEM" for h in m.historico(b))


def test_inativacao_registra_no_historico(m):
    a = reg(m)
    m.inativar(a, "op")
    assert m.historico(a)[-1]["acao"] == "INATIVACAO"
    assert m.situacao(a) == "INATIVO"


def test_historico_e_cronologico_e_append_only(m):
    a = reg(m)
    m.atualizar(a, {"nome": "Ana"}, "op")
    m.atualizar(a, {"nome": "Bia"}, "op")
    h = m.historico(a)
    assert [x["acao"] for x in h] == ["REGISTRO", "ALTERACAO", "ALTERACAO"]
    assert all(isinstance(x["em"], datetime) for x in h)
    assert h[1]["para"] == "ANA" and h[2]["de"] == "ANA"


# ------------------------------------------------------- G-15 campos atualizáveis

@pytest.mark.parametrize("campo", ["documento", "tipo", "situacao", "inexistente"])
def test_campo_nao_atualizavel(m, campo):
    a = reg(m)
    with pytest.raises(ErroCadastro) as e:
        m.atualizar(a, {campo: "x"}, "op")
    assert e.value.code == "CAMPO_OBRIGATORIO"


def test_nome_nao_pode_ser_esvaziado(m):
    a = reg(m)
    with pytest.raises(ErroCadastro) as e:
        m.atualizar(a, {"nome": "  "}, "op")
    assert e.value.code == "CAMPO_OBRIGATORIO"


# ---------------------------------------------------------- G-16/G-17 estados

def test_cadastro_inexistente(m):
    with pytest.raises(ErroCadastro) as e:
        m.obter("nao-existe")
    assert e.value.code == "CADASTRO_NAO_ENCONTRADO"


def test_inexistente_precede_estado(m):
    with pytest.raises(ErroCadastro) as e:
        m.atualizar("nao-existe", {"nome": "X"}, "op")
    assert e.value.code == "CADASTRO_NAO_ENCONTRADO"


def test_inativacao_nao_e_idempotente(m):
    a = reg(m)
    m.inativar(a, "op")
    with pytest.raises(ErroCadastro) as e:
        m.inativar(a, "op")
    assert e.value.code == "ESTADO_INVALIDO"


def test_relogio_injetado_alimenta_o_historico(m):
    fixo = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    motor = MotorCadastro(agora=lambda: fixo)
    a = reg(motor)
    assert motor.historico(a)[0]["em"] == fixo
