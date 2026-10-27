"""Importações: histórico (com desfazer), cruzamento Domínio × SEFAZ e Controle Fiscal. Sem importação de XLSX."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ...db import db
from ...models import Empresa, Importacao, Usuario
from ...services import controle_fiscal as svc_cf
from ...services import cruzamento as svc_cruz
from ...services import importacao as svc_imp
from ...util import competencia, competencia_padrao, utc_para_local
from .. import comum
from ..auth import exigir_usuario
from ..json import Entrada, RespostaJSON
from ..rota import RotaFaturamento

router = APIRouter(route_class=RotaFaturamento, default_response_class=RespostaJSON, tags=["importação"])


class TokenEntrada(Entrada):
    token: str


# ====================================================================== histórico

def _importacao_json(imp: Importacao) -> dict:
    r = svc_imp.resumo(imp)
    return {
        "id": imp.id, "data": imp.data, "arquivo": imp.arquivo, "desfeita": imp.desfeita,
        "usuario": comum.usuario_json(imp.usuario), "responsavel": comum.usuario_json(imp.responsavel),
        "fonte": r.get("fonte", "planilha"),
        "empresas_criadas": len(r.get("empresas_criadas") or []),
        "lancamentos_criados": r.get("lancamentos_criados") or 0,
        "lancamentos_alterados": r.get("lancamentos_alterados") or 0,
        "ajustes_criados": r.get("ajustes_criados") or 0,
        "avisos": r.get("avisos") or [],
        "n_avisos_destaque": r.get("n_avisos_destaque") or 0,
    }


@router.get("/importacoes")
def importacoes(usuario: Usuario = Depends(exigir_usuario)):
    return {"importacoes": [_importacao_json(i) for i in svc_imp.listar()],
            "cruzamento": svc_cruz.configurado()}


@router.post("/importacoes/{importacao_id}/desfazer")
def importacao_desfazer(importacao_id: int, usuario: Usuario = Depends(exigir_usuario)):
    imp = db.session.get(Importacao, importacao_id)
    if imp is None:
        raise comum.nao_encontrado("Importação não encontrada.")
    out = svc_imp.desfazer(imp, usuario)
    db.session.commit()
    return {"resultado": out, "importacao": _importacao_json(imp)}


# ====================================================================== Controle Fiscal

@router.get("/controle-fiscal")
def controle_fiscal_info(usuario: Usuario = Depends(exigir_usuario)):
    comp = competencia_padrao()
    return {"configurado": svc_cf.provedor() is not None, "inicio_padrao": comum.comp_json(comp),
            "competencias": comum.competencias_para_seletor(comp)}


class ControleFiscalEntrada(Entrada):
    inicio: str | None = None
    aplicar: bool = False


@router.post("/controle-fiscal")
def controle_fiscal(dados: ControleFiscalEntrada, usuario: Usuario = Depends(exigir_usuario)):
    prov = svc_cf.provedor()
    if prov is None:
        raise comum.erro("Controle Fiscal não configurado: informe FOLHA_DATABASE_URL no .env.", 422)
    inicio = comum.comp_ou_padrao(dados.inicio)
    # Na aplicação a fonte é relida: vale o que está no Controle Fiscal agora.
    rel = svc_cf.sincronizar(prov, usuario, inicio=inicio, aplicar=dados.aplicar)
    if dados.aplicar and not rel.erros:
        db.session.commit()
    else:
        db.session.rollback()
    return {"aplicado": dados.aplicar and not rel.erros, "inicio": comum.comp_json(inicio),
            "relatorio": {**rel.como_dict(), "divergencias": rel.divergencias, "tem_alteracoes": rel.tem_alteracoes}}


# ====================================================================== cruzamento Domínio × SEFAZ

def _numeros(n) -> dict | None:
    if n is None:
        return None
    return {"qtde_autor": n.qtde_autor, "valor_autor": n.valor_autor, "qtde_canc": n.qtde_canc,
            "valor_canc": n.valor_canc, "aj_qtde": n.aj_qtde, "aj_valor": n.aj_valor}


def _previa_cruzamento_json(previa, token: str) -> dict:
    return {
        "token": token,
        "competencia": comum.comp_json(previa.comp),
        "obtido_em": previa.obtido_em,
        "obtido_em_local": utc_para_local(previa.obtido_em),
        "a_importar": previa.a_importar,
        "mudaram_la": previa.mudaram_la,
        "mudaram_la_batidas": previa.mudaram_la_batidas,
        "iguais": previa.contar(svc_cruz.SIT_IGUAL),
        "sem_dados": previa.contar(svc_cruz.SIT_SEM_DADOS),
        "empresas": [{
            "empresa": comum.empresa_resumo(ep.empresa),
            "responsavel": comum.usuario_json(ep.responsavel),
            "pode_editar": ep.pode_editar,
            "mudou_la": ep.mudou_la,
            "linhas": [{
                "chave": l.chave, "tipo": comum.tipo_json(l.tipo), "situacao": l.situacao, "texto": l.texto,
                "mudou_la": l.mudou_la, "bateu": l.bateu, "selecionavel": l.selecionavel, "marcada": l.marcada,
                "anterior": _numeros(l.anterior), "nova": _numeros(l.nova), "atual": _numeros(l.atual),
                "notas": l.notas, "notas_omitidas": l.notas_omitidas,
            } for l in ep.linhas],
        } for ep in previa.empresas],
        "so_la": previa.so_la,
        "sem_cnpj_aqui": [comum.empresa_resumo(e) for e in previa.sem_cnpj_aqui],
        "fora_do_cruzamento": [comum.empresa_resumo(e) for e in previa.fora_do_cruzamento],
    }


@router.get("/cruzamento")
def cruzamento_info(competencia: str | None = None, usuario: Usuario = Depends(exigir_usuario)):
    comp = comum.comp_ou_padrao(competencia)
    return {"configurado": svc_cruz.configurado(), "competencia": comum.comp_json(comp),
            "competencias": comum.competencias_para_seletor(comp)}


@router.get("/cruzamento/previa")
def cruzamento_previa(competencia: str | None = None, carteira: str | None = None, empresa: int | None = None,
                      usuario: Usuario = Depends(exigir_usuario)):
    if not svc_cruz.configurado():
        raise comum.erro("Cruzamento não configurado: informe CRUZAMENTO_URL e CRUZAMENTO_API_KEY no .env.", 422,
                         "nao_configurado")
    comp = comum.comp_ou_padrao(competencia)
    resp_id, _ = comum.carteira(carteira, usuario)
    emp = db.session.get(Empresa, empresa) if empresa else None
    if empresa and emp is None:
        raise comum.nao_encontrado("Empresa não encontrada.")
    if emp is not None and not emp.cnpj:
        raise comum.erro(f"{emp.nome} não tem CNPJ cadastrado aqui: sem ele não dá para achar a empresa no cruzamento.")
    dados = svc_cruz.buscar(comp, cnpj=emp.cnpj if emp else None)
    previa = svc_cruz.montar_previa(dados, comp, None if emp else resp_id, usuario,
                                    empresa_id=emp.id if emp else None)
    return _previa_cruzamento_json(previa, svc_cruz.guardar(dados))


class AplicarCruzamentoEntrada(Entrada):
    token: str
    linhas: list[str] = []
    substituto: bool = False


@router.post("/cruzamento/aplicar")
def cruzamento_aplicar(dados: AplicarCruzamentoEntrada, usuario: Usuario = Depends(exigir_usuario)):
    fonte = svc_cruz.carregar(dados.token)
    competencia(fonte.get("competencia", ""))
    imp = svc_cruz.aplicar(fonte, set(dados.linhas), usuario, substituto=dados.substituto)
    db.session.commit()
    svc_cruz.descartar(dados.token)
    r = svc_imp.resumo(imp)
    return {"importacao": _importacao_json(imp), "resumo": {
        "lancamentos_criados": r.get("lancamentos_criados", 0), "lancamentos_alterados": r.get("lancamentos_alterados", 0),
        "ajustes_criados": r.get("ajustes_criados", 0), "sem_mudanca": r.get("sem_mudanca", 0),
        "ignorados_outra_carteira": r.get("ignorados_outra_carteira", 0), "ignorados_bateu": r.get("ignorados_bateu", 0)}}


@router.post("/cruzamento/descartar")
def cruzamento_descartar(dados: TokenEntrada, usuario: Usuario = Depends(exigir_usuario)):
    svc_cruz.descartar(dados.token)
    return {"ok": True}

