"""Importação da planilha antiga (Fase 2) e da planilha de responsáveis (Fase 3).

Regras ficam em services/importacao.py e responsaveis.py; aqui só upload, prévia e confirmação.
"""
from __future__ import annotations

import csv
import io

from flask import Response, abort, flash, redirect, render_template, request, url_for

from .. import bp
from ..extensions import db
from ..identidade import exigir_usuario, usuario_atual
from ..models import Importacao, Usuario
from ..responsaveis import ProvedorPlanilha, provedor_configurado, sincronizar
from ..services import RegraViolada
from ..services import empresas as svc_emp
from ..services import importacao as svc_imp
from ..util import ValorInvalido, comp_curta, competencia, competencia_padrao
from .routes import _competencias_para_seletor

EXTENSOES_PLANILHA = (".xlsx", ".xlsm")
EXTENSOES_RESPONSAVEIS = (".xlsx", ".xlsm", ".csv", ".txt")


def _arquivo_enviado(extensoes: tuple[str, ...]) -> tuple[bytes, str]:
    f = request.files.get("arquivo")
    if f is None or not f.filename:
        raise ValorInvalido("Escolha um arquivo.")
    nome = f.filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if not nome.lower().endswith(extensoes):
        raise ValorInvalido(f"Formato não aceito: use {' ou '.join(extensoes)}.")
    conteudo = f.read()
    if not conteudo:
        raise ValorInvalido("O arquivo está vazio.")
    return conteudo, nome


def _usuario_do_form(campo: str = "responsavel_id") -> Usuario | None:
    u = db.session.get(Usuario, request.form.get(campo, type=int) or 0)
    return u if u is not None and u.ativo else None


# ====================================================================== planilha antiga

@bp.get("/importacao")
@exigir_usuario
def importacao():
    historico = [(imp, svc_imp.resumo(imp)) for imp in svc_imp.listar()]
    return render_template("faturamento/importacao.html", usuarios=svc_emp.usuarios_ativos(), historico=historico)


@bp.post("/importacao/previa")
@exigir_usuario
def importacao_previa():
    responsavel = _usuario_do_form() or usuario_atual()
    try:
        conteudo, nome = _arquivo_enviado(EXTENSOES_PLANILHA)
        previa = svc_imp.analisar(conteudo, nome)
    except ValorInvalido as exc:
        flash(str(exc), "erro")
        return redirect(url_for("faturamento.importacao"))
    if not previa.itens:
        flash(f"Nenhuma linha com números encontrada em {nome} (aba {previa.aba}).", "erro")
        return redirect(url_for("faturamento.importacao"))
    token = svc_imp.guardar_previa(previa)
    return render_template(
        "faturamento/importacao_previa.html", previa=previa, token=token, responsavel=responsavel,
        usuarios=svc_emp.usuarios_ativos(), empresas=previa.empresas(),
        totais=previa.totais_por_competencia(), conflitos=previa.conflitos(),
        outras=previa.outras_carteiras(usuario_atual(), responsavel), opcao_outras=svc_imp.OPCAO_OUTRAS,
    )


@bp.post("/importacao/confirmar")
@exigir_usuario
def importacao_confirmar():
    token = request.form.get("token", "")
    responsavel = _usuario_do_form()
    if request.form.get("acao") == "cancelar":
        svc_imp.descartar(token)
        flash("Importação cancelada. Nada foi gravado.", "info")
        return redirect(url_for("faturamento.importacao"))
    try:
        if responsavel is None:
            raise ValorInvalido("Escolha o responsável pelas empresas novas.")
        previa = svc_imp.carregar_previa(token)
        imp = svc_imp.confirmar(previa, responsavel, usuario_atual(), previa.arquivo,
                                outras_carteiras=request.form.get("outras_carteiras") == "1")
        db.session.commit()
    except (ValorInvalido, RegraViolada) as exc:
        db.session.rollback()
        for m in getattr(exc, "mensagens", [str(exc)]):
            flash(m, "erro")
        return redirect(url_for("faturamento.importacao"))
    svc_imp.descartar(token)
    r = svc_imp.resumo(imp)
    flash(
        f"Importação #{imp.id} concluída: {len(r['empresas_criadas'])} empresa(s) criada(s), "
        f"{r['lancamentos_criados']} lançamento(s) novo(s), {r['lancamentos_alterados']} alterado(s), "
        f"{r['sem_mudanca']} sem mudança, {r['ajustes_criados']} ajuste(s).", "sucesso")
    if r.get("ignorados_outra_carteira"):
        flash(f"{r['ignorados_outra_carteira']} lançamento(s) de carteiras de outras pessoas não foram importados "
              f"(marque “{svc_imp.OPCAO_OUTRAS}” para incluí-los).", "erro")
    if r.get("ignorados_bateu"):
        flash(f"{r['ignorados_bateu']} lançamento(s) já conferido(s) ('Bateu') não foram alterados.", "erro")
    if r.get("n_avisos_destaque"):
        flash(f"{r['n_avisos_destaque']} aviso(s) precisam de correção no lançamento — veja a lista na importação #{imp.id}.", "erro")
    return redirect(url_for("faturamento.importacao", aberta=imp.id))


