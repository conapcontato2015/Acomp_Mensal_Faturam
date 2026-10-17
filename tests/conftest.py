"""Fixtures compartilhadas. Banco SQLite em memória, recriado a cada teste."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from faturamento.bootstrap import semear
from faturamento.config import TestConfig, configurar
from faturamento.db import abrir_escopo, fechar_escopo
from faturamento.db import db as _db
from faturamento.models import TipoDocumento, Usuario
from faturamento.services import empresas as svc_emp
from faturamento.util import competencia


@pytest.fixture()
def app():
    """Configuração de teste ativa e banco recriado. ``app.config`` é a configuração em uso (altere no teste)."""
    cfg = configurar(TestConfig)
    token = abrir_escopo()
    _db.create_all()
    semear()
    yield SimpleNamespace(config=cfg)
    _db.session.remove()
    _db.drop_all()
    fechar_escopo(token)


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
def comp():
    return competencia("2026-08")
