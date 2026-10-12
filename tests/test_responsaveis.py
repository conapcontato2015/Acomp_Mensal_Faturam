"""Importação da planilha de responsáveis (carteira). Dados sintéticos."""
from __future__ import annotations

import io
import re

import pytest

from conftest import TOKEN_CSRF
from openpyxl import Workbook
from sqlalchemy import select

from faturamento.models import ORIGEM_PLANILHA, EmpresaResponsavel
from faturamento.responsaveis import ProvedorPlanilha, sincronizar
from faturamento.services import empresas as svc_emp
from faturamento.util import competencia

CNPJ_ALFA = "11222333000181"


@pytest.fixture(autouse=True)
def dados_tmp(app, tmp_path):
    app.config["DADOS_DIR"] = tmp_path
    return tmp_path


@pytest.fixture()
def carteira(nova_empresa):
    return {
        "alfa": nova_empresa("Loja Alfa (Matriz)", responsavel="Natan", cnpj=CNPJ_ALFA),
        "beta": nova_empresa("Padaria Beta", responsavel="Natan"),
        "gama": nova_empresa("Gama Serviços", responsavel="Hellen"),
    }


def _xlsx(linhas) -> bytes:
    wb = Workbook()
    for l in linhas:
        wb.active.append(l)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _enviar(cli, conteudo: bytes, nome: str, inicio="2026-09"):
    return cli.post("/empresas/importar-responsaveis",
                    data={"csrf_token": TOKEN_CSRF, "arquivo": (io.BytesIO(conteudo), nome), "inicio": inicio},
                    content_type="multipart/form-data")


def _token(html):
    m = re.search(r'name="token" value="([^"]+)"', html)
    return m.group(1) if m else None


@pytest.mark.parametrize("sep", [";", ","])
def test_csv_com_ponto_e_virgula_e_virgula(app, db, carteira, sep):
    texto = sep.join(["CNPJ", "EMPRESA", "RESPONSAVEL", "INICIO"]) + "\n"
    texto += sep.join(["11.222.333/0001-81", "", "Mariana", "2026-08"]) + "\n"
    texto += sep.join(["", "PADARIA BETA", "jaisa", ""]) + "\n"
    texto += sep.join(["", "Gama Servicos", "Hellen", ""]) + "\n"
    prov = ProvedorPlanilha(texto.encode("utf-8"), "resp.csv")
    previa = sincronizar(prov, None, inicio_padrao=competencia("2026-09"), aplicar=False)
    assert len(previa.alteradas) == 2 and previa.sem_mudanca == 1
    assert svc_emp.responsavel_atual(carteira["alfa"]).nome == "Natan"  # prévia não grava

    rel = sincronizar(prov, None, inicio_padrao=competencia("2026-09"), aplicar=True)
    db.session.commit()
    assert len(rel.alteradas) == 2
    assert svc_emp.responsavel_em(carteira["alfa"], competencia("2026-08")).nome == "Mariana"
    assert svc_emp.responsavel_em(carteira["alfa"], competencia("2026-07")).nome == "Natan"
    assert svc_emp.responsavel_em(carteira["beta"], competencia("2026-09")).nome == "Jaísa"


def test_tela_fluxo_xlsx_com_historico_planilha(app, db, login, carteira, usuarios, dados_tmp):
    cli = login("Natan")
    pagina = cli.get("/empresas/importar-responsaveis").get_data(as_text=True)
    assert "não configurada (manual)" in pagina and "RESPONSAVEL" in pagina

    dados = _xlsx([["EMPRESA", "RESPONSAVEL"], ["Loja Alfa (Matriz)", "Hellen"], ["Padaria Beta", "Natan"]])
    resp = _enviar(cli, dados, "carteira.xlsx")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Loja Alfa (Matriz): Natan → Hellen" in html
    token = _token(html)
    assert token and (dados_tmp / "importacoes" / f"{token}.bin").exists()
    assert svc_emp.responsavel_atual(carteira["alfa"]).nome == "Natan"

    resp = cli.post("/empresas/importar-responsaveis/confirmar",
                    data={"csrf_token": TOKEN_CSRF, "token": token, "inicio": "2026-09", "acao": "confirmar"})
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/empresas")
    db.session.expire_all()
    vinc = db.session.scalar(select(EmpresaResponsavel).where(
        EmpresaResponsavel.empresa_id == carteira["alfa"].id, EmpresaResponsavel.inicio == competencia("2026-09")))
    assert vinc.usuario.nome == "Hellen" and vinc.origem == ORIGEM_PLANILHA
    assert vinc.registrado_por_id == usuarios["Natan"].id
    assert not (dados_tmp / "importacoes" / f"{token}.bin").exists()
    html = cli.get("/empresas").get_data(as_text=True)
    assert "Responsáveis atualizados: 1 empresa(s) trocada(s)" in html


