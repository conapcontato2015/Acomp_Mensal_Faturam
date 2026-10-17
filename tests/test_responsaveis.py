"""Importação da planilha de responsáveis (carteira). Dados sintéticos."""
from __future__ import annotations

import io

import pytest

from openpyxl import Workbook

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


