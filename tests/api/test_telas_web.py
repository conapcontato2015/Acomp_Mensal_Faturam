"""Telas Next.js compiladas (web/out) servidas pelo servidor.py no caminho do Conap Ferramentas."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from faturamento.config import TestConfig

PASTA = Path(__file__).resolve().parents[2] / "web" / "out"
TELAS = ["", "lancamento", "conferencia", "conferencia/imprimir", "empresas", "empresas/editar",
         "empresas/responsaveis", "empresas/controle-fiscal", "empresas/plataforma", "tipos-documento",
         "importacao", "importacao/cruzamento", "historico"]
PRONTAS = {"", "lancamento"}  # telas já migradas; as demais entram a cada lote


@pytest.mark.parametrize("tela", sorted(PRONTAS))
def test_tela_compilada_existe(tela):
    assert (PASTA / "ferramentas" / "faturamento" / tela / "index.html").exists(), f"rode npm run build em web/ ({tela})"


def test_servidor_serve_telas_e_redireciona_a_raiz():
    import servidor

    app = servidor.criar_app(TestConfig, preparar_banco=False)
    with TestClient(app) as c:
        r = c.get("/", follow_redirects=False)
        assert r.status_code in (302, 307) and r.headers["location"] == "/ferramentas/faturamento/"
        r = c.get("/ferramentas/faturamento/")
        assert r.status_code == 200 and "Faturamento" in r.text
        assert c.get("/api/faturamento/saude").status_code == 200
