"""Cadastro de tipos de documento e o sentido "Outros" (fora dos totais de entradas/saídas e do gráfico)."""
from __future__ import annotations

import pytest

from faturamento.models import OUTROS
from faturamento.services import RegraViolada
from faturamento.services import lancamentos as svc_lanc
from faturamento.services import resumo as svc_res
from faturamento.services import tipos as svc_tipos



def _salvar(empresa, comp, tipo, valor, natan):
    svc_lanc.salvar_mes(empresa, comp, [{"tipo_id": tipo.id, "qtde_autor": "1", "valor_autor": valor,
                                         "qtde_canc": "", "valor_canc": ""}], natan)


def test_criar_gera_codigo_unico_e_ordem_no_fim(app, db, usuarios):
    natan = usuarios["Natan"]
    t1 = svc_tipos.criar("SPED Entradas", "E", natan)
    t2 = svc_tipos.criar("sped entradas 2", "E", natan)
    db.session.commit()
    assert t1.codigo == "SPED_ENTRADAS" and t2.codigo == "SPED_ENTRADAS_2"
    assert t1.ordem > 70 and t2.ordem > t1.ordem and t1.ativo
    with pytest.raises(RegraViolada, match="Já existe"):
        svc_tipos.criar("SPED ENTRADAS", "E", natan)
    with pytest.raises(RegraViolada, match="Entrada, Saída ou Outros"):
        svc_tipos.criar("Qualquer", "X", natan)
    with pytest.raises(RegraViolada, match="nome"):
        svc_tipos.criar("  ", "E", natan)


def test_sentido_trava_depois_de_ter_lancamento(app, db, usuarios, tipos, nova_empresa, comp):
    natan = usuarios["Natan"]
    novo = svc_tipos.criar("Ext. Financeiro", "S", natan)
    db.session.commit()
    svc_tipos.atualizar(novo, natan, sentido="E")  # sem lançamentos: pode mudar
    assert novo.sentido == "E"
    e = nova_empresa("Loja", tipos_codigos=())
    e.tipos = [novo]
    db.session.commit()
    _salvar(e, comp, novo, "10,00", natan)
    db.session.commit()
    with pytest.raises(RegraViolada, match="sentido não pode mudar"):
        svc_tipos.atualizar(novo, natan, sentido="S")
    svc_tipos.atualizar(novo, natan, nome="Extrato Financeiro", ativo=False)  # o resto pode
    assert novo.nome == "Extrato Financeiro" and novo.ativo is False


def test_outros_fica_fora_do_grafico_do_painel_e_agrupa_na_conferencia(app, db, usuarios, tipos, nova_empresa, comp):
    natan = usuarios["Natan"]
    caixa = svc_tipos.criar("Receb. Caixa", OUTROS, natan)
    db.session.commit()
    e = nova_empresa("Regime de Caixa", tipos_codigos=("NFE_SAI",))
    e.tipos = list(e.tipos) + [caixa]
    db.session.commit()
    svc_lanc.salvar_mes(e, comp, [
        {"tipo_id": tipos["NFE_SAI"].id, "qtde_autor": "2", "valor_autor": "100,00", "qtde_canc": "", "valor_canc": ""},
        {"tipo_id": caixa.id, "qtde_autor": "5", "valor_autor": "999,00", "qtde_canc": "", "valor_canc": ""},
    ], natan)
    db.session.commit()

    serie = next(p for p in svc_res.evolucao(e, comp, 1))
    assert str(serie["saidas"]) == "100.00" and str(serie["entradas"]) == "0"
    linha = next(l for l in svc_res.painel(comp, None) if l.empresa.id == e.id)
    assert str(linha.saidas) == "100.00" and str(linha.entradas) == "0"

    cartao = svc_res.conferencia(comp, None)[0]
    assert [b.sentido for b in cartao.blocos] == ["S", "O"]
    outros = cartao.blocos[1]
    assert outros.titulo == "OUTROS" and outros.nome_subtotal == "outros"
    assert str(outros.valor_autor) == "999.00"
    assert [t.nome for t in svc_lanc.tipos_do_mes(e, comp)] == ["NF-e Saídas", "Receb. Caixa"]


