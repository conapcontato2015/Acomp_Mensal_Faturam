"""Regras do lançamento mensal, ajustes, 'bateu', fechamento e consultas de resumo/painel."""
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from faturamento.models import Auditoria, Fechamento, Lancamento
from faturamento.services import RegraViolada, SemPermissao
from faturamento.services import fechamento as svc_fech
from faturamento.services import lancamentos as svc
from faturamento.services import resumo as svc_res
from faturamento.util import competencia_atual, somar_meses


def linha(tipo, qa=None, va=None, qc=None, vc=None):
    return {"tipo_id": tipo.id, "qtde_autor": qa, "valor_autor": va, "qtde_canc": qc, "valor_canc": vc}


@pytest.fixture()
def emp(nova_empresa):
    return nova_empresa("Bio Seiva", responsavel="Natan", tipos_codigos=("NFE_ENT", "NFE_SAI", "NFCE"))


def _lanc(db, emp, comp, tipo):
    db.session.expire_all()
    return svc.buscar(emp.id, comp, tipo.id)


# ------------------------------------------------------------------ salvar_mes

def test_salvar_mes_cria_e_atualiza_upsert(db, emp, comp, usuarios, tipos):
    natan = usuarios["Natan"]
    res = svc.salvar_mes(emp, comp, [linha(tipos["NFE_ENT"], "10", "1.234,56"), linha(tipos["NFE_SAI"])], natan)
    db.session.commit()
    assert res.alterados == 1  # linha vazia não cria registro
    l = _lanc(db, emp, comp, tipos["NFE_ENT"])
    assert (l.qtde_autor, l.valor_autor) == (10, Decimal("1234.56"))
    assert svc.buscar(emp.id, comp, tipos["NFE_SAI"].id) is None

    res = svc.salvar_mes(emp, comp, [linha(tipos["NFE_ENT"], "12", "2.000,00", "1", "50")], natan)
    db.session.commit()
    assert res.alterados == 1
    assert db.session.scalar(select(func.count(Lancamento.id))) == 1  # atualizou, não duplicou
    l = _lanc(db, emp, comp, tipos["NFE_ENT"])
    assert (l.qtde_autor, l.valor_autor, l.qtde_canc, l.valor_canc) == (12, Decimal("2000.00"), 1, Decimal("50.00"))


def test_salvar_mes_sem_mudanca_nao_conta_nem_audita(db, emp, comp, usuarios, tipos):
    natan = usuarios["Natan"]
    svc.salvar_mes(emp, comp, [linha(tipos["NFE_ENT"], 3, "300")], natan)
    db.session.commit()
    n_aud = db.session.scalar(select(func.count(Auditoria.id)))
    res = svc.salvar_mes(emp, comp, [linha(tipos["NFE_ENT"], "3", "300,00")], natan)
    assert res.alterados == 0
    assert db.session.scalar(select(func.count(Auditoria.id))) == n_aud


def test_salvar_mes_tudo_ou_nada(db, emp, comp, usuarios, tipos):
    natan = usuarios["Natan"]
    with pytest.raises(RegraViolada) as exc:
        svc.salvar_mes(emp, comp, [
            linha(tipos["NFE_ENT"], "10", "100,00"),       # válida
            linha(tipos["NFE_SAI"], "abc", "10"),           # inválida
        ], natan)
    db.session.rollback()
    assert any("não é um número válido" in m for m in exc.value.mensagens)
    assert db.session.scalar(select(func.count(Lancamento.id))) == 0


def test_valor_sem_quantidade_rejeitado(emp, comp, usuarios, tipos):
    with pytest.raises(RegraViolada) as exc:
        svc.salvar_mes(emp, comp, [linha(tipos["NFE_ENT"], None, "100,00")], usuarios["Natan"])
    assert any("quantidade e valor juntos" in m for m in exc.value.mensagens)
    with pytest.raises(RegraViolada):
        svc.salvar_mes(emp, comp, [linha(tipos["NFE_ENT"], None, None, "2", None)], usuarios["Natan"])


def test_negativo_rejeitado(emp, comp, usuarios, tipos):
    with pytest.raises(RegraViolada) as exc:
        svc.salvar_mes(emp, comp, [linha(tipos["NFE_ENT"], "-1", "100")], usuarios["Natan"])
    assert any("negativos" in m for m in exc.value.mensagens)
    with pytest.raises(RegraViolada):
        svc.salvar_mes(emp, comp, [linha(tipos["NFE_ENT"], "1", "-100,00")], usuarios["Natan"])


