"""Módulo plugável de Acompanhamento Mensal de Faturamento (CONAP).

Uso em qualquer app Flask:

    from faturamento import init_app
    init_app(app, url_prefix="/faturamento")

As telas ficam em ``<prefixo>/`` e a API JSON em ``<prefixo>/api/faturamento/v1``.
"""
from __future__ import annotations

from flask import Blueprint, Flask

from .extensions import db

bp = Blueprint(
    "faturamento", __name__,
    template_folder="templates",
    static_folder="static/faturamento",
    static_url_path="/static/faturamento",
)
api_bp = Blueprint("faturamento_api", __name__)

__version__ = "1.0.0"


def init_app(app: Flask, url_prefix: str | None = None) -> None:
    from . import models  # noqa: F401  (registra as tabelas)
    from . import api, views  # noqa: F401  (registra as rotas)
    from .identidade import modo_local, usuario_atual
    from .util import (
        comp_curta, comp_extenso, comp_iso, comp_rotulo, competencia_atual, fmt_inteiro, fmt_moeda,
    )

    from .config import config

    prefixo = (url_prefix if url_prefix is not None else app.config.get("URL_PREFIX", "")).rstrip("/")
    # As regras leem a configuração ativa; aqui ela passa a ser a do app Flask (telas antigas).
    config.vincular(app.config)
    db.configurar(app.config["SQLALCHEMY_DATABASE_URI"])

    from flask import g

    from .db import abrir_escopo, fechar_escopo

    @app.before_request
    def _abrir_sessao():
        g._fat_escopo = abrir_escopo()  # uma sessão por requisição, como no Flask-SQLAlchemy

    @app.teardown_request
    def _fechar_sessao(_exc=None):
        token = g.pop("_fat_escopo", None)
        if token is not None:
            fechar_escopo(token)
    app.register_blueprint(bp, url_prefix=prefixo or None)
    app.register_blueprint(api_bp, url_prefix=f"{prefixo}/api/faturamento/v1")

    app.jinja_env.filters.update(
        moeda=fmt_moeda, inteiro=fmt_inteiro, comp_curta=comp_curta, comp_extenso=comp_extenso,
        comp_iso=comp_iso, comp_rotulo=comp_rotulo,
    )

    @app.context_processor
    def _contexto():
        return {
            "usuario_atual": usuario_atual(),
            "modo_local": modo_local(),
            "competencia_atual": competencia_atual(),
            "versao_faturamento": __version__,
        }
