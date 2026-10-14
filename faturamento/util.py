"""Conversões no formato brasileiro e utilidades de competência."""
from __future__ import annotations

import os
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]
MESES_CURTOS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


class ValorInvalido(ValueError):
    pass


def _carregar_fuso():
    """Fuso do escritório (Fortaleza-CE, UTC-3 fixo). Troca por FUSO_HORARIO no .env."""
    nome = os.getenv("FUSO_HORARIO", "America/Fortaleza")
    try:
        return ZoneInfo(nome)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return timezone(timedelta(hours=-3), "America/Fortaleza")  # sem tzdata instalado


FUSO = _carregar_fuso()


def agora() -> datetime:
    """Data/hora de Fortaleza (sem fuso embutido), igual em qualquer máquina: PC, servidor ou Docker."""
    return datetime.now(FUSO).replace(tzinfo=None)


def hoje() -> date:
    return agora().date()


def utc_para_local(texto, vazio: str = "—") -> str:
    """'2026-09-05T12:00:00.000Z' (UTC) -> '05/09/2026 09:00' no fuso de Fortaleza."""
    t = str(texto or "").strip()
    if not t:
        return vazio
    try:
        dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        return t
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(FUSO).strftime("%d/%m/%Y %H:%M")


MAX_DIGITOS_INTEIROS = 13          # NUMERIC(15,2): 13 dígitos antes da vírgula
MAX_INTEIRO = 2_147_483_647        # coluna INTEGER (quantidades)
_MILHAR = re.compile(r"[-+]?\d{1,3}(\.\d{3})+")


def _checar_tamanho(d: Decimal, original) -> Decimal:
    if abs(d) >= Decimal(10) ** MAX_DIGITOS_INTEIROS:
        raise ValorInvalido(f"'{original}': valor grande demais")
    return d


def _limpar(texto) -> str:
    return str(texto).strip().replace("R$", "").replace(" ", "").replace(" ", "")


def parse_decimal(valor) -> Decimal | None:
    """Aceita '1.234,56', '1234,56', '1234.56', 1234.56. Vazio -> None."""
    if valor is None:
        return None
    if isinstance(valor, bool):
        raise ValorInvalido("valor inválido")
    try:
        if isinstance(valor, Decimal):
            return _checar_tamanho(valor, valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if isinstance(valor, (int, float)):
            return _checar_tamanho(Decimal(str(valor)), valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:  # nan/inf
        raise ValorInvalido(f"'{valor}' não é um número") from exc
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
        digitos = inteiro.lstrip("+-")
        # "6.370" = seis mil trezentos e setenta; mas "0.125" é decimal (milhar não começa com 0)
        if len(frac) == 3 and digitos.isdigit() and not digitos.startswith("0"):
            t = inteiro + frac
    try:
        return _checar_tamanho(Decimal(t), valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValorInvalido(f"'{valor}' não é um número") from exc


def parse_inteiro(valor) -> int | None:
    if valor is None:
        return None
    if isinstance(valor, bool):
        raise ValorInvalido("valor inválido")
    if isinstance(valor, float):
        if valor != valor or valor in (float("inf"), float("-inf")) or valor != int(valor):
            raise ValorInvalido(f"'{valor}' não é um número inteiro")
        valor = int(valor)
    if isinstance(valor, int):
        n = valor
    else:
        t = _limpar(valor)
        if t == "":
            return None
        if _MILHAR.fullmatch(t):  # só pontos de milhar: "1.234", "12.345.678"
            t = t.replace(".", "")
        if not re.fullmatch(r"[-+]?\d+", t):
            raise ValorInvalido(f"'{valor}' não é um número inteiro")
        n = int(t)
    if abs(n) > MAX_INTEIRO:
        raise ValorInvalido(f"'{valor}': valor grande demais")
    return n


def fmt_moeda(valor, vazio: str = "—") -> str:
    if valor is None:
        return vazio
    v = Decimal(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
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
    ano_mes = (int(m.group(1)), int(m.group(2))) if m else None
    if ano_mes is None:
        m = re.fullmatch(r"(\d{1,2})/(\d{4})", t)
        ano_mes = (int(m.group(2)), int(m.group(1))) if m else None
    if ano_mes and 1 <= ano_mes[1] <= 12 and ano_mes[0] >= 1900:
        return date(ano_mes[0], ano_mes[1], 1)
    raise ValorInvalido(f"Competência inválida: '{valor}' (use AAAA-MM)")


def competencia_atual() -> date:
    d = hoje()
    return date(d.year, d.month, 1)


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
