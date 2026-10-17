"""Empresas, carteira, tipos de documento e cadastro vindo do Conap Ferramentas (fonte "plataforma")."""
from __future__ import annotations

import sqlite3

import pytest

from faturamento.services import empresas_plataforma as svc_plat

from .conftest import API


def test_criar_listar_e_alterar_empresa(entrar, usuarios, tipos):
    c = entrar("Natan")
    r = c.post(f"{API}/empresas", json={"nome": "Mercadinho X", "cnpj": "12.345.678/0001-90",
                                        "tipos": [tipos["NFCE"]], "responsavelId": usuarios["Hellen"]})
    assert r.status_code == 201, r.json()
    e = r.json()["empresa"]
    assert e["cnpjFormatado"] == "12.345.678/0001-90" and e["responsavel"]["nome"] == "Hellen"

    j = c.get(f"{API}/empresas").json()
    assert j["carteira"] == "todos" and j["fontePlataforma"] is False
    (linha,) = j["empresas"]
    assert linha["origem"] == "manual" and [t["nome"] for t in linha["tipos"]] == ["NFC-e"]

    r = c.put(f"{API}/empresas/{e['id']}", json={"nome": "Mercadinho X (Matriz)", "ativa": False,
                                                 "tipos": [tipos["NFCE"], tipos["NFE_SAI"]]})
    assert r.status_code == 200 and r.json()["empresa"]["nome"] == "Mercadinho X (Matriz)"
    assert c.get(f"{API}/empresas?inativas=false").json()["empresas"] == []

    d = c.get(f"{API}/empresas/{e['id']}").json()
    assert d["empresa"]["ativa"] is False and set(d["empresa"]["tipos"]) == {tipos["NFCE"], tipos["NFE_SAI"]}
    assert d["historicoResponsaveis"][0]["desdeOInicio"] is True
    assert any("alterado" in h["descricao"] for h in d["historico"])


@pytest.mark.parametrize("corpo, msg", [({"nome": ""}, "Informe o nome"), ({"nome": "A", "cnpj": "123"}, "14 dígitos")])
def test_criar_empresa_invalida_422(entrar, corpo, msg):
    r = entrar().post(f"{API}/empresas", json=corpo)
    assert r.status_code == 422 and msg in r.json()["mensagens"][0]


def test_trocar_responsavel_a_partir_da_competencia(entrar, nova_empresa, usuarios):
    eid = nova_empresa("Bio Seiva")
    c = entrar("Mariana")  # qualquer usuário pode trocar
    r = c.post(f"{API}/empresas/{eid}/responsavel", json={"usuarioId": usuarios["Hellen"], "inicio": "2026-09"})
    assert r.json()["alterado"] is True and r.json()["empresa"]["responsavel"]["nome"] == "Hellen"
    r = c.post(f"{API}/empresas/{eid}/responsavel", json={"usuarioId": usuarios["Hellen"], "inicio": "2026-09"})
    assert r.json()["alterado"] is False
    # agosto continua do Natan
    j = c.get(f"{API}/painel?competencia=2026-08&carteira={usuarios['Natan']}").json()
    assert [e["empresa"]["id"] for e in j["empresas"]] == [eid]
    assert c.post(f"{API}/empresas/{eid}/responsavel", json={"usuarioId": 999}).status_code == 400


def test_tipos_de_documento(entrar):
    c = entrar()
    r = c.post(f"{API}/tipos-documento", json={"nome": "Recebimento de caixa", "sentido": "O"})
    assert r.status_code == 201 and r.json()["tipo"]["sentidoNome"] == "Outros"
    tid = r.json()["tipo"]["id"]
    j = c.get(f"{API}/tipos-documento?todos=true").json()
    novo = next(t for t in j["tipos"] if t["id"] == tid)
    assert novo["uso"] == {"empresas": 0, "lancamentos": 0}
    assert c.put(f"{API}/tipos-documento/{tid}", json={"ativo": False}).json()["tipo"]["ativo"] is False
    assert all(t["id"] != tid for t in c.get(f"{API}/tipos-documento").json()["tipos"])
    assert c.post(f"{API}/tipos-documento", json={"nome": "nfc-e", "sentido": "S"}).status_code == 422  # repetido


# ------------------------------------------------------------------ cadastro do Conap Ferramentas

