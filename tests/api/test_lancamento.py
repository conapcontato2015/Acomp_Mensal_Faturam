"""Lançamento pela API: números, ajustes, "bateu", sem movimento e carteira de outra pessoa."""
from __future__ import annotations

import pytest

from .conftest import API

H = {"X-Requested-With": "fetch"}  # DELETE sem corpo, como o front envia


@pytest.fixture()
def emp(nova_empresa):
    return nova_empresa("Bio Seiva", responsavel="Natan", tipos_codigos=("NFE_ENT", "NFE_SAI"))


def _linha(tipo_id, qa, va, qc=None, vc=None):
    return {"tipoId": tipo_id, "qtdeAutor": qa, "valorAutor": va, "qtdeCanc": qc, "valorCanc": vc}


def test_inicio_lista_minha_carteira_com_status_e_as_outras(entrar, nova_empresa):
    nova_empresa("Minha A", responsavel="Natan")
    nova_empresa("Dela B", responsavel="Hellen")
    j = entrar("Natan").get(f"{API}/lancamento/inicio?competencia=2026-08").json()
    assert [(e["nome"], e["status"]) for e in j["minhas"]] == [("Minha A", "pendente")]
    assert [e["nome"] for e in j["outras"]] == ["Dela B"]
    assert j["competencia"]["valor"] == "2026-08"


def test_gravar_e_ler_lancamentos(entrar, emp, tipos):
    c = entrar("Natan")
    r = c.put(f"{API}/lancamento/{emp}/2026-08", json={"linhas": [
        _linha(tipos["NFE_ENT"], "10", "1.234,56"), _linha(tipos["NFE_SAI"], 3, 300, "5", "500")]})
    assert r.status_code == 200, r.json()
    j = r.json()
    assert j["alterados"] == 2 and j["status"] == "preenchido" and len(j["avisos"]) == 1  # mais canceladas

    j = c.get(f"{API}/lancamento?empresa={emp}&competencia=2026-08").json()
    assert j["competencia"]["valor"] == "2026-08" and j["podeEditar"] is True and j["futura"] is False
    assert j["responsavel"]["nome"] == "Natan" and j["empresa"]["nome"] == "Bio Seiva"
    ent = next(l for l in j["linhas"] if l["tipo"]["codigo"] == "NFE_ENT")
    assert ent["qtdeAutor"] == 10 and ent["valorAutor"] == "1234.56" and ent["totalValorAutor"] == "1234.56"
    assert len(j["evolucao"]) == 8 and len(j["grafico"]) == 8 and j["alturaGrafico"] == 180
    assert j["evolucao"][-1]["entradas"] == "1234.56" and j["evolucao"][-1]["competencia"]["rotulo"] == "Ago/26"


def test_gravar_invalido_422_e_nada_gravado(entrar, emp, tipos):
    c = entrar("Natan")
    r = c.put(f"{API}/lancamento/{emp}/2026-08", json={"linhas": [
        _linha(tipos["NFE_ENT"], "10", "100"), _linha(tipos["NFE_SAI"], None, "300")]})
    assert r.status_code == 422 and r.json()["erro"] == "regra_violada"
    assert "quantidade e valor juntos" in r.json()["mensagens"][0]
    j = c.get(f"{API}/lancamento?empresa={emp}&competencia=2026-08").json()
    assert all(l["id"] is None for l in j["linhas"])


def test_competencia_invalida_400_e_empresa_inexistente_404(entrar, emp):
    c = entrar("Natan")
    assert c.put(f"{API}/lancamento/{emp}/agosto", json={"linhas": []}).status_code == 400
    assert c.get(f"{API}/lancamento?empresa={emp}&competencia=xx").status_code == 400
    r = c.put(f"{API}/lancamento/9999/2026-08", json={"linhas": []})
    assert r.status_code == 404 and r.json()["erro"] == "nao_encontrado"


