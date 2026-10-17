"""Faturamento rodando sozinho (no PC ou num servidor): API FastAPI + telas Next.js já compiladas.

    python servidor.py                          -> prepara o banco, abre o navegador (http://localhost:5000)
    python servidor.py --sem-navegador
    uvicorn servidor:criar_app --factory        -> servidor (as migrações rodam ao subir)

Telas: ``web/out`` (export estático do Next.js, gerado por ``npm run build`` em ``web/``), servidas em
``/ferramentas/faturamento/`` — o mesmo caminho que a ferramenta terá no Conap Ferramentas.
API: ``/api/faturamento/*``.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from faturamento.config import Config, config, configurar

RAIZ = Path(__file__).resolve().parent
PASTA_TELAS = RAIZ / "web" / "out"
CAMINHO_TELAS = "/ferramentas/faturamento"


def criar_app(cfg=Config, preparar_banco: bool = True, telas: Path | None = PASTA_TELAS) -> FastAPI:
    configurar(cfg)

    @asynccontextmanager
    async def ciclo(_app: FastAPI):
        if preparar_banco:
            from faturamento.bootstrap import preparar_banco as preparar
            from faturamento.services.backup import backup_diario

            preparar()
            destino = backup_diario(config["SQLALCHEMY_DATABASE_URI"], Path(config["DADOS_DIR"]) / "backups",
                                    config["BACKUP_DIAS"])
            if destino:
                logging.info("Backup do dia: %s", destino)
        yield

    from faturamento import __version__
    from faturamento.http import router

    # Como na plataforma: documentação automática do FastAPI desligada.
    app = FastAPI(title="Faturamento CONAP", version=__version__, lifespan=ciclo,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(router)

    @app.get("/", include_in_schema=False)
    def _raiz():
        return RedirectResponse(f"{CAMINHO_TELAS}/")

    if telas is not None and telas.exists():
        # html=True: /ferramentas/faturamento/painel/ -> painel/index.html (export com trailingSlash)
        app.mount("/", StaticFiles(directory=telas, html=True), name="telas")
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    import uvicorn

    app = criar_app()
    host, port = config["HOST"], int(config["PORT"])
    url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}{CAMINHO_TELAS}/"
    if not PASTA_TELAS.exists():
        logging.warning("Telas não encontradas em %s — só a API está disponível.", PASTA_TELAS)
    if "--sem-navegador" not in sys.argv and os.getenv("ABRIR_NAVEGADOR", "1") == "1":
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    logging.info("Sistema de Faturamento em %s (host %s). Feche esta janela para encerrar.", url, host)
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
