"""Fixtures compartilhadas. Banco SQLite em memória, recriado a cada teste."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app import create_app
from config import TestConfig
from faturamento.bootstrap import semear
from faturamento.extensions import db as _db
from faturamento.models import TipoDocumento, Usuario
from faturamento.services import empresas as svc_emp
from faturamento.util import competencia


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        _db.create_all()
        semear()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def db(app):
    return _db


@pytest.fixture()
def usuarios(app):
    return {u.nome: u for u in _db.session.scalars(select(Usuario))}


@pytest.fixture()
def tipos(app):
    return {t.codigo: t for t in _db.session.scalars(select(TipoDocumento))}


@pytest.fixture()
def nova_empresa(app, usuarios, tipos):
    """nova_empresa('Nome', responsavel='Natan', tipos_codigos=('NFE_ENT','NFCE'))"""

    def fabrica(nome="Empresa Teste", responsavel="Natan", tipos_codigos=("NFE_ENT", "NFE_SAI", "NFCE"), cnpj=None):
        resp = usuarios[responsavel]
        e = svc_emp.criar_empresa(nome, resp, resp, cnpj=cnpj, tipo_ids=[tipos[c].id for c in tipos_codigos])
        _db.session.commit()
        return e

    return fabrica


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def login(client, usuarios):
    """login('Natan') -> client já com o usuário na sessão."""

    def entrar(nome="Natan"):
        client.post("/entrar", data={"usuario_id": usuarios[nome].id})
        return client

    return entrar


@pytest.fixture()
def comp():
    return competencia("2026-08")
