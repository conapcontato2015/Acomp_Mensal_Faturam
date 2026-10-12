"""Sincronização com o Controle Fiscal: escolha da competência, prévia e aplicação.

A regra fica em services/controle_fiscal.py; aqui só se lê o formulário e monta a página.
"""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for

from .. import bp
from ..extensions import db
from ..identidade import exigir_usuario, usuario_atual
from ..services import RegraViolada
from ..services import controle_fiscal as svc_cf
from ..util import ValorInvalido, comp_curta, competencia, competencia_padrao
from .routes import _competencias_para_seletor


def _inicio_do_form():
    v = request.form.get("inicio")
    return competencia(v) if v else competencia_padrao()


def _pagina(**ctx):
    inicio = ctx.pop("inicio", competencia_padrao())
    return render_template("faturamento/controle_fiscal.html", inicio=inicio,
                           competencias=_competencias_para_seletor(inicio), **ctx)


@bp.route("/empresas/controle-fiscal", methods=["GET", "POST"])
@exigir_usuario
def controle_fiscal():
    prov = svc_cf.provedor()
    if prov is None:
        return _pagina(configurado=False, relatorio=None)
    if request.method == "GET":
        return _pagina(configurado=True, relatorio=None)
    try:
        inicio = _inicio_do_form()
    except ValorInvalido as exc:
        flash(str(exc), "erro")
        return redirect(url_for("faturamento.controle_fiscal"))
    rel = svc_cf.sincronizar(prov, usuario_atual(), inicio=inicio, aplicar=False)
    db.session.rollback()  # prévia: nada fica pendente na sessão
    return _pagina(configurado=True, relatorio=rel, inicio=inicio)


@bp.post("/empresas/controle-fiscal/aplicar")
@exigir_usuario
def controle_fiscal_aplicar():
    prov = svc_cf.provedor()
    if prov is None:
        flash("Controle Fiscal não configurado: informe FOLHA_DATABASE_URL no .env.", "erro")
        return redirect(url_for("faturamento.empresas"))
    try:
        inicio = _inicio_do_form()
        # Relê a fonte na hora de aplicar: vale o que está no Controle Fiscal agora.
        rel = svc_cf.sincronizar(prov, usuario_atual(), inicio=inicio, aplicar=True)
        if rel.erros:
            raise ValorInvalido("; ".join(rel.erros))
        db.session.commit()
    except (ValorInvalido, RegraViolada) as exc:
        db.session.rollback()
        flash(str(exc), "erro")
        return redirect(url_for("faturamento.controle_fiscal"))
    flash(f"Controle Fiscal sincronizado: {len(rel.trocas)} responsável(is) trocado(s) a partir de "
          f"{comp_curta(inicio)}, {len(rel.cnpjs_preenchidos)} CNPJ(s) preenchido(s), "
          f"{len(rel.codigos_vinculados)} código(s) vinculado(s), {rel.sem_mudanca} sem mudança.", "sucesso")
    pendencias = (rel.divergencias + len(rel.responsaveis_sem_correspondencia) + len(rel.sem_responsavel_la))
    if pendencias:
        flash(f"{pendencias} item(ns) para conferir (divergências, empresas sem responsável lá ou nomes sem "
              "correspondência) — veja a prévia de novo para os detalhes.", "erro")
    return redirect(url_for("faturamento.empresas"))
