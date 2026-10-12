"""API JSON /api/faturamento/v1."""
import pytest

API = "/api/faturamento/v1"


@pytest.fixture()
def emp(nova_empresa):
    return nova_empresa("Bio Seiva", responsavel="Natan", tipos_codigos=("NFE_ENT", "NFE_SAI"))


def _linha(tipo, qa, va, qc=None, vc=None):
    return {"tipo_id": tipo.id, "qtde_autor": qa, "valor_autor": va, "qtde_canc": qc, "valor_canc": vc}


@pytest.mark.parametrize("metodo, rota, corpo", [
    ("put", "/lancamentos/{eid}/2026-08", {"linhas": []}),
    ("post", "/lancamentos/{eid}/2026-08/{tid}/ajustes", {"qtde": 1, "valor": "1"}),
    ("put", "/lancamentos/1/bateu", {"bateu": True}),
    ("post", "/empresas/{eid}/responsavel", {"usuario_id": 1}),
    ("post", "/empresas", {"nome": "X"}),
    ("put", "/fechamentos/{eid}/2026-08", {"status": "sem_movimento"}),
])
def test_escrita_sem_sessao_401(client, emp, tipos, metodo, rota, corpo):
    r = getattr(client, metodo)(API + rota.format(eid=emp.id, tid=tipos["NFE_ENT"].id), json=corpo)
    assert r.status_code == 401
    assert r.get_json()["erro"] == "usuario_nao_identificado"


def test_sessao_por_api(client, usuarios):
    assert client.get(API + "/sessao").get_json()["usuario"] is None
    r = client.post(API + "/sessao", json={"usuario_id": usuarios["Hellen"].id})
    assert r.status_code == 200
    assert client.get(API + "/sessao").get_json()["usuario"]["nome"] == "Hellen"
    assert client.post(API + "/sessao", json={"usuario_id": 999}).status_code == 400


def test_indice_usuarios_tipos(client, login):
    assert client.get(API + "/").get_json()["versao"] == "v1"
    login("Natan")
    assert len(client.get(API + "/usuarios").get_json()) == 4
    assert len(client.get(API + "/tipos-documento").get_json()) == 7


def test_gravar_e_ler_lancamentos(login, emp, tipos):
    c = login("Natan")
    r = c.put(f"{API}/lancamentos/{emp.id}/2026-08", json={"linhas": [
        _linha(tipos["NFE_ENT"], "10", "1.234,56"), _linha(tipos["NFE_SAI"], "3", "300", "5", "500")]})
    assert r.status_code == 200, r.get_json()
    j = r.get_json()
    assert j["alterados"] == 2 and j["status"] == "preenchido" and len(j["avisos"]) == 1

    r = c.get(f"{API}/lancamentos?empresa={emp.id}&competencia=2026-08")
    j = r.get_json()
    assert j["competencia"] == "2026-08" and j["pode_editar"] is True
    ent = next(l for l in j["linhas"] if l["tipo"]["codigo"] == "NFE_ENT")
    assert ent["qtde_autor"] == 10 and ent["valor_autor"] == "1234.56" and ent["total_valor_autor"] == "1234.56"


def test_gravar_invalido_422_e_nada_gravado(login, emp, tipos):
    c = login("Natan")
    r = c.put(f"{API}/lancamentos/{emp.id}/2026-08", json={"linhas": [
        _linha(tipos["NFE_ENT"], "10", "100"), _linha(tipos["NFE_SAI"], None, "300")]})
    assert r.status_code == 422 and r.get_json()["erro"] == "regra_violada"
    j = c.get(f"{API}/lancamentos?empresa={emp.id}&competencia=2026-08").get_json()
    assert all(l["id"] is None for l in j["linhas"])


def test_competencia_invalida_400(login, emp):
    c = login("Natan")
    assert c.put(f"{API}/lancamentos/{emp.id}/agosto", json={"linhas": []}).status_code == 400
    assert c.get(f"{API}/lancamentos?empresa={emp.id}&competencia=xx").status_code == 400


def test_empresa_inexistente_404(login):
    c = login("Natan")
    r = c.put(f"{API}/lancamentos/9999/2026-08", json={"linhas": []})
    assert r.status_code == 404 and r.get_json()["erro"] == "nao_encontrado"