def test_tipo_inexistente_e_sem_tipo(emp, comp, usuarios):
    with pytest.raises(RegraViolada) as exc:
        svc.salvar_mes(emp, comp, [{"tipo_id": 9999}, {"qtde_autor": 1}], usuarios["Natan"])
    assert len(exc.value.mensagens) == 2


def test_competencia_futura_rejeitada(emp, tipos, usuarios):
    futura = somar_meses(competencia_atual(), 1)
    with pytest.raises(RegraViolada, match="futura"):
        svc.salvar_mes(emp, futura, [linha(tipos["NFE_ENT"], 1, 1)], usuarios["Natan"])


def test_canceladas_maior_que_autorizadas_gera_aviso_nao_erro(db, emp, comp, usuarios, tipos):
    res = svc.salvar_mes(emp, comp, [linha(tipos["NFE_SAI"], "2", "200", "5", "500")], usuarios["Natan"])
    db.session.commit()
    assert res.alterados == 1
    assert len(res.avisos) == 1 and "mais canceladas" in res.avisos[0]
    assert _lanc(db, emp, comp, tipos["NFE_SAI"]).qtde_canc == 5


def test_salvar_mes_audita(db, emp, comp, usuarios, tipos):
    svc.salvar_mes(emp, comp, [linha(tipos["NFE_ENT"], 1, 10)], usuarios["Natan"])
    db.session.commit()
    reg = db.session.scalar(select(Auditoria).where(Auditoria.tabela == "fat_lancamento"))
    assert reg.acao == "criar" and reg.usuario_nome == "Natan" and reg.empresa_id == emp.id


# ------------------------------------------------------------------ ajustes

def test_ajustes_entram_nos_totais(db, emp, comp, usuarios, tipos):
    natan = usuarios["Natan"]
    svc.salvar_mes(emp, comp, [linha(tipos["NFE_ENT"], "10", "1.000,00", "1", "100")], natan)
    l = svc.buscar(emp.id, comp, tipos["NFE_ENT"].id)
    svc.adicionar_ajuste(l, "AUTOR", "3", "300,50", natan)
    svc.adicionar_ajuste(l, "AUTOR", "-1", "-50", natan)  # ajuste negativo é permitido
    svc.adicionar_ajuste(l, "canc", "2", "20", natan)     # grupo aceita minúsculas
    db.session.commit()
    l = _lanc(db, emp, comp, tipos["NFE_ENT"])
    assert l.qtde_autor == 10 and l.valor_autor == Decimal("1000.00")  # original não muda
    assert l.ajuste_qtde_autor == 2 and l.ajuste_valor_autor == Decimal("250.50")
    assert l.total_qtde_autor == 12
    assert l.total_valor_autor == Decimal("1250.50")
    assert l.total_qtde_canc == 3 and l.total_valor_canc == Decimal("120.00")
    assert l.tem_ajuste


def test_ajuste_motivo_padrao_e_outro_exige_observacao(emp, comp, usuarios, tipos):
    natan = usuarios["Natan"]
    l = svc.obter_ou_criar(emp, comp, tipos["NFE_ENT"], natan)
    aj = svc.adicionar_ajuste(l, "AUTOR", 1, 10, natan)
    assert aj.motivo.startswith("Arquivos a mais")
    with pytest.raises(RegraViolada, match="Outro"):
        svc.adicionar_ajuste(l, "AUTOR", 1, 10, natan, motivo="Outro")
    aj2 = svc.adicionar_ajuste(l, "AUTOR", 1, 10, natan, motivo="Outro", observacao="XML enviado por e-mail")
    assert aj2.observacao == "XML enviado por e-mail"


@pytest.mark.parametrize("grupo, q, v, trecho", [
    ("XYZ", 1, 1, "Grupo"),
    ("AUTOR", None, 10, "quantidade e valor"),
    ("AUTOR", 1, "", "quantidade e valor"),
    ("AUTOR", 0, "0,00", "zerado"),
    ("AUTOR", "abc", 1, "não é um número"),
])
def test_ajuste_invalido(emp, comp, usuarios, tipos, grupo, q, v, trecho):
    l = svc.obter_ou_criar(emp, comp, tipos["NFE_ENT"], usuarios["Natan"])
    with pytest.raises(RegraViolada, match=trecho):
        svc.adicionar_ajuste(l, grupo, q, v, usuarios["Natan"])


