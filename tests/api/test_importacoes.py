"""Importações pela API: planilha antiga, responsáveis, Controle Fiscal, cruzamento Domínio × SEFAZ e histórico.

Planilhas e bancos sintéticos — nenhum dado de cliente.
"""
from __future__ import annotations

import io
import json
import sqlite3
import threading
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from openpyxl import Workbook

from .conftest import API

UP = {"X-Requested-With": "fetch"}  # uploads multipart só com o cabeçalho do front
CAB = ["EMPRESA", "COMP.", "TIPO", "QTDE_AUTOR", "VALOR_AUTOR", "AJUSTE_QTDE_AUTOR", "AJUSTE_VALOR_AUTOR",
       "QTDE_CANC", "VALOR_CANC"]


@pytest.fixture(autouse=True)
def dados_tmp(app, tmp_path, opcoes):
    opcoes(DADOS_DIR=tmp_path)
    return tmp_path


def _planilha(linhas) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "DADOS"
    ws.append([])
    ws.append([None, *CAB])
    for ln in linhas:
        ws.append([None, *ln])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


AGO = datetime(2026, 8, 1)
LINHAS = [
    ["LOJA ALFA (MATRIZ)", AGO, "NFC-e", 100, 1000.5, 5, 50.25, 2, 20],
    ["PADARIA BETA", AGO, "NF-e ENTRADAS", None, 500, None, None, None, None],  # valor sem qtde: aviso
    ["PADARIA BETA", AGO, "MDF-e", 1, 10, None, None, None, None],               # tipo desconhecido
]


def test_planilha_previa_confirmar_e_desfazer(entrar, usuarios):
    c = entrar("Natan")
    r = c.post(f"{API}/importacoes/previa", headers=UP, data={"responsavelId": str(usuarios["Natan"])},
               files={"arquivo": ("FATURAMENTO_V2.xlsx", _planilha(LINHAS))})
    assert r.status_code == 200, r.json()
    p = r.json()
    assert p["aba"] == "DADOS" and p["nLancamentos"] == 2 and p["nAjustes"] == 1
    assert [e["nome"] for e in p["empresas"]] == ["Loja Alfa (Matriz)", "Padaria Beta"] and all(e["nova"] for e in p["empresas"])
    assert p["totais"][0]["competencia"]["valor"] == "2026-08" and p["totais"][0]["saidas"]["valor"] == "1050.75"
    assert any("MDF-e" in a["texto"] for a in p["avisos"]) and any(a["destaque"] for a in p["avisos"])

    r = c.post(f"{API}/importacoes/confirmar", json={"token": p["token"], "responsavelId": usuarios["Natan"]})
    assert r.status_code == 200, r.json()
    res = r.json()["resumo"]
    assert res["lancamentosCriados"] == 2 and res["ajustesCriados"] == 1 and len(res["empresasCriadas"]) == 2
    imp = r.json()["importacao"]
    assert imp["fonte"] == "planilha" and imp["usuario"]["nome"] == "Natan"
    assert c.post(f"{API}/importacoes/confirmar", json={"token": p["token"], "responsavelId": usuarios["Natan"]}).status_code == 400

    lista = c.get(f"{API}/importacoes").json()["importacoes"]
    assert [i["id"] for i in lista] == [imp["id"]] and lista[0]["lancamentosCriados"] == 2

    assert entrar("Hellen").post(f"{API}/importacoes/{imp['id']}/desfazer", json={}).status_code == 422  # só quem importou
    c = entrar("Natan")
    r = c.post(f"{API}/importacoes/{imp['id']}/desfazer", json={})
    assert r.status_code == 200 and r.json()["resultado"]["removidos"] == 2 and r.json()["importacao"]["desfeita"] is True


def test_planilha_invalida_e_descartar(entrar):
    c = entrar()
    r = c.post(f"{API}/importacoes/previa", headers=UP, files={"arquivo": ("x.csv", b"a;b")})
    assert r.status_code == 400 and "Formato" in r.json()["mensagens"][0]
    r = c.post(f"{API}/importacoes/previa", headers=UP, files={"arquivo": ("x.xlsx", b"nao e zip")})
    assert r.status_code == 400 and ".xlsx" in r.json()["mensagens"][0]
    r = c.post(f"{API}/importacoes/previa", headers=UP, files={"arquivo": ("x.xlsx", _planilha(LINHAS))})
    assert c.post(f"{API}/importacoes/descartar", json={"token": r.json()["token"]}).json() == {"ok": True}
    assert c.post(f"{API}/importacoes/confirmar", json={"token": r.json()["token"], "responsavelId": 1}).status_code == 400


