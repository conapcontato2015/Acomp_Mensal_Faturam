"""Comandos de migração do banco (Alembic) sem Flask.

    python -m faturamento.migracoes upgrade
    python -m faturamento.migracoes revision -m "descrição"     (gera a partir dos modelos)
    python -m faturamento.migracoes check
    python -m faturamento.migracoes current | history
"""
from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    from alembic import command

    from .bootstrap import config_alembic
    from .config import Config, configurar

    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__)
        return 1
    configurar(Config)
    cfg = config_alembic()
    acao, resto = argv[0], argv[1:]
    if acao == "upgrade":
        command.upgrade(cfg, resto[0] if resto else "head")
    elif acao == "downgrade":
        command.downgrade(cfg, resto[0] if resto else "-1")
    elif acao == "revision":
        msg = resto[resto.index("-m") + 1] if "-m" in resto else "alteracao"
        command.revision(cfg, message=msg, autogenerate=True)
    elif acao == "check":
        command.check(cfg)
    elif acao == "current":
        command.current(cfg)
    elif acao == "history":
        command.history(cfg)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
