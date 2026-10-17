"""Lançamento do mês por empresa: números da SEFAZ, ajustes, "bateu" e "sem movimento"."""
from __future__ import annotations

from typing import Union

from fastapi import APIRouter, Depends
from pydantic import Field

from ...db import db
from ...models import Ajuste, Empresa, Lancamento, TipoDocumento, Usuario
from ...services import empresas as svc_emp
from ...services import fechamento as svc_fech
from ...services import lancamentos as svc_lanc
from ...services import resumo as svc_res
from ...util import competencia, competencia_atual
from .. import comum
from ..auth import exigir_usuario
from ..json import Entrada, RespostaJSON
from ..rota import RotaFaturamento

router = APIRouter(route_class=RotaFaturamento, default_response_class=RespostaJSON, tags=["lançamento"])

Numero = Union[str, int, float, None]  # como digitado ("1.234,56") ou já número


def _empresa(eid: int) -> Empresa:
    e = db.session.get(Empresa, eid)
    if e is None:
        raise comum.nao_encontrado("Empresa não encontrada.")
    return e


def _comp_caminho(texto: str):
    try:
        return competencia(texto)
    except ValueError as exc:
        raise comum.erro(str(exc), 400, "parametro_invalido") from exc


def _linhas(empresa: Empresa, comp) -> list[dict]:
    return [comum.lancamento_json(l.lancamento, l.tipo) for l in svc_lanc.carregar_mes(empresa, comp)]


def _carteira_completa(empresa: Empresa, comp) -> dict:
    """Quantas linhas com movimento existem e quantas bateram (para os confetes)."""
    lancs = [l for l in svc_lanc.lancamentos_do_mes(empresa, comp).values() if l.tem_movimento]
    return {"linhas": len(lancs), "bateram": sum(1 for l in lancs if l.bateu)}


@router.get("/lancamento/inicio")
def inicio(competencia: str | None = None, usuario: Usuario = Depends(exigir_usuario)):
    """Tela inicial do lançamento: nada é carregado até escolher a empresa."""
    comp = comum.comp_ou_padrao(competencia)
    minhas = svc_emp.listar_empresas(usuario.id, comp)
    todas = svc_emp.listar_empresas(None, comp)
    status = svc_fech.status_em_lote(minhas, comp)
    ids = {e.id for e in minhas}
    return {
        "competencia": comum.comp_json(comp),
        "minhas": [{**comum.empresa_resumo(e), "status": status[e.id]} for e in minhas],
        "outras": [comum.empresa_resumo(e) for e in todas if e.id not in ids],
    }


@router.get("/lancamento")
def lancamento(empresa: int, competencia: str | None = None, usuario: Usuario = Depends(exigir_usuario)):
    comp = comum.comp_ou_padrao(competencia)
    emp = _empresa(empresa)
    minhas = svc_emp.listar_empresas(usuario.id, comp)
    todas = svc_emp.listar_empresas(None, comp)
    ids = [e.id for e in minhas]
    proxima = minhas[ids.index(emp.id) + 1] if emp.id in ids and ids.index(emp.id) + 1 < len(ids) else None
    evolucao = svc_res.evolucao(emp, comp, 8)
    resp = svc_emp.responsavel_em(emp, comp)
    return {
        "competencia": comum.comp_json(comp),
        "empresa": comum.empresa_resumo(emp),
        "responsavel": comum.usuario_json(resp),
        "status": svc_fech.status_mes(emp, comp),
        "pode_editar": svc_lanc.pode_editar(usuario, emp, comp),
        "futura": comp > competencia_atual(),
        "linhas": _linhas(emp, comp),
        "proxima": comum.empresa_resumo(proxima) if proxima else None,
        "minhas": [comum.empresa_resumo(e) for e in minhas],
        "outras": [comum.empresa_resumo(e) for e in todas if e.id not in set(ids)],
        "evolucao": [{**p, "competencia": comum.comp_json(p["competencia"])} for p in evolucao],
        "grafico": svc_res.alturas_grafico(evolucao),
        "altura_grafico": svc_res.ALTURA_GRAFICO,
    }


class LinhaEntrada(Entrada):
    tipo_id: int
    qtde_autor: Numero = None
    valor_autor: Numero = None
    qtde_canc: Numero = None
    valor_canc: Numero = None


class SalvarEntrada(Entrada):
    linhas: list[LinhaEntrada] = Field(default_factory=list)
    substituto: bool = False


def _bruto(v):
    return "" if v is None else v