@bp.post("/importacao/<int:iid>/desfazer")
@exigir_usuario
def importacao_desfazer(iid: int):
    imp = db.session.get(Importacao, iid)
    if imp is None:
        abort(404)
    try:
        out = svc_imp.desfazer(imp, usuario_atual())
        db.session.commit()
    except RegraViolada as exc:
        db.session.rollback()
        for m in exc.mensagens:
            flash(m, "erro")
        return redirect(url_for("faturamento.importacao"))
    msg = (f"Importação #{iid} desfeita: {out['removidos']} lançamento(s) removido(s), "
           f"{out['restaurados']} com os números anteriores restaurados, {out['empresas_removidas']} empresa(s) removida(s).")
    flash(msg, "sucesso")
    if out["mantidos_bateu"]:
        flash(f"{out['mantidos_bateu']} lançamento(s) já conferido(s) ('Bateu') foram mantidos.", "erro")
    if out.get("mantidos_editados"):
        lista = ", ".join(out["editados"][:10]) + ("…" if len(out["editados"]) > 10 else "")
        flash(f"{out['mantidos_editados']} lançamento(s) alterado(s) depois da importação foram mantidos como estão: "
              f"{lista}.", "erro")
    return redirect(url_for("faturamento.importacao"))


# ====================================================================== responsáveis

@bp.route("/empresas/importar-responsaveis", methods=["GET", "POST"])
@exigir_usuario
def importar_responsaveis():
    provedor = provedor_configurado().nome
    competencias = _competencias_para_seletor(competencia_padrao())
    inicio_padrao = competencia_padrao()
    if request.method == "GET":
        return render_template("faturamento/importar_responsaveis.html", provedor=provedor, relatorio=None,
                               competencias=competencias, inicio_padrao=inicio_padrao)
    try:
        if request.form.get("inicio"):
            inicio_padrao = competencia(request.form["inicio"])
        conteudo, nome = _arquivo_enviado(EXTENSOES_RESPONSAVEIS)
    except ValorInvalido as exc:
        flash(str(exc), "erro")
        return redirect(url_for("faturamento.importar_responsaveis"))
    rel = sincronizar(ProvedorPlanilha(conteudo, nome), usuario_atual(), inicio_padrao=inicio_padrao, aplicar=False)
    db.session.rollback()  # prévia: garante que nada fique pendente na sessão
    token = svc_imp.guardar_arquivo(conteudo, nome) if rel.alteradas and not rel.erros else None
    return render_template("faturamento/importar_responsaveis.html", provedor=provedor, relatorio=rel, token=token,
                           arquivo=nome, competencias=competencias, inicio_padrao=inicio_padrao)


@bp.post("/empresas/importar-responsaveis/confirmar")
@exigir_usuario
def importar_responsaveis_confirmar():
    token = request.form.get("token", "")
    if request.form.get("acao") == "cancelar":
        svc_imp.descartar(token)
        flash("Importação de responsáveis cancelada. Nada foi alterado.", "info")
        return redirect(url_for("faturamento.importar_responsaveis"))
    try:
        inicio = competencia(request.form["inicio"]) if request.form.get("inicio") else competencia_padrao()
        conteudo, nome = svc_imp.carregar_arquivo(token)
        rel = sincronizar(ProvedorPlanilha(conteudo, nome), usuario_atual(), inicio_padrao=inicio, aplicar=True)
        if rel.erros:
            raise ValorInvalido("; ".join(rel.erros))
        db.session.commit()
    except (ValorInvalido, RegraViolada) as exc:
        db.session.rollback()
        flash(str(exc), "erro")
        return redirect(url_for("faturamento.importar_responsaveis"))
    svc_imp.descartar(token)
    flash(f"Responsáveis atualizados: {len(rel.alteradas)} empresa(s) trocada(s), {rel.sem_mudanca} sem mudança "
          f"(a partir de {comp_curta(inicio)} quando a planilha não informa INICIO).", "sucesso")
    nao = len(rel.empresas_nao_encontradas) + len(rel.responsaveis_nao_encontrados)
    if nao:
        flash(f"{nao} linha(s) não aplicada(s): empresa ou responsável não encontrado.", "erro")
    return redirect(url_for("faturamento.empresas"))


@bp.get("/empresas/importar-responsaveis/modelo.csv")
@exigir_usuario
def importar_responsaveis_modelo():
    saida = io.StringIO()
    w = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    w.writerow(["CNPJ", "EMPRESA", "RESPONSAVEL", "INICIO"])
    for e in svc_emp.listar_empresas(None, incluir_inativas=True):
        resp = svc_emp.responsavel_atual(e)
        w.writerow([e.cnpj_formatado, e.nome, resp.nome if resp else "", ""])
    corpo = "﻿" + saida.getvalue()  # BOM: o Excel abre com acentos certos
    return Response(corpo.encode("utf-8"), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=modelo_responsaveis.csv"})
