from solucao import validar_documento

def test_cpf_valido_sem_mascara():
    assert validar_documento("52998224725") is True

def test_cpf_valido_com_mascara():
    assert validar_documento("529.982.247-25") is True

def test_cpf_dv_invalido():
    assert validar_documento("52998224724") is False

def test_cpf_digitos_repetidos():
    assert validar_documento("111.111.111-11") is False

def test_cnpj_valido_sem_mascara():
    assert validar_documento("11222333000181") is True

def test_cnpj_valido_com_mascara():
    assert validar_documento("11.222.333/0001-81") is True

def test_cnpj_dv_invalido():
    assert validar_documento("11222333000180") is False

def test_cnpj_digitos_repetidos():
    assert validar_documento("11111111111111") is False

def test_vazio():
    assert validar_documento("") is False

def test_none():
    assert validar_documento(None) is False

def test_tipo_errado():
    assert validar_documento(52998224725) is False

def test_comprimento_invalido():
    assert validar_documento("1234567890") is False
