"""Status do mês por empresa: pendente, sem movimento ou preenchido."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select

from ..extensions import db
from ..models import (
    STATUS_PENDENTE, STATUS_PREENCHIDO, STATUS_SEM_MOVIMENTO, Empresa, Fechamento, Lancamento, Usuario,
)
from ..util import comp_curta
from . import RegraViolada, auditoria
from .lancamentos import exigir_edicao, lancamentos_do_mes

ROTULOS = {
    STATUS_PENDENTE: "Pendente",
    STATUS_PREENCHIDO: "Preenchido",
    STATUS_SEM_MOVIMENTO: "Sem movimento",
}


_CONSULTAR = object()  # "marca" não informada: busca no banco (None = já sei que não tem marca)


def status_mes(empresa: Empresa, comp: date, lancs=None, marca=_CONSULTAR) -> str:
    lancs = lancs if lancs is not None else lancamentos_do_mes(empresa, comp)
    if any(l.tem_movimento for l in lancs.values()):
        return STATUS_PREENCHIDO
    if marca is _CONSULTAR:
        marca = db.session.scalar(select(Fechamento).where(Fechamento.empresa_id == empresa.id, Fechamento.competencia == comp))
    if marca is not None and marca.status == STATUS_SEM_MOVIMENTO:
        return STATUS_SEM_MOVIMENTO
    return STATUS_PENDENTE


def status_em_lote(empresas: list[Empresa], comp: date) -> dict[int, str]:
    """Status de várias empresas com 2 consultas no total (em vez de 2 por empresa)."""
    ids = [e.id for e in empresas]
    if not ids:
        return {}
    por_emp: dict[int, dict] = {i: {} for i in ids}
    for l in db.session.scalars(select(Lancamento).where(Lancamento.competencia == comp, Lancamento.empresa_id.in_(ids))):
        por_emp[l.empresa_id][l.tipo_id] = l
    marcas = {f.empresa_id: f for f in db.session.scalars(
        select(Fechamento).where(Fechamento.competencia == comp, Fechamento.empresa_id.in_(ids)))}
    return {e.id: status_mes(e, comp, por_emp[e.id], marcas.get(e.id)) for e in empresas}


def marcar_sem_movimento(empresa: Empresa, comp: date, usuario: Usuario, ativo: bool = True,
                         substituto: bool = False) -> str:
    exigir_edicao(usuario, empresa, comp, substituto)
    lancs = lancamentos_do_mes(empresa, comp)
    if ativo and any(l.tem_movimento for l in lancs.values()):
        raise RegraViolada("A empresa já tem lançamentos neste mês; não pode ser marcada como sem movimento.")
    f = db.session.scalar(select(Fechamento).where(Fechamento.empresa_id == empresa.id, Fechamento.competencia == comp))
    if ativo:
        if f is None:
            f = Fechamento(empresa_id=empresa.id, competencia=comp, status=STATUS_SEM_MOVIMENTO, usuario_id=usuario.id)
            db.session.add(f)
        else:
            f.status = STATUS_SEM_MOVIMENTO
            f.usuario_id = usuario.id
        acao = "marcar_sem_movimento"
    else:
        if f is not None:
            db.session.delete(f)
        acao = "desmarcar_sem_movimento"
    auditoria.registrar("fat_fechamento", acao, usuario, empresa_id=empresa.id,
                        descricao=f"{empresa.nome} · {comp_curta(comp)}: {'sem movimento' if ativo else 'voltou para pendente'}")
    db.session.flush()
    return status_mes(empresa, comp)
