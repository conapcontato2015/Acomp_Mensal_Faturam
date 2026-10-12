"""Telas HTML: acesso, renderização e formulários."""
import pytest

from conftest import TOKEN_CSRF
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


def test_entrar_lista_usuarios_e_sair(client, usuarios, csrf):
    r = client.get("/entrar")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    for nome in ("Hellen", "Jaísa", "Mariana", "Natan"):
        assert nome in html
    tok = csrf(client)
    r = client.post("/entrar?proximo=/empresas", data={"usuario_id": usuarios["Natan"].id, "csrf_token": tok})
    assert r.status_code == 302 and r.headers["Location"].endswith("/empresas")
    r = client.post("/entrar?proximo=http://malicioso.example", data={"usuario_id": usuarios["Natan"].id, "csrf_token": tok})
    assert "malicioso" not in r.headers["Location"]
    assert client.get("/sair").status_code == 302          # GET não desloga
    assert client.get("/").status_code == 200
    assert client.post("/sair", data={"csrf_token": tok}).status_code == 302
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
        "csrf_token": TOKEN_CSRF,
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
    r = c.post("/empresas/nova", data={"csrf_token": TOKEN_CSRF, "nome": "Outra", "cnpj": "123"})
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
        "csrf_token": TOKEN_CSRF,
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
    r = login("Natan").post(f"/empresas/{outra.id}", data={"csrf_token": TOKEN_CSRF, "nome": "Bio Seiva"})
    assert r.status_code == 200 and "Já existe uma empresa chamada Bio Seiva" in r.get_data(as_text=True)


def test_salvar_formulario_sem_trocar_responsavel_nao_altera_historico(login, emp, usuarios, db):
    c = login("Natan")
    atual = competencia_atual()
    c.post(f"{API}/empresas/{emp.id}/responsavel", json={"usuario_id": usuarios["Hellen"].id, "inicio": comp_iso(atual)})
    # Formulário abre com Hellen selecionada e início = competência padrão (mês anterior); usuário só muda o nome.
    c.post(f"/empresas/{emp.id}", data={"csrf_token": TOKEN_CSRF, "nome": "Bio Seiva 2", "ativa": "1", "responsavel_id": str(usuarios["Hellen"].id),
                                         "inicio": comp_iso(competencia_padrao()),
                                         "responsavel_original": str(usuarios["Hellen"].id),
                                         "inicio_original": comp_iso(competencia_padrao())})
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


# ------------------------------------------------------------------ JS da tela de lançamento (node)

def _rodar_harness_js():
    import json
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which("node") or shutil.which("nodejs")
    if not node:
        pytest.skip("node não instalado")
    raiz = Path(__file__).resolve().parent
    js = raiz.parent / "faturamento" / "static" / "faturamento" / "js"
    out = subprocess.run([node, str(raiz / "js" / "lancamento_harness.js"), str(js)],
                         capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout)


def test_js_bateu_bloqueado_com_edicao_nao_salva():
    r = _rodar_harness_js()
    assert r["inicial"] == {"disabled": False, "title": "", "erro": ""}
    assert r["editado"]["disabled"] is True and r["editado"]["title"] == "Salve as alterações antes de marcar"
    assert r["revertido"]["disabled"] is False  # mesmo número com outra grafia não é edição


def test_js_quantidade_inteira_e_parse_num():
    r = _rodar_harness_js()
    assert "Quantidade deve ser número inteiro" in r["fracao"]["erro"]
    assert r["milhar"]["erro"] == ""
    assert r["parseInteiro"] == {"1.5": "fracao", "1,5": "fracao", "12.34": "fracao", "1.234": 1234,
                                 "abc": "NaN", "vazio": None}
    assert r["parseNum"] == {"0.125": 0.125, "6.370": 6370, "01.250": 1.25, "grande": "NaN"}


# ------------------------------------------------------------------ regressões da revisão: CSRF / sessão

