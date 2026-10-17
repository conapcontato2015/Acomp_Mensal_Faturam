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


def migrar(url: str | None = None) -> None:
    """Aplica as migrações pendentes (Alembic) no banco ativo."""
    from alembic import command

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
