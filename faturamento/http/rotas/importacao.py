"""Importações: planilha antiga, responsáveis (planilha), cruzamento Domínio × SEFAZ e Controle Fiscal."""
from __future__ import annotations

import csv
import io
from dataclasses import asdict

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response

from ...db import db
from ...models import Empresa, Importacao, Usuario
from ...responsaveis import ProvedorPlanilha, provedor_configurado, sincronizar
from ...services import controle_fiscal as svc_cf
from ...services import cruzamento as svc_cruz
from ...services import empresas as svc_emp
from ...services import importacao as svc_imp
from ...util import ValorInvalido, comp_iso, competencia, competencia_padrao, utc_para_local
from .. import comum
from ..auth import exigir_usuario
from ..json import Entrada, RespostaJSON
from ..rota import RotaFaturamento

router = APIRouter(route_class=RotaFaturamento, default_response_class=RespostaJSON, tags=["importação"])

EXTENSOES_PLANILHA = (".xlsx", ".xlsm")
EXTENSOES_RESPONSAVEIS = (".xlsx", ".xlsm", ".csv", ".txt")
LIMITE_UPLOAD = 20 * 1024 * 1024


async def _ler(arquivo: UploadFile | None, extensoes: tuple[str, ...]) -> tuple[bytes, str]:
    if arquivo is None or not arquivo.filename:
        raise ValorInvalido("Escolha um arquivo.")
    nome = arquivo.filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if not nome.lower().endswith(extensoes):
        raise ValorInvalido(f"Formato não aceito: use {' ou '.join(extensoes)}.")
    conteudo = await arquivo.read(LIMITE_UPLOAD + 1)
    if len(conteudo) > LIMITE_UPLOAD:
        raise ValorInvalido("Arquivo grande demais (máximo 20 MB).")
    if not conteudo:
        raise ValorInvalido("O arquivo está vazio.")
    return conteudo, nome


def _usuario(uid: int | None) -> Usuario | None:
    u = db.session.get(Usuario, uid) if uid else None
    return u if u is not None and u.ativo else None


# ====================================================================== planilha antiga

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
            "usuarios": [comum.usuario_json(u) for u in svc_emp.usuarios_ativos()],
            "opcao_outras": svc_imp.OPCAO_OUTRAS,
            "cruzamento": svc_cruz.configurado()}


def _previa_json(previa: svc_imp.Previa, token: str, usuario: Usuario, responsavel: Usuario) -> dict:
    return {
        "token": token, "arquivo": previa.arquivo, "aba": previa.aba, "linha_cabecalho": previa.linha_cabecalho,
        "linhas_lidas": previa.linhas_lidas, "linhas_vazias": previa.linhas_vazias,
        "n_lancamentos": previa.n_lancamentos, "n_ajustes": previa.n_ajustes,
        "competencias": [comum.comp_json(c) for c in previa.competencias],
        "avisos": [asdict(a) for a in previa.avisos],
        "empresas": [{**e, "competencias": [comp_iso(c) for c in e["competencias"]],
                      "primeira": comum.comp_json(e["primeira"]), "ultima": comum.comp_json(e["ultima"])}
                     for e in previa.empresas()],
        "totais": [{"competencia": comum.comp_json(t["competencia"]), "lancamentos": t["lancamentos"],
                    "empresas": t["empresas"], "entradas": t["E"], "saidas": t["S"]}
                   for t in previa.totais_por_competencia()],
        "conflitos": previa.conflitos(),
        "outras_carteiras": previa.outras_carteiras(usuario, responsavel),
        "responsavel": comum.usuario_json(responsavel),
        "opcao_outras": svc_imp.OPCAO_OUTRAS,
    }


@router.post("/importacoes/previa")
async def importacao_previa(arquivo: UploadFile | None = File(default=None), responsavel_id: int | None = Form(default=None),
                            usuario: Usuario = Depends(exigir_usuario)):
    conteudo, nome = await _ler(arquivo, EXTENSOES_PLANILHA)
    responsavel = _usuario(responsavel_id) or usuario
    previa = svc_imp.analisar(conteudo, nome)
    if not previa.itens:
        raise comum.erro(f"Nenhuma linha com números encontrada em {nome} (aba {previa.aba}).", 422)
    token = svc_imp.guardar_previa(previa)
    return _previa_json(previa, token, usuario, responsavel)


class ConfirmarEntrada(Entrada):
    token: str
    responsavel_id: int
    outras_carteiras: bool = False


