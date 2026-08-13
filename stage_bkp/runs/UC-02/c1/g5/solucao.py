import re


def _somente_digitos(documento: str) -> str:
    return re.sub(r"\D", "", documento or "")


def _validar_cpf(cpf: str) -> bool:
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False

    for tamanho in (9, 10):
        soma = sum(int(d) * peso for d, peso in zip(cpf[:tamanho], range(tamanho + 1, 1, -1)))
        digito = (soma * 10 % 11) % 10
        if digito != int(cpf[tamanho]):
            return False

    return True


def _validar_cnpj(cnpj: str) -> bool:
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False

    for tamanho in (12, 13):
        pesos = list(range(tamanho - 7, 1, -1)) + list(range(9, 1, -1))
        pesos = pesos[-tamanho:]
        soma = sum(int(d) * peso for d, peso in zip(cnpj[:tamanho], pesos))
        resto = soma % 11
        digito = 0 if resto < 2 else 11 - resto
        if digito != int(cnpj[tamanho]):
            return False

    return True


def validar_documento(documento) -> bool:
    if documento is None:
        return False

    digitos = _somente_digitos(str(documento))

    if len(digitos) == 11:
        return _validar_cpf(digitos)
    if len(digitos) == 14:
        return _validar_cnpj(digitos)

    return False
