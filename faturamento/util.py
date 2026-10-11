"""Conversões no formato brasileiro e utilidades de competência."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]
MESES_CURTOS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


class ValorInvalido(ValueError):
    pass


def _limpar(texto) -> str:
    return str(texto).strip().replace("R$", "").replace(" ", "").replace(" ", "")


def parse_decimal(valor) -> Decimal | None:
    """Aceita '1.234,56', '1234,56', '1234.56', 1234.56. Vazio -> None."""
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return valor.quantize(Decimal("0.01"))
    if isinstance(valor, (int, float)):
        return Decimal(str(valor)).quantize(Decimal("0.01"))
    t = _limpar(valor)
    if t == "":
        return None
    if not re.fullmatch(r"[-+]?[\d.,]+", t):
        raise ValorInvalido(f"'{valor}' não é um número")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") > 1:
        t = t.replace(".", "")
    elif "." in t:
        inteiro, _, frac = t.partition(".")
        if len(frac) == 3 and inteiro.lstrip("+-").isdigit():  # "6.370" = seis mil trezentos e setenta
            t = inteiro + frac
    try:
        return Decimal(t).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValorInvalido(f"'{valor}' não é um número") from exc


def parse_inteiro(valor) -> int | None:
    if valor is None:
        return None
    if isinstance(valor, bool):
        raise ValorInvalido("valor inválido")
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float):
        if valor != int(valor):
            raise ValorInvalido(f"'{valor}' não é um número inteiro")
        return int(valor)
    t = _limpar(valor).replace(".", "")
    if t == "":
        return None
    if not re.fullmatch(r"[-+]?\d+", t):
        raise ValorInvalido(f"'{valor}' não é um número inteiro")
    return int(t)


def fmt_moeda(valor, vazio: str = "—") -> str:
    if valor is None:
        return vazio
    v = Decimal(valor).quantize(Decimal("0.01"))
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if v < 0 else "") + s


def fmt_inteiro(valor, vazio: str = "—") -> str:
    if valor is None:
        return vazio
    s = f"{abs(int(valor)):,}".replace(",", ".")
    return ("-" if int(valor) < 0 else "") + s


def competencia(valor) -> date:
    """'2026-08', '08/2026', date, datetime -> date(2026, 8, 1)."""
    if isinstance(valor, datetime):
        return date(valor.year, valor.month, 1)
    if isinstance(valor, date):
        return date(valor.year, valor.month, 1)
    t = str(valor).strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})(?:-\d{1,2})?", t)
    if m:
        return date(int(m.group(1)), int(m.group(2)), 1)
    m = re.fullmatch(r"(\d{1,2})/(\d{4})", t)
    if m:
        return date(int(m.group(2)), int(m.group(1)), 1)
    raise ValorInvalido(f"Competência inválida: '{valor}' (use AAAA-MM)")


def competencia_atual() -> date:
    hoje = date.today()
    return date(hoje.year, hoje.month, 1)


def competencia_padrao() -> date:
    """O mês de trabalho normal é o anterior ao atual."""
    return somar_meses(competencia_atual(), -1)


def somar_meses(c: date, n: int) -> date:
    total = c.year * 12 + (c.month - 1) + n
    return date(total // 12, total % 12 + 1, 1)


def comp_iso(c: date) -> str:
    return f"{c.year:04d}-{c.month:02d}"


def comp_curta(c: date) -> str:
    return f"{c.month:02d}/{c.year:04d}"


def comp_extenso(c: date) -> str:
    return f"{MESES[c.month - 1].capitalize()} de {c.year}"


def comp_rotulo(c: date) -> str:
    return f"{MESES_CURTOS[c.month - 1]}/{str(c.year)[2:]}"


def so_digitos(texto) -> str:
    return re.sub(r"\D", "", str(texto or ""))


def normalizar_nome(texto) -> str:
    """Para casar nomes vindos de planilha: sem acento, maiúsculo, espaços simples."""
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t).strip().upper()


def nome_exibicao(texto) -> str:
    """'MERCADINHO MILHÃ (MATRIZ)' -> 'Mercadinho Milhã (Matriz)'. Mantém siglas curtas."""
    palavras = []
    for p in re.sub(r"\s+", " ", str(texto).strip()).split(" "):
        miolo = p.strip("()")
        if miolo.isupper() and len(miolo) <= 2 and miolo not in {"DE", "DA", "DO", "E"}:
            palavras.append(p)
        elif miolo.upper() in {"DE", "DA", "DO", "DAS", "DOS", "E"}:
            palavras.append(p.lower())
        elif miolo.upper() in {"IBTI", "CNPJ", "ME", "EPP", "LTDA"}:
            palavras.append(p)
        else:
            palavras.append(p.capitalize() if not p.startswith("(") else "(" + p[1:].capitalize())
    return " ".join(palavras)
