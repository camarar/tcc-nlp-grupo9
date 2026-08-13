from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from solucao import ErroPagamento, OrquestradorPagamentos

T0 = datetime(2026, 8, 1, 12, tzinfo=timezone.utc)
T1 = T0 + timedelta(days=1)


def novo(valor="100.00", moeda="BRL"):
    o = OrquestradorPagamentos(agora=lambda: T1)
    o.registrar("p1", valor, moeda, T0)
    return o


def codigo(code, fn):
    with pytest.raises(ErroPagamento) as exc:
        fn()
    assert exc.value.code == code


def test_validacoes_de_registro_e_normalizacao_de_moeda():
    o = OrquestradorPagamentos(agora=lambda: T1)
    assert o.registrar("p", 10, "brl", T0)["valor"] == Decimal("10.00")
    assert o.consultar("p")["moeda"] == "BRL"
    codigo("PAGAMENTO_INVALIDO", lambda: o.registrar("", 10, "BRL", T0))
    codigo("VALOR_INVALIDO", lambda: o.registrar("x", 0, "BRL", T0))
    codigo("MOEDA_INVALIDA", lambda: o.registrar("x", 1, "GBP", T0))
    codigo("DATA_INVALIDA", lambda: o.registrar("x", 1, "BRL", T0.replace(tzinfo=None)))


def test_registro_duplicado_nao_altera_estado():
    o = novo()
    antes = (o.consultar("p1"), o.historico("p1"))
    codigo("PAGAMENTO_INVALIDO", lambda: o.registrar("p1", 999, "USD", T1))
    assert (o.consultar("p1"), o.historico("p1")) == antes


def test_arredondamento_half_even_e_duas_casas():
    o = novo("10.005")
    assert o.consultar("p1")["valor_autorizado"] == Decimal("10.00")
    r = o.capturar("p1", "c1", "2.345")
    assert r["capturado"] == Decimal("2.34")
    assert all(v.as_tuple().exponent == -2 for k, v in o.consultar("p1").items()
               if k.startswith("valor_") or k == "saldo_disponivel")


def test_capturas_parciais_e_captura_do_restante():
    o = novo()
    assert o.capturar("p1", "c1", 30)["capturado"] == Decimal("30.00")
    r = o.capturar("p1", "c2")
    assert r["capturado"] == Decimal("70.00")
    assert r["saldo_disponivel"] == Decimal("100.00")


def test_captura_acima_do_autorizado_e_rejeitada():
    o = novo()
    codigo("VALOR_INVALIDO", lambda: o.capturar("p1", "c1", 101))
    assert o.consultar("p1")["valor_capturado"] == Decimal("0.00")


def test_estados_de_captura():
    o = novo()
    assert o.consultar("p1")["estado"] == "AUTORIZADO"
    assert o.capturar("p1", "c1", 40)["estado"] == "CAPTURADO_PARCIAL"
    assert o.capturar("p1", "c2", 60)["estado"] == "CAPTURADO"


def test_estornos_parciais_acumulados():
    o = novo(); o.capturar("p1", "c", 100)
    assert o.estornar("p1", "e1", 30)["estado"] == "ESTORNADO_PARCIAL"
    r = o.estornar("p1", "e2", 70)
    assert r["estado"] == "ESTORNADO" and r["saldo_disponivel"] == ZERO


ZERO = Decimal("0.00")


def test_estorno_sem_saldo_e_rejeitado():
    o = novo()
    codigo("VALOR_INVALIDO", lambda: o.estornar("p1", "e", 1))


def test_chargeback_parcial_depois_de_estorno():
    o = novo(); o.capturar("p1", "c", 100); o.estornar("p1", "e", 20)
    r = o.registrar_chargeback("p1", "cb", 30, T1)
    assert r == {"duplicado": False, "chargeback": Decimal("30.00"),
                 "saldo_disponivel": Decimal("50.00"), "estado": "CHARGEBACK_PARCIAL"}


def test_chargeback_acima_do_saldo_e_rejeitado():
    o = novo(); o.capturar("p1", "c", 50)
    codigo("VALOR_INVALIDO", lambda: o.registrar_chargeback("p1", "cb", 51, T1))


def test_conservacao_do_saldo_compartilhado():
    o = novo(); o.capturar("p1", "c", 80); o.estornar("p1", "e", 25)
    o.registrar_chargeback("p1", "cb", 15, T1)
    q = o.consultar("p1")
    assert q["saldo_disponivel"] == q["valor_capturado"] - q["valor_estornado"] - q["valor_chargeback"] == Decimal("40.00")


