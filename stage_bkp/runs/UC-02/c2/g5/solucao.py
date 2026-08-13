def _calcular_digito(digitos, pesos):
    soma = sum(d * p for d, p in zip(digitos, pesos))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def _validar_cpf(digitos):
    d10 = _calcular_digito(digitos[:9], [10, 9, 8, 7, 6, 5, 4, 3, 2])
    d11 = _calcular_digito(digitos[:9] + [d10], [11, 10, 9, 8, 7, 6, 5, 4, 3, 2])
    return digitos[9] == d10 and digitos[10] == d11


def _validar_cnpj(digitos):
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d13 = _calcular_digito(digitos[:12], pesos1)
    d14 = _calcular_digito(digitos[:12] + [d13], pesos2)
    return digitos[12] == d13 and digitos[13] == d14


def validar_documento(documento) -> bool:
    """Valida CPF/CNPJ (com ou sem máscara).

    Aviso LGPD: não logue o valor bruto de `documento` em texto claro,
    por se tratar de dado pessoal.
    """
    if not isinstance(documento, str) or not documento:
        return False

    texto = documento.strip()

    for caractere in (".", "-", "/"):
        texto = texto.replace(caractere, "")

    if not texto.isdigit():
        return False

    if len(texto) not in (11, 14):
        return False

    if len(set(texto)) == 1:
        return False

    digitos = [int(c) for c in texto]

    if len(digitos) == 11:
        return _validar_cpf(digitos)
    return _validar_cnpj(digitos)
