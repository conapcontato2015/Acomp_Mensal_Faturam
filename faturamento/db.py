"""Acesso ao banco sem depender de framework web (Flask, FastAPI…).

``db`` imita a parte do Flask-SQLAlchemy que o sistema usa (``db.Model``, ``db.Table``, ``db.Column``,
``db.session``, ``create_all``/``drop_all``), mas é SQLAlchemy puro:

- ``db.configurar(url)`` cria o engine (uma vez, ao iniciar o sistema ou nos testes);
- ``db.session`` é uma sessão por "escopo": uma por requisição na API (ver ``escopo_da_requisicao``)
  e, fora de requisição (scripts, testes), uma por thread.

Assim as regras (``faturamento/services``) rodam iguais aqui, no FastAPI e dentro da plataforma.
"""
from __future__ import annotations

import contextvars
import threading
import uuid
from contextlib import contextmanager

from sqlalchemy import Column, MetaData, Table, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker
from sqlalchemy.pool import StaticPool

# Nomes de constraints estáveis: necessário para migrações funcionarem igual em SQLite e PostgreSQL.
CONVENCAO = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCAO)


_escopo: contextvars.ContextVar[str | None] = contextvars.ContextVar("fat_escopo_sessao", default=None)


def _escopo_atual():
    return _escopo.get() or ("thread", threading.get_ident())


def _sqlite_pragmas(conexao, _registro) -> None:
    cur = conexao.cursor()
    cur.execute("PRAGMA busy_timeout = 5000")  # várias pessoas gravando ao mesmo tempo na rede
    cur.close()


class _Banco:
    """Fachada única para modelos e sessão."""

    Model = Base
    metadata = Base.metadata
    Column = Column

    def __init__(self) -> None:
        self.engine: Engine | None = None
        self._fabrica = sessionmaker()
        self.session = scoped_session(self._fabrica, scopefunc=_escopo_atual)

    @staticmethod
    def Table(nome: str, *colunas, **kw) -> Table:  # noqa: N802 (mesmo nome do Flask-SQLAlchemy)
        return Table(nome, Base.metadata, *colunas, **kw)

    def configurar(self, url: str, **opcoes) -> Engine:
        """Cria o engine para ``url``. Chamar de novo troca o banco (usado nos testes)."""
        self.session.remove()
        if self.engine is not None:
            self.engine.dispose()
        if url.startswith("sqlite"):
            # A API atende em várias threads; o SQLite precisa aceitar isso.
            opcoes.setdefault("connect_args", {}).setdefault("check_same_thread", False)
            if url in ("sqlite://", "sqlite:///:memory:"):
                opcoes["poolclass"] = StaticPool  # mesmo banco em memória para todas as conexões
        else:
            opcoes.setdefault("pool_pre_ping", True)
        self.engine = create_engine(url, **opcoes)
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", _sqlite_pragmas)
        self._fabrica.configure(bind=self.engine)
        return self.engine

    def exigir_engine(self) -> Engine:
        if self.engine is None:
            raise RuntimeError("Banco não configurado: chame db.configurar(url) ao iniciar o sistema.")
        return self.engine

    def create_all(self) -> None:
        self.metadata.create_all(self.exigir_engine())

    def drop_all(self) -> None:
        self.metadata.drop_all(self.exigir_engine())


db = _Banco()


def abrir_escopo() -> contextvars.Token:
    """Começa uma sessão própria (ex.: no início de uma requisição). Devolve o token para ``fechar_escopo``."""
    return _escopo.set(uuid.uuid4().hex)


def fechar_escopo(token: contextvars.Token) -> None:
    db.session.remove()
    _escopo.reset(token)


@contextmanager
def escopo_da_requisicao():
    """Uma sessão própria durante o bloco; fechada no fim (com rollback do que não foi confirmado)."""
    token = _escopo.set(uuid.uuid4().hex)
    try:
        yield db.session
    finally:
        db.session.remove()
        _escopo.reset(token)
