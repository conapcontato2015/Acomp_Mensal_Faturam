"""Preparação do banco: migrações + dados mínimos (usuários e tipos de documento)."""
from __future__ import annotations

from pathlib import Path

from flask import Flask
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


def preparar_banco(app: Flask) -> None:
    """Aplica as migrações (Alembic) e semeia. Chamado ao iniciar o sistema."""
    from flask_migrate import upgrade

    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if uri.startswith("sqlite:///"):
        Path(uri.replace("sqlite:///", "", 1)).parent.mkdir(parents=True, exist_ok=True)
    with app.app_context():
        pasta = Path(app.root_path).parent / "migrations"
        if pasta.exists():
            upgrade(directory=str(pasta))
        else:  # pragma: no cover - instalação sem migrações
            db.create_all()
        semear()
