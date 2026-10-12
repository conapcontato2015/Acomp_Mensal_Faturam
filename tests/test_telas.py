"""Telas HTML: acesso, renderização e formulários."""
import pytest
from sqlalchemy import select

from faturamento.models import Empresa
from faturamento.services import empresas as svc_emp
from faturamento.services import lancamentos as svc_lanc
from faturamento.util import (
    comp_iso,
    competencia,
    competencia_atual,
    competencia_padrao,
)

API = "/api/faturamento/v1"


@pytest.fixture()
def emp(nova_empresa):
    return nova_empresa("Bio Seiva", responsavel="Natan", cnpj="12345678000190")


def _paginas(eid):
    return ["/", "/?competencia=2026-08&carteira=todos&status=pendente", "/lancamento",
            f"/lancamento?empresa={eid}&competencia=2026-08", "/empresas", "/empresas?carteira=todos&inativas=0&busca=bio",
            "/empresas/nova", f"/empresas/{eid}", "/historico", f"/historico?empresa={eid}"]


def test_sem_sessao_redireciona_para_entrar(client, emp):
    for url in _paginas(emp.id):
        r = client.get(url)
        assert r.status_code == 302, url
        assert "/entrar" in r.headers["Location"]


def test_entrar_lista_usuarios_e_sair(client, usuarios):
    r = client.get("/entrar")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    for nome in ("Hellen", "Jaísa", "Mariana", "Natan"):
        assert nome in html
    r = client.post("/entrar?proximo=/empresas", data={"usuario_id": usuarios["Natan"].id})
    assert r.status_code == 302 and r.headers["Location"].endswith("/empresas")
    r = client.post("/entrar?proximo=http://malicioso.example", data={"usuario_id": usuarios["Natan"].id})
    assert "malicioso" not in r.headers["Location"]
    assert client.get("/sair").status_code == 302
    assert client.get("/").status_code == 302


def test_todas_as_paginas_200_logado(login, emp, tipos, usuarios):
    c = login("Natan")
    svc_lanc.salvar_mes(emp, competencia("2026-08"), [{"tipo_id": tipos["NFE_ENT"].id, "qtde_autor": 1, "valor_autor": "10"}],
                        usuarios["Natan"])
    for url in _paginas(emp.id):
        r = c.get(url)
        assert r.status_code == 200, url


def test_paginas_vazias_200(login):
    c = login("Hellen")
    for url in ("/", "/lancamento", "/empresas", "/empresas/nova", "/historico"):
        assert c.get(url).status_code == 200, url
    assert "Nenhuma empresa" in c.get("/empresas").get_data(as_text=True)
    assert "Nenhuma alteração" in c.get("/historico").get_data(as_text=True)


def test_empresa_inexistente_404(login):
    assert login("Natan").get("/empresas/9999").status_code == 404


def test_competencia_mes_invalido_na_url_nao_quebra(login, app):
    app.config["PROPAGATE_EXCEPTIONS"] = False
    assert login("Natan").get("/?competencia=2026-13").status_code == 200


# ------------------------------------------------------------------ tela de empresas

def test_listagem_empresas_conteudo(login, nova_empresa, usuarios, tipos, db):
    nova_empresa("Bio Seiva", responsavel="Natan", cnpj="12345678000190", tipos_codigos=("NFE_ENT", "NFCE"))
    ibti = nova_empresa("IBTI", responsavel="Hellen", tipos_codigos=())
    svc_emp.atualizar_empresa(ibti, usuarios["Natan"], ativa=False)
    db.session.commit()
    c = login("Natan")
    html = c.get("/empresas").get_data(as_text=True)
    assert "Integração de responsáveis: não configurada" in html
    assert "Importar responsáveis (planilha)" in html and "Importar planilha antiga" in html and "Nova empresa" in html
    assert "12.345.678/0001-90" in html
    assert '<span class="tag E">NF-e Entradas</span>' in html and '<span class="tag S">NFC-e</span>' in html
    assert "Nenhum tipo definido" in html
    assert "opacity:.55" in html  # inativa esmaecida
    assert 'aria-label="Responsável de Bio Seiva"' in html
    assert f'value="{comp_iso(competencia_padrao())}" selected' in html  # "Trocas valem a partir de"

    html = c.get("/empresas?carteira=todos&inativas=0").get_data(as_text=True)
    assert "IBTI" not in html and "Bio Seiva" in html
    html = c.get(f"/empresas?carteira={usuarios['Hellen'].id}&inativas=1").get_data(as_text=True)
    assert "IBTI" in html and "Bio Seiva" not in html
    html = c.get("/empresas?carteira=todos&busca=ibti").get_data(as_text=True)
    assert "IBTI" in html and "Bio Seiva" not in html


