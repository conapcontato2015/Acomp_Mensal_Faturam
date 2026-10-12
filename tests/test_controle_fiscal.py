"""Integração (só leitura) com o banco do Controle Fiscal.

O banco do Controle Fiscal é simulado por um arquivo SQLite com as tabelas ``empresa`` e
``responsavel`` iguais às do outro sistema (app/models.py dele).
"""
from __future__ import annotations

import hashlib
import sqlite3

import pytest
from sqlalchemy import select

from config import _normalizar_url
from faturamento.models import ORIGEM_INTEGRACAO, Auditoria, Empresa, EmpresaResponsavel
from faturamento.responsaveis import ProvedorControleFiscal, ler_mapa_responsaveis, provedor_configurado
from faturamento.services import controle_fiscal as svc_cf
from faturamento.services import empresas as svc_emp
from faturamento.util import competencia

from conftest import TOKEN_CSRF

ESQUEMA = """
CREATE TABLE responsavel (id INTEGER PRIMARY KEY, nome VARCHAR(80) NOT NULL UNIQUE,
                          ordem INTEGER NOT NULL DEFAULT 0, ativo BOOLEAN NOT NULL DEFAULT 1);
CREATE TABLE regime (id INTEGER PRIMARY KEY, nome VARCHAR(60) NOT NULL UNIQUE);
CREATE TABLE empresa (id INTEGER PRIMARY KEY, codigo VARCHAR(10) NOT NULL UNIQUE, razao_social VARCHAR(160) NOT NULL,
                      cnpj VARCHAR(20), regime_id INTEGER NOT NULL REFERENCES regime(id),
                      responsavel_id INTEGER REFERENCES responsavel(id), sem_movimento BOOLEAN NOT NULL DEFAULT 0,
                      ativo BOOLEAN NOT NULL DEFAULT 1, observacao TEXT);
"""


@pytest.fixture()
def banco_cf(tmp_path, app):
    """Cria o banco falso do Controle Fiscal e liga FOLHA_DATABASE_URL nele.

    banco_cf.empresa(codigo, razao, cnpj=None, resp=None, ativo=True) adiciona uma linha.
    """
    caminho = tmp_path / "controle_fiscal.db"
    con = sqlite3.connect(caminho)
    con.executescript(ESQUEMA)
    con.execute("INSERT INTO regime (id, nome) VALUES (1, 'Simples Nacional')")
    con.commit()

    class Banco:
        path = caminho
        ids = {}

        def responsavel(self, nome):
            if nome not in self.ids:
                cur = con.execute("INSERT INTO responsavel (nome, ordem, ativo) VALUES (?, 0, 1)", (nome,))
                con.commit()
                self.ids[nome] = cur.lastrowid
            return self.ids[nome]

        def empresa(self, codigo, razao, cnpj=None, resp=None, ativo=True, sem_movimento=False):
            rid = self.responsavel(resp) if resp else None
            con.execute("INSERT INTO empresa (codigo, razao_social, cnpj, regime_id, responsavel_id, sem_movimento, ativo) "
                        "VALUES (?, ?, ?, 1, ?, ?, ?)", (codigo, razao, cnpj, rid, sem_movimento, ativo))
            con.commit()

        def hash(self):
            return hashlib.sha256(self.path.read_bytes()).hexdigest()

    app.config["FOLHA_DATABASE_URL"] = f"sqlite:///{caminho.as_posix()}"
    app.config["FOLHA_MAPA_RESPONSAVEIS"] = ""
    yield Banco()
    con.close()


INICIO = competencia("2026-09")


def _sinc(aplicar=False, usuario=None, inicio=INICIO):
    return svc_cf.sincronizar(svc_cf.provedor(), usuario, inicio=inicio, aplicar=aplicar)


# ---------------------------------------------------------------------------------------- serviço

def test_previa_nao_altera_nada(banco_cf, nova_empresa, db):
    e = nova_empresa("Mercadinho Milhã", responsavel="Natan")
    banco_cf.empresa("101", "MERCADINHO MILHA", cnpj="12.345.678/0001-90", resp="Hellen")
    antes_aud = db.session.query(Auditoria).count()
    rel = _sinc(aplicar=False)
    db.session.rollback()
    assert rel.trocas == ["Mercadinho Milhã: Natan → Hellen"]
    assert rel.cnpjs_preenchidos and rel.codigos_vinculados
    db.session.expire_all()
    e = db.session.get(Empresa, e.id)
    assert e.cnpj is None and e.external_id is None
    assert svc_emp.responsavel_atual(e).nome == "Natan"
    assert db.session.query(Auditoria).count() == antes_aud


