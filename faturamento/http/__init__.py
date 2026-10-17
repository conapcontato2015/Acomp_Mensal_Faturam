"""API do Faturamento em FastAPI, no padrão do Conap Ferramentas.

Todas as rotas ficam sob ``/api/faturamento`` (prefixo próprio da ferramenta, como as demais da
plataforma). Para plugar no FastAPI do Conap Ferramentas:

    from faturamento.config import configurar, Config
    from faturamento.http import router as faturamento_router

    configurar(Config)                    # banco e opções (DATABASE_URL, MODO_AUTH=plataforma, JWT_*)
    app.include_router(faturamento_router)

Sozinho (no PC): ``python servidor.py`` — ver ``servidor.py``.
"""
from __future__ import annotations

from fastapi import APIRouter

from .json import RespostaJSON
from .rota import RotaFaturamento
from .rotas import conferencia, empresas, historico, importacao, lancamento, painel, sessao

PREFIXO = "/api/faturamento"

router = APIRouter(prefix=PREFIXO, route_class=RotaFaturamento, default_response_class=RespostaJSON)
for _m in (sessao, painel, lancamento, conferencia, empresas, importacao, historico):
    router.include_router(_m.router)


@router.get("/saude", tags=["infra"])
def saude():
    """Status da API e do banco, no formato do /api/health da plataforma."""
    from sqlalchemy import text

    from ..db import db

    try:
        db.session.execute(text("SELECT 1"))
        banco = "ok"
    except Exception:  # noqa: BLE001 - só informa
        banco = "erro"
    return {"status": "ok", "banco": banco}


__all__ = ["router", "PREFIXO"]
