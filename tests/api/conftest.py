"""Fixtures da API FastAPI (/api/faturamento). Banco SQLite em memória, recriado a cada teste."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from faturamento.bootstrap import semear
from faturamento.config import TestConfig, config
from faturamento.db import db
from faturamento.models import TipoDocumento, Usuario
from faturamento.services import empresas as svc_emp
from faturamento.util import competencia

API = "/api/faturamento"


@pytest.fixture()
def cfg():
    """Configuração dos testes; altere ``cfg[...]`` dentro do teste para ligar opções."""
    return TestConfig


@pytest.fixture()
def app(cfg):
    import servidor

    aplicacao = servidor.criar_app(cfg, preparar_banco=False, telas=None)
    db.create_all()
    semear()
    db.session.remove()
    yield aplicacao
    db.session.remove()
    db.drop_all()


@pytest.fixture()
def cliente(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def usuarios(app):
    """{nome: id}"""
    ids = {u.nome: u.id for u in db.session.scalars(select(Usuario))}
    db.session.remove()
    return ids


@pytest.fixture()
def tipos(app):
    """{codigo: id}"""
    ids = {t.codigo: t.id for t in db.session.scalars(select(TipoDocumento))}
    db.session.remove()
    return ids


@pytest.fixture()
def nova_empresa(app, usuarios, tipos):
    """nova_empresa('Nome', responsavel='Natan', tipos_codigos=('NFE_ENT','NFCE'), cnpj=None) -> id"""

    def fabrica(nome="Empresa Teste", responsavel="Natan", tipos_codigos=("NFE_ENT", "NFE_SAI", "NFCE"), cnpj=None):
        resp = db.session.get(Usuario, usuarios[responsavel])
        e = svc_emp.criar_empresa(nome, resp, resp, cnpj=cnpj, tipo_ids=[tipos[c] for c in tipos_codigos])
        db.session.commit()
        eid = e.id
        db.session.remove()
        return eid

    return fabrica


@pytest.fixture()
def entrar(cliente, usuarios):
    """entrar('Natan') -> cliente com o cookie do usuário."""

    def fazer(nome="Natan"):
        r = cliente.post(f"{API}/sessao", json={"usuarioId": usuarios[nome]})
        assert r.status_code == 200, r.text
        return cliente

    return fazer


@pytest.fixture()
def comp():
    return competencia("2026-08")


@pytest.fixture()
def opcoes():
    """opcoes(CHAVE=valor, ...) liga opções na configuração ativa durante o teste."""

    def ligar(**kw):
        config.update(kw)

    return ligar