def test_ajuste_so_de_valor_e_permitido(emp, comp, usuarios, tipos):
    l = svc.obter_ou_criar(emp, comp, tipos["NFE_ENT"], usuarios["Natan"])
    aj = svc.adicionar_ajuste(l, "AUTOR", 0, "15,00", usuarios["Natan"])
    assert aj.qtde == 0 and aj.valor == Decimal("15.00")


def test_remover_ajuste(db, emp, comp, usuarios, tipos):
    natan = usuarios["Natan"]
    l = svc.obter_ou_criar(emp, comp, tipos["NFE_ENT"], natan)
    aj = svc.adicionar_ajuste(l, "AUTOR", 2, 20, natan)
    db.session.commit()
    svc.remover_ajuste(aj, natan)
    db.session.commit()
    assert _lanc(db, emp, comp, tipos["NFE_ENT"]).ajustes == []


# ------------------------------------------------------------------ bateu

def test_bateu_trava_numeros_e_ajustes(db, emp, comp, usuarios, tipos):
    natan = usuarios["Natan"]
    svc.salvar_mes(emp, comp, [linha(tipos["NFE_ENT"], 5, 500)], natan)
    l = svc.buscar(emp.id, comp, tipos["NFE_ENT"].id)
    aj = svc.adicionar_ajuste(l, "AUTOR", 1, 10, natan)
    svc.marcar_bateu(l, True, natan)
    db.session.commit()
    assert l.bateu and l.bateu_por_id == natan.id and l.bateu_em is not None

    with pytest.raises(RegraViolada, match="Bateu"):
        svc.salvar_mes(emp, comp, [linha(tipos["NFE_ENT"], 6, 600)], natan)
    db.session.rollback()
    with pytest.raises(RegraViolada, match="Bateu"):
        svc.adicionar_ajuste(l, "AUTOR", 1, 10, natan)
    db.session.rollback()
    with pytest.raises(RegraViolada, match="Bateu"):
        svc.remover_ajuste(aj, natan)
    db.session.rollback()

    # salvar com os mesmos números não é mudança: passa mesmo travado
    assert svc.salvar_mes(emp, comp, [linha(tipos["NFE_ENT"], "5", "500,00")], natan).alterados == 0

    svc.marcar_bateu(l, False, natan)
    assert l.bateu_por_id is None and l.bateu_em is None
    assert svc.salvar_mes(emp, comp, [linha(tipos["NFE_ENT"], 6, 600)], natan).alterados == 1


def test_bateu_rollback_desfaz_linhas_anteriores_do_mesmo_salvamento(db, emp, comp, usuarios, tipos):
    """Linha travada no meio do lote: o service levanta e o rollback do chamador desfaz o resto."""
    natan = usuarios["Natan"]
    svc.salvar_mes(emp, comp, [linha(tipos["NFE_ENT"], 1, 10), linha(tipos["NFE_SAI"], 2, 20)], natan)
    svc.marcar_bateu(svc.buscar(emp.id, comp, tipos["NFE_SAI"].id), True, natan)
    db.session.commit()
    with pytest.raises(RegraViolada):
        svc.salvar_mes(emp, comp, [linha(tipos["NFE_ENT"], 9, 90), linha(tipos["NFE_SAI"], 3, 30)], natan)
    db.session.rollback()
    assert _lanc(db, emp, comp, tipos["NFE_ENT"]).qtde_autor == 1


def test_marcar_bateu_empresa_so_linhas_com_movimento(db, emp, comp, usuarios, tipos):
    natan = usuarios["Natan"]
    svc.salvar_mes(emp, comp, [linha(tipos["NFE_ENT"], 1, 10), linha(tipos["NFE_SAI"], 0, 0)], natan)
    assert svc.marcar_bateu_empresa(emp, comp, True, natan) == 1
    assert svc.buscar(emp.id, comp, tipos["NFE_SAI"].id).bateu is False


# ------------------------------------------------------------------ permissão

