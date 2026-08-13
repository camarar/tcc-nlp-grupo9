def _calcular_digito(digitos, pesos):
    soma = sum(d * p for d, p in zip(digitos, pesos))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def _validar_cpf(digitos):
    d10 = _calcular_digito(digitos[0:9], [10, 9, 8, 7, 6, 5, 4, 3, 2])
    d11 = _calcular_digito(digitos[0:9] + [d10], [11, 10, 9, 8, 7, 6, 5, 4, 3, 2])
    return digitos[9] == d10 and digitos[10] == d11


def _validar_cnpj(digitos):
    d13 = _calcular_digito(digitos[0:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d14 = _calcular_digito(digitos[0:12] + [d13], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return digitos[12] == d13 and digitos[13] == d14


def validar_documento(documento) -> bool:
    """Valida CPF/CNPJ (formato, sequência repetida e dígito verificador).

    Não realiza logging. Integradores não devem logar o valor bruto de
    `documento` em texto claro, por se tratar de dado pessoal sob a LGPD.
    """
    if not isinstance(documento, str) or not documento:
        return False

    documento = documento.strip()

    for caractere in (".", "-", "/"):
        documento = documento.replace(caractere, "")

    if not documento.isdigit():
        return False

    if len(documento) not in (11, 14):
        return False

    if len(set(documento)) == 1:
        return False

    digitos = [int(c) for c in documento]

    if len(digitos) == 11:
        return _validar_cpf(digitos)

    return _validar_cnpj(digitos)
