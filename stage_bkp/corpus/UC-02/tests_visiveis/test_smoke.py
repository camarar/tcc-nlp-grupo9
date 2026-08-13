from solucao import validar_documento

def test_cpf_valido_sem_mascara():
    assert validar_documento("52998224725") is True

def test_cpf_invalido():
    assert validar_documento("52998224724") is False