def test_aplicar_troca_responsavel_com_origem_integracao(banco_cf, nova_empresa, usuarios, db):
    e = nova_empresa("Bio Seiva", responsavel="Natan", cnpj="11222333000144")
    banco_cf.empresa("7", "BIO SEIVA LTDA", cnpj="11.222.333/0001-44", resp="Jaísa")
    rel = _sinc(aplicar=True, usuario=usuarios["Natan"])
    db.session.commit()
    assert rel.trocas == ["Bio Seiva: Natan → Jaísa"] and not rel.casadas_pelo_nome
    assert svc_emp.responsavel_em(e, INICIO).nome == "Jaísa"
    assert svc_emp.responsavel_em(e, competencia("2026-08")).nome == "Natan"
    vinc = db.session.scalar(select(EmpresaResponsavel).where(EmpresaResponsavel.empresa_id == e.id,
                                                               EmpresaResponsavel.inicio == INICIO))
    assert vinc.origem == ORIGEM_INTEGRACAO
    assert e.external_id == "cf:7"
    descricoes = [a.descricao for a in db.session.scalars(select(Auditoria).where(Auditoria.empresa_id == e.id))]
    assert any("Controle Fiscal" in d and "Jaísa" in d for d in descricoes)
    assert any("Controle Fiscal" in d and "Cadastro" in d for d in descricoes)
    # rodar de novo não muda nada
    rel2 = _sinc(aplicar=True, usuario=usuarios["Natan"])
    assert rel2.trocas == [] and rel2.sem_mudanca == 1 and not rel2.tem_alteracoes


def test_casa_por_cnpj_e_por_nome_sinalizando(banco_cf, nova_empresa):
    nova_empresa("Nome Diferente Aqui", responsavel="Natan", cnpj="11222333000144")
    nova_empresa("Padaria Pão Quente", responsavel="Natan")
    banco_cf.empresa("1", "OUTRO NOME LÁ", cnpj="11222333000144", resp="Natan")
    banco_cf.empresa("2", "PADARIA PAO QUENTE", resp="Natan")
    rel = _sinc()
    assert rel.sem_mudanca == 2 and rel.nao_encontradas == []
    assert len(rel.casadas_pelo_nome) == 1
    assert "Padaria Pão Quente" in rel.casadas_pelo_nome[0] and "casada pelo nome — confira" in rel.casadas_pelo_nome[0]


def test_cnpj_preenchido_so_quando_vazio_e_divergente_listado(banco_cf, nova_empresa, usuarios, db):
    vazia = nova_empresa("Loja Vazia", responsavel="Natan")
    cheia = nova_empresa("Loja Cheia", responsavel="Natan", cnpj="99888777000166")
    banco_cf.empresa("1", "LOJA VAZIA", cnpj="11.222.333/0001-44", resp="Natan")
    banco_cf.empresa("2", "LOJA CHEIA", cnpj="55.444.333/0001-22", resp="Natan")
    rel = _sinc(aplicar=True, usuario=usuarios["Natan"])
    db.session.commit()
    assert rel.cnpjs_preenchidos == ["Loja Vazia: 11.222.333/0001-44"]
    assert len(rel.cnpj_divergente) == 1 and "Loja Cheia" in rel.cnpj_divergente[0]
    assert vazia.cnpj == "11222333000144"
    assert cheia.cnpj == "99888777000166"  # nunca sobrescreve


def test_ativo_divergente_listado_e_nao_aplicado(banco_cf, nova_empresa, usuarios, db):
    e = nova_empresa("Fechada Lá", responsavel="Natan", cnpj="11222333000144")
    banco_cf.empresa("1", "FECHADA LA", cnpj="11222333000144", resp="Natan", ativo=False, sem_movimento=True)
    rel = _sinc(aplicar=True, usuario=usuarios["Natan"])
    db.session.commit()
    assert rel.ativa_divergente == ["Fechada Lá: inativa no Controle Fiscal e ativa aqui"]
    assert e.ativa is True


