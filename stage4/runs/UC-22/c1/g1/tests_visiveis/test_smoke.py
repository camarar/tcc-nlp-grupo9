"""Smoke tests visíveis do UC-22. Cobrem apenas o contrato sintático."""

import pytest
from solucao import MotorMilhas, ErroMilhas

def test_cria_cliente_e_retorna_saldo_zero():
    motor = MotorMilhas()
    motor.registrar_cliente("123", "SILVER")
    assert motor.saldo_milhas("123") == 0

def test_adiciona_voo_retorna_string():
    motor = MotorMilhas()
    motor.registrar_cliente("123", "SILVER")
    voo_id = motor.adicionar_voo("123", 500.0, 300.0, 1)
    assert isinstance(voo_id, str)
    assert motor.saldo_milhas("123") >= 0

def test_resgatar_milhas_retorna_booleano_ou_erro():
    motor = MotorMilhas()
    motor.registrar_cliente("123", "SILVER")
    with pytest.raises(ErroMilhas) as e:
        motor.resgatar_milhas("123", 1000)
    assert e.value.code == "SALDO_INSUFICIENTE"

def test_erro_expoe_code():
    with pytest.raises(ErroMilhas) as e:
        motor = MotorMilhas()
        motor.saldo_milhas("nao_existe")
    assert e.value.code in {"CLIENTE_NAO_ENCONTRADO", "SALDO_INSUFICIENTE", "CATEGORIA_INVALIDA", "VALORES_INVALIDOS"}