def test_ajustes_e_bateu(login, emp, tipos):
    c = login("Natan")
    tid = tipos["NFE_ENT"].id
    c.put(f"{API}/lancamentos/{emp.id}/2026-08", json={"linhas": [_linha(tipos["NFE_ENT"], 10, "1000")]})

    r = c.post(f"{API}/lancamentos/{emp.id}/2026-08/{tid}/ajustes",
               json={"grupo": "AUTOR", "qtde": "2", "valor": "200,00"})
    assert r.status_code == 201, r.get_json()
    j = r.get_json()
    assert j["ajuste"]["motivo"].startswith("Arquivos a mais")
    assert j["lancamento"]["total_qtde_autor"] == 12 and j["lancamento"]["total_valor_autor"] == "1200.00"
    lid, aid = j["lancamento"]["id"], j["ajuste"]["id"]

    r = c.post(f"{API}/lancamentos/{emp.id}/2026-08/{tid}/ajustes", json={"qtde": 1, "valor": 1, "motivo": "Outro"})
    assert r.status_code == 422

    r = c.put(f"{API}/lancamentos/{lid}/bateu", json={"bateu": True})
    assert r.get_json() == {"id": lid, "bateu": True}

    # travado: números, ajustes e remoção recusados
    r = c.put(f"{API}/lancamentos/{emp.id}/2026-08", json={"linhas": [_linha(tipos["NFE_ENT"], 11, "1100")]})
    assert r.status_code == 422 and "Bateu" in r.get_json()["mensagens"][0]
    assert c.post(f"{API}/lancamentos/{emp.id}/2026-08/{tid}/ajustes", json={"qtde": 1, "valor": 1}).status_code == 422
    assert c.delete(f"{API}/ajustes/{aid}", json={}).status_code == 422

    c.put(f"{API}/lancamentos/{lid}/bateu", json={"bateu": False})
    r = c.delete(f"{API}/ajustes/{aid}", json={})
    assert r.status_code == 200 and r.get_json()["lancamento"]["ajustes"] == []


def test_ajuste_cria_lancamento_se_nao_existe(login, emp, tipos):
    c = login("Natan")
    r = c.post(f"{API}/lancamentos/{emp.id}/2026-08/{tipos['NFE_SAI'].id}/ajustes", json={"qtde": 1, "valor": "10"})
    assert r.status_code == 201
    assert r.get_json()["lancamento"]["qtde_autor"] is None
    assert r.get_json()["lancamento"]["total_qtde_autor"] == 1


def test_outra_carteira_403_somente_leitura(login, emp, tipos):
    c = login("Natan")
    c.put(f"{API}/lancamentos/{emp.id}/2026-08", json={"linhas": [_linha(tipos["NFE_ENT"], 1, "10")]})
    lid = c.get(f"{API}/lancamentos?empresa={emp.id}&competencia=2026-08").get_json()["linhas"][0]["id"]

    c = login("Hellen")
    j = c.get(f"{API}/lancamentos?empresa={emp.id}&competencia=2026-08").get_json()
    assert j["pode_editar"] is False  # pode ver

    for r in (
        c.put(f"{API}/lancamentos/{emp.id}/2026-08", json={"linhas": [_linha(tipos["NFE_ENT"], 2, "20")]}),
        c.post(f"{API}/lancamentos/{emp.id}/2026-08/{tipos['NFE_ENT'].id}/ajustes", json={"qtde": 1, "valor": 1}),
        c.put(f"{API}/lancamentos/{lid}/bateu", json={"bateu": True}),
        c.put(f"{API}/fechamentos/{emp.id}/2026-08", json={"status": "pendente"}),
        c.put(f"{API}/conferencia/{emp.id}/2026-08", json={"bateu": True}),
    ):
        assert r.status_code == 403
        assert r.get_json()["erro"] == "somente_leitura"

    r = c.put(f"{API}/lancamentos/{emp.id}/2026-08", json={"linhas": [_linha(tipos["NFE_ENT"], 2, "20")], "substituto": True})
    assert r.status_code == 200 and r.get_json()["alterados"] == 1