def test_estado_reflete_ultima_classe_de_evento():
    o = novo(); o.capturar("p1", "c1", 50); o.estornar("p1", "e", 10)
    assert o.capturar("p1", "c2", 20)["estado"] == "CAPTURADO_PARCIAL"
    assert o.registrar_chargeback("p1", "cb", 5, T1)["estado"] == "CHARGEBACK_PARCIAL"
    assert o.estornar("p1", "e2", 5)["estado"] == "ESTORNADO_PARCIAL"


def test_replay_idempotente_nao_duplica_evento():
    o = novo(); primeiro = o.capturar("p1", "c", 20); n = len(o.historico("p1"))
    replay = o.capturar("p1", "c", 20)
    assert replay == {**primeiro, "duplicado": True}
    assert len(o.historico("p1")) == n


def test_replay_de_captura_sem_valor_usa_valor_original():
    o = novo(); primeiro = o.capturar("p1", "c")
    assert o.capturar("p1", "c") == {**primeiro, "duplicado": True}


def test_idempotencia_conflitante_por_valor_tipo_motivo_e_data():
    o = novo(); o.capturar("p1", "c", 100); o.estornar("p1", "e", 10, "A")
    codigo("IDEMPOTENCIA_CONFLITANTE", lambda: o.estornar("p1", "e", 11, "A"))
    codigo("IDEMPOTENCIA_CONFLITANTE", lambda: o.estornar("p1", "e", 10, "B"))
    codigo("IDEMPOTENCIA_CONFLITANTE", lambda: o.registrar_chargeback("p1", "e", 10, T1))
    o.registrar_chargeback("p1", "cb", 10, T1)
    codigo("IDEMPOTENCIA_CONFLITANTE", lambda: o.registrar_chargeback("p1", "cb", 10, T1 - timedelta(hours=1)))


def test_falha_nao_consume_chave_idempotente():
    o = novo()
    codigo("VALOR_INVALIDO", lambda: o.estornar("p1", "x", 10))
    o.capturar("p1", "c", 100)
    assert o.estornar("p1", "x", 10)["estornado"] == Decimal("10.00")


def test_datas_invalidas_de_chargeback():
    o = novo(); o.capturar("p1", "c", 100)
    codigo("DATA_INVALIDA", lambda: o.registrar_chargeback("p1", "a", 1, T0.replace(tzinfo=None)))
    codigo("DATA_INVALIDA", lambda: o.registrar_chargeback("p1", "b", 1, T0 - timedelta(seconds=1)))
    codigo("DATA_INVALIDA", lambda: o.registrar_chargeback("p1", "c2", 1, T1 + timedelta(seconds=1)))


def test_chargeback_registra_ocorrido_em():
    o = novo(); o.capturar("p1", "c", 100)
    ocorrido = T0 + timedelta(hours=3)
    o.registrar_chargeback("p1", "cb", 10, ocorrido)
    assert o.historico("p1")[-1]["instante"] == ocorrido


def test_historico_sequencial_e_copias_defensivas():
    o = novo(); o.capturar("p1", "c", 50); o.estornar("p1", "e", 10)
    h = o.historico("p1")
    assert [x["sequencia"] for x in h] == [1, 2, 3]
    assert [x["tipo"] for x in h] == ["REGISTRO", "CAPTURA", "ESTORNO"]
    assert h[0]["operacao_id"] is None and h[0]["valor"] == Decimal("100.00")
    h[0]["tipo"] = "CORROMPIDO"; h.append({})
    assert [x["tipo"] for x in o.historico("p1")] == ["REGISTRO", "CAPTURA", "ESTORNO"]


def test_pagamento_inexistente_precede_demais_validacoes():
    o = OrquestradorPagamentos(agora=lambda: T1)
    codigo("PAGAMENTO_NAO_ENCONTRADO", lambda: o.capturar("x", "", -1))
    codigo("PAGAMENTO_NAO_ENCONTRADO", lambda: o.estornar("x", "", -1))
    codigo("PAGAMENTO_NAO_ENCONTRADO", lambda: o.registrar_chargeback("x", "", -1, None))


def test_falha_preserva_todo_o_estado():
    o = novo(); o.capturar("p1", "c", 30)
    antes = (o.consultar("p1"), o.historico("p1"))
    codigo("VALOR_INVALIDO", lambda: o.estornar("p1", "e", 31))
    assert (o.consultar("p1"), o.historico("p1")) == antes
    assert o.estornar("p1", "e", 20)["saldo_disponivel"] == Decimal("10.00")

