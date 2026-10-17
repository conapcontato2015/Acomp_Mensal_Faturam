"""Banco criado pela versão antiga sem o registro do Alembic: o sistema abre sem tentar recriar as tabelas."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from faturamento.bootstrap import MARCOS_MIGRACOES, PASTA_MIGRACOES, adotar_banco_sem_versao, preparar_banco
from faturamento.config import TestConfig, configurar
from faturamento.db import db


def _versao(arquivo: Path):
    con = sqlite3.connect(arquivo)
    try:
        return [r[0] for r in con.execute("SELECT version_num FROM alembic_version")]
    finally:
        con.close()


@pytest.fixture()
def banco_arquivo(tmp_path):
    arquivo = tmp_path / "faturamento.db"
    configurar(TestConfig, SQLALCHEMY_DATABASE_URI=f"sqlite:///{arquivo.as_posix()}")
    yield arquivo
    db.session.remove()
    configurar(TestConfig)


def _criar_legado(arquivo: Path, sem: tuple[str, ...] = ()):
    """Tabelas como a versão antiga deixava: tudo criado, sem ``alembic_version`` (e com dados)."""
    from faturamento import models  # noqa: F401

    tabelas = [t for n, t in db.metadata.tables.items() if n not in sem]
    db.metadata.create_all(db.engine, tables=tabelas)
    con = sqlite3.connect(arquivo)
    con.execute("INSERT INTO fat_usuario (nome, ativo) VALUES ('Natan', 1)")
    con.commit()
    con.close()


def test_banco_antigo_sem_versao_abre_e_mantem_os_dados(banco_arquivo):
    _criar_legado(banco_arquivo)
    preparar_banco()  # antes: "table fat_auditoria already exists"
    preparar_banco()  # segunda abertura também
    assert _versao(banco_arquivo) == [MARCOS_MIGRACOES[-1][0]]
    con = sqlite3.connect(banco_arquivo)
    assert con.execute("SELECT COUNT(*) FROM fat_usuario WHERE nome = 'Natan'").fetchone()[0] == 1
    con.close()


def test_banco_antigo_sem_a_ultima_tabela_recebe_so_o_que_falta(banco_arquivo):
    _criar_legado(banco_arquivo, sem=("fat_fonte_versao",))
    assert adotar_banco_sem_versao() == "f276d432fc3e"
    preparar_banco()
    assert _versao(banco_arquivo) == ["98eb04af4a73"]
    con = sqlite3.connect(banco_arquivo)
    assert con.execute("SELECT name FROM sqlite_master WHERE name = 'fat_fonte_versao'").fetchone()
    con.close()


def test_banco_novo_ou_ja_versionado_nao_e_marcado(banco_arquivo):
    assert adotar_banco_sem_versao() is None  # vazio: o upgrade cria tudo
    preparar_banco()
    assert adotar_banco_sem_versao() is None  # já tem versão


def test_toda_migracao_tem_marco():
    """Migração nova que cria tabela precisa entrar em MARCOS_MIGRACOES (para reconhecer bancos sem versão)."""
    revisoes = {re.search(r"^revision = '(\w+)'", p.read_text(encoding="utf-8"), re.M).group(1)
                for p in (PASTA_MIGRACOES / "versions").glob("*.py")}
    assert revisoes == {r for r, _ in MARCOS_MIGRACOES}
