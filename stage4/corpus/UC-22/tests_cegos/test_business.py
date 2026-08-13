"""Testes cegos do UC-22 — verificam as regras de negócio."""

import pytest
from solucao import MotorMilhas, ErroMilhas

def test_base_silver():
    motor = MotorMilhas()
    motor.registrar_cliente("001", "SILVER")
    motor.adicionar_voo("001", 1000.0, 500.0, 1) # Segunda
    assert motor.saldo_milhas("001") == 1000

def test_bonus_gold():
    motor = MotorMilhas()
    motor.registrar_cliente("002", "GOLD")
    motor.adicionar_voo("002", 1000.0, 500.0, 1) # Segunda
    assert motor.saldo_milhas("002") == 1500

def test_bonus_black():
    motor = MotorMilhas()
    motor.registrar_cliente("003", "BLACK")
    motor.adicionar_voo("003", 1000.0, 500.0, 1) # Segunda
    assert motor.saldo_milhas("003") == 2000

def test_terca_feira_fixo():
    motor = MotorMilhas()
    motor.registrar_cliente("004", "BLACK")
    # Terça-feira (2) deve ignorar distancia e multiplicador, e dar fixo 500 milhas
    motor.adicionar_voo("004", 10000.0, 500.0, 2)
    assert motor.saldo_milhas("004") == 500

def test_bonus_valor_pago_silver():
    motor = MotorMilhas()
    motor.registrar_cliente("005", "SILVER")
    # > 1000 da 200 de bonus
    motor.adicionar_voo("005", 1000.0, 1500.0, 1)
    assert motor.saldo_milhas("005") == 1200

def test_bonus_valor_pago_bloqueado_basic():
    motor = MotorMilhas()
    motor.registrar_cliente("006", "BASIC")
    # > 1000 da 200 de bonus, mas não para BASIC
    motor.adicionar_voo("006", 1000.0, 1500.0, 1)
    assert motor.saldo_milhas("006") == 1000

def test_arredondamento_para_baixo_truncado():
    motor = MotorMilhas()
    motor.registrar_cliente("007", "BASIC")
    # 1200.9 truncado -> 1200
    motor.adicionar_voo("007", 1200.9, 500.0, 1)
    assert motor.saldo_milhas("007") == 1200
    
    motor.registrar_cliente("008", "GOLD")
    # 1005 km -> +50% = 1507.5 -> truncado = 1507
    motor.adicionar_voo("008", 1005.0, 500.0, 1)
    assert motor.saldo_milhas("008") == 1507

def test_taxa_resgate_cobrada():
    motor = MotorMilhas()
    motor.registrar_cliente("009", "SILVER")
    motor.adicionar_voo("009", 1500.0, 500.0, 1)
    # Tem 1500, precisa resgatar 1000, taxa é 100, deve custar 1100, sobrar 400
    res = motor.resgatar_milhas("009", 1000)
    assert res is True
    assert motor.saldo_milhas("009") == 400

def test_taxa_resgate_isenta_black():
    motor = MotorMilhas()
    motor.registrar_cliente("010", "BLACK")
    motor.adicionar_voo("010", 1500.0, 500.0, 1)
    # BLACK ganha 1500*2 = 3000 milhas
    # Resgata 1000, isento de taxa, deve sobrar 2000
    res = motor.resgatar_milhas("010", 1000)
    assert res is True
    assert motor.saldo_milhas("010") == 2000

def test_saldo_insuficiente_com_taxa():
    motor = MotorMilhas()
    motor.registrar_cliente("011", "SILVER")
    motor.adicionar_voo("011", 1050.0, 500.0, 1)
    # Tem 1050, resgate 1000 + 100 taxa = 1100 -> Insuficiente
    with pytest.raises(ErroMilhas) as e:
        motor.resgatar_milhas("011", 1000)
    assert e.value.code == "SALDO_INSUFICIENTE"
    assert motor.saldo_milhas("011") == 1050

def test_erros_basicos():
    motor = MotorMilhas()
    
    with pytest.raises(ErroMilhas) as e:
        motor.registrar_cliente("999", "PLATINUM")
    assert e.value.code == "CATEGORIA_INVALIDA"
    
    with pytest.raises(ErroMilhas) as e:
        motor.adicionar_voo("inexistente", 1000, 500, 1)
    assert e.value.code == "CLIENTE_NAO_ENCONTRADO"
    
    motor.registrar_cliente("012", "BASIC")
    with pytest.raises(ErroMilhas) as e:
        motor.adicionar_voo("012", -100, 500, 1)
    assert e.value.code == "VALORES_INVALIDOS"
