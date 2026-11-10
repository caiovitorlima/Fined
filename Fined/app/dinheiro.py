import re
from decimal import ROUND_HALF_UP, Decimal

MAXIMO_CENTAVOS = 1_000_000_000

_FORMATOS = (
    (re.compile(r"\d+"), lambda s: s),
    (re.compile(r"\d+[.,]\d{1,2}"), lambda s: s.replace(",", ".")),
    (re.compile(r"\d{1,3}(?:\.\d{3})+"), lambda s: s.replace(".", "")),
    (re.compile(r"\d{1,3}(?:\.\d{3})+,\d{1,2}"), lambda s: s.replace(".", "").replace(",", ".")),
    (re.compile(r"\d{1,3}(?:,\d{3})+\.\d{1,2}"), lambda s: s.replace(",", "")),
)


def ler_valor(texto):
    bruto = (texto or "").strip()
    for lixo in ("R$", "r$", " ", " "):
        bruto = bruto.replace(lixo, "")
    if bruto.startswith("+"):
        bruto = bruto[1:]
    if not bruto:
        raise ValueError("Informe um valor.")
    if bruto.startswith("-"):
        raise ValueError("O valor precisa ser maior que zero.")
    for padrao, normalizar in _FORMATOS:
        if padrao.fullmatch(bruto):
            numero = Decimal(normalizar(bruto))
            break
    else:
        raise ValueError("Valor inválido. Escreva algo como 25,90.")
    total = int((numero * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if total <= 0:
        raise ValueError("O valor precisa ser maior que zero.")
    if total > MAXIMO_CENTAVOS:
        raise ValueError("Valor alto demais. O limite é R$ 10.000.000,00.")
    return total


def _milhar(numero):
    return f"{numero:,}".replace(",", ".")


def reais(centavos):
    return _milhar(abs(int(centavos or 0)) // 100)


def centavos(valor):
    return f"{abs(int(valor or 0)) % 100:02d}"


def brl(valor, sinal=False):
    numero = int(valor or 0)
    corpo = f"R$ {reais(numero)},{centavos(numero)}"
    if numero < 0:
        return "−" + corpo
    if sinal and numero > 0:
        return "+" + corpo
    return corpo


def para_campo(valor):
    numero = int(valor or 0)
    return f"{numero // 100},{numero % 100:02d}"