@pytest.fixture()
def base_plataforma(tmp_path, opcoes):
    """Cadastro geral simulado (SQLite) com nomes de coluna diferentes, ligado como fonte de empresas."""
    caminho = tmp_path / "plataforma.db"
    con = sqlite3.connect(caminho)
    con.executescript("""
        CREATE TABLE clientes (codigo INTEGER PRIMARY KEY, razao_social TEXT, documento TEXT, situacao TEXT);
        INSERT INTO clientes VALUES (10, 'MERCADINHO ALFA', '12.345.678/0001-90', 'A');
        INSERT INTO clientes VALUES (11, 'PADARIA BETA LTDA', NULL, 'A');
        INSERT INTO clientes VALUES (12, 'LOJA NOVA', '98.765.432/0001-10', 'I');
    """)
    con.commit()
    con.close()
    opcoes(EMPRESAS_FONTE="plataforma", PLATAFORMA_DATABASE_URL=f"sqlite:///{caminho.as_posix()}",
           PLATAFORMA_EMPRESAS_TABELA="clientes",
           PLATAFORMA_EMPRESAS_COLUNAS="id=codigo;nome=razao_social;cnpj=documento;ativa=situacao")
    return caminho


def test_ler_cadastro_da_plataforma_com_colunas_mapeadas(app, base_plataforma):
    dados = svc_plat.ler_empresas()
    assert dados == [
        {"id": "10", "nome": "MERCADINHO ALFA", "cnpj": "12345678000190", "ativa": True},
        {"id": "11", "nome": "PADARIA BETA LTDA", "cnpj": None, "ativa": True},
        {"id": "12", "nome": "LOJA NOVA", "cnpj": "98765432000110", "ativa": False},
    ]


def test_coluna_ou_tabela_com_nome_perigoso_e_recusada():
    with pytest.raises(Exception, match="inválido"):
        svc_plat.mapa_colunas("nome=razao_social) FROM x --")
    with pytest.raises(Exception, match="inválido"):
        svc_plat._tabela("clientes;--")


def test_sincronizar_previa_e_aplicar(entrar, nova_empresa, usuarios, base_plataforma, opcoes):
    opcoes(EMPRESAS_FONTE="local")
    alfa = nova_empresa("Mercadinho Alfa", cnpj="12345678000190")
    beta = nova_empresa("Padaria Beta Ltda")
    so_aqui = nova_empresa("Só Aqui")
    opcoes(EMPRESAS_FONTE="plataforma")
    c = entrar("Natan")

    r = c.post(f"{API}/empresas/plataforma/sincronizar", json={})
    rel = r.json()["relatorio"]
    assert r.json()["aplicado"] is False and rel["lidas"] == 3
    assert rel["vinculadas"] == ["Mercadinho Alfa (pelo CNPJ)", "Padaria Beta Ltda (pelo nome)"]
    assert rel["casadasPeloNome"] == ["Padaria Beta Ltda ↔ PADARIA BETA LTDA"]
    assert rel["novas"] == ["LOJA NOVA · 98765432000110"] and rel["soAqui"] == ["Só Aqui"]
    assert c.get(f"{API}/empresas/{alfa}").json()["empresa"]["externalId"] is None  # prévia não grava

    r = c.post(f"{API}/empresas/plataforma/sincronizar",
               json={"aplicar": True, "criarNovas": True, "responsavelId": usuarios["Hellen"]})
    assert r.json()["aplicado"] is True and r.json()["relatorio"]["criadas"] == ["Loja Nova"]
    assert c.get(f"{API}/empresas/{alfa}").json()["empresa"]["externalId"] == "plat:10"
    assert c.get(f"{API}/empresas/{beta}").json()["empresa"]["externalId"] == "plat:11"
    nova = next(e for e in c.get(f"{API}/empresas").json()["empresas"] if e["nome"] == "Loja Nova")
    assert nova["externalId"] == "plat:12" and nova["ativa"] is False and nova["responsavel"]["nome"] == "Hellen"
    assert c.post(f"{API}/empresas/plataforma/sincronizar", json={}).json()["relatorio"]["semMudanca"] == 3
    assert so_aqui  # continua aqui, só listada


def test_com_fonte_plataforma_cadastro_nao_e_editado_aqui(entrar, nova_empresa, tipos, base_plataforma, opcoes):
    opcoes(EMPRESAS_FONTE="local")
    eid = nova_empresa("Mercadinho Alfa", cnpj="12345678000190")
    opcoes(EMPRESAS_FONTE="plataforma")
    c = entrar("Natan")
    r = c.post(f"{API}/empresas", json={"nome": "Nova"})
    assert r.status_code == 422 and "Conap Ferramentas" in r.json()["mensagens"][0]
    r = c.put(f"{API}/empresas/{eid}", json={"nome": "Outro nome"})
    assert r.status_code == 422
    # tipos usados e responsável continuam sendo do faturamento
    r = c.put(f"{API}/empresas/{eid}", json={"nome": "Mercadinho Alfa", "tipos": [tipos["NFCE"]]})
    assert r.status_code == 200 and r.json()["empresa"]["tipos"] == [tipos["NFCE"]]
    assert c.get(f"{API}/empresas").json()["fontePlataforma"] is True