def test_outra_carteira_e_somente_leitura(db, emp, comp, usuarios, tipos):
    hellen = usuarios["Hellen"]
    assert svc.pode_editar(hellen, emp, comp) is False
    assert svc.pode_editar(usuarios["Natan"], emp, comp) is True
    assert svc.pode_editar(None, emp, comp) is False
    with pytest.raises(SemPermissao, match="Natan"):
        svc.salvar_mes(emp, comp, [linha(tipos["NFE_ENT"], 1, 10)], hellen)
    l = svc.obter_ou_criar(emp, comp, tipos["NFE_ENT"], usuarios["Natan"])
    with pytest.raises(SemPermissao):
        svc.adicionar_ajuste(l, "AUTOR", 1, 1, hellen)
    with pytest.raises(SemPermissao):
        svc.marcar_bateu(l, True, hellen)
    with pytest.raises(SemPermissao):
        svc_fech.marcar_sem_movimento(emp, comp, hellen)
    with pytest.raises(SemPermissao):
        svc.exigir_edicao(None, emp, comp)


def test_substituto_pode_editar(db, emp, comp, usuarios, tipos):
    hellen = usuarios["Hellen"]
    res = svc.salvar_mes(emp, comp, [linha(tipos["NFE_ENT"], 1, 10)], hellen, substituto=True)
    assert res.alterados == 1
    l = svc.buscar(emp.id, comp, tipos["NFE_ENT"].id)
    assert l.criado_por_id == hellen.id
    assert l.responsavel_id == usuarios["Natan"].id  # carteira continua do responsável
    svc.adicionar_ajuste(l, "AUTOR", 1, 1, hellen, substituto=True)
    svc.marcar_bateu(l, True, hellen, substituto=True)
    assert l.bateu


# ------------------------------------------------------------------ carregar_mes

def test_carregar_mes_inclui_tipo_lancado_fora_dos_tipos_usados(db, emp, comp, usuarios, tipos):
    svc.salvar_mes(emp, comp, [linha(tipos["CTE_ENT"], 1, 10)], usuarios["Natan"])
    linhas = svc.carregar_mes(emp, comp)
    codigos = [l.tipo.codigo for l in linhas]
    assert codigos == ["CTE_ENT", "NFE_ENT", "NFE_SAI", "NFCE"]  # entradas antes, depois pela ordem
    vazia = next(l for l in linhas if l.tipo.codigo == "NFCE")
    assert vazia.lancamento is None and vazia.bateu is False and vazia.ajustes == [] and vazia.qtde_autor is None


# ------------------------------------------------------------------ fechamento

def test_sem_movimento(db, emp, comp, usuarios, tipos):
    natan = usuarios["Natan"]
    assert svc_fech.status_mes(emp, comp) == "pendente"
    assert svc_fech.marcar_sem_movimento(emp, comp, natan) == "sem_movimento"
    db.session.commit()
    assert svc_fech.status_mes(emp, comp) == "sem_movimento"
    assert svc_fech.marcar_sem_movimento(emp, comp, natan, ativo=False) == "pendente"


def test_nao_marca_sem_movimento_com_lancamento(db, emp, comp, usuarios, tipos):
    natan = usuarios["Natan"]
    svc.salvar_mes(emp, comp, [linha(tipos["NFE_ENT"], 1, 10)], natan)
    assert svc_fech.status_mes(emp, comp) == "preenchido"
    with pytest.raises(RegraViolada, match="sem movimento"):
        svc_fech.marcar_sem_movimento(emp, comp, natan)


def test_salvar_lancamento_limpa_sem_movimento(db, emp, comp, usuarios, tipos):
    natan = usuarios["Natan"]
    svc_fech.marcar_sem_movimento(emp, comp, natan)
    db.session.commit()
    svc.salvar_mes(emp, comp, [linha(tipos["NFE_ENT"], 1, 10)], natan)
    db.session.commit()
    assert db.session.scalar(select(Fechamento)) is None
    assert svc_fech.status_mes(emp, comp) == "preenchido"


def test_ajuste_limpa_sem_movimento(db, emp, comp, usuarios, tipos):
    natan = usuarios["Natan"]
    svc_fech.marcar_sem_movimento(emp, comp, natan)
    l = svc.obter_ou_criar(emp, comp, tipos["NFE_ENT"], natan)
    svc.adicionar_ajuste(l, "AUTOR", 1, 10, natan)
    db.session.commit()
    assert svc_fech.status_mes(emp, comp) == "preenchido"


# ------------------------------------------------------------------ resumo / conferência

