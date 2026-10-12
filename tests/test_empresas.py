"""Cadastro de empresas e carteira (responsável com histórico por competência)."""
from datetime import date

import pytest
from sqlalchemy import select

from faturamento.models import Auditoria, EmpresaResponsavel
from faturamento.services import RegraViolada
from faturamento.services import empresas as svc
from faturamento.util import competencia


def test_criar_empresa_com_vinculo_inicial(db, usuarios, tipos):
    natan = usuarios["Natan"]
    e = svc.criar_empresa("  Bio   Seiva ", natan, natan, cnpj="12.345.678/0001-90",
                          tipo_ids=[tipos["NFE_SAI"].id, tipos["NFE_ENT"].id])
    db.session.commit()
    assert e.nome == "Bio Seiva"
    assert e.cnpj == "12345678000190" and e.cnpj_formatado == "12.345.678/0001-90"
    assert [t.codigo for t in e.tipos] == ["NFE_ENT", "NFE_SAI"]  # ordem do tipo
    assert len(e.historico_responsaveis) == 1
    v = e.historico_responsaveis[0]
    assert v.usuario_id == natan.id and v.origem == "manual" and v.inicio == date(2000, 1, 1)
    assert svc.responsavel_atual(e).id == natan.id
    assert db.session.scalar(select(Auditoria).where(Auditoria.acao == "criar", Auditoria.empresa_id == e.id))


@pytest.mark.parametrize("nome, cnpj, trecho", [
    ("", None, "nome"),
    ("Nova", "123", "14 dígitos"),
    ("bio seiva", None, "Já existe"),          # nome igual ignorando caixa/acento
    ("Outra", "12345678000190", "CNPJ já cadastrado"),
])
def test_criar_empresa_validacoes(nova_empresa, usuarios, nome, cnpj, trecho):
    nova_empresa("Bio Seiva", cnpj="12345678000190")
    with pytest.raises(RegraViolada, match=trecho):
        svc.criar_empresa(nome, usuarios["Natan"], usuarios["Natan"], cnpj=cnpj)


def test_atualizar_empresa_audita_so_quando_muda(db, nova_empresa, usuarios, tipos):
    e = nova_empresa("Bio Seiva")
    natan = usuarios["Natan"]
    antes = db.session.query(Auditoria).count()
    svc.atualizar_empresa(e, natan, nome="Bio Seiva", tipo_ids=[t.id for t in e.tipos])
    assert db.session.query(Auditoria).count() == antes
    svc.atualizar_empresa(e, natan, nome="Bio Seiva Ltda", ativa=False, tipo_ids=[tipos["NFCE"].id])
    db.session.commit()
    assert (e.nome, e.ativa, [t.codigo for t in e.tipos]) == ("Bio Seiva Ltda", False, ["NFCE"])
    reg = db.session.scalar(select(Auditoria).where(Auditoria.acao == "alterar"))
    assert "Bio Seiva Ltda" in reg.descricao


def test_atualizar_cnpj_vazio_limpa(db, nova_empresa, usuarios):
    e = nova_empresa("Bio Seiva", cnpj="12345678000190")
    svc.atualizar_empresa(e, usuarios["Natan"], cnpj="")
    assert e.cnpj is None and e.cnpj_formatado == ""


def test_definir_responsavel_mantem_meses_anteriores(db, nova_empresa, usuarios):
    e = nova_empresa("Bio Seiva", responsavel="Natan")
    natan, hellen = usuarios["Natan"], usuarios["Hellen"]
    assert svc.definir_responsavel(e, hellen, competencia("2026-09"), usuarios["Jaísa"]) is True
    db.session.commit()

    assert svc.responsavel_em(e, competencia("2026-08")).id == natan.id
    assert svc.responsavel_em(e, competencia("2026-09")).id == hellen.id
    assert svc.responsavel_em(e, competencia("2027-01")).id == hellen.id
    assert svc.responsavel_em(e, competencia("1999-01")).id == natan.id  # antes de tudo vale o mais antigo

    hist = e.historico_responsaveis
    assert [(v.usuario.nome, v.inicio) for v in hist] == [("Hellen", date(2026, 9, 1)), ("Natan", date(2000, 1, 1))]
    assert hist[0].registrado_por_id == usuarios["Jaísa"].id and hist[0].origem == "manual"

    reg = db.session.scalar(select(Auditoria).where(Auditoria.acao == "trocar_responsavel"))
    assert reg.usuario_nome == "Jaísa"
    assert "Natan → Hellen" in reg.descricao and "09/2026" in reg.descricao


