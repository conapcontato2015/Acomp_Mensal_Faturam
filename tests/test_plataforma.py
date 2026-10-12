"""Fase 4: módulo plugado em outra aplicação, com login vindo da plataforma."""
from __future__ import annotations

from flask import Flask

from config import TestConfig
from faturamento import init_app
from faturamento.bootstrap import semear
from faturamento.extensions import db


class PlataformaConfig(TestConfig):
    MODO_AUTH = "plataforma"
    AUTH_HEADER = "X-Remote-User"


def _app_da_plataforma():
    """Simula a plataforma do escritório: um app Flask que só chama init_app com prefixo."""
    app = Flask("plataforma", static_folder=None)
    app.config.from_object(PlataformaConfig)
    init_app(app, url_prefix="/faturamento")
    return app


def test_modulo_plugado_com_prefixo_e_login_por_cabecalho():
    app = _app_da_plataforma()
    with app.app_context():
        db.create_all()
        semear()
        c = app.test_client()
        # sem cabeçalho: tela recusa e API pede identificação
        assert c.get("/faturamento/").status_code == 403
        assert c.get("/faturamento/api/faturamento/v1/sessao").get_json()["usuario"] is None
        # com o login da plataforma (nome sem acento também casa)
        h = {"X-Remote-User": "jaisa"}
        r = c.get("/faturamento/", headers=h)
        assert r.status_code == 200
        assert "Jaísa" in r.get_data(as_text=True)
        assert c.get("/faturamento/static/faturamento/css/app.css").status_code == 200
        s = c.get("/faturamento/api/faturamento/v1/sessao", headers=h).get_json()
        assert s["usuario"]["nome"] == "Jaísa" and s["modo_auth"] == "plataforma"
        # a janela de escolha de usuário não existe no modo plataforma
        assert c.get("/faturamento/entrar", headers=h).status_code == 302
        assert c.post("/faturamento/api/faturamento/v1/sessao", json={"usuario_id": 1}).status_code == 400
        db.drop_all()


def test_usuario_por_external_id():
    app = _app_da_plataforma()
    with app.app_context():
        db.create_all()
        semear()
        from sqlalchemy import select
        from faturamento.models import Usuario
        u = db.session.scalar(select(Usuario).where(Usuario.nome == "Mariana"))
        u.external_id = "mariana.s@conap"
        db.session.commit()
        r = app.test_client().get("/faturamento/api/faturamento/v1/sessao", headers={"X-Remote-User": "mariana.s@conap"})
        assert r.get_json()["usuario"]["nome"] == "Mariana"
        db.drop_all()


def test_postgres_url_normalizada(monkeypatch):
    from pathlib import Path
    import config
    monkeypatch.setenv("DATABASE_URL", "postgres://u:s@h:5432/conap")
    assert config._database_url(Path("/x")) == "postgresql+psycopg://u:s@h:5432/conap"
    monkeypatch.setenv("DATABASE_URL", "")
    assert config._database_url(Path("/x")).startswith("sqlite:///")