def test_conferencia_blocos_por_sentido(db, nova_empresa, comp, usuarios, tipos):
    natan = usuarios["Natan"]
    e = nova_empresa("Eletrolar", tipos_codigos=("NFE_ENT", "CTE_ENT", "NFE_SAI", "NFCE"))
    svc.salvar_mes(e, comp, [
        linha(tipos["NFE_ENT"], 10, "1.000,00"), linha(tipos["CTE_ENT"], 2, "50,00", 1, "5"),
        linha(tipos["NFE_SAI"], 4, "400,00"), linha(tipos["NFCE"], 100, "2.500,00"),
    ], natan)
    svc.adicionar_ajuste(svc.buscar(e.id, comp, tipos["NFCE"].id), "AUTOR", 1, "10", natan)
    db.session.commit()

    cartoes = svc_res.conferencia(comp, natan.id)
    assert len(cartoes) == 1
    c = cartoes[0]
    assert [b.sentido for b in c.blocos] == ["E", "S"]
    for b in c.blocos:
        assert {l.tipo.sentido for l in b.linhas} == {b.sentido}  # nunca mistura sentidos
    ent, sai = c.blocos
    assert ent.titulo == "ENTRADAS" and sai.titulo == "SAÍDAS"
    assert [l.tipo.codigo for l in ent.linhas] == ["CTE_ENT", "NFE_ENT"]
    assert (ent.qtde_autor, ent.valor_autor) == (12, Decimal("1050.00"))
    assert (ent.qtde_canc, ent.valor_canc) == (1, Decimal("5.00"))
    assert (sai.qtde_autor, sai.valor_autor) == (105, Decimal("2910.00"))  # inclui ajuste
    assert c.total == 4 and c.n_bateu == 0 and not c.tudo_bateu

    so_saidas = svc_res.conferencia(comp, natan.id, sentido="S")
    assert [b.sentido for b in so_saidas[0].blocos] == ["S"]

    svc.marcar_bateu(svc.buscar(e.id, comp, tipos["NFE_ENT"].id), True, natan)
    assert len(svc_res.conferencia(comp, natan.id, situacao="conferidas")[0].linhas) == 1
    assert len(svc_res.conferencia(comp, natan.id, situacao="pendentes")[0].linhas) == 3
    prog = svc_res.progresso_conferencia(comp, natan.id)
    assert prog["linhas"] == 4 and prog["bateram"] == 1 and prog["percentual"] == 25
    assert svc_res.conferencia(comp, usuarios["Hellen"].id) == []


def test_conferencia_ignora_empresa_sem_movimento(db, emp, comp, usuarios, tipos):
    svc.salvar_mes(emp, comp, [linha(tipos["NFE_ENT"], 0, 0)], usuarios["Natan"])
    assert svc_res.conferencia(comp, None) == []


# ------------------------------------------------------------------ painel

def _saidas(emp, comp, valor, usuario, tipo):
    svc.salvar_mes(emp, comp, [linha(tipo, 1, valor)], usuario)


def test_painel_status_e_totais(db, nova_empresa, comp, usuarios, tipos):
    natan = usuarios["Natan"]
    a = nova_empresa("A Preenchida")
    b = nova_empresa("B Sem Movimento")
    nova_empresa("C Pendente")
    nova_empresa("D da Hellen", responsavel="Hellen")
    svc.salvar_mes(a, comp, [linha(tipos["NFE_ENT"], 1, "100"), linha(tipos["NFE_SAI"], 2, "300"),
                             linha(tipos["NFCE"], 3, "200")], natan)
    svc_fech.marcar_sem_movimento(b, comp, natan)
    db.session.commit()

    linhas = {l.empresa.nome: l for l in svc_res.painel(comp, natan.id)}
    assert set(linhas) == {"A Preenchida", "B Sem Movimento", "C Pendente"}
    la = linhas["A Preenchida"]
    assert la.status == "preenchido" and la.entradas == Decimal(100) and la.saidas == Decimal(500)
    assert (la.tipos_usados, la.tipos_lancados, la.linhas, la.bateram) == (3, 3, 3, 0)
    assert linhas["B Sem Movimento"].status == "sem_movimento"
    assert linhas["C Pendente"].status == "pendente" and linhas["C Pendente"].entradas is None
    assert linhas["C Pendente"].status_anterior == "pendente"
    assert len(svc_res.painel(comp, None)) == 4