def test_mapa_de_nomes_e_responsavel_desconhecido(banco_cf, nova_empresa, app):
    nova_empresa("Empresa A", responsavel="Hellen", cnpj="11222333000144")
    nova_empresa("Empresa B", responsavel="Hellen", cnpj="55444333000122")
    nova_empresa("Empresa C", responsavel="Hellen", cnpj="66555444000133")
    banco_cf.empresa("1", "EMPRESA A", cnpj="11222333000144", resp="NATAN LIMA")
    banco_cf.empresa("2", "EMPRESA B", cnpj="55444333000122", resp="Fulano de Tal")
    banco_cf.empresa("3", "EMPRESA C", cnpj="66555444000133", resp=None)
    banco_cf.empresa("4", "SÓ LÁ", cnpj="77666555000144", resp="Natan")
    app.config["FOLHA_MAPA_RESPONSAVEIS"] = "Natan Lima=Natan; Outro = Mariana"
    rel = _sinc()
    assert rel.trocas == ["Empresa A: Hellen → Natan"]
    assert rel.responsaveis_sem_correspondencia == ["Fulano de Tal (Empresa B)"]
    assert rel.sem_responsavel_la == ["Empresa C"]
    assert rel.so_no_controle_fiscal == 1


def test_empresa_daqui_nao_encontrada_la(banco_cf, nova_empresa):
    nova_empresa("Só Aqui", responsavel="Natan")
    banco_cf.empresa("1", "OUTRA", resp="Natan")
    rel = _sinc()
    assert rel.nao_encontradas == ["Só Aqui"] and rel.so_no_controle_fiscal == 1


def test_ler_mapa_responsaveis():
    assert ler_mapa_responsaveis("Natan Lima=Natan; Jaisa  Souza = Jaísa;lixo;=x") == {
        "NATAN LIMA": "Natan", "JAISA SOUZA": "Jaísa"}
    assert ler_mapa_responsaveis("") == {}


def test_url_postgres_normalizada():
    assert _normalizar_url("postgresql://u:s@localhost:5432/cf") == "postgresql+psycopg://u:s@localhost:5432/cf"
    assert _normalizar_url("postgres://u:s@h/cf") == "postgresql+psycopg://u:s@h/cf"
    assert _normalizar_url("") == ""


def test_falha_de_conexao_vira_erro_amigavel(app, tmp_path):
    prov = ProvedorControleFiscal(f"sqlite:///{(tmp_path / 'nao' / 'existe.db').as_posix()}")
    rel = svc_cf.sincronizar(prov, None)
    assert rel.erros and "Não foi possível conectar ao banco do Controle Fiscal" in rel.erros[0]
    assert "FOLHA_DATABASE_URL" in rel.erros[0]
    rel = svc_cf.sincronizar(ProvedorControleFiscal("isto nao e uma url"), None)
    assert rel.erros and "endereço inválido" in rel.erros[0]


def test_provedor_configurado_controle_fiscal(app, banco_cf):
    app.config["RESPONSAVEIS_PROVEDOR"] = "controle_fiscal"
    prov = provedor_configurado()
    assert isinstance(prov, ProvedorControleFiscal) and prov.nome == "controle_fiscal"
    assert prov.origem == ORIGEM_INTEGRACAO


def test_provedor_traz_codigo_e_ativo(banco_cf, app):
    banco_cf.empresa("42", "ALFA", cnpj="11.222.333/0001-44", resp="Natan", ativo=False)
    [a] = svc_cf.provedor().buscar()
    assert (a.codigo, a.ativo, a.cnpj, a.empresa, a.responsavel) == ("42", False, "11222333000144", "ALFA", "Natan")


def test_somente_leitura_banco_intacto(banco_cf, nova_empresa, usuarios, db):
    nova_empresa("Loja Vazia", responsavel="Natan")
    banco_cf.empresa("1", "LOJA VAZIA", cnpj="11.222.333/0001-44", resp="Hellen", ativo=False)
    antes = banco_cf.hash()
    rel = _sinc(aplicar=True, usuario=usuarios["Natan"])
    db.session.commit()
    assert rel.trocas and rel.cnpjs_preenchidos
    assert banco_cf.hash() == antes


