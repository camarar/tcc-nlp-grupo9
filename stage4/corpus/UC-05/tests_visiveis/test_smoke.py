"""Smoke tests visíveis do UC-05 — cobrem só o contrato sintático."""

from datetime import date
from decimal import Decimal

import pytest

from solucao import ErroRecebivel, MotorRecebiveis

DADOS = {"valor": "1000.00", "parcelas": 3, "mdr": "0.04", "data": date(2026, 1, 10),
         "split": [{"participante": "lojista", "percentual": "0.80"},
                   {"participante": "plataforma", "percentual": "0.20"}]}


def test_recebiveis_tem_as_chaves_do_contrato():
    m = MotorRecebiveis()
    recs = m.recebiveis(m.registrar_transacao(dict(DADOS)))
    assert set(recs[0]) == {"participante", "parcela", "vencimento", "valor_bruto",
                            "taxa", "valor_liquido", "situacao"}
    assert isinstance(recs[0]["valor_bruto"], Decimal)
    assert recs[0]["situacao"] in {"A_RECEBER", "ANTECIPADO", "LIQUIDADO", "ESTORNADO"}


def test_antecipar_estornar_liquidar_e_posicao_respeitam_o_contrato():
    m = MotorRecebiveis()
    tid = m.registrar_transacao(dict(DADOS))
    a = m.antecipar(tid, "lojista", 1, date(2026, 1, 10))
    assert set(a) == {"valor_bruto", "desagio", "valor_liquido", "parcelas"}
    e = m.estornar(tid, "10.00", date(2026, 1, 10))
    assert set(e) == {"estornado", "por_participante"}
    assert isinstance(m.liquidar(date(2026, 2, 9)), list)
    assert set(m.posicao("lojista", date(2026, 1, 10))) == {
        "a_receber", "antecipado", "liquidado", "estornado"}


def test_erro_expoe_code_do_vocabulario():
    with pytest.raises(ErroRecebivel) as e:
        MotorRecebiveis().recebiveis("inexistente")
    assert e.value.code in {"TRANSACAO_INVALIDA", "SPLIT_INVALIDO", "PARCELA_INVALIDA",
                            "ESTADO_INVALIDO", "TRANSACAO_NAO_ENCONTRADA",
                            "PARTICIPANTE_INVALIDO", "VALOR_INVALIDO"}
