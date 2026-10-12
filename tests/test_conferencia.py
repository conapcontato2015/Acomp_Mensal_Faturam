"""Tela de conferência e exportações (Excel e página de impressão)."""
from __future__ import annotations

import re
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import load_workbook

from faturamento.extensions import db as _db
from faturamento.services import lancamentos as svc_lanc


def _lancar(empresa, comp, usuario, tipos, valores):
    """valores: {codigo: (qtde_autor, valor_autor, qtde_canc, valor_canc)}"""
    linhas = [{"tipo_id": tipos[c].id, "qtde_autor": v[0], "valor_autor": v[1], "qtde_canc": v[2], "valor_canc": v[3]}
              for c, v in valores.items()]
    svc_lanc.salvar_mes(empresa, comp, linhas, usuario)
    _db.session.commit()
    return {c: svc_lanc.buscar(empresa.id, comp, tipos[c].id) for c in valores}


@pytest.fixture()
def cenario(app, nova_empresa, usuarios, tipos, comp):
    natan, hellen = usuarios["Natan"], usuarios["Hellen"]
    alfa = nova_empresa("Alfa Comércio", "Natan")
    beta = nova_empresa("Beta Serviços", "Natan")
    gama = nova_empresa("Gama Hellen", "Hellen")
    la = _lancar(alfa, comp, natan, tipos, {
        "NFE_ENT": (168, "190505.28", 1, "328.99"),
        "NFE_SAI": (18, "9593.45", None, None),
        "NFCE": (6431, "186864.95", 27, "727.40"),
    })
    svc_lanc.adicionar_ajuste(la["NFCE"], "AUTOR", 61, "1295.50", natan)
    _db.session.commit()
    lb = _lancar(beta, comp, natan, tipos, {"NFE_ENT": (3, "22.43", None, None)})
    svc_lanc.marcar_bateu(lb["NFE_ENT"], True, natan)
    lg = _lancar(gama, comp, hellen, tipos, {"NFE_SAI": (5, "1000.00", None, None)})
    _db.session.commit()
    return {"alfa": alfa, "beta": beta, "gama": gama, "la": la, "lb": lb, "lg": lg}


def _selos_habilitados(html: str) -> int:
    return len([m for m in re.findall(r'<button type="button" class="selo"[^>]*>', html) if "disabled" not in m])


def test_pagina_com_dados(login, cenario):
    c = login("Natan")
    r = c.get("/conferencia?competencia=2026-08")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Conferência · Agosto de 2026" in html
    assert "Alfa Comércio" in html and "Beta Serviços" in html
    assert "Gama Hellen" not in html  # outra carteira
    # valores com ajuste (186.864,95 + 1.295,50) e quantidades pt-BR
    assert "188.160,45" in html and "6.492" in html
    assert "±aj" in html
    assert "Faltam 3" in html and "✓ Tudo bateu" in html
    assert 'data-bateram="1"' in html and 'data-linhas="4"' in html
    assert _selos_habilitados(html) > 0
    assert "somente leitura" not in html.lower()


def test_carteira_de_outra_pessoa_e_somente_leitura(login, cenario, usuarios):
    c = login("Natan")
    html = c.get(f"/conferencia?competencia=2026-08&carteira={usuarios['Hellen'].id}").get_data(as_text=True)
    assert "Gama Hellen" in html and "Alfa Comércio" not in html
    assert "Somente leitura" in html
    assert 'class="selo"' in html
    assert _selos_habilitados(html) == 0
    assert re.search(r'data-acao="marcar"\s+disabled', html)


def test_carteira_todos_e_somente_leitura(login, cenario):
    html = login("Natan").get("/conferencia?competencia=2026-08&carteira=todos").get_data(as_text=True)
    assert "Gama Hellen" in html and "Alfa Comércio" in html
    assert _selos_habilitados(html) == 0


def test_vista_pendencia_esconde_empresas_conferidas(login, cenario):
    c = login("Natan")
    html = c.get("/conferencia?competencia=2026-08&vista=pendencia").get_data(as_text=True)
    assert "Alfa Comércio" in html
    assert "Beta Serviços" not in html
    # os contadores continuam considerando a carteira toda
    assert 'data-ok="1"' in html and 'data-pendentes="1"' in html


def test_vazios(login, cenario, usuarios, db):
    c = login("Natan")
    html = c.get("/conferencia?competencia=2026-07").get_data(as_text=True)
    assert "Nenhum lançamento com movimento" in html
    svc_lanc.marcar_bateu_empresa(cenario["alfa"], cenario["la"]["NFCE"].competencia, True, usuarios["Natan"])
    db.session.commit()
    html = c.get("/conferencia?competencia=2026-08&vista=pendencia").get_data(as_text=True)
    assert "já foram conferidas" in html
    assert "Alfa Comércio" not in html


