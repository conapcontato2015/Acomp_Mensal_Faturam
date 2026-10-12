"""Importar os números do mês do cruzamento Domínio × SEFAZ: busca, prévia com versões e aplicação.

As regras ficam em services/cruzamento.py; aqui só se lê o formulário e monta a página.
"""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for

from .. import bp
from ..extensions import db
from ..identidade import exigir_usuario, usuario_atual
from ..models import Empresa
from ..services import RegraViolada
from ..services import cruzamento as svc
from ..services import empresas as svc_emp
from ..services import importacao as svc_imp
from ..util import ValorInvalido, comp_curta, competencia
from .routes import _carteira, _comp, _competencias_para_seletor


def _empresa_do_filtro() -> Empresa | None:
    eid = request.args.get("empresa", type=int)
    return db.session.get(Empresa, eid) if eid else None


@bp.get("/importacao/cruzamento")
@exigir_usuario
def cruzamento():
    comp = _comp()
    resp_id, carteira = _carteira()
    empresa = _empresa_do_filtro()
    ctx = dict(comp=comp, competencias=_competencias_para_seletor(comp), carteira=carteira, resp_id=resp_id,
               usuarios=svc_emp.usuarios_ativos(), empresa=empresa, configurado=svc.configurado(),
               previa=None, token=None, svc=svc)
    if not ctx["configurado"] or request.args.get("ver") != "1":
        return render_template("faturamento/cruzamento.html", **ctx)
    if empresa is not None and not empresa.cnpj:
        flash(f"{empresa.nome} não tem CNPJ cadastrado aqui: sem ele não dá para achar a empresa no cruzamento.", "erro")
        return render_template("faturamento/cruzamento.html", **ctx)
    try:
        dados = svc.buscar(comp, cnpj=empresa.cnpj if empresa else None)
    except svc.ErroCruzamento as exc:
        for m in exc.mensagens:
            flash(m, "erro")
        return render_template("faturamento/cruzamento.html", **ctx)
    previa = svc.montar_previa(dados, comp, None if empresa else resp_id, usuario_atual(),
                               empresa_id=empresa.id if empresa else None)
    ctx.update(previa=previa, token=svc.guardar(dados))
    return render_template("faturamento/cruzamento.html", **ctx)


@bp.post("/importacao/cruzamento/aplicar")
@exigir_usuario
def cruzamento_aplicar():
    token = request.form.get("token", "")
    voltar = url_for("faturamento.cruzamento", competencia=request.form.get("competencia") or None,
                     carteira=request.form.get("carteira") or None)
    if request.form.get("acao") == "cancelar":
        svc.descartar(token)
        flash("Nada foi importado.", "info")
        return redirect(voltar)
    try:
        dados = svc.carregar(token)
        competencia(dados.get("competencia", ""))
        imp = svc.aplicar(dados, set(request.form.getlist("linha")), usuario_atual(),
                          substituto=request.form.get("substituto") == "1")
        db.session.commit()
    except (ValorInvalido, RegraViolada) as exc:
        db.session.rollback()
        for m in getattr(exc, "mensagens", [str(exc)]):
            flash(m, "erro")
        return redirect(voltar)
    svc.descartar(token)
    r = svc_imp.resumo(imp)
    flash(f"Importação #{imp.id} do cruzamento ({comp_curta(competencia(dados['competencia']))}): "
          f"{r['lancamentos_criados']} lançamento(s) novo(s), {r['lancamentos_alterados']} alterado(s), "
          f"{r['ajustes_criados']} ajuste(s) sugerido(s), {r['sem_mudanca']} sem mudança. Dá para desfazer em "
          "Importar planilha.", "sucesso")
    if r.get("ignorados_outra_carteira"):
        flash(f"{r['ignorados_outra_carteira']} linha(s) de carteiras de outras pessoas não foram importadas "
              "(marque “Importar como substituto” para incluí-las).", "erro")
    if r.get("ignorados_bateu"):
        flash(f"{r['ignorados_bateu']} linha(s) já conferida(s) ('Bateu') não foram alteradas.", "erro")
    return redirect(url_for("faturamento.importacao", aberta=imp.id))