@pytest.mark.parametrize("rota", ["/entrar", "/sair", "/empresas/nova", "/importacao/previa", "/importacao/confirmar",
                                  "/importacao/1/desfazer", "/empresas/importar-responsaveis",
                                  "/empresas/importar-responsaveis/confirmar"])
def test_post_de_formulario_sem_token_csrf_400(login, usuarios, rota):
    c = login("Natan")
    r = c.post(rota, data={"usuario_id": usuarios["Hellen"].id, "nome": "X"})
    assert r.status_code == 400
    r = c.post(rota, data={"usuario_id": usuarios["Hellen"].id, "nome": "X", "csrf_token": "outro"})
    assert r.status_code == 400
    assert c.get("/").status_code == 200  # continua logado como antes


def test_entrar_sem_token_nao_troca_usuario(client, usuarios, csrf):
    csrf(client)
    assert client.post("/entrar", data={"usuario_id": usuarios["Natan"].id}).status_code == 400
    assert client.get("/").status_code == 302


def test_todo_formulario_post_tem_token_csrf(login, emp, usuarios, tipos):
    import re
    c = login("Natan")
    html_todos = []
    for url in ("/", "/empresas/nova", f"/empresas/{emp.id}", "/importacao", "/empresas/importar-responsaveis"):
        html_todos.append(c.get(url).get_data(as_text=True))
    c.post("/sair", data={"csrf_token": TOKEN_CSRF})
    html_todos.append(c.get("/entrar").get_data(as_text=True))
    n = 0
    for html in html_todos:
        for form in re.findall(r'<form[^>]*method="post".*?</form>', html, flags=re.S | re.I):
            n += 1
            assert 'name="csrf_token" value="' in form, form[:200]
    assert n >= 6


def test_token_csrf_gerado_na_sessao_e_aceito(client, usuarios):
    import re
    html = client.get("/entrar").get_data(as_text=True)
    tok = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    assert len(tok) >= 32
    r = client.post("/entrar", data={"usuario_id": usuarios["Natan"].id, "csrf_token": tok})
    assert r.status_code == 302 and client.get("/").status_code == 200


def test_cookie_de_sessao_samesite_lax(app):
    from config import Config
    assert Config.SESSION_COOKIE_SAMESITE == "Lax" and app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_sair_get_nao_desloga_e_menu_usa_post(login):
    c = login("Natan")
    r = c.get("/sair")
    assert r.status_code == 302 and "/entrar" not in r.headers["Location"]
    assert c.get("/").status_code == 200
    html = c.get("/").get_data(as_text=True)
    assert 'action="/sair"' in html and 'method="post"' in html
    assert c.post("/sair", data={"csrf_token": TOKEN_CSRF}).headers["Location"].endswith("/entrar")
    assert c.get("/").status_code == 302


@pytest.mark.parametrize("proximo", ["//malicioso.example/x", "/\\malicioso.example", "/\\/malicioso.example",
                                     "https://malicioso.example", "/\t/malicioso.example",
                                     "javascript:alert(1)"])
def test_entrar_proximo_nao_redireciona_para_fora(client, usuarios, csrf, proximo):
    from urllib.parse import quote
    tok = csrf(client)
    r = client.post("/entrar?proximo=" + quote(proximo, safe=""), data={"usuario_id": usuarios["Natan"].id,
                                                                      "csrf_token": tok})
    assert r.status_code == 302
    loc = r.headers["Location"]
    assert "malicioso" not in loc and "javascript" not in loc


def test_entrar_proximo_local_mantido(client, usuarios, csrf):
    tok = csrf(client)
    r = client.post("/entrar?proximo=/historico%3Fempresa%3D1", data={"usuario_id": usuarios["Natan"].id,
                                                                      "csrf_token": tok})
    assert r.headers["Location"].endswith("/historico?empresa=1")


# ------------------------------------------------------------------ regressões: formulário de empresa

