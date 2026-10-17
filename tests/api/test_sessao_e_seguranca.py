"""Sessão local ("Quem está usando?"), login da plataforma (JWT), proteção contra CSRF e formato JSON."""
from __future__ import annotations

import time

import jwt
import pytest
from sqlalchemy import select

from faturamento.db import db
from faturamento.http.auth import COOKIE_LOCAL
from faturamento.http.json import chave_camel, chave_snake, para_json
from faturamento.models import Usuario

from .conftest import API


def test_sessao_sem_usuario_lista_nomes_no_modo_local(cliente):
    s = cliente.get(f"{API}/sessao").json()
    assert s["usuario"] is None and s["modoAuth"] == "local"
    assert [u["nome"] for u in s["usuarios"]] == ["Hellen", "Jaísa", "Mariana", "Natan"]
    assert s["recursos"] == {"cruzamento": False, "controleFiscal": False, "empresasFonte": "local",
                             "provedorResponsaveis": "manual"}


def test_entrar_grava_cookie_assinado_e_sair_apaga(cliente, usuarios):
    r = cliente.post(f"{API}/sessao", json={"usuarioId": usuarios["Jaísa"]})
    assert r.status_code == 200 and r.json()["usuario"]["nome"] == "Jaísa"
    cookie = cliente.cookies.get(COOKIE_LOCAL)
    assert cookie and cookie.startswith(f"{usuarios['Jaísa']}.")
    assert cliente.get(f"{API}/sessao").json()["usuario"]["nome"] == "Jaísa"
    cliente.delete(f"{API}/sessao", headers={"X-Requested-With": "fetch"})
    assert cliente.get(f"{API}/sessao").json()["usuario"] is None


def test_cookie_adulterado_nao_vale(cliente, usuarios):
    cliente.post(f"{API}/sessao", json={"usuarioId": usuarios["Natan"]})
    _uid, momento, assinatura = cliente.cookies.get(COOKIE_LOCAL).split(".")
    cliente.cookies.set(COOKIE_LOCAL, f"{usuarios['Hellen']}.{momento}.{assinatura}")
    assert cliente.get(f"{API}/sessao").json()["usuario"] is None
    assert cliente.get(f"{API}/painel").status_code == 401


@pytest.mark.parametrize("corpo", [{"usuarioId": 999}, {"usuarioId": "abc"}, {}])
def test_entrar_com_usuario_invalido(cliente, corpo):
    r = cliente.post(f"{API}/sessao", json=corpo)
    assert r.status_code == 400 and r.json()["erro"] == "parametro_invalido"


@pytest.mark.parametrize("rota", ["/painel", "/referencias", "/empresas", "/lancamento/inicio", "/conferencia",
                                  "/historico", "/importacoes", "/tipos-documento"])
def test_rotas_exigem_usuario(cliente, rota):
    r = cliente.get(API + rota)
    assert r.status_code == 401
    assert r.json() == {"erro": "usuario_nao_identificado", "mensagens": ["Escolha quem está usando o sistema."]}


def test_escrita_sem_json_recusada_csrf(entrar, nova_empresa):
    c = entrar()
    eid = nova_empresa()
    r = c.post(f"{API}/empresas/{eid}/responsavel", data={"usuarioId": 1})
    assert r.status_code == 415 and r.json()["erro"] == "tipo_conteudo"
    # upload multipart só com o cabeçalho do front
    r = c.post(f"{API}/importacoes/previa", files={"arquivo": ("a.xlsx", b"x")})
    assert r.status_code == 415


def test_saude(cliente):
    assert cliente.get(f"{API}/saude").json() == {"status": "ok", "banco": "ok"}


def test_respostas_em_camel_case_com_decimais_em_texto():
    from decimal import Decimal
    assert para_json({"qtde_autor": 1, "valor_autor": Decimal("10.50"), "lista": [{"criado_em": None}],
                      "NF_ENTRADA_TODAS": 1}) == \
        {"qtdeAutor": 1, "valorAutor": "10.50", "lista": [{"criadoEm": None}], "NF_ENTRADA_TODAS": 1}
    assert chave_camel("ajuste_qtde_autor") == "ajusteQtdeAutor"
    assert chave_snake("ajusteQtdeAutor") == "ajuste_qtde_autor"


# ------------------------------------------------------------------ plataforma (JWT)

SEGREDO = "segredo-da-plataforma-de-teste-com-32-bytes"


@pytest.fixture()
def plataforma(opcoes):
    opcoes(MODO_AUTH="plataforma", JWT_SEGREDO=SEGREDO, JWT_COOKIE="token", JWT_CAMPO_ID="sub",
           JWT_CAMPO_NOME="nome", JWT_CRIAR_USUARIO=True)


def _token(**claims):
    claims.setdefault("exp", int(time.time()) + 600)
    return jwt.encode(claims, SEGREDO, algorithm="HS256")


def test_jwt_no_cookie_liga_usuario_existente_pelo_nome(cliente, plataforma):
    cliente.cookies.set("token", _token(sub="u-77", nome="jaisa"))
    s = cliente.get(f"{API}/sessao").json()
    assert s["modoAuth"] == "plataforma" and s["usuario"]["nome"] == "Jaísa" and s["usuarios"] == []
    u = db.session.scalar(select(Usuario).where(Usuario.nome == "Jaísa"))
    assert u.external_id == "u-77"  # vinculado na primeira entrada
    db.session.remove()
    # depois casa pelo id mesmo que o nome no token mude
    cliente.cookies.set("token", _token(sub="u-77", nome="Jaisa Souza"))
    assert cliente.get(f"{API}/sessao").json()["usuario"]["nome"] == "Jaísa"


def test_jwt_por_bearer_e_usuario_novo_criado(cliente, plataforma):
    h = {"Authorization": "Bearer " + _token(sub="42", nome="Carla")}
    assert cliente.get(f"{API}/sessao", headers=h).json()["usuario"]["nome"] == "Carla"
    assert cliente.get(f"{API}/painel", headers=h).status_code == 200


def test_jwt_invalido_ou_vencido_nao_entra(cliente, plataforma):
    cliente.cookies.set("token", jwt.encode({"sub": "1", "nome": "Natan", "exp": int(time.time()) + 60}, "outro",
                                            algorithm="HS256"))
    assert cliente.get(f"{API}/sessao").json()["usuario"] is None
    cliente.cookies.set("token", _token(sub="1", nome="Natan", exp=int(time.time()) - 10))
    r = cliente.get(f"{API}/painel")
    assert r.status_code == 401 and "Conap Ferramentas" in r.json()["mensagens"][0]


def test_modo_plataforma_nao_aceita_janela_local(cliente, plataforma, usuarios):
    r = cliente.post(f"{API}/sessao", json={"usuarioId": usuarios["Natan"]})
    assert r.status_code == 400 and r.json()["erro"] == "modo_plataforma"


def test_plataforma_sem_jwt_configurado_usa_cabecalho(cliente, opcoes):
    opcoes(MODO_AUTH="plataforma", JWT_SEGREDO="", JWT_CHAVE_PUBLICA="", AUTH_HEADER="X-Remote-User")
    assert cliente.get(f"{API}/sessao", headers={"X-Remote-User": "mariana"}).json()["usuario"]["nome"] == "Mariana"