@pytest.mark.parametrize("atual, alerta", [("160", True), ("140", False), ("40", True), ("60", False)])
def test_painel_alerta_variacao(db, emp, comp, usuarios, tipos, atual, alerta):
    natan = usuarios["Natan"]
    for i in (1, 2, 3):
        _saidas(emp, somar_meses(comp, -i), "100", natan, tipos["NFE_SAI"])
    _saidas(emp, comp, atual, natan, tipos["NFE_SAI"])
    db.session.commit()
    lp = svc_res.painel(comp, natan.id)[0]
    assert lp.variacao_saidas == pytest.approx(float(Decimal(atual) / 100 - 1))
    assert (lp.alerta is not None) is alerta
    if alerta:
        assert "média dos 3 meses" in lp.alerta


def test_painel_alerta_exatamente_50_por_cento(db, emp, comp, usuarios, tipos):
    natan = usuarios["Natan"]
    for i in (1, 2, 3):
        _saidas(emp, somar_meses(comp, -i), "100", natan, tipos["NFE_SAI"])
    _saidas(emp, comp, "150", natan, tipos["NFE_SAI"])
    db.session.commit()
    assert svc_res.painel(comp, natan.id)[0].alerta is not None  # >= 50%


def test_painel_sem_historico_suficiente_nao_alerta(db, emp, comp, usuarios, tipos):
    natan = usuarios["Natan"]
    _saidas(emp, somar_meses(comp, -1), "100", natan, tipos["NFE_SAI"])
    _saidas(emp, comp, "1000", natan, tipos["NFE_SAI"])
    db.session.commit()
    lp = svc_res.painel(comp, natan.id)[0]
    assert lp.alerta is None and lp.variacao_saidas is None


def test_evolucao_separa_ajuste(db, emp, comp, usuarios, tipos):
    natan = usuarios["Natan"]
    svc.salvar_mes(emp, comp, [linha(tipos["NFE_SAI"], 1, "100")], natan)
    svc.adicionar_ajuste(svc.buscar(emp.id, comp, tipos["NFE_SAI"].id), "AUTOR", 1, "25", natan)
    serie = svc_res.evolucao(emp, comp, 3)
    assert [p["competencia"] for p in serie] == [somar_meses(comp, -2), somar_meses(comp, -1), comp]
    assert serie[-1]["saidas"] == Decimal(100) and serie[-1]["saidas_ajuste"] == Decimal(25)
    assert serie[0]["saidas"] == 0


# ------------------------------------------------------------------ regressões da revisão

@pytest.mark.parametrize("linhas", ["x", {"tipo_id": 1}, [1, 2], ["a"], None, [None]])
def test_salvar_mes_formato_invalido_vira_regra(emp, comp, usuarios, linhas):
    with pytest.raises(RegraViolada, match="lista de objetos"):
        svc.salvar_mes(emp, comp, linhas, usuarios["Natan"])


def test_salvar_mes_tipo_repetido_rejeitado(db, emp, comp, usuarios, tipos):
    with pytest.raises(RegraViolada, match="mais de uma vez"):
        svc.salvar_mes(emp, comp, [linha(tipos["NFE_ENT"], 1, 10), linha(tipos["NFE_ENT"], 2, 20)], usuarios["Natan"])
    db.session.rollback()
    assert _lanc(db, emp, comp, tipos["NFE_ENT"]) is None


@pytest.mark.parametrize("qa", ["1.5", "12.34", "1,5"])
def test_salvar_mes_quantidade_fracionada_rejeitada(emp, comp, usuarios, tipos, qa):
    with pytest.raises(RegraViolada):
        svc.salvar_mes(emp, comp, [linha(tipos["NFE_ENT"], qa, "10")], usuarios["Natan"])


def test_ajuste_em_competencia_futura_rejeitado(db, emp, usuarios, tipos):
    futura = somar_meses(competencia_atual(), 1)
    with pytest.raises(RegraViolada, match="futura"):
        svc.obter_ou_criar(emp, futura, tipos["NFE_ENT"], usuarios["Natan"])
    assert db.session.scalar(select(func.count(Lancamento.id))) == 0
    # lançamento futuro gravado por fora (ex.: banco antigo) também não aceita ajuste
    lanc = Lancamento(empresa_id=emp.id, competencia=futura, tipo_id=tipos["NFE_ENT"].id)
    db.session.add(lanc)
    db.session.flush()
    with pytest.raises(RegraViolada, match="futura"):
        svc.adicionar_ajuste(lanc, "AUTOR", 1, "1", usuarios["Natan"])