def test_form_empresa_tipos_invalidos_mostra_erro(login, emp):
    c = login("Natan")
    r = c.post(f"/empresas/{emp.id}", data={"csrf_token": TOKEN_CSRF, "nome": "Bio Seiva", "tipos": ["abc"]})
    assert r.status_code == 200 and "Tipo de documento inválido." in r.get_data(as_text=True)
    r = c.post("/empresas/nova", data={"csrf_token": TOKEN_CSRF, "nome": "Nova", "tipos": ["1", "x"]})
    assert r.status_code == 200 and "Tipo de documento inválido." in r.get_data(as_text=True)


def test_form_empresa_compara_responsavel_na_competencia_escolhida(login, emp, usuarios, db):
    """Hellen é a responsável atual (desde este mês); mudar só o início para 2 meses atrás deve valer."""
    from faturamento.util import somar_meses
    c = login("Natan")
    atual = competencia_atual()
    c.post(f"{API}/empresas/{emp.id}/responsavel", json={"usuario_id": usuarios["Hellen"].id, "inicio": comp_iso(atual)})
    antes = comp_iso(somar_meses(atual, -2))
    c.post(f"/empresas/{emp.id}", data={"csrf_token": TOKEN_CSRF, "nome": "Bio Seiva", "ativa": "1",
                                        "responsavel_id": str(usuarios["Hellen"].id), "inicio": antes,
                                        "responsavel_original": str(usuarios["Hellen"].id),
                                        "inicio_original": comp_iso(competencia_padrao())})
    db.session.expire_all()
    e = db.session.get(Empresa, emp.id)
    assert svc_emp.responsavel_em(e, competencia(antes)).nome == "Hellen"
    assert [v.usuario.nome for v in e.historico_responsaveis] == ["Hellen", "Natan"]


def test_form_empresa_abre_com_campos_originais(login, emp, usuarios):
    html = login("Natan").get(f"/empresas/{emp.id}").get_data(as_text=True)
    assert f'name="responsavel_original" value="{usuarios["Natan"].id}"' in html
    assert f'name="inicio_original" value="{comp_iso(competencia_padrao())}"' in html


def test_lista_de_empresas_atualiza_select_com_responsavel_atual():
    from pathlib import Path
    html = (Path(__file__).resolve().parent.parent / "faturamento" / "templates" / "faturamento" / "empresas.html").read_text(
        encoding="utf-8")
    assert "r.empresa.responsavel" in html and "sel.value = String(atual.id)" in html


# ------------------------------------------------------------------ regressões: histórico

def test_historico_paginado_50_por_pagina(login, db, usuarios):
    from faturamento.services import auditoria as aud
    for i in range(60):
        aud.registrar("fat_teste", "x", usuarios["Natan"], descricao=f"Registro número {i:02d}")
    db.session.commit()
    c = login("Natan")
    html = c.get("/historico").get_data(as_text=True)
    assert html.count("Registro número") == 50
    assert "Registro número 59" in html and "Registro número 09" not in html
    assert "pagina=2" in html and "Mais antigas" in html and "Mais recentes" not in html
    html = c.get("/historico?pagina=2").get_data(as_text=True)
    assert html.count("Registro número") == 10 and "Registro número 00" in html
    assert "pagina=1" in html and "Mais antigas" not in html
    assert c.get("/historico?pagina=abc").status_code == 200
    assert c.get("/historico?pagina=-3").status_code == 200


def test_historico_detalhe_em_pt_br(login, db, usuarios):
    from faturamento.services import auditoria as aud
    aud.registrar("fat_teste", "x", usuarios["Natan"], descricao="Formatação",
                  antes={"inicio": "2026-08-01", "valor": "1234.50", "ajustes_ids": [7, 8]},
                  depois={"inicio": "2026-09-01", "valor": "-10.00", "ajustes_ids": [9], "data": "2026-10-05",
                          "criado_em": "2026-10-05T14:30:12", "competencias": ["2026-01", "2026-02"]})
    db.session.commit()
    html = login("Natan").get("/historico").get_data(as_text=True)
    assert "inicio:</span> 08/2026 → <strong>09/2026</strong>" in html
    assert "valor:</span> 1.234,50 → <strong>-10,00</strong>" in html
    assert "data:</span> 05/10/2026" in html and "criado_em:</span> 05/10/2026 14:30" in html
    assert "competencias:</span> 01/2026, 02/2026" in html
    assert "ajustes_ids" not in html


