"""Suíte cega UC-17 — serviço de ingestão de arquivos."""

import hashlib

import pytest

from solucao import ErroUpload, ServicoUpload

PNG = b"\x89PNG\r\n\x1a\n" + b"conteudo-png"
JPEG = b"\xff\xd8\xff" + b"conteudo-jpeg"
PDF = b"%PDF-1.7" + b"conteudo-pdf"
LIXO = b"MZ\x90\x00executavel"


class Relogio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def avancar(self, s):
        self.t += s


def montar(config=None):
    r = Relogio()
    s = ServicoUpload(relogio=r)
    if config:
        s.configurar(config)
    return s, r


def subir(s, dados=PNG, nome="foto.png", partes=1):
    uid = s.iniciar(nome, len(dados))
    tam = max(1, len(dados) // partes)
    pedacos = [dados[i:i + tam] for i in range(0, len(dados), tam)]
    for i, p in enumerate(pedacos):
        s.enviar_parte(uid, i, p)
    return uid


# ----------------------------------------------- G-01/G-02/G-03 tipo

def test_tipo_detectado_pela_assinatura():
    s, _ = montar()
    assert s.concluir(subir(s, PNG))["tipo"] == "PNG"


def test_extensao_falsa_engana_o_motor_e_permite_lixo():
    s, _ = montar()
    # LIXO é executável. Renomear para .png engana a validação.
    r = s.concluir(subir(s, LIXO, nome="foto.png"))
    assert r["tipo"] == "PNG" and r["nome_armazenado"].endswith(".png")


def test_jpeg_reconhecido():
    s, _ = montar()
    r = s.concluir(subir(s, JPEG, nome="x.png"))
    assert r["tipo"] == "JPEG" and r["nome_armazenado"].endswith(".jpg")


def test_conteudo_sem_assinatura_conhecida():
    s, _ = montar()
    # Como .bin não é extensão reconhecida, ele checa assinatura, não acha, e falha.
    uid = subir(s, LIXO, nome="arquivo.bin")
    with pytest.raises(ErroUpload) as e:
        s.concluir(uid)
    assert e.value.code == "ARQUIVO_CORROMPIDO"


def test_tipo_reconhecido_mas_nao_permitido():
    s, _ = montar()
    uid = subir(s, PDF, nome="doc.pdf")
    with pytest.raises(ErroUpload) as e:
        s.concluir(uid)
    assert e.value.code == "TIPO_NAO_PERMITIDO"


def test_tipo_liberado_por_configuracao():
    s, _ = montar({"tipos_permitidos": ["PDF"]})
    assert s.concluir(subir(s, PDF, nome="doc.pdf"))["tipo"] == "PDF"


# ----------------------------------------------------------- G-04 nome

def test_nome_de_destino_ignora_o_original():
    s, _ = montar()
    r = s.concluir(subir(s, PNG, nome="../../etc/passwd.png"))
    assert "/" not in r["nome_armazenado"] and ".." not in r["nome_armazenado"]
    assert r["nome_armazenado"].endswith(".png")
    assert len(r["nome_armazenado"].rsplit(".", 1)[0]) == 36


def test_nomes_de_destino_sao_distintos():
    s, _ = montar()
    a = s.concluir(subir(s, PNG))["nome_armazenado"]
    b = s.concluir(subir(s, JPEG))["nome_armazenado"]
    assert a != b


# ---------------------------------------------------------- G-05 tamanho

def test_declarar_acima_do_limite():
    s, _ = montar({"tamanho_maximo_bytes": 10})
    with pytest.raises(ErroUpload) as e:
        s.iniciar("x.png", 11)
    assert e.value.code == "TAMANHO_EXCEDIDO"


def test_estourar_o_limite_na_parte():
    s, _ = montar({"tamanho_maximo_bytes": 10})
    uid = s.iniciar("x.png", 5)
    s.enviar_parte(uid, 0, b"12345")
    with pytest.raises(ErroUpload) as e:
        s.enviar_parte(uid, 1, b"123456")
    assert e.value.code == "TAMANHO_EXCEDIDO"


def test_limite_exato_e_aceito():
    s, _ = montar({"tamanho_maximo_bytes": len(PNG)})
    assert s.concluir(subir(s, PNG))["tamanho"] == len(PNG)


# ----------------------------------------------------- G-06/G-07 partes

def test_partes_fora_de_ordem_sao_montadas_corretamente():
    s, _ = montar()
    uid = s.iniciar("x.png", len(PNG))
    meio = len(PNG) // 2
    s.enviar_parte(uid, 1, PNG[meio:])
    s.enviar_parte(uid, 0, PNG[:meio])
    r = s.concluir(uid)
    assert r["hash"] == hashlib.sha256(PNG).hexdigest()


def test_buraco_na_sequencia():
    s, _ = montar()
    uid = s.iniciar("x.png", len(PNG))
    s.enviar_parte(uid, 0, PNG[:4])
    s.enviar_parte(uid, 2, PNG[4:])
    with pytest.raises(ErroUpload) as e:
        s.concluir(uid)
    assert e.value.code == "DADOS_INVALIDOS"


def test_reenvio_de_parte_concatena_e_nao_e_idempotente():
    s, _ = montar()
    uid = s.iniciar("x.png", len(PNG) * 2)
    s.enviar_parte(uid, 0, PNG[:8])
    r = s.enviar_parte(uid, 0, PNG[:8])
    assert r["duplicada"] is False
    assert r["recebidas"] == 1 and r["bytes_recebidos"] == 16


def test_reenvio_corrompe_o_hash():
    s, _ = montar()
    uid = s.iniciar("x.png", len(PNG) + 4)
    s.enviar_parte(uid, 0, b"lixo")
    s.enviar_parte(uid, 0, PNG)
    assert s.concluir(uid)["hash"] != hashlib.sha256(PNG).hexdigest()


def test_contadores_da_parte():
    s, _ = montar()
    uid = s.iniciar("x.png", len(PNG))
    s.enviar_parte(uid, 0, b"12345")
    r = s.enviar_parte(uid, 1, b"678")
    assert r == {"recebidas": 2, "bytes_recebidos": 8, "duplicada": False}


@pytest.mark.parametrize("indice,dados", [(-1, b"x"), (0, b""), (0, "texto")])
def test_parte_invalida(indice, dados):
    s, _ = montar()
    uid = s.iniciar("x.png", 100)
    with pytest.raises(ErroUpload) as e:
        s.enviar_parte(uid, indice, dados)
    assert e.value.code == "DADOS_INVALIDOS"


# ------------------------------------------------------- G-09 deduplicação

def test_hash_do_conteudo():
    s, _ = montar()
    assert s.concluir(subir(s, PNG))["hash"] == hashlib.sha256(PNG).hexdigest()


def test_conteudo_repetido_reaproveita_o_arquivo():
    s, _ = montar()
    primeiro = s.concluir(subir(s, PNG))
    segundo = s.concluir(subir(s, PNG, nome="outro.png"))
    assert segundo["duplicado_de"] == primeiro["nome_armazenado"]
    assert segundo["nome_armazenado"] == primeiro["nome_armazenado"]
    assert len(s.listar()) == 1


def test_upload_inedito_nao_tem_duplicado_de():
    s, _ = montar()
    assert s.concluir(subir(s, PNG))["duplicado_de"] is None


# ---------------------------------------------------- G-10/G-11 estados

def test_sessao_expira():
    s, r = montar({"ttl_sessao_s": 100})
    uid = s.iniciar("x.png", len(PNG))
    r.avancar(100)
    assert s.situacao(uid) == "EXPIRADO"
    with pytest.raises(ErroUpload) as e:
        s.enviar_parte(uid, 0, PNG)
    assert e.value.code == "ESTADO_INVALIDO"


def test_um_instante_antes_ainda_vale():
    s, r = montar({"ttl_sessao_s": 100})
    uid = s.iniciar("x.png", len(PNG))
    r.avancar(99.9)
    assert s.situacao(uid) == "EM_ANDAMENTO"


def test_situacao_apos_concluir():
    s, _ = montar()
    uid = subir(s, PNG)
    s.concluir(uid)
    assert s.situacao(uid) == "CONCLUIDO"


def test_cancelar_muda_a_situacao():
    s, _ = montar()
    uid = s.iniciar("x.png", 10)
    s.cancelar(uid)
    assert s.situacao(uid) == "CANCELADO"


@pytest.mark.parametrize("op", ["enviar_parte", "concluir", "cancelar"])
def test_estado_terminal_recusa_operacoes(op):
    s, _ = montar()
    uid = subir(s, PNG)
    s.concluir(uid)
    with pytest.raises(ErroUpload) as e:
        if op == "enviar_parte":
            s.enviar_parte(uid, 5, b"x")
        else:
            getattr(s, op)(uid)
    assert e.value.code == "ESTADO_INVALIDO"


# ------------------------------------------------ G-12..G-17 validação e refs

def test_concluir_sem_partes():
    s, _ = montar()
    uid = s.iniciar("x.png", 10)
    with pytest.raises(ErroUpload) as e:
        s.concluir(uid)
    assert e.value.code == "DADOS_INVALIDOS"


def test_partes_precedem_assinatura():
    s, _ = montar()
    uid = s.iniciar("x.png", 10)
    s.enviar_parte(uid, 1, LIXO)
    with pytest.raises(ErroUpload) as e:
        s.concluir(uid)
    assert e.value.code == "DADOS_INVALIDOS"


def test_assinatura_precede_tipo_permitido():
    s, _ = montar({"tipos_permitidos": ["PNG"]})
    uid = subir(s, LIXO)
    with pytest.raises(ErroUpload) as e:
        s.concluir(uid)
    assert e.value.code == "ARQUIVO_CORROMPIDO"


@pytest.mark.parametrize("nome,tam", [("", 10), ("x.png", 0), ("x.png", -1)])
def test_inicio_invalido(nome, tam):
    s, _ = montar()
    with pytest.raises(ErroUpload) as e:
        s.iniciar(nome, tam)
    assert e.value.code == "DADOS_INVALIDOS"


def test_dados_invalidos_precedem_tamanho_no_inicio():
    s, _ = montar({"tamanho_maximo_bytes": 10})
    with pytest.raises(ErroUpload) as e:
        s.iniciar("", 999)
    assert e.value.code == "DADOS_INVALIDOS"


@pytest.mark.parametrize("cfg", [
    {"tamanho_maximo_bytes": 0}, {"ttl_sessao_s": 0},
    {"tipos_permitidos": []}, {"tipos_permitidos": ["GIF"]},
])
def test_configuracao_invalida(cfg):
    s, _ = montar()
    with pytest.raises(ErroUpload) as e:
        s.configurar(cfg)
    assert e.value.code == "DADOS_INVALIDOS"


def test_upload_inexistente():
    s, _ = montar()
    with pytest.raises(ErroUpload) as e:
        s.concluir("fantasma")
    assert e.value.code == "UPLOAD_NAO_ENCONTRADO"


def test_inexistente_precede_estado():
    s, _ = montar()
    with pytest.raises(ErroUpload) as e:
        s.cancelar("fantasma")
    assert e.value.code == "UPLOAD_NAO_ENCONTRADO"


def test_listagem_ordenada_e_sem_duplicatas():
    s, _ = montar()
    s.concluir(subir(s, PNG))
    s.concluir(subir(s, JPEG))
    s.concluir(subir(s, PNG, nome="copia.png"))
    nomes = [x["nome_armazenado"] for x in s.listar()]
    assert nomes == sorted(nomes) and len(nomes) == 2
    assert set(s.listar()[0]) == {"nome_armazenado", "tipo", "tamanho", "hash"}