def test_responsaveis_por_planilha(entrar, nova_empresa, usuarios):
    eid = nova_empresa("Bio Seiva", cnpj="12345678000190")
    c = entrar("Natan")
    modelo = c.get(f"{API}/responsaveis/modelo.csv")
    assert modelo.status_code == 200 and modelo.content.startswith("﻿".encode())
    assert "12.345.678/0001-90;Bio Seiva;Natan;" in modelo.content.decode("utf-8-sig")
    csv = "CNPJ;EMPRESA;RESPONSAVEL;INICIO\r\n12.345.678/0001-90;Bio Seiva;Hellen;\r\n;Inexistente;Natan;\r\n"
    r = c.post(f"{API}/responsaveis/previa", headers=UP, data={"inicio": "2026-09"},
               files={"arquivo": ("resp.csv", csv.encode())})
    j = r.json()
    assert j["relatorio"]["alteradas"] == ["Bio Seiva: Natan → Hellen"] and j["token"]
    assert j["relatorio"]["empresasNaoEncontradas"] == ["Inexistente"]
    r = c.post(f"{API}/responsaveis/confirmar", json={"token": j["token"], "inicio": "2026-09"})
    assert r.status_code == 200
    assert c.get(f"{API}/empresas/{eid}").json()["empresa"]["responsavel"]["nome"] == "Hellen"


def test_controle_fiscal(entrar, nova_empresa, tmp_path, opcoes):
    eid = nova_empresa("Bio Seiva")
    c = entrar("Natan")
    assert c.get(f"{API}/controle-fiscal").json()["configurado"] is False
    assert c.post(f"{API}/controle-fiscal", json={}).status_code == 422
    caminho = tmp_path / "cf.db"
    con = sqlite3.connect(caminho)
    con.executescript("""
        CREATE TABLE responsavel (id INTEGER PRIMARY KEY, nome TEXT, ordem INT, ativo BOOL);
        CREATE TABLE empresa (id INTEGER PRIMARY KEY, codigo TEXT, razao_social TEXT, cnpj TEXT,
                              responsavel_id INT, ativo BOOL);
        INSERT INTO responsavel VALUES (1, 'Hellen', 0, 1);
        INSERT INTO empresa VALUES (1, '77', 'BIO SEIVA', '12.345.678/0001-90', 1, 1);
    """)
    con.commit()
    con.close()
    opcoes(FOLHA_DATABASE_URL=f"sqlite:///{caminho.as_posix()}", FOLHA_MAPA_RESPONSAVEIS="")
    r = c.post(f"{API}/controle-fiscal", json={"inicio": "2026-09"})
    rel = r.json()["relatorio"]
    assert r.json()["aplicado"] is False and rel["trocas"] and rel["cnpjsPreenchidos"] and rel["temAlteracoes"]
    r = c.post(f"{API}/controle-fiscal", json={"inicio": "2026-09", "aplicar": True})
    assert r.json()["aplicado"] is True
    e = c.get(f"{API}/empresas/{eid}").json()["empresa"]
    assert e["cnpj"] == "12345678000190" and e["externalId"] == "cf:77" and e["responsavel"]["nome"] == "Hellen"


# ------------------------------------------------------------------ cruzamento (servidor falso do Manus)

CHAVE = "chave-de-teste-123456"


