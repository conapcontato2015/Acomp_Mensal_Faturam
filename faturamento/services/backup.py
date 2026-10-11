"""Backup diário do banco SQLite (modo local). No PostgreSQL o backup é do servidor."""
from __future__ import annotations

import shutil
import sqlite3
from datetime import date
from pathlib import Path


def caminho_sqlite(uri: str) -> Path | None:
    if not uri.startswith("sqlite:///"):
        return None
    p = Path(uri.replace("sqlite:///", "", 1))
    return p if p.exists() else None


def backup_diario(uri: str, pasta: Path, manter_dias: int = 30, hoje: date | None = None) -> Path | None:
    """Cria ``faturamento-AAAAMMDD.db`` uma vez por dia e apaga os mais antigos que ``manter_dias`` cópias."""
    if manter_dias <= 0:
        return None
    origem = caminho_sqlite(uri)
    if origem is None:
        return None
    pasta.mkdir(parents=True, exist_ok=True)
    hoje = hoje or date.today()
    destino = pasta / f"faturamento-{hoje:%Y%m%d}.db"
    if not destino.exists():
        # API de backup do SQLite: cópia consistente mesmo com o sistema aberto.
        with sqlite3.connect(origem) as src, sqlite3.connect(destino) as dst:
            src.backup(dst)
    copias = sorted(pasta.glob("faturamento-*.db"))
    for velho in copias[:-manter_dias]:
        velho.unlink(missing_ok=True)
    return destino


def copiar(origem: Path, destino: Path) -> None:  # pragma: no cover - utilitário manual
    shutil.copy2(origem, destino)