def test_api_bateu_reflete_na_pagina(login, cenario):
    c = login("Natan")
    lid = cenario["la"]["NFE_ENT"].id
    r = c.put(f"/api/faturamento/v1/lancamentos/{lid}/bateu", json={"bateu": True})
    assert r.status_code == 200 and r.get_json()["bateu"] is True
    html = c.get("/conferencia?competencia=2026-08").get_data(as_text=True)
    assert re.search(rf'data-lanc="{lid}"[^>]*aria-pressed="true"', html)
    assert "Faltam 2" in html and 'data-bateram="2"' in html

    eid = cenario["alfa"].id
    r = c.put(f"/api/faturamento/v1/conferencia/{eid}/2026-08", json={"bateu": True})
    assert r.status_code == 200
    html = c.get("/conferencia?competencia=2026-08").get_data(as_text=True)
    assert "Faltam" not in html and 'data-ok="2"' in html and 'data-pendentes="0"' in html


def test_api_bateu_negado_para_outra_carteira(login, cenario):
    c = login("Natan")
    lid = cenario["lg"]["NFE_SAI"].id
    r = c.put(f"/api/faturamento/v1/lancamentos/{lid}/bateu", json={"bateu": True})
    assert r.status_code == 403


def _ler_xlsx(resp):
    wb = load_workbook(BytesIO(resp.data))
    ws = wb.active
    return wb, ws, [list(r) for r in ws.iter_rows(values_only=True)]


def test_excel(login, cenario):
    c = login("Natan")
    r = c.get("/conferencia/excel?competencia=2026-08")
    assert r.status_code == 200
    assert "conferencia-2026-08.xlsx" in r.headers["Content-Disposition"]
    wb, ws, linhas = _ler_xlsx(r)
    assert ws.title == "Conferência 08-2026"
    assert linhas[0] == ["Empresa", "Responsável", "Sentido", "Tipo", "Qtde autorizada", "Valor autorizado",
                         "Qtde cancelada", "Valor cancelado", "Ajuste qtde", "Ajuste valor", "Bateu"]
    assert ws.freeze_panes == "A2"
    assert ws["A1"].font.bold and ws["A1"].fill.fgColor.rgb.endswith("202F5A")
    corpo = linhas[1:]
    # Alfa: 1 entrada + subtotal, 2 saídas + subtotal; Beta: 1 entrada + subtotal
    assert len(corpo) == 7
    nfce = next(l for l in corpo if l[0] == "Alfa Comércio" and l[3] == "NFC-e")
    assert nfce[4] == 6492 and Decimal(str(nfce[5])) == Decimal("188160.45")
    assert nfce[8] == 61 and Decimal(str(nfce[9])) == Decimal("1295.50") and nfce[10] == "Não"
    beta = next(l for l in corpo if l[0] == "Beta Serviços" and l[3] == "NF-e Entradas")
    assert beta[10] == "Sim"

    subs = [(i, l) for i, l in enumerate(corpo, start=2) if str(l[3]).startswith("Subtotal")]
    assert [(l[0], l[2], l[3]) for _, l in subs] == [
        ("Alfa Comércio", "Entrada", "Subtotal entradas"),
        ("Alfa Comércio", "Saída", "Subtotal saídas"),
        ("Beta Serviços", "Entrada", "Subtotal entradas"),
    ]
    sub_e, sub_s = subs[0][1], subs[1][1]
    assert sub_e[4] == 168 and Decimal(str(sub_e[5])) == Decimal("190505.28")
    assert sub_s[4] == 18 + 6492 and Decimal(str(sub_s[5])) == Decimal("9593.45") + Decimal("188160.45")
    # entradas e saídas nunca somadas: nenhum valor da planilha é E+S da Alfa
    soma_es = Decimal("190505.28") + Decimal("9593.45") + Decimal("188160.45")
    assert all(Decimal(str(l[5])) != soma_es for l in corpo if l[5] is not None)
    assert not any("total" in str(l[3]).lower() and "subtotal" not in str(l[3]).lower() for l in corpo)
    for i, _ in subs:
        assert ws.cell(row=i, column=1).font.bold
    assert ws.cell(row=2, column=5).number_format == "#,##0"
    assert ws.cell(row=2, column=6).number_format == "#,##0.00"


def test_excel_carteira_vazia(login, app, usuarios):
    r = login("Natan").get("/conferencia/excel?competencia=2026-08")
    assert r.status_code == 200
    _, _, linhas = _ler_xlsx(r)
    assert len(linhas) == 1


def test_imprimir(login, cenario):
    c = login("Natan")
    r = c.get("/conferencia/imprimir?competencia=2026-08&carteira=todos")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    for nome in ("Alfa Comércio", "Beta Serviços", "Gama Hellen"):
        assert nome in html
    assert "logo-conap-cor.png" in html
    assert "window.print()" in html and "Imprimir / salvar PDF" in html
    assert 'class="side"' not in html
    assert "Subtotal entradas" in html and "Subtotal saídas" in html
    assert "Agosto de 2026" in html and "Todas as pessoas" in html


def test_exige_usuario(client, cenario):
    r = client.get("/conferencia")
    assert r.status_code == 302