def test_filtro_hist_valores():
    from faturamento.views.routes import fmt_historico
    assert fmt_historico({"responsavel": "Hellen", "inicio": "2026-09-01", "x_ids": [1]}) == \
        "responsavel: Hellen, inicio: 09/2026"
    assert fmt_historico([{"responsavel": "Hellen", "inicio": "2026-09-01"}, {"responsavel": "Ana", "inicio": None}]) == \
        "responsavel: Hellen, inicio: 09/2026; responsavel: Ana, inicio: —"
    assert fmt_historico(1234) == "1.234" and fmt_historico(None) == "—" and fmt_historico(True) == "sim"


# ------------------------------------------------------------------ regressões: gráfico do lançamento

def test_alturas_grafico_limitadas_e_nao_negativas():
    from decimal import Decimal as D

    from faturamento.views.routes import alturas_grafico
    serie = [
        {"entradas": D("1000"), "entradas_ajuste": D("-300"), "saidas": D("500"), "saidas_ajuste": D("0")},
        {"entradas": D("100"), "entradas_ajuste": D("-500"), "saidas": D("1000"), "saidas_ajuste": D("1000")},
        {"entradas": D("0"), "entradas_ajuste": D("0"), "saidas": D("0"), "saidas_ajuste": D("50")},
    ]
    g = alturas_grafico(serie)
    for m in g:
        assert all(v >= 0 for v in m.values())
        assert m["e_base"] + m["e_aj"] <= 180 and m["s_base"] + m["s_aj"] <= 180
    assert g[1]["s_base"] + g[1]["s_aj"] == 180                 # maior barra (base + ajuste) = topo
    assert g[0] == {"e_base": 63, "e_aj": 0, "s_base": 45, "s_aj": 0}  # ajuste negativo só reduz a base
    assert g[1]["e_base"] == 0 and g[1]["e_aj"] == 0             # base + ajuste < 0 -> zero
    assert g[2]["s_aj"] == 5
    assert alturas_grafico([{"entradas": D(0), "entradas_ajuste": D(0), "saidas": D(0), "saidas_ajuste": D(0)}]) == \
        [{"e_base": 0, "e_aj": 0, "s_base": 0, "s_aj": 0}]


def test_grafico_na_tela_com_ajuste_negativo(login, emp, tipos, usuarios, db):
    import re
    natan = usuarios["Natan"]
    comp = competencia("2026-08")
    svc_lanc.salvar_mes(emp, comp, [{"tipo_id": tipos["NFE_ENT"].id, "qtde_autor": 1, "valor_autor": "100"}], natan)
    lanc = svc_lanc.buscar(emp.id, comp, tipos["NFE_ENT"].id)
    svc_lanc.adicionar_ajuste(lanc, "AUTOR", -1, "-400", natan)
    svc_lanc.salvar_mes(emp, competencia("2026-07"), [{"tipo_id": tipos["NFE_SAI"].id, "qtde_autor": 1,
                                                       "valor_autor": "50"}], natan)
    db.session.commit()
    html = login("Natan").get(f"/lancamento?empresa={emp.id}&competencia=2026-08").get_data(as_text=True)
    alturas = [int(h) for h in re.findall(r'class="seg[^"]*" style="height:(-?\d+)px', html)]
    assert alturas and min(alturas) >= 0 and max(alturas) <= 180
    assert 180 in alturas  # saídas de 07/2026 são a maior barra
