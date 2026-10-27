"""Importações pela API: Controle Fiscal, cruzamento Domínio × SEFAZ e histórico (sem XLSX).

Bancos e respostas sintéticos — nenhum dado de cliente.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from .conftest import API

@pytest.fixture(autouse=True)
def dados_tmp(app, tmp_path, opcoes):
    opcoes(DADOS_DIR=tmp_path)
    return tmp_path


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


def test_controle_fiscal_sem_acesso_ao_banco_explica_sem_erro_500(entrar, tmp_path, opcoes):
    c = entrar("Natan")
    opcoes(FOLHA_DATABASE_URL=f"sqlite:///{(tmp_path / 'nao' / 'existe.db').as_posix()}")
    r = c.post(f"{API}/controle-fiscal", json={"inicio": "2026-09"})
    assert r.status_code == 200
    assert r.json()["aplicado"] is False and r.json()["relatorio"]["erros"]


@pytest.mark.parametrize("rota", ["/importacoes/previa", "/importacoes/confirmar", "/importacoes/descartar",
                                  "/responsaveis/previa", "/responsaveis/confirmar"])
def test_nao_ha_importacao_de_xlsx(entrar, rota):
    """A carga inicial é feita fora do sistema: as rotas de upload de planilha não existem mais."""
    c = entrar()
    assert c.post(API + rota, json={"token": "x"}).status_code in (404, 405)
    assert c.get(API + "/responsaveis/modelo.csv").status_code == 404
