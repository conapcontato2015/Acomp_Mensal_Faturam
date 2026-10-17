"""Ambiente do Alembic: usa os modelos de ``faturamento.models`` e o banco da configuração ativa."""
import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from faturamento import models  # noqa: F401  (registra as tabelas)
from faturamento.config import config as config_sistema
from faturamento.db import db

config = context.config
if config.config_file_name is not None and not config.attributes.get("sem_log"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)
logger = logging.getLogger("alembic.env")

target_metadata = db.metadata


def _url() -> str:
    url = config.get_main_option("sqlalchemy.url")
    return url or config_sistema["SQLALCHEMY_DATABASE_URI"]


def run_migrations_offline():
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    def process_revision_directives(ctx, revision, directives):
        # "revision --autogenerate" sem mudança nos modelos não gera arquivo vazio
        if getattr(config.cmd_opts, "autogenerate", False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info("Nenhuma mudança nos modelos.")

    conexao_externa = config.attributes.get("connection")
    if conexao_externa is not None:
        _rodar(conexao_externa, process_revision_directives)
        return
    engine = create_engine(_url(), poolclass=NullPool)
    with engine.connect() as connection:
        _rodar(connection, process_revision_directives)
    engine.dispose()


def _rodar(connection, process_revision_directives):
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True,
                      process_revision_directives=process_revision_directives)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