@pytest.fixture()
def servidor_cruzamento(opcoes):
    estado = {"empresas": []}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):  # noqa: N802
            url = urllib.parse.urlparse(self.path)
            entrada = json.loads(urllib.parse.parse_qs(url.query)["input"][0])["json"]
            ok = self.headers.get("Authorization") == f"Bearer {CHAVE}"
            corpo = ({"result": {"data": {"json": {"versao": 1, "competencia": entrada["competencia"],
                                                   "geradoEm": "2026-09-05T12:00:00.000Z",
                                                   "empresas": estado["empresas"]}}}} if ok
                     else {"error": {"json": {"message": "Chave inválida"}}})
            b = json.dumps(corpo).encode()
            self.send_response(200 if ok else 401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    opcoes(CRUZAMENTO_URL=f"http://127.0.0.1:{srv.server_port}", CRUZAMENTO_API_KEY=CHAVE, CRUZAMENTO_TIMEOUT=5)
    yield estado
    srv.shutdown()
    srv.server_close()


def _tipo_la(nome, aut, falta=(0, "0.00")):
    return {"tipo": nome, "sefazImportado": True, "dominioImportado": True,
            "autorizadas": {"qtde": aut[0], "valor": aut[1]}, "canceladas": {"qtde": 0, "valor": "0.00"},
            "faltaSefaz": {"qtde": falta[0], "valor": falta[1], "notas": [{"numero": "77", "serie": "1"}],
                           "notasOmitidas": 0}}


def test_cruzamento_previa_e_aplicar(entrar, nova_empresa, servidor_cruzamento):
    eid = nova_empresa("Mercadinho A", cnpj="12345678000190")
    servidor_cruzamento["empresas"] = [{"cnpj": "12345678000190", "razaoSocial": "MERCADINHO A",
                                        "tipos": [_tipo_la("NFCE_AUTORIZADA", (100, "1500.25"), (1, "15.30"))]}]
    c = entrar("Natan")
    assert c.get(f"{API}/cruzamento?competencia=2026-08").json()["configurado"] is True
    p = c.get(f"{API}/cruzamento/previa?competencia=2026-08&carteira=todos").json()
    assert p["aImportar"] == 1 and p["obtidoEmLocal"] == "05/09/2026 09:00"
    (linha,) = p["empresas"][0]["linhas"]
    assert linha["chave"] == f"{eid}:NFCE" and linha["situacao"] == "novo" and linha["nova"]["valorAutor"] == "1500.25"
    assert linha["nova"]["ajQtde"] == 1 and linha["marcada"] is True

    r = c.post(f"{API}/cruzamento/aplicar", json={"token": p["token"], "linhas": [linha["chave"]]})
    assert r.status_code == 200, r.json()
    assert r.json()["resumo"]["lancamentosCriados"] == 1 and r.json()["resumo"]["ajustesCriados"] == 1
    assert r.json()["importacao"]["fonte"] == "cruzamento"
    j = c.get(f"{API}/lancamento?empresa={eid}&competencia=2026-08").json()
    nfce = next(l for l in j["linhas"] if l["tipo"]["codigo"] == "NFCE")
    assert nfce["totalQtdeAutor"] == 101

    # muda lá: a prévia mostra a versão anterior
    servidor_cruzamento["empresas"][0]["tipos"] = [_tipo_la("NFCE_AUTORIZADA", (101, "1510.25"), (1, "15.30"))]
    p = c.get(f"{API}/cruzamento/previa?competencia=2026-08&empresa={eid}").json()
    linha = p["empresas"][0]["linhas"][0]
    assert linha["situacao"] == "mudou_la" and linha["anterior"]["qtdeAutor"] == 100 and p["mudaramLa"] == 1


def test_cruzamento_erros(entrar, nova_empresa, servidor_cruzamento, opcoes):
    sem_cnpj = nova_empresa("Sem CNPJ")
    c = entrar("Natan")
    r = c.get(f"{API}/cruzamento/previa?competencia=2026-08&empresa={sem_cnpj}")
    assert r.status_code == 422 and "CNPJ" in r.json()["mensagens"][0]
    opcoes(CRUZAMENTO_API_KEY="errada-errada-errada")
    r = c.get(f"{API}/cruzamento/previa?competencia=2026-08")
    assert r.status_code == 422 and "recusou a chave" in r.json()["mensagens"][0]
    opcoes(CRUZAMENTO_URL="")
    assert c.get(f"{API}/cruzamento/previa").json()["erro"] == "nao_configurado"


# ------------------------------------------------------------------ histórico

def test_historico_com_mudancas_formatadas(entrar, nova_empresa, usuarios):
    eid = nova_empresa("Bio Seiva")
    c = entrar("Mariana")
    c.post(f"{API}/empresas/{eid}/responsavel", json={"usuarioId": usuarios["Hellen"], "inicio": "2026-09"})
    j = c.get(f"{API}/historico?empresa={eid}").json()
    reg = j["registros"][0]
    assert reg["usuario"] == "Mariana" and "Natan → Hellen" in reg["descricao"]
    mud = {m["campo"]: m for m in reg["mudancas"]}
    assert mud["responsavel"]["antes"] == "Natan" and mud["responsavel"]["depois"] == "Hellen"
    assert mud["inicio"]["depois"] == "09/2026"
    assert j["pagina"] == 1 and j["temProxima"] is False and j["filtro"]["empresa"] == eid
    assert c.get(f"{API}/historico?usuario={usuarios['Hellen']}").json()["registros"] == []