def test_fechamento_sem_movimento(login, emp, tipos):
    c = login("Natan")
    r = c.put(f"{API}/fechamentos/{emp.id}/2026-08", json={"status": "sem_movimento"})
    assert r.get_json() == {"status": "sem_movimento"}
    assert c.put(f"{API}/fechamentos/{emp.id}/2026-08", json={"status": "xx"}).status_code == 400
    c.put(f"{API}/lancamentos/{emp.id}/2026-08", json={"linhas": [_linha(tipos["NFE_ENT"], 1, "10")]})
    assert c.get(f"{API}/lancamentos?empresa={emp.id}&competencia=2026-08").get_json()["status"] == "preenchido"
    assert c.put(f"{API}/fechamentos/{emp.id}/2026-08", json={"status": "sem_movimento"}).status_code == 422


def test_fechamento_competencia_invalida_400(login, emp):
    c = login("Natan")
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    assert c.put(f"{API}/fechamentos/{emp.id}/agosto", json={"status": "pendente"}).status_code == 400


def test_trocar_responsavel(login, emp, usuarios):
    c = login("Mariana")  # qualquer usuário pode trocar
    r = c.post(f"{API}/empresas/{emp.id}/responsavel", json={"usuario_id": usuarios["Hellen"].id, "inicio": "2026-09"})
    assert r.status_code == 200
    j = r.get_json()
    assert j["alterado"] is True
    h = j["empresa"]["historico_responsaveis"]
    assert h[0]["usuario"]["nome"] == "Hellen" and h[0]["inicio"] == "2026-09" and h[0]["origem"] == "manual"
    assert h[1]["usuario"]["nome"] == "Natan"

    r = c.post(f"{API}/empresas/{emp.id}/responsavel", json={"usuario_id": usuarios["Hellen"].id, "inicio": "2026-09"})
    assert r.get_json()["alterado"] is False
    assert c.post(f"{API}/empresas/{emp.id}/responsavel", json={"usuario_id": 999}).status_code == 400
    assert c.post(f"{API}/empresas/{emp.id}/responsavel",
                  json={"usuario_id": usuarios["Hellen"].id, "inicio": "set/26"}).status_code == 400

    lista = c.get(f"{API}/empresas?responsavel={usuarios['Hellen'].id}&competencia=2026-09").get_json()
    assert [e["nome"] for e in lista] == ["Bio Seiva"]
    assert c.get(f"{API}/empresas?responsavel={usuarios['Hellen'].id}&competencia=2026-08").get_json() == []

    aud = c.get(f"{API}/auditoria?empresa={emp.id}").get_json()
    assert aud[0]["acao"] == "trocar_responsavel" and aud[0]["usuario"] == "Mariana"
    assert aud[0]["antes"] == {"responsavel": "Natan"}


def test_criar_e_alterar_empresa(login, usuarios, tipos):
    c = login("Natan")
    r = c.post(f"{API}/empresas", json={"nome": "Nova", "cnpj": "12345678000190", "tipos": [tipos["NFCE"].id],
                                        "responsavel_id": usuarios["Jaísa"].id})
    assert r.status_code == 201
    j = r.get_json()
    assert j["responsavel"]["nome"] == "Jaísa" and j["tipos"] == [tipos["NFCE"].id]
    r = c.put(f"{API}/empresas/{j['id']}", json={"ativa": False})
    assert r.get_json()["ativa"] is False
    assert c.post(f"{API}/empresas", json={"nome": "Nova"}).status_code == 422
    assert c.get(f"{API}/empresas/9999").status_code == 404


def test_resumo_e_painel(login, emp, tipos):
    c = login("Natan")
    c.put(f"{API}/lancamentos/{emp.id}/2026-08", json={"linhas": [
        _linha(tipos["NFE_ENT"], 1, "10"), _linha(tipos["NFE_SAI"], 2, "20")]})
    j = c.get(f"{API}/resumo?competencia=2026-08").get_json()
    blocos = j["empresas"][0]["blocos"]
    assert [b["sentido"] for b in blocos] == ["E", "S"]
    assert blocos[1]["subtotal"]["valor_autor"] == "20.00"
    assert j["progresso"]["linhas"] == 2
    p = c.get(f"{API}/painel?competencia=2026-08").get_json()
    assert p["empresas"][0]["status"] == "preenchido" and p["empresas"][0]["saidas"] == "20.00"
    ev = c.get(f"{API}/evolucao?empresa={emp.id}&ate=2026-08&meses=2").get_json()
    assert [x["competencia"] for x in ev] == ["2026-07", "2026-08"]


# ------------------------------------------------------------------ regressões da revisão