def test_listagem_mostra_provedor_configurado(login, app, emp):
    app.config["RESPONSAVEIS_PROVEDOR"] = "api"
    html = login("Natan").get("/empresas").get_data(as_text=True)
    assert "Integração de responsáveis: api" in html
    assert "não configurada" not in html


def test_criar_empresa_pelo_formulario(login, usuarios, tipos, db):
    c = login("Natan")
    r = c.post("/empresas/nova", data={
        "nome": "Mercadinho Milhã", "cnpj": "12.345.678/0001-90", "ativa": "1",
        "tipos": [str(tipos["NFE_ENT"].id), str(tipos["NFCE"].id)], "responsavel_id": str(usuarios["Jaísa"].id),
    })
    assert r.status_code == 302 and r.headers["Location"].endswith("/empresas")
    e = db.session.scalar(select(Empresa).where(Empresa.nome == "Mercadinho Milhã"))
    assert e.cnpj == "12345678000190" and e.ativa is True
    assert {t.codigo for t in e.tipos} == {"NFE_ENT", "NFCE"}
    assert svc_emp.responsavel_atual(e).nome == "Jaísa"
    html = c.get("/empresas").get_data(as_text=True)
    assert "Mercadinho Milhã salva." in html


def test_criar_empresa_invalida_mostra_erro_e_mantem_dados(login, emp):
    c = login("Natan")
    r = c.post("/empresas/nova", data={"nome": "Outra", "cnpj": "123"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "CNPJ deve ter 14 dígitos" in html
    assert 'value="Outra"' in html


def test_editar_empresa_pelo_formulario(login, emp, usuarios, tipos, db):
    c = login("Hellen")  # qualquer um edita o cadastro
    html = c.get(f"/empresas/{emp.id}").get_data(as_text=True)
    assert "Vale a partir da competência" in html
    assert "Meses anteriores continuam no resumo de quem cuidava na época." in html
    assert "Histórico" in html and "Empresa Bio Seiva cadastrada" in html

    r = c.post(f"/empresas/{emp.id}", data={
        "nome": "Bio Seiva Ltda", "cnpj": "12345678000190", "tipos": [str(tipos["NFE_SAI"].id)],
        "responsavel_id": str(usuarios["Mariana"].id), "inicio": "2026-09",
    })  # sem "ativa" = desmarcada
    assert r.status_code == 302
    db.session.expire_all()
    e = db.session.get(Empresa, emp.id)
    assert e.nome == "Bio Seiva Ltda" and e.ativa is False and [t.codigo for t in e.tipos] == ["NFE_SAI"]
    assert svc_emp.responsavel_em(e, competencia("2026-08")).nome == "Natan"
    assert svc_emp.responsavel_em(e, competencia("2026-09")).nome == "Mariana"

    html = c.get(f"/empresas/{emp.id}").get_data(as_text=True)
    assert "Cadastro de Bio Seiva Ltda alterado" in html
    assert "a partir de 09/2026" in html and "desde o início" in html


def test_editar_empresa_nome_duplicado(login, nova_empresa, emp):
    outra = nova_empresa("Outra")
    r = login("Natan").post(f"/empresas/{outra.id}", data={"nome": "Bio Seiva"})
    assert r.status_code == 200 and "Já existe uma empresa chamada Bio Seiva" in r.get_data(as_text=True)


def test_salvar_formulario_sem_trocar_responsavel_nao_altera_historico(login, emp, usuarios, db):
    c = login("Natan")
    atual = competencia_atual()
    c.post(f"{API}/empresas/{emp.id}/responsavel", json={"usuario_id": usuarios["Hellen"].id, "inicio": comp_iso(atual)})
    # Formulário abre com Hellen selecionada e início = competência padrão (mês anterior); usuário só muda o nome.
    c.post(f"/empresas/{emp.id}", data={"nome": "Bio Seiva 2", "ativa": "1", "responsavel_id": str(usuarios["Hellen"].id),
                                         "inicio": comp_iso(competencia_padrao())})
    db.session.expire_all()
    e = db.session.get(Empresa, emp.id)
    assert len(e.historico_responsaveis) == 2
    assert svc_emp.responsavel_em(e, competencia_padrao()).nome == "Natan"


def test_trocar_responsavel_reflete_na_listagem_e_historico(login, emp, usuarios):
    c = login("Mariana")
    r = c.post(f"{API}/empresas/{emp.id}/responsavel", json={"usuario_id": usuarios["Hellen"].id,
                                                               "inicio": comp_iso(competencia_padrao())})
    assert r.status_code == 200 and r.get_json()["alterado"] is True

    html = c.get(f"/empresas?carteira={usuarios['Hellen'].id}").get_data(as_text=True)
    assert "Bio Seiva" in html
    assert f'<option value="{usuarios["Hellen"].id}" selected>Hellen</option>' in html
    html = c.get(f"/empresas?carteira={usuarios['Natan'].id}").get_data(as_text=True)
    assert "Bio Seiva" not in html

    html = c.get(f"/historico?empresa={emp.id}").get_data(as_text=True)
    assert "Responsável de Bio Seiva: Natan → Hellen" in html
    assert "Natan → <strong>Hellen</strong>" in html  # detalhe antes → depois
    assert "Mariana" in html
    html = c.get(f"/historico?usuario={usuarios['Hellen'].id}").get_data(as_text=True)
    assert "Nenhuma alteração registrada com esses filtros" in html

    html = c.get(f"/empresas/{emp.id}").get_data(as_text=True)
    assert "Natan → Hellen" in html


def test_troca_por_planilha_mostra_origem(login, emp, usuarios, db):
    svc_emp.definir_responsavel(emp, usuarios["Hellen"], competencia_padrao(), usuarios["Natan"], origem="planilha")
    db.session.commit()
    html = login("Natan").get("/empresas?carteira=todos").get_data(as_text=True)
    assert "data-origem>Planilha</span>" in html


def test_historico_detalhe_de_lancamento(login, emp, tipos, usuarios, db):
    natan = usuarios["Natan"]
    comp = competencia("2026-08")
    linha = {"tipo_id": tipos["NFE_ENT"].id, "qtde_autor": 1, "valor_autor": "10"}
    svc_lanc.salvar_mes(emp, comp, [linha], natan)
    svc_lanc.salvar_mes(emp, comp, [{**linha, "qtde_autor": 2}], natan)
    db.session.commit()
    html = login("Natan").get("/historico").get_data(as_text=True)
    assert "Bio Seiva · 08/2026 · NF-e Entradas" in html
    assert "qtde_autor:</span> 1 → <strong>2</strong>" in html


def test_arquivos_estaticos_sao_servidos(client):
    """CSS, JS e logo precisam responder 200 (o blueprint aponta para static/faturamento)."""
    for caminho in ("css/app.css", "js/app.js", "js/lancamento.js", "js/conferencia.js", "img/logo-conap-branco.png"):
        r = client.get(f"/static/faturamento/{caminho}")
        assert r.status_code == 200, caminho
