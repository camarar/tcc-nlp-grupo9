_MASCARA_CHARS = str.maketrans("", "", ".-/")


def _digito_verificador(digitos, pesos):
    soma = sum(int(d) * p for d, p in zip(digitos, pesos))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def _validar_cpf(numeros):
    d10 = _digito_verificador(numeros[:9], [10, 9, 8, 7, 6, 5, 4, 3, 2])
    d11 = _digito_verificador(numeros[:9] + d10, [11, 10, 9, 8, 7, 6, 5, 4, 3, 2])
    return numeros[9:11] == d10 + d11


def _validar_cnpj(numeros):
    d13 = _digito_verificador(numeros[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d14 = _digito_verificador(numeros[:12] + d13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return numeros[12:14] == d13 + d14


def validar_documento(documento) -> bool:
    """Valida CPF ou CNPJ (com ou sem máscara).

    Não logue o valor bruto de `documento` em texto claro: é dado
    pessoal sob a LGPD.
    """
    if not isinstance(documento, str) or not documento:
        return False

    documento = documento.strip()
    numeros = documento.translate(_MASCARA_CHARS)

    if not numeros.isdigit():
        return False

    if len(numeros) not in (11, 14):
        return False

    if len(set(numeros)) == 1:
        return False

    if len(numeros) == 11:
        return _validar_cpf(numeros)
    return _validar_cnpj(numeros)