def test_empresa_e_usuario_desconhecidos(app, db, login, carteira):
    cli = login("Natan")
    texto = "EMPRESA;RESPONSAVEL\nEmpresa Fantasma;Natan\nPadaria Beta;Fulano\nGama Serviços;Natan\n"
    html = _enviar(cli, texto.encode(), "r.csv").get_data(as_text=True)
    assert "Empresa não cadastrada: Empresa Fantasma" in html
    assert "Responsável desconhecido: Fulano (Padaria Beta)" in html
    assert "Gama Serviços: Hellen → Natan" in html


def test_planilha_sem_colunas_e_sem_trocas(app, db, login, carteira):
    cli = login("Natan")
    html = _enviar(cli, b"NOME;OUTRA\nx;y\n", "r.csv").get_data(as_text=True)
    assert "precisa das colunas RESPONSAVEL" in html and _token(html) is None
    html = _enviar(cli, b"EMPRESA;RESPONSAVEL\nPadaria Beta;Natan\n", "r.csv").get_data(as_text=True)
    assert "Nenhuma troca a aplicar" in html and _token(html) is None
    resp = cli.post("/empresas/importar-responsaveis", data={"csrf_token": TOKEN_CSRF, "arquivo": (io.BytesIO(b"x"), "r.pdf")},
                    content_type="multipart/form-data", follow_redirects=True)
    assert "Formato não aceito" in resp.get_data(as_text=True)


def test_cancelar_e_token_invalido(app, db, login, carteira):
    cli = login("Natan")
    token = _token(_enviar(cli, b"EMPRESA;RESPONSAVEL\nPadaria Beta;Mariana\n", "r.csv").get_data(as_text=True))
    resp = cli.post("/empresas/importar-responsaveis/confirmar", data={"csrf_token": TOKEN_CSRF, "token": token, "acao": "cancelar"},
                    follow_redirects=True)
    assert "Nada foi alterado" in resp.get_data(as_text=True)
    resp = cli.post("/empresas/importar-responsaveis/confirmar", data={"csrf_token": TOKEN_CSRF, "token": token}, follow_redirects=True)
    assert "expirado" in resp.get_data(as_text=True)
    assert svc_emp.responsavel_atual(carteira["beta"]).nome == "Natan"


def test_modelo_csv(app, db, login, carteira):
    cli = login("Natan")
    resp = cli.get("/empresas/importar-responsaveis/modelo.csv")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv" and "attachment" in resp.headers["Content-Disposition"]
    texto = resp.data.decode("utf-8-sig")
    linhas = texto.strip().splitlines()
    assert linhas[0] == "CNPJ;EMPRESA;RESPONSAVEL;INICIO"
    assert "11.222.333/0001-81;Loja Alfa (Matriz);Natan;" in linhas
    assert ";Gama Serviços;Hellen;" in linhas
    # o modelo baixado volta sem mudanças
    rel = sincronizar(ProvedorPlanilha(resp.data, "modelo.csv"), None, aplicar=False)
    assert rel.alteradas == [] and rel.sem_mudanca == 3 and not rel.erros


# ------------------------------------------------------------------ regressões da revisão

@pytest.mark.parametrize("conteudo, nome", [
    (b"lixo que nao e zip", "r.xlsx"),
    (b"PK\x03\x04quebrado", "r.xlsx"),
    (b'CNPJ;RESPONSAVEL\n"aberto;Natan\n' + b"x" * 200000, "r.csv"),
], ids=["xlsx-texto", "xlsx-zip-quebrado", "csv-campo-gigante"])
def test_arquivo_ilegivel_vira_erro_amigavel(app, db, carteira, usuarios, conteudo, nome):
    rel = sincronizar(ProvedorPlanilha(conteudo, nome), usuarios["Natan"], aplicar=False)
    assert rel.erros and rel.erros[0].startswith("Arquivo ilegível")


def test_csv_de_uma_coluna_nao_quebra(app, db, carteira, usuarios):
    # Sniffer não acha delimitador em arquivo de uma coluna: usa ';' e reclama das colunas que faltam
    rel = sincronizar(ProvedorPlanilha(b"RESPONSAVEL\nNatan\nHellen\n", "r.csv"), usuarios["Natan"], aplicar=False)
    assert rel.erros == ["A planilha precisa das colunas RESPONSAVEL e CNPJ ou EMPRESA (na primeira linha)."]


def test_tela_arquivo_ilegivel_nao_da_500(app, db, login, carteira):
    cli = login("Natan")
    resp = _enviar(cli, b"lixo", "r.xlsx")
    assert resp.status_code == 200
    assert "Arquivo ilegível" in resp.get_data(as_text=True)
