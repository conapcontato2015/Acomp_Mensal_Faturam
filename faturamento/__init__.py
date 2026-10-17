"""Módulo de Acompanhamento Mensal de Faturamento (CONAP), no formato de ferramenta do Conap Ferramentas.

- Regras de negócio: ``faturamento.services`` (sem framework web).
- API JSON (FastAPI): ``faturamento.http.router``, com prefixo ``/api/faturamento``. Para plugar num app
  FastAPI já existente (ex.: o backend da plataforma)::

      from faturamento.config import configurar
      from faturamento.http import router
      configurar(MinhaConfig)
      app.include_router(router)

- Telas (Next.js): pasta ``web/``, em ``/ferramentas/faturamento``.
- Rodando sozinho (no PC ou num servidor): ``servidor.py``.
"""
from __future__ import annotations

__version__ = "2.0.0"
