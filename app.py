"""Aplicação para rodar o módulo de faturamento sozinho (no PC ou num servidor).

    python app.py            -> servidor local (waitress) e abre o navegador
    flask --app app db ...   -> comandos de migração (Alembic)

Dentro da plataforma do escritório, use só ``faturamento.init_app(app_da_plataforma)``.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import webbrowser

from flask import Flask, redirect, url_for

from config import Config


def create_app(config_obj=Config) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config.from_object(config_obj)

    from faturamento import init_app
    init_app(app)

    prefixo = (app.config.get("URL_PREFIX") or "").rstrip("/")
    if prefixo:
        @app.get("/")
        def _raiz():
            return redirect(url_for("faturamento.painel"))

    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app = create_app()

    from faturamento.bootstrap import preparar_banco
    from faturamento.services.backup import backup_diario

    preparar_banco(app)
    destino = backup_diario(app.config["SQLALCHEMY_DATABASE_URI"], app.config["DADOS_DIR"] / "backups",
                            app.config["BACKUP_DIAS"])
    if destino:
        logging.info("Backup do dia: %s", destino)

    host, port = app.config["HOST"], app.config["PORT"]
    url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}/"
    if "--sem-navegador" not in sys.argv and os.getenv("ABRIR_NAVEGADOR", "1") == "1":
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    logging.info("Sistema de Faturamento em %s (host %s). Feche esta janela para encerrar.", url, host)

    from waitress import serve
    serve(app, host=host, port=port, threads=8)


if __name__ == "__main__":
    main()
