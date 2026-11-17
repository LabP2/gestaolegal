"""Validação de CPF informado na correção de cadastros legados."""
import re


def cpf_valido(valor: str) -> bool:
    if not re.fullmatch(r"[0-9.\- ]+", valor):
        return False
    digits = re.sub(r"\D", "", valor)
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    for size in (9, 10):
        digit = (sum(int(digits[i]) * (size + 1 - i) for i in range(size)) * 10 % 11) % 10
        if digit != int(digits[size]):
            return False
    return True
