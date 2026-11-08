"""Número de processo no padrão CNJ (Resolução 65/2008): 20 dígitos.

`NNNNNNN-DD.AAAA.J.TR.OOOO`. O DJEN devolve o número sem máscara; o cadastro
aceita texto livre. O casamento entre os dois usa só os dígitos.
"""

import re

_NAO_DIGITO = re.compile(r"\D")


def normalizar_cnj(numero: str | None) -> str | None:
    """Os 20 dígitos do número, ou None se não seguir o padrão CNJ."""
    if not numero:
        return None
    digitos = _NAO_DIGITO.sub("", numero)
    return digitos if len(digitos) == 20 else None


def mascarar_cnj(digitos: str | None) -> str | None:
    """`NNNNNNNDDAAAAJTROOOO` -> `NNNNNNN-DD.AAAA.J.TR.OOOO`."""
    if not digitos or len(digitos) != 20 or not digitos.isdigit():
        return digitos
    d = digitos
    return f"{d[:7]}-{d[7:9]}.{d[9:13]}.{d[13]}.{d[14:16]}.{d[16:]}"
