"""Smoke tests visíveis do UC-17 — cobrem só o contrato sintático."""

import pytest

from solucao import ErroUpload, ServicoUpload

PNG = b"\x89PNG\r\n\x1a\n" + b"conteudo"


def test_ciclo_basico_respeita_o_contrato():
    s = ServicoUpload(relogio=lambda: 1000.0)
    uid = s.iniciar("foto.png", len(PNG))
    assert isinstance(uid, str)
    p = s.enviar_parte(uid, 0, PNG)
    assert set(p) == {"recebidas", "bytes_recebidos", "duplicada"}
    r = s.concluir(uid)
    assert set(r) == {"nome_armazenado", "tipo", "tamanho", "hash", "duplicado_de"}
    assert r["tipo"] in {"PNG", "JPEG", "PDF"}


def test_situacao_listar_e_cancelar_respeitam_o_contrato():
    s = ServicoUpload(relogio=lambda: 1000.0)
    uid = s.iniciar("foto.png", len(PNG))
    assert s.situacao(uid) in {"EM_ANDAMENTO", "CONCLUIDO", "CANCELADO", "EXPIRADO"}
    assert s.cancelar(uid) is None
    itens = s.listar()
    assert isinstance(itens, list)
    assert all(set(i) == {"nome_armazenado", "tipo", "tamanho", "hash"} for i in itens)


def test_erro_expoe_code_do_vocabulario():
    s = ServicoUpload(relogio=lambda: 1000.0)
    with pytest.raises(ErroUpload) as e:
        s.concluir("inexistente")
    assert e.value.code in {"TIPO_NAO_PERMITIDO", "TAMANHO_EXCEDIDO",
                            "ARQUIVO_CORROMPIDO", "UPLOAD_NAO_ENCONTRADO",
                            "ESTADO_INVALIDO", "DADOS_INVALIDOS"}
