"""Conversões no formato brasileiro e competência."""
from datetime import date, datetime
from decimal import Decimal

import pytest

from faturamento.util import (
    ValorInvalido,
    comp_curta,
    comp_extenso,
    comp_iso,
    comp_rotulo,
    competencia,
    fmt_inteiro,
    fmt_moeda,
    nome_exibicao,
    normalizar_nome,
    parse_decimal,
    parse_inteiro,
    so_digitos,
    somar_meses,
)

# ------------------------------------------------------------------ parse_decimal

@pytest.mark.parametrize("entrada, esperado", [
    ("1.234,56", Decimal("1234.56")),
    ("1234,56", Decimal("1234.56")),
    ("1234.56", Decimal("1234.56")),
    ("R$ 1.234,56", Decimal("1234.56")),
    ("  395.464,73 ", Decimal("395464.73")),
    ("6.370", Decimal("6370.00")),          # ponto de milhar sem centavos
    ("1.234.567", Decimal("1234567.00")),   # vários pontos = milhar
    ("1.234.567,8", Decimal("1234567.80")),
    ("12.5", Decimal("12.50")),             # ponto decimal "americano"
    ("-1.234,56", Decimal("-1234.56")),
    ("0", Decimal("0.00")),
    (1234.5, Decimal("1234.50")),
    (10, Decimal("10.00")),
    (Decimal("3.456"), Decimal("3.46")),
])
def test_parse_decimal_aceita_formatos(entrada, esperado):
    assert parse_decimal(entrada) == esperado


@pytest.mark.parametrize("vazio", [None, "", "   ", "R$"])
def test_parse_decimal_vazio_vira_none(vazio):
    assert parse_decimal(vazio) is None


@pytest.mark.parametrize("ruim", ["abc", "12a", "1,2,3", "1.2.3,4,5", "--5", "R$ x"])
def test_parse_decimal_invalido_levanta(ruim):
    with pytest.raises(ValorInvalido):
        parse_decimal(ruim)


def test_parse_decimal_booleano_levanta_valor_invalido():
    with pytest.raises(ValorInvalido):
        parse_decimal(True)


# ------------------------------------------------------------------ parse_inteiro

@pytest.mark.parametrize("entrada, esperado", [
    ("12", 12), ("1.234", 1234), (" 7 ", 7), ("-3", -3), ("+4", 4), (5, 5), (5.0, 5), ("0", 0),
])
def test_parse_inteiro(entrada, esperado):
    assert parse_inteiro(entrada) == esperado


@pytest.mark.parametrize("vazio", [None, "", "  "])
def test_parse_inteiro_vazio(vazio):
    assert parse_inteiro(vazio) is None


@pytest.mark.parametrize("ruim", ["1,5", "abc", 2.5, True, "3x"])
def test_parse_inteiro_invalido(ruim):
    with pytest.raises(ValorInvalido):
        parse_inteiro(ruim)


# ------------------------------------------------------------------ formatação

@pytest.mark.parametrize("valor, esperado", [
    (Decimal("1234.5"), "1.234,50"),
    (Decimal(0), "0,00"),
    (Decimal("-1234567.891"), "-1.234.567,89"),
    (Decimal("0.006"), "0,01"),
    (395464.73, "395.464,73"),
    (None, "—"),
])
def test_fmt_moeda(valor, esperado):
    assert fmt_moeda(valor) == esperado


def test_fmt_moeda_vazio_personalizado():
    assert fmt_moeda(None, "") == ""


def test_fmt_inteiro():
    assert fmt_inteiro(1234567) == "1.234.567"
    assert fmt_inteiro(-1500) == "-1.500"
    assert fmt_inteiro(None) == "—"


# ------------------------------------------------------------------ competência

@pytest.mark.parametrize("entrada", ["2026-08", "2026-8", "08/2026", "8/2026", "2026-08-17",
                                     date(2026, 8, 31), datetime(2026, 8, 5, 10, 30)])  # noqa: DTZ001
def test_competencia_normaliza_para_dia_1(entrada):
    assert competencia(entrada) == date(2026, 8, 1)


@pytest.mark.parametrize("ruim", ["", "agosto", "2026/08", "26-08", "08-2026"])
def test_competencia_invalida(ruim):
    with pytest.raises(ValorInvalido):
        competencia(ruim)


@pytest.mark.parametrize("ruim", ["2026-13", "00/2026"])
def test_competencia_mes_fora_do_intervalo(ruim):
    with pytest.raises(ValorInvalido):
        competencia(ruim)


def test_somar_meses_vira_o_ano():
    assert somar_meses(date(2026, 1, 1), -1) == date(2025, 12, 1)
    assert somar_meses(date(2026, 11, 1), 3) == date(2027, 2, 1)
    assert somar_meses(date(2026, 8, 1), 0) == date(2026, 8, 1)


def test_rotulos_de_competencia():
    c = date(2026, 9, 1)
    assert comp_iso(c) == "2026-09"
    assert comp_curta(c) == "09/2026"
    assert comp_extenso(c) == "Setembro de 2026"
    assert comp_rotulo(c) == "Set/26"


# ------------------------------------------------------------------ textos

def test_normalizar_nome_e_digitos():
    assert normalizar_nome("  Mercadinho   Milhã ") == "MERCADINHO MILHA"
    assert so_digitos("12.345.678/0001-90") == "12345678000190"
    assert so_digitos(None) == ""


def test_nome_exibicao():
    assert nome_exibicao("MERCADINHO MILHÃ (MATRIZ)") == "Mercadinho Milhã (Matriz)"
    assert nome_exibicao("ROGER DE SOLONOPOLE") == "Roger de Solonopole"