def test_definir_responsavel_sem_mudanca_retorna_false(db, nova_empresa, usuarios):
    e = nova_empresa("Bio Seiva", responsavel="Natan")
    assert svc.definir_responsavel(e, usuarios["Natan"], competencia("2026-09"), usuarios["Natan"]) is False
    assert len(e.historico_responsaveis) == 1


def test_definir_responsavel_mesmo_inicio_substitui(db, nova_empresa, usuarios):
    e = nova_empresa("Bio Seiva", responsavel="Natan")
    inicio = competencia("2026-09")
    svc.definir_responsavel(e, usuarios["Hellen"], inicio, usuarios["Natan"])
    svc.definir_responsavel(e, usuarios["Mariana"], inicio, usuarios["Natan"], origem="planilha")
    db.session.commit()
    hist = e.historico_responsaveis
    assert len(hist) == 2
    assert hist[0].usuario.nome == "Mariana" and hist[0].origem == "planilha"


def test_definir_responsavel_retroativo_nao_apaga_troca_futura(db, nova_empresa, usuarios):
    e = nova_empresa("Bio Seiva", responsavel="Natan")
    svc.definir_responsavel(e, usuarios["Hellen"], competencia("2026-09"), usuarios["Natan"])
    svc.definir_responsavel(e, usuarios["Mariana"], competencia("2026-06"), usuarios["Natan"])
    db.session.commit()
    nomes = {c: svc.responsavel_em(e, competencia(c)).nome for c in ("2026-05", "2026-06", "2026-08", "2026-09")}
    assert nomes == {"2026-05": "Natan", "2026-06": "Mariana", "2026-08": "Mariana", "2026-09": "Hellen"}


def test_listar_empresas_por_carteira_e_competencia(db, nova_empresa, usuarios):
    a = nova_empresa("Alfa", responsavel="Natan")
    nova_empresa("Beta", responsavel="Hellen")
    inativa = nova_empresa("Gama", responsavel="Natan", cnpj="11222333000144")
    svc.atualizar_empresa(inativa, usuarios["Natan"], ativa=False)
    svc.definir_responsavel(a, usuarios["Hellen"], competencia("2026-09"), usuarios["Natan"])
    db.session.commit()
    natan, hellen = usuarios["Natan"].id, usuarios["Hellen"].id

    def nomes(*args, **kw):
        return [e.nome for e in svc.listar_empresas(*args, **kw)]

    assert nomes(natan, competencia("2026-08")) == ["Alfa"]
    assert nomes(natan, competencia("2026-09")) == []
    assert nomes(hellen, competencia("2026-09")) == ["Alfa", "Beta"]
    assert nomes(hellen, competencia("2026-08")) == ["Beta"]
    assert nomes(natan, competencia("2026-08"), incluir_inativas=True) == ["Alfa", "Gama"]
    assert nomes(None, competencia("2026-08")) == ["Alfa", "Beta"]
    assert nomes(None, incluir_inativas=True, busca="gam") == ["Gama"]
    assert nomes(None, incluir_inativas=True, busca="11.222.333") == ["Gama"]
    assert nomes(None, busca="zzz") == []


def test_buscas_por_nome_e_cnpj(nova_empresa):
    e = nova_empresa("Mercadinho Milhã", cnpj="12345678000190")
    assert svc.buscar_por_nome("MERCADINHO MILHA").id == e.id
    assert svc.buscar_por_cnpj("12.345.678/0001-90").id == e.id
    assert svc.buscar_por_cnpj("") is None


def test_usuarios_e_tipos_ativos(app):
    assert [u.nome for u in svc.usuarios_ativos()] == ["Hellen", "Jaísa", "Mariana", "Natan"]
    assert [t.codigo for t in svc.tipos_ativos()][:2] == ["CTE_ENT", "NFE_ENT"]


def test_vinculo_gravado_no_banco(db, nova_empresa, usuarios):
    e = nova_empresa("Bio Seiva")
    svc.definir_responsavel(e, usuarios["Hellen"], competencia("2026-09"), usuarios["Natan"])
    db.session.commit()
    assert db.session.query(EmpresaResponsavel).filter_by(empresa_id=e.id).count() == 2