@router.put("/lancamento/{empresa_id}/{comp}")
def salvar(empresa_id: int, comp: str, dados: SalvarEntrada, usuario: Usuario = Depends(exigir_usuario)):
    emp = _empresa(empresa_id)
    c = _comp_caminho(comp)
    linhas = [{"tipo_id": l.tipo_id, "qtde_autor": _bruto(l.qtde_autor), "valor_autor": _bruto(l.valor_autor),
               "qtde_canc": _bruto(l.qtde_canc), "valor_canc": _bruto(l.valor_canc)} for l in dados.linhas]
    res = svc_lanc.salvar_mes(emp, c, linhas, usuario, substituto=dados.substituto)
    db.session.commit()
    return {"alterados": res.alterados, "avisos": res.avisos, "status": svc_fech.status_mes(emp, c),
            "linhas": _linhas(emp, c)}


class AjusteEntrada(Entrada):
    grupo: str = "AUTOR"
    qtde: Numero = None
    valor: Numero = None
    motivo: str | None = None
    observacao: str | None = None
    substituto: bool = False


@router.post("/lancamento/{empresa_id}/{comp}/{tipo_id}/ajustes", status_code=201)
def criar_ajuste(empresa_id: int, comp: str, tipo_id: int, dados: AjusteEntrada,
                 usuario: Usuario = Depends(exigir_usuario)):
    emp = _empresa(empresa_id)
    c = _comp_caminho(comp)
    tipo = db.session.get(TipoDocumento, tipo_id)
    if tipo is None:
        raise comum.nao_encontrado("Tipo de documento inexistente.")
    svc_lanc.exigir_edicao(usuario, emp, c, dados.substituto)
    lanc = svc_lanc.obter_ou_criar(emp, c, tipo, usuario)
    aj = svc_lanc.adicionar_ajuste(lanc, dados.grupo, dados.qtde, dados.valor, usuario, motivo=dados.motivo,
                                   observacao=dados.observacao, substituto=True)
    db.session.commit()
    return RespostaJSON({"ajuste": comum.ajuste_json(aj), "linha": comum.lancamento_json(lanc, tipo),
                         "status": svc_fech.status_mes(emp, c)}, status_code=201)


@router.delete("/ajustes/{ajuste_id}")
def remover_ajuste(ajuste_id: int, substituto: bool = False, usuario: Usuario = Depends(exigir_usuario)):
    aj = db.session.get(Ajuste, ajuste_id)
    if aj is None:
        raise comum.nao_encontrado("Ajuste não encontrado.")
    lanc = aj.lancamento
    svc_lanc.remover_ajuste(aj, usuario, substituto)
    db.session.commit()
    return {"linha": comum.lancamento_json(lanc, lanc.tipo)}


class BateuEntrada(Entrada):
    bateu: bool
    substituto: bool = False


@router.put("/lancamentos/{lancamento_id}/bateu")
def bateu(lancamento_id: int, dados: BateuEntrada, usuario: Usuario = Depends(exigir_usuario)):
    lanc = db.session.get(Lancamento, lancamento_id)
    if lanc is None:
        raise comum.nao_encontrado("Lançamento não encontrado.")
    svc_lanc.marcar_bateu(lanc, dados.bateu, usuario, dados.substituto)
    db.session.commit()
    return {"id": lanc.id, "bateu": lanc.bateu, "empresa": _carteira_completa(lanc.empresa, lanc.competencia)}


@router.put("/conferencia/{empresa_id}/{comp}/bateu")
def bateu_empresa(empresa_id: int, comp: str, dados: BateuEntrada, usuario: Usuario = Depends(exigir_usuario)):
    emp = _empresa(empresa_id)
    c = _comp_caminho(comp)
    n = svc_lanc.marcar_bateu_empresa(emp, c, dados.bateu, usuario, dados.substituto)
    db.session.commit()
    return {"alterados": n, "empresa": _carteira_completa(emp, c)}


class FechamentoEntrada(Entrada):
    status: str
    substituto: bool = False


@router.put("/fechamento/{empresa_id}/{comp}")
def fechamento(empresa_id: int, comp: str, dados: FechamentoEntrada, usuario: Usuario = Depends(exigir_usuario)):
    emp = _empresa(empresa_id)
    c = _comp_caminho(comp)
    if dados.status not in ("sem_movimento", "pendente"):
        raise comum.erro("status deve ser 'sem_movimento' ou 'pendente'.", 400, "parametro_invalido")
    novo = svc_fech.marcar_sem_movimento(emp, c, usuario, dados.status == "sem_movimento", dados.substituto)
    db.session.commit()
    return {"status": novo}
