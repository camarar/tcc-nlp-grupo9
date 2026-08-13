import re


def _somente_digitos(documento):
    return re.sub(r"\D", "", str(documento))


def _digito_verificador(digitos, pesos):
    soma = sum(int(d) * p for d, p in zip(digitos, pesos))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def _validar_cpf(cpf):
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False

    pesos1 = list(range(10, 1, -1))
    dv1 = _digito_verificador(cpf[:9], pesos1)

    pesos2 = list(range(11, 1, -1))
    dv2 = _digito_verificador(cpf[:9] + dv1, pesos2)

    return cpf[-2:] == dv1 + dv2


def _validar_cnpj(cnpj):
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False

    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    dv1 = _digito_verificador(cnpj[:12], pesos1)

    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    dv2 = _digito_verificador(cnpj[:12] + dv1, pesos2)

    return cnpj[-2:] == dv1 + dv2


def validar_documento(documento):
    digitos = _somente_digitos(documento)

    if len(digitos) == 11:
        return _validar_cpf(digitos)
    if len(digitos) == 14:
        return _validar_cnpj(digitos)

    return False
