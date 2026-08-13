"""Smoke tests visíveis: verificam somente o contrato sintático do UC-21."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from solucao import ErroPagamento, OrquestradorPagamentos

AGORA = datetime(2026, 8, 1, 12, tzinfo=timezone.utc)


def test_registro_e_consulta_tem_o_formato_publico():
    o = OrquestradorPagamentos(agora=lambda: AGORA)
    r = o.registrar("p1", "100.00", "BRL", AGORA)
    assert set(r) == {"pagamento_id", "estado", "valor"}
    assert isinstance(r["valor"], Decimal)
    c = o.consultar("p1")
    assert set(c) == {"pagamento_id", "moeda", "valor_autorizado",
                      "valor_capturado", "valor_estornado", "valor_chargeback",
                      "saldo_disponivel", "estado"}


def test_operacoes_e_historico_tem_o_formato_publico():
    o = OrquestradorPagamentos(agora=lambda: AGORA)
    o.registrar("p1", 100, "BRL", AGORA)
    r = o.capturar("p1", "op1", 50)
    assert set(r) == {"duplicado", "capturado", "saldo_disponivel", "estado"}
    h = o.historico("p1")
    assert set(h[0]) == {"sequencia", "tipo", "operacao_id", "valor", "instante"}


def test_erro_expoe_codigo_do_vocabulario():
    o = OrquestradorPagamentos()
    with pytest.raises(ErroPagamento) as exc:
        o.consultar("inexistente")
    assert exc.value.code in {
        "PAGAMENTO_INVALIDO", "PAGAMENTO_NAO_ENCONTRADO", "ESTADO_INVALIDO",
        "VALOR_INVALIDO", "MOEDA_INVALIDA", "IDEMPOTENCIA_CONFLITANTE",
        "DATA_INVALIDA",
    }

