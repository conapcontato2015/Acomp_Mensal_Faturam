"""Listas não podem fazer uma consulta por empresa (N+1): com 248 empresas a tela travava."""
from __future__ import annotations

from sqlalchemy import event

from faturamento.extensions import db as _db
from faturamento.services import fechamento as svc_fech
from faturamento.services import lancamentos as svc_lanc
from faturamento.services import resumo as svc_res
from faturamento.services import empresas as svc_emp
from faturamento.util import competencia

COMP = competencia("2026-08")


def _contar(fn):
    n = {"q": 0}

    def ouvir(*a, **k):
        n["q"] += 1

    event.listen(_db.engine, "before_cursor_execute", ouvir)
    try:
        fn()
    finally:
        event.remove(_db.engine, "before_cursor_execute", ouvir)
    return n["q"]


def _criar(nova_empresa, tipos, usuarios, quantas):
    for i in range(quantas):
        e = nova_empresa(f"Empresa {i:03d}", tipos_codigos=("NFE_ENT", "NFE_SAI"))
        if i % 3 == 0:
            svc_lanc.salvar_mes(e, COMP, [{"tipo_id": tipos["NFE_SAI"].id, "qtde_autor": "1", "valor_autor": "10,00",
                                           "qtde_canc": "", "valor_canc": ""}], usuarios["Natan"])
    _db.session.commit()
    _db.session.expire_all()


def test_painel_e_conferencia_tem_poucas_consultas_independente_do_numero_de_empresas(app, usuarios, tipos, nova_empresa):
    _criar(nova_empresa, tipos, usuarios, 40)
    assert _contar(lambda: svc_res.painel(COMP, None)) <= 20
    _db.session.expire_all()
    assert _contar(lambda: svc_res.conferencia(COMP, None)) <= 15
    _db.session.expire_all()
    assert _contar(lambda: svc_emp.listar_empresas(None, COMP)) <= 8


def test_status_em_lote_igual_ao_individual(app, usuarios, tipos, nova_empresa):
    _criar(nova_empresa, tipos, usuarios, 9)
    sem_mov = svc_emp.buscar_por_nome("Empresa 001")
    svc_fech.marcar_sem_movimento(sem_mov, COMP, usuarios["Natan"])
    _db.session.commit()
    empresas = svc_emp.listar_empresas(None, COMP)
    em_lote = svc_fech.status_em_lote(empresas, COMP)
    assert em_lote == {e.id: svc_fech.status_mes(e, COMP) for e in empresas}
    assert set(em_lote.values()) == {"preenchido", "sem_movimento", "pendente"}
    assert _contar(lambda: svc_fech.status_em_lote(empresas, COMP)) <= 8  # constante, não 2 por empresa
