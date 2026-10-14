"""Fuso de Fortaleza (UTC-3) independente da máquina e confetes de parabéns."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from faturamento import util

RAIZ = Path(__file__).resolve().parent.parent / "faturamento"


def test_agora_e_hoje_usam_fortaleza_e_nao_o_relogio_da_maquina():
    ref = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-3))).replace(tzinfo=None)
    a = util.agora()
    assert a.tzinfo is None and abs(a - ref) < timedelta(seconds=5)
    assert util.hoje() == a.date()


def test_virada_do_mes_segue_a_meia_noite_de_fortaleza(monkeypatch):
    # 30/09 às 23:30 em Fortaleza já é 01/10 02:30 em UTC: o mês de trabalho ainda é setembro
    monkeypatch.setattr(util, "agora", lambda: datetime(2026, 9, 30, 23, 30))
    assert util.competencia_atual() == date(2026, 9, 1)
    assert util.competencia_padrao() == date(2026, 8, 1)
    monkeypatch.setattr(util, "agora", lambda: datetime(2026, 10, 1, 0, 5))
    assert util.competencia_atual() == date(2026, 10, 1)


def test_utc_para_local_em_formato_brasileiro():
    assert util.utc_para_local("2026-09-05T12:00:00.000Z") == "05/09/2026 09:00"
    assert util.utc_para_local("2026-09-01T02:30:00Z") == "31/08/2026 23:30"  # vira o dia para trás
    assert util.utc_para_local("") == "—" and util.utc_para_local(None) == "—"
    assert util.utc_para_local("sem data") == "sem data"


def test_tela_do_cruzamento_nao_mostra_mais_utc():
    html = (RAIZ / "templates/faturamento/cruzamento.html").read_text(encoding="utf-8")
    assert "|hora_br" in html and "(UTC)" not in html


def test_confete_ligado_na_conferencia_e_no_lancamento():
    app_js = (RAIZ / "static/faturamento/js/app.js").read_text(encoding="utf-8")
    assert "function confete" in app_js and "prefers-reduced-motion" in app_js
    assert "FAT.confete" in (RAIZ / "static/faturamento/js/conferencia.js").read_text(encoding="utf-8")
    lanc = (RAIZ / "static/faturamento/js/lancamento.js").read_text(encoding="utf-8")
    assert "FAT.confete" in lanc and "timeZone: 'America/Fortaleza'" in lanc
