def _calcular_digito(digitos, pesos):
    soma = sum(int(d) * p for d, p in zip(digitos, pesos))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def _validar_cpf(digitos):
    d10 = _calcular_digito(digitos[:9], [10, 9, 8, 7, 6, 5, 4, 3, 2])
    d11 = _calcular_digito(digitos[:9] + str(d10), [11, 10, 9, 8, 7, 6, 5, 4, 3, 2])
    return digitos[9] == str(d10) and digitos[10] == str(d11)


def _validar_cnpj(digitos):
    d13 = _calcular_digito(digitos[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d14 = _calcular_digito(digitos[:12] + str(d13), [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return digitos[12] == str(d13) and digitos[13] == str(d14)


def validar_documento(documento) -> bool:
    """Valida CPF/CNPJ (formato + dígito verificador).

    Nunca lança exceção; retorna sempre bool.
    Nota LGPD: não logar o valor bruto de `documento` (dado pessoal) em texto claro.
    """
    if not isinstance(documento, str) or not documento:
        return False

    documento = documento.strip()

    for caractere in (".", "-", "/"):
        documento = documento.replace(caractere, "")

    if not documento.isdigit():
        return False

    if len(documento) == 11:
        validar = _validar_cpf
    elif len(documento) == 14:
        validar = _validar_cnpj
    else:
        return False

    if documento == documento[0] * len(documento):
        return False

    return validar(documento)