@router.post("/importacoes/confirmar")
def importacao_confirmar(dados: ConfirmarEntrada, usuario: Usuario = Depends(exigir_usuario)):
    responsavel = _usuario(dados.responsavel_id)
    if responsavel is None:
        raise comum.erro("Escolha o responsável pelas empresas novas.", 400, "parametro_invalido")
    previa = svc_imp.carregar_previa(dados.token)
    imp = svc_imp.confirmar(previa, responsavel, usuario, previa.arquivo, outras_carteiras=dados.outras_carteiras)
    db.session.commit()
    svc_imp.descartar(dados.token)
    r = svc_imp.resumo(imp)
    return {"importacao": _importacao_json(imp), "resumo": {
        "empresas_criadas": r.get("empresas_criadas", []), "lancamentos_criados": r.get("lancamentos_criados", 0),
        "lancamentos_alterados": r.get("lancamentos_alterados", 0), "sem_mudanca": r.get("sem_mudanca", 0),
        "ajustes_criados": r.get("ajustes_criados", 0), "ignorados_outra_carteira": r.get("ignorados_outra_carteira", 0),
        "ignorados_bateu": r.get("ignorados_bateu", 0), "n_avisos_destaque": r.get("n_avisos_destaque", 0)}}


class TokenEntrada(Entrada):
    token: str


@router.post("/importacoes/descartar")
def importacao_descartar(dados: TokenEntrada, usuario: Usuario = Depends(exigir_usuario)):
    svc_imp.descartar(dados.token)
    return {"ok": True}


@router.post("/importacoes/{importacao_id}/desfazer")
def importacao_desfazer(importacao_id: int, usuario: Usuario = Depends(exigir_usuario)):
    imp = db.session.get(Importacao, importacao_id)
    if imp is None:
        raise comum.nao_encontrado("Importação não encontrada.")
    out = svc_imp.desfazer(imp, usuario)
    db.session.commit()
    return {"resultado": out, "importacao": _importacao_json(imp)}


# ====================================================================== responsáveis por planilha

def _rel_responsaveis(rel) -> dict:
    return rel.como_dict()


@router.get("/responsaveis/modelo.csv", response_class=Response)
def modelo_responsaveis(usuario: Usuario = Depends(exigir_usuario)):
    saida = io.StringIO()
    w = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    w.writerow(["CNPJ", "EMPRESA", "RESPONSAVEL", "INICIO"])
    for e in svc_emp.listar_empresas(None, incluir_inativas=True):
        resp = svc_emp.responsavel_atual(e)
        w.writerow([e.cnpj_formatado, e.nome, resp.nome if resp else "", ""])
    corpo = "﻿" + saida.getvalue()  # BOM: o Excel abre com acentos certos
    return Response(corpo.encode("utf-8"), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=modelo_responsaveis.csv"})


@router.get("/responsaveis")
def responsaveis_info(usuario: Usuario = Depends(exigir_usuario)):
    comp = competencia_padrao()
    return {"provedor": provedor_configurado().nome, "inicio_padrao": comum.comp_json(comp),
            "competencias": comum.competencias_para_seletor(comp)}


@router.post("/responsaveis/previa")
async def responsaveis_previa(arquivo: UploadFile | None = File(default=None), inicio: str | None = Form(default=None),
                              usuario: Usuario = Depends(exigir_usuario)):
    inicio_c = comum.comp_ou_padrao(inicio)
    conteudo, nome = await _ler(arquivo, EXTENSOES_RESPONSAVEIS)
    rel = sincronizar(ProvedorPlanilha(conteudo, nome), usuario, inicio_padrao=inicio_c, aplicar=False)
    db.session.rollback()  # prévia: nada fica pendente
    token = svc_imp.guardar_arquivo(conteudo, nome) if rel.alteradas and not rel.erros else None
    return {"token": token, "arquivo": nome, "inicio": comum.comp_json(inicio_c), "relatorio": _rel_responsaveis(rel)}


class ConfirmarResponsaveisEntrada(Entrada):
    token: str
    inicio: str | None = None


@router.post("/responsaveis/confirmar")
def responsaveis_confirmar(dados: ConfirmarResponsaveisEntrada, usuario: Usuario = Depends(exigir_usuario)):
    inicio = comum.comp_ou_padrao(dados.inicio)
    conteudo, nome = svc_imp.carregar_arquivo(dados.token)
    rel = sincronizar(ProvedorPlanilha(conteudo, nome), usuario, inicio_padrao=inicio, aplicar=True)
    if rel.erros:
        raise comum.erro(rel.erros, 422)
    db.session.commit()
    svc_imp.descartar(dados.token)
    return {"inicio": comum.comp_json(inicio), "relatorio": _rel_responsaveis(rel)}


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