def test_ajustes_e_bateu_com_aviso_de_empresa_completa(entrar, emp, tipos):
    c = entrar("Natan")
    tid = tipos["NFE_ENT"]
    c.put(f"{API}/lancamento/{emp}/2026-08", json={"linhas": [_linha(tid, 10, "1000")]})

    r = c.post(f"{API}/lancamento/{emp}/2026-08/{tid}/ajustes", json={"grupo": "AUTOR", "qtde": "2", "valor": "200,00"})
    assert r.status_code == 201, r.json()
    j = r.json()
    assert j["ajuste"]["motivo"].startswith("Arquivos a mais") and j["ajuste"]["criadoPor"]["nome"] == "Natan"
    assert j["linha"]["totalQtdeAutor"] == 12 and j["linha"]["totalValorAutor"] == "1200.00"
    assert j["linha"]["ajusteCurto"] == "+2 · 200,00" and "Inclui ajuste" in j["linha"]["dicaAjuste"]
    lid, aid = j["linha"]["id"], j["ajuste"]["id"]

    r = c.post(f"{API}/lancamento/{emp}/2026-08/{tid}/ajustes", json={"qtde": 1, "valor": 1, "motivo": "Outro"})
    assert r.status_code == 422  # "Outro" exige observação

    r = c.put(f"{API}/lancamentos/{lid}/bateu", json={"bateu": True})
    assert r.json() == {"id": lid, "bateu": True, "empresa": {"linhas": 1, "bateram": 1}}  # -> confetes

    # travado: números, ajustes e remoção recusados
    r = c.put(f"{API}/lancamento/{emp}/2026-08", json={"linhas": [_linha(tid, 11, "1100")]})
    assert r.status_code == 422 and "Bateu" in r.json()["mensagens"][0]
    assert c.post(f"{API}/lancamento/{emp}/2026-08/{tid}/ajustes", json={"qtde": 1, "valor": 1}).status_code == 422
    assert c.delete(f"{API}/ajustes/{aid}", headers=H).status_code == 422

    c.put(f"{API}/lancamentos/{lid}/bateu", json={"bateu": False})
    r = c.delete(f"{API}/ajustes/{aid}", headers=H)
    assert r.status_code == 200 and r.json()["linha"]["ajustes"] == []


def test_ajuste_cria_lancamento_se_nao_existe(entrar, emp, tipos):
    c = entrar("Natan")
    r = c.post(f"{API}/lancamento/{emp}/2026-08/{tipos['NFE_SAI']}/ajustes", json={"qtde": 1, "valor": "10"})
    assert r.status_code == 201
    assert r.json()["linha"]["qtdeAutor"] is None and r.json()["linha"]["totalQtdeAutor"] == 1


def test_outra_carteira_403_e_substituto(entrar, emp, tipos):
    c = entrar("Natan")
    c.put(f"{API}/lancamento/{emp}/2026-08", json={"linhas": [_linha(tipos["NFE_ENT"], 1, "10")]})
    lid = c.get(f"{API}/lancamento?empresa={emp}&competencia=2026-08").json()["linhas"][0]["id"]

    c = entrar("Hellen")
    assert c.get(f"{API}/lancamento?empresa={emp}&competencia=2026-08").json()["podeEditar"] is False  # pode ver
    for r in (
        c.put(f"{API}/lancamento/{emp}/2026-08", json={"linhas": [_linha(tipos["NFE_ENT"], 2, "20")]}),
        c.post(f"{API}/lancamento/{emp}/2026-08/{tipos['NFE_ENT']}/ajustes", json={"qtde": 1, "valor": 1}),
        c.put(f"{API}/lancamentos/{lid}/bateu", json={"bateu": True}),
        c.put(f"{API}/fechamento/{emp}/2026-08", json={"status": "pendente"}),
        c.put(f"{API}/conferencia/{emp}/2026-08/bateu", json={"bateu": True}),
    ):
        assert r.status_code == 403 and r.json()["erro"] == "somente_leitura"
        assert "somente leitura" in r.json()["mensagens"][0]

    r = c.put(f"{API}/lancamento/{emp}/2026-08", json={"linhas": [_linha(tipos["NFE_ENT"], 2, "20")], "substituto": True})
    assert r.status_code == 200 and r.json()["alterados"] == 1


def test_fechamento_sem_movimento(entrar, emp, tipos):
    c = entrar("Natan")
    assert c.put(f"{API}/fechamento/{emp}/2026-08", json={"status": "sem_movimento"}).json() == {"status": "sem_movimento"}
    assert c.put(f"{API}/fechamento/{emp}/2026-08", json={"status": "xx"}).status_code == 400
    c.put(f"{API}/lancamento/{emp}/2026-08", json={"linhas": [_linha(tipos["NFE_ENT"], 1, "10")]})
    assert c.get(f"{API}/lancamento?empresa={emp}&competencia=2026-08").json()["status"] == "preenchido"
    assert c.put(f"{API}/fechamento/{emp}/2026-08", json={"status": "sem_movimento"}).status_code == 422
    assert c.put(f"{API}/fechamento/{emp}/agosto", json={"status": "pendente"}).status_code == 400


def test_bateu_da_empresa_inteira(entrar, emp, tipos):
    c = entrar("Natan")
    c.put(f"{API}/lancamento/{emp}/2026-08", json={"linhas": [_linha(tipos["NFE_ENT"], 1, "10"),
                                                               _linha(tipos["NFE_SAI"], 2, "20")]})
    r = c.put(f"{API}/conferencia/{emp}/2026-08/bateu", json={"bateu": True})
    assert r.json() == {"alterados": 2, "empresa": {"linhas": 2, "bateram": 2}}


def test_proxima_empresa_da_carteira(entrar, nova_empresa):
    a = nova_empresa("Alfa")
    nova_empresa("Beta")
    j = entrar("Natan").get(f"{API}/lancamento?empresa={a}&competencia=2026-08").json()
    assert j["proxima"]["nome"] == "Beta" and [e["nome"] for e in j["minhas"]] == ["Alfa", "Beta"]