@pytest.mark.parametrize("rota", ["/usuarios", "/tipos-documento", "/empresas", "/empresas/{eid}",
                                  "/lancamentos?empresa={eid}", "/painel", "/resumo", "/evolucao?empresa={eid}",
                                  "/auditoria"])
def test_leitura_sem_sessao_401(client, emp, rota):
    r = client.get(API + rota.format(eid=emp.id))
    assert r.status_code == 401 and r.get_json()["erro"] == "usuario_nao_identificado"


def test_indice_e_sessao_sem_login_continuam_abertos(client):
    assert client.get(API + "/").status_code == 200
    assert client.get(API + "/sessao").status_code == 200


@pytest.mark.parametrize("metodo, rota", [
    ("post", "/sessao"), ("post", "/empresas"), ("put", "/empresas/{eid}"), ("put", "/lancamentos/{eid}/2026-08"),
    ("delete", "/ajustes/1"), ("post", "/empresas/{eid}/responsavel"),
])
def test_escrita_sem_json_415(login, emp, metodo, rota):
    c = login("Natan")
    r = getattr(c, metodo)(API + rota.format(eid=emp.id), data={"usuario_id": "1"})
    assert r.status_code == 415 and r.get_json()["erro"] == "tipo_conteudo"
    r = getattr(c, metodo)(API + rota.format(eid=emp.id), data="{}", content_type="text/plain")
    assert r.status_code == 415


@pytest.mark.parametrize("uid", ["1", "abc", [1], True, 1.5, {"a": 1}])
def test_sessao_usuario_id_nao_inteiro_400(client, uid):
    client.application.config["PROPAGATE_EXCEPTIONS"] = False
    r = client.post(API + "/sessao", json={"usuario_id": uid})
    assert r.status_code == 400


def test_alterar_empresa_valida_tipos_e_ativa(login, emp, tipos):
    c = login("Natan")
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    for ruim in ("abc", [1, "x"], ["1"], 5, [True]):
        assert c.put(f"{API}/empresas/{emp.id}", json={"tipos": ruim}).status_code == 400, ruim
    assert c.put(f"{API}/empresas/{emp.id}", json={"ativa": "talvez"}).status_code == 400
    assert c.put(f"{API}/empresas/{emp.id}", json={"ativa": "false"}).get_json()["ativa"] is False
    assert c.put(f"{API}/empresas/{emp.id}", json={"ativa": 1}).get_json()["ativa"] is True
    assert c.put(f"{API}/empresas/{emp.id}", json={"ativa": "0"}).get_json()["ativa"] is False
    assert c.put(f"{API}/empresas/{emp.id}", json={"ativa": True, "tipos": [tipos["NFCE"].id]}).get_json()["tipos"] == \
        [tipos["NFCE"].id]


@pytest.mark.parametrize("linhas", ["x", [1], {"a": 1}])
def test_gravar_linhas_mal_formadas_422(login, emp, linhas):
    c = login("Natan")
    c.application.config["PROPAGATE_EXCEPTIONS"] = False
    assert c.put(f"{API}/lancamentos/{emp.id}/2026-08", json={"linhas": linhas}).status_code == 422


def test_trocar_responsavel_ignora_origem_do_cliente(login, emp, usuarios):
    c = login("Natan")
    r = c.post(f"{API}/empresas/{emp.id}/responsavel",
               json={"usuario_id": usuarios["Hellen"].id, "inicio": "2026-09", "origem": "integracao"})
    assert r.get_json()["empresa"]["historico_responsaveis"][0]["origem"] == "manual"


def test_trocar_responsavel_retroativo_devolve_o_atual(login, emp, usuarios):
    from faturamento.util import comp_iso, competencia_atual, somar_meses
    c = login("Natan")
    atual = competencia_atual()
    c.post(f"{API}/empresas/{emp.id}/responsavel", json={"usuario_id": usuarios["Hellen"].id, "inicio": comp_iso(atual)})
    r = c.post(f"{API}/empresas/{emp.id}/responsavel",
               json={"usuario_id": usuarios["Mariana"].id, "inicio": comp_iso(somar_meses(atual, -2))})
    j = r.get_json()
    assert j["alterado"] is True and j["empresa"]["responsavel"]["nome"] == "Mariana"
    assert [h["usuario"]["nome"] for h in j["empresa"]["historico_responsaveis"]] == ["Mariana", "Natan"]
