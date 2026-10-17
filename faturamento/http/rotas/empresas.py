"""Empresas (cadastro, carteira, tipos usados) e tipos de documento."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ...db import db
from ...models import ORIGEM_MANUAL, SENTIDOS, Empresa, TipoDocumento, Usuario
from ...services import auditoria as aud
from ...services import empresas as svc_emp
from ...services import empresas_plataforma as svc_plat
from ...services import tipos as svc_tipos
from ...util import competencia, competencia_atual, competencia_padrao
from .. import comum
from ..auth import exigir_usuario
from ..json import Entrada, RespostaJSON
from ..rota import RotaFaturamento

router = APIRouter(route_class=RotaFaturamento, default_response_class=RespostaJSON, tags=["empresas"])


def _empresa(eid: int) -> Empresa:
    e = db.session.get(Empresa, eid)
    if e is None:
        raise comum.nao_encontrado("Empresa não encontrada.")
    return e


def _linha_lista(e: Empresa) -> dict:
    hist = e.historico_responsaveis
    return {**comum.empresa_resumo(e), "external_id": e.external_id,
            "responsavel": comum.usuario_json(svc_emp.responsavel_atual(e)),
            "origem": hist[0].origem if hist else None,
            "tipos": [comum.tipo_json(t) for t in e.tipos]}


@router.get("/empresas")
def listar(carteira: str | None = None, busca: str | None = None, inativas: bool = True,
           usuario: Usuario = Depends(exigir_usuario)):
    resp_id, carteira_sel = comum.carteira(carteira, usuario, padrao_todos=True)
    lista = svc_emp.listar_empresas(resp_id, competencia_atual(), incluir_inativas=inativas, busca=busca)
    comp = competencia_padrao()
    return {
        "carteira": carteira_sel,
        "busca": busca or "",
        "inativas": inativas,
        "inicio_padrao": comum.comp_json(comp),
        "competencias": comum.competencias_para_seletor(comp),
        "fonte_plataforma": svc_plat.fonte_plataforma(),
        "empresas": [_linha_lista(e) for e in lista],
    }


@router.get("/empresas/{empresa_id}")
def detalhe(empresa_id: int, usuario: Usuario = Depends(exigir_usuario)):
    e = _empresa(empresa_id)
    comp = competencia_padrao()
    return {
        "empresa": {**comum.empresa_json(e), "tipos": [t.id for t in e.tipos]},
        "historico_responsaveis": [{
            "usuario": comum.usuario_json(v.usuario), "inicio": comum.comp_json(v.inicio),
            "desde_o_inicio": v.inicio.year <= 2000, "origem": v.origem,
            "registrado_por": comum.usuario_json(v.registrado_por), "registrado_em": v.registrado_em,
        } for v in e.historico_responsaveis],
        "historico": [{"id": r.id, "data": r.data, "usuario": r.usuario_nome, "descricao": r.descricao or r.acao}
                      for r in aud.listar(empresa_id=e.id, limite=30)],
        "inicio_padrao": comum.comp_json(comp),
        "competencias": comum.competencias_para_seletor(comp),
        "fonte_plataforma": svc_plat.fonte_plataforma(),
    }


class EmpresaEntrada(Entrada):
    nome: str | None = None
    cnpj: str | None = None
    ativa: bool | None = None
    tipos: list[int] | None = None
    responsavel_id: int | None = None
    inicio: str | None = None  # competência a partir da qual vale a troca de responsável


def _usuario(uid: int | None) -> Usuario | None:
    u = db.session.get(Usuario, uid) if uid else None
    return u if u is not None and u.ativo else None


@router.post("/empresas", status_code=201)
def criar(dados: EmpresaEntrada, usuario: Usuario = Depends(exigir_usuario)):
    svc_plat.exigir_cadastro_local("o cadastro de empresas novas")
    resp = _usuario(dados.responsavel_id) or usuario
    e = svc_emp.criar_empresa(dados.nome or "", resp, usuario, cnpj=dados.cnpj, tipo_ids=dados.tipos or [],
                              ativa=True if dados.ativa is None else dados.ativa)
    db.session.commit()
    return RespostaJSON({"empresa": comum.empresa_json(e)}, status_code=201)


@router.put("/empresas/{empresa_id}")
def alterar(empresa_id: int, dados: EmpresaEntrada, usuario: Usuario = Depends(exigir_usuario)):
    e = _empresa(empresa_id)
    if svc_plat.fonte_plataforma():
        mudou_cadastro = ((dados.nome is not None and dados.nome.strip() != e.nome)
                          or (dados.cnpj is not None and (e.cnpj or "") != "".join(c for c in dados.cnpj if c.isdigit()))
                          or (dados.ativa is not None and dados.ativa != e.ativa))
        if mudou_cadastro:
            svc_plat.exigir_cadastro_local("nome, CNPJ e situação")
        svc_emp.atualizar_empresa(e, usuario, tipo_ids=dados.tipos)
    else:
        svc_emp.atualizar_empresa(e, usuario, nome=dados.nome, cnpj=dados.cnpj, ativa=dados.ativa, tipo_ids=dados.tipos)
    alterado = False
    novo = _usuario(dados.responsavel_id)
    if novo is not None:
        inicio = competencia(dados.inicio) if dados.inicio else competencia_padrao()
        alterado = svc_emp.definir_responsavel(e, novo, inicio, usuario, origem=ORIGEM_MANUAL)
    db.session.commit()
    db.session.refresh(e)
    return {"empresa": comum.empresa_json(e), "responsavel_alterado": alterado}


class ResponsavelEntrada(Entrada):
    usuario_id: int
    inicio: str | None = None


@router.post("/empresas/{empresa_id}/responsavel")
def trocar_responsavel(empresa_id: int, dados: ResponsavelEntrada, usuario: Usuario = Depends(exigir_usuario)):
    e = _empresa(empresa_id)
    novo = _usuario(dados.usuario_id)
    if novo is None:
        raise comum.erro("Usuário inválido.", 400, "parametro_invalido")
    inicio = comum.comp_ou_padrao(dados.inicio)
    # origem é sempre "manual" aqui: planilha/integração só pelos provedores (o cliente não escolhe).
    mudou = svc_emp.definir_responsavel(e, novo, inicio, usuario, origem=ORIGEM_MANUAL)
    db.session.commit()
    db.session.refresh(e)
    return {"alterado": mudou, "empresa": _linha_lista(e)}


# ------------------------------------------------------------------ cadastro do Conap Ferramentas

class SincronizarPlataformaEntrada(Entrada):
    aplicar: bool = False
    criar_novas: bool = False
    responsavel_id: int | None = None


@router.post("/empresas/plataforma/sincronizar")
def sincronizar_plataforma(dados: SincronizarPlataformaEntrada, usuario: Usuario = Depends(exigir_usuario)):
    """Compara (prévia) ou aplica o cadastro geral de empresas do Conap Ferramentas."""
    rel = svc_plat.sincronizar(usuario, aplicar=dados.aplicar, criar_novas=dados.criar_novas,
                               responsavel_novas=_usuario(dados.responsavel_id) or usuario)
    if dados.aplicar and not rel.erros:
        db.session.commit()
    else:
        db.session.rollback()
    return {"aplicado": dados.aplicar and not rel.erros, "relatorio": rel.como_dict()}


# ------------------------------------------------------------------ tipos de documento

@router.get("/tipos-documento")
def tipos(todos: bool = False, usuario: Usuario = Depends(exigir_usuario)):
    lista = svc_tipos.listar() if todos else svc_emp.tipos_ativos()
    return {"tipos": [{**comum.tipo_json(t), "uso": svc_tipos.uso(t) if todos else None} for t in lista],
            "sentidos": [{"valor": k, "nome": v[0], "titulo": v[1]} for k, v in SENTIDOS.items()]}


class TipoEntrada(Entrada):
    nome: str | None = None
    sentido: str | None = None
    modelo: str | None = None
    ordem: int | str | None = None
    ativo: bool | None = None


@router.post("/tipos-documento", status_code=201)
def criar_tipo(dados: TipoEntrada, usuario: Usuario = Depends(exigir_usuario)):
    t = svc_tipos.criar(dados.nome or "", dados.sentido, usuario, modelo=dados.modelo, ordem=dados.ordem)
    db.session.commit()
    return RespostaJSON({"tipo": comum.tipo_json(t)}, status_code=201)


@router.put("/tipos-documento/{tipo_id}")
def alterar_tipo(tipo_id: int, dados: TipoEntrada, usuario: Usuario = Depends(exigir_usuario)):
    t = db.session.get(TipoDocumento, tipo_id)
    if t is None:
        raise comum.nao_encontrado("Tipo de documento inexistente.")
    svc_tipos.atualizar(t, usuario, nome=dados.nome, sentido=dados.sentido, modelo=dados.modelo,
                        ordem=dados.ordem, ativo=dados.ativo)
    db.session.commit()
    return {"tipo": comum.tipo_json(t)}
