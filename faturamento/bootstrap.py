"""Preparação do banco: migrações + dados mínimos (usuários e tipos de documento)."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from .extensions import db
from .models import ENTRADA, SAIDA, TipoDocumento, Usuario

USUARIOS_PADRAO = ["Hellen", "Jaísa", "Mariana", "Natan"]

TIPOS_PADRAO = [
    # codigo, nome, modelo, sentido, ordem
    ("CTE_ENT", "CT-e Entradas", "CT-e", ENTRADA, 10),
    ("NFE_ENT", "NF-e Entradas", "NF-e", ENTRADA, 20),
    ("NFSE_ENT", "NFS-e Entradas", "NFS-e", ENTRADA, 30),
    ("CTE_SAI", "CT-e Saídas", "CT-e", SAIDA, 40),
    ("NFE_SAI", "NF-e Saídas", "NF-e", SAIDA, 50),
    ("NFCE", "NFC-e", "NFC-e", SAIDA, 60),
    ("NFSE_SAI", "NFS-e Saídas", "NFS-e", SAIDA, 70),
]


def semear() -> None:
    """Idempotente: cria só o que falta."""
    existentes = {u.nome for u in db.session.scalars(select(Usuario))}
    for nome in USUARIOS_PADRAO:
        if nome not in existentes:
            db.session.add(Usuario(nome=nome))
    tipos = {t.codigo for t in db.session.scalars(select(TipoDocumento))}
    for codigo, nome, modelo, sentido, ordem in TIPOS_PADRAO:
        if codigo not in tipos:
            db.session.add(TipoDocumento(codigo=codigo, nome=nome, modelo=modelo, sentido=sentido, ordem=ordem))
    db.session.commit()


PASTA_MIGRACOES = Path(__file__).resolve().parent.parent / "migrations"


def config_alembic(url: str | None = None):
    """Configuração do Alembic apontando para ``migrations/`` e para o banco ativo."""
    from alembic.config import Config as AlembicConfig

    from .config import config

    cfg = AlembicConfig(str(PASTA_MIGRACOES / "alembic.ini"))
    cfg.set_main_option("script_location", str(PASTA_MIGRACOES))
    cfg.set_main_option("sqlalchemy.url", (url or config["SQLALCHEMY_DATABASE_URI"]).replace("%", "%%"))
    return cfg


# Tabela que cada migração criou: serve para reconhecer até onde um banco sem registro de versão chegou.
# Ao criar migração nova que cria tabela, acrescente aqui (na ordem).
MARCOS_MIGRACOES = [
    ("f276d432fc3e", "fat_empresa"),       # estrutura inicial
    ("98eb04af4a73", "fat_fonte_versao"),  # versões do cruzamento
]


def adotar_banco_sem_versao(url: str | None = None) -> str | None:
    """Banco com as tabelas ``fat_*`` mas sem o registro do Alembic (``alembic_version``).

    Acontecia com bancos criados pela versão Flask antiga com SQLAlchemy 2.1: as tabelas eram criadas, mas o
    registro da versão não era gravado — e o próximo início tentava criar tudo de novo ("table already exists").
    Aqui o banco é marcado na última migração cujas tabelas já existem; o ``upgrade`` aplica só o que faltar.
    Devolve a revisão marcada (ou None se não precisou).
    """
    from alembic import command
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.pool import NullPool

    from .config import config

    engine = create_engine(url or config["SQLALCHEMY_DATABASE_URI"], poolclass=NullPool)
    try:
        with engine.connect() as con:
            tabelas = set(inspect(con).get_table_names())
            if "alembic_version" in tabelas and con.execute(text("SELECT COUNT(*) FROM alembic_version")).scalar():
                return None
    finally:
        engine.dispose()
    revisao = None
    for rev, tabela in MARCOS_MIGRACOES:
        if tabela not in tabelas:
            break
        revisao = rev
    if revisao is not None:
        command.stamp(config_alembic(url), revisao)
    return revisao


def migrar(url: str | None = None) -> None:
    """Aplica as migrações pendentes (Alembic) no banco ativo."""
    from alembic import command

    adotar_banco_sem_versao(url)
    command.upgrade(config_alembic(url), "head")


def preparar_banco(_app=None) -> None:
    """Aplica as migrações e semeia. Chamado ao iniciar o sistema (o banco já deve estar configurado)."""
    from .config import config

    uri = config["SQLALCHEMY_DATABASE_URI"]
    if uri.startswith("sqlite:///"):
        Path(uri.replace("sqlite:///", "", 1)).parent.mkdir(parents=True, exist_ok=True)
    if PASTA_MIGRACOES.exists():
        migrar(uri)
    else:  # pragma: no cover - instalação sem migrações
        db.create_all()
    semear()
    db.session.remove()