def test_sessao_somente_leitura_recusa_escrita(banco_cf):
    """O motor do provedor abre o arquivo em modo só leitura: escrita é recusada."""
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError
    eng = svc_cf.provedor()._engine()
    try:
        with eng.connect() as conn, pytest.raises(OperationalError):
            conn.execute(text("DELETE FROM empresa"))
    finally:
        eng.dispose()


# ---------------------------------------------------------------------------------------- telas

def test_banner_nao_configurado(login, app):
    app.config["FOLHA_DATABASE_URL"] = ""
    html = login("Natan").get("/empresas").get_data(as_text=True)
    assert "Controle Fiscal: não configurado" in html and "FOLHA_DATABASE_URL" in html
    assert "Sincronizar com o Controle Fiscal" not in html
    assert "/empresas/importar-responsaveis" in html


def test_banner_configurado(login, banco_cf):
    html = login("Natan").get("/empresas").get_data(as_text=True)
    assert "Controle Fiscal: configurado" in html and "Sincronizar com o Controle Fiscal" in html
    assert "/empresas/controle-fiscal" in html


def test_pagina_sem_configuracao(login, app):
    app.config["FOLHA_DATABASE_URL"] = ""
    r = login("Natan").get("/empresas/controle-fiscal")
    assert r.status_code == 200 and "não configurado" in r.get_data(as_text=True)


def test_telas_previa_e_aplicar(login, banco_cf, nova_empresa, db):
    e = nova_empresa("Mercadinho Milhã", responsavel="Natan")
    banco_cf.empresa("101", "MERCADINHO MILHA", cnpj="12.345.678/0001-90", resp="Hellen", ativo=False)
    c = login("Natan")
    html = c.get("/empresas/controle-fiscal").get_data(as_text=True)
    assert "Trocas valem a partir de" in html and "Ver prévia" in html and 'name="csrf_token"' in html

    r = c.post("/empresas/controle-fiscal", data={"csrf_token": TOKEN_CSRF, "inicio": "2026-09"})
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "Natan → Hellen" in html and "12.345.678/0001-90" in html
    assert "casada pelo nome — confira" in html and "inativa no Controle Fiscal e ativa aqui" in html
    assert "/empresas/controle-fiscal/aplicar" in html
    db.session.expire_all()
    assert db.session.get(Empresa, e.id).cnpj is None  # prévia não grava

    # sem CSRF: recusado
    assert c.post("/empresas/controle-fiscal/aplicar", data={"inicio": "2026-09"}).status_code == 400

    r = c.post("/empresas/controle-fiscal/aplicar", data={"csrf_token": TOKEN_CSRF, "inicio": "2026-09"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/empresas")
    html = c.get("/empresas").get_data(as_text=True)
    assert "Controle Fiscal sincronizado: 1 responsável(is) trocado(s) a partir de 09/2026" in html
    db.session.expire_all()
    e = db.session.get(Empresa, e.id)
    assert e.cnpj == "12345678000190" and e.ativa is True
    assert svc_emp.responsavel_em(e, INICIO).nome == "Hellen"


def test_tela_erro_de_conexao_sem_500(login, app, tmp_path):
    app.config["FOLHA_DATABASE_URL"] = f"sqlite:///{(tmp_path / 'nao' / 'existe.db').as_posix()}"
    c = login("Natan")
    r = c.post("/empresas/controle-fiscal", data={"csrf_token": TOKEN_CSRF, "inicio": "2026-09"})
    assert r.status_code == 200
    assert "Não foi possível conectar ao banco do Controle Fiscal" in r.get_data(as_text=True)
    r = c.post("/empresas/controle-fiscal/aplicar", data={"csrf_token": TOKEN_CSRF, "inicio": "2026-09"})
    assert r.status_code == 302
    html = c.get(r.headers["Location"]).get_data(as_text=True)
    assert "Não foi possível conectar ao banco do Controle Fiscal" in html


def test_competencia_invalida_na_previa(login, banco_cf):
    r = login("Natan").post("/empresas/controle-fiscal", data={"csrf_token": TOKEN_CSRF, "inicio": "xx"})
    assert r.status_code == 302
