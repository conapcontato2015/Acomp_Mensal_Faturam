"""Telas (HTML). Toda regra está em services/; aqui só se lê parâmetros e monta a página."""
from __future__ import annotations

from datetime import date

from flask import abort, flash, redirect, render_template, request, url_for

from .. import bp
from ..extensions import db
from ..identidade import definir_usuario, exigir_usuario, modo_local, sair, usuario_atual
from ..models import MOTIVOS_AJUSTE, Empresa, Usuario
from ..services import RegraViolada
from ..services import auditoria as aud
from ..services import empresas as svc_emp
from ..services import fechamento as svc_fech
from ..services import lancamentos as svc_lanc
from ..services import resumo as svc_res
from ..util import ValorInvalido, competencia, competencia_atual, competencia_padrao, somar_meses


# ------------------------------------------------------------------ utilidades

def _comp() -> date:
    v = request.args.get("competencia")
    try:
        return competencia(v) if v else competencia_padrao()
    except ValorInvalido:
        return competencia_padrao()


def _carteira() -> tuple[int | None, str]:
    """Carteira escolhida no seletor: id do usuário, ou None para 'Todos'. Padrão: a do usuário da sessão."""
    v = request.args.get("carteira")
    if v == "todos":
        return None, "todos"
    if v and v.isdigit():
        return int(v), v
    u = usuario_atual()
    return (u.id, str(u.id)) if u else (None, "todos")


def _competencias_para_seletor(atual: date, n: int = 18) -> list[date]:
    hoje = competencia_atual()
    lista = [somar_meses(hoje, -i) for i in range(n)]
    if atual not in lista:
        lista.append(atual)
    return sorted(lista, reverse=True)


@bp.app_template_global()
def iniciais(nome: str) -> str:
    return (nome or "?").strip()[:1].upper()


# ------------------------------------------------------------------ sessão

@bp.route("/entrar", methods=["GET", "POST"])
def escolher_usuario():
    if not modo_local():
        return redirect(url_for("faturamento.painel"))
    if request.method == "POST":
        u = db.session.get(Usuario, request.form.get("usuario_id", type=int) or 0)
        if u and u.ativo:
            definir_usuario(u)
            proximo = request.args.get("proximo") or url_for("faturamento.painel")
            if not proximo.startswith("/"):
                proximo = url_for("faturamento.painel")
            return redirect(proximo)
        flash("Escolha um usuário.", "erro")
    return render_template("faturamento/entrar.html", usuarios=svc_emp.usuarios_ativos())


@bp.get("/sair")
def sair_view():
    sair()
    return redirect(url_for("faturamento.escolher_usuario"))


# ------------------------------------------------------------------ painel

@bp.get("/")
@exigir_usuario
def painel():
    comp = _comp()
    resp_id, carteira = _carteira()
    filtro = request.args.get("status", "todos")
    linhas = svc_res.painel(comp, resp_id)
    contagem = {s: sum(1 for l in linhas if l.status == s) for s in ("pendente", "preenchido", "sem_movimento")}
    if filtro in contagem:
        linhas_vis = [l for l in linhas if l.status == filtro]
    else:
        linhas_vis = linhas
    total = len(linhas)
    feitos = contagem["preenchido"] + contagem["sem_movimento"]
    return render_template(
        "faturamento/painel.html", comp=comp, linhas=linhas_vis, total=total, contagem=contagem,
        progresso=round(feitos / total * 100) if total else 0, feitos=feitos, filtro=filtro,
        carteira=carteira, resp_id=resp_id, usuarios=svc_emp.usuarios_ativos(),
        competencias=_competencias_para_seletor(comp), rotulos=svc_fech.ROTULOS,
        somente_leitura=resp_id != usuario_atual().id,
        alertas=sum(1 for l in linhas if l.alerta),
    )


# ------------------------------------------------------------------ lançamento

@bp.get("/lancamento")
@exigir_usuario
def lancamento():
    comp = _comp()
    usuario = usuario_atual()
    empresa_id = request.args.get("empresa", type=int)
    minhas = svc_emp.listar_empresas(usuario.id, comp)
    todas = svc_emp.listar_empresas(None, comp)
    empresa = db.session.get(Empresa, empresa_id) if empresa_id else (minhas[0] if minhas else None)
    if empresa is None:
        return render_template("faturamento/lancamento.html", comp=comp, empresa=None, minhas=minhas, todas=todas,
                               competencias=_competencias_para_seletor(comp))
    linhas = svc_lanc.carregar_mes(empresa, comp)
    pode = svc_lanc.pode_editar(usuario, empresa, comp)
    resp = svc_emp.responsavel_em(empresa, comp)
    ids = [e.id for e in minhas]
    proxima = None
    if empresa.id in ids and ids.index(empresa.id) + 1 < len(ids):
        proxima = minhas[ids.index(empresa.id) + 1]
    linhas_ajustes = {
        str(l.tipo.id): [{"id": a.id, "grupo": a.grupo, "qtde": a.qtde, "valor": str(a.valor), "motivo": a.motivo,
                          "observacao": a.observacao or "", "por": a.criado_por.nome if a.criado_por else "",
                          "em": a.criado_em.strftime("%d/%m/%Y")} for a in l.ajustes]
        for l in linhas
    }
    return render_template(
        "faturamento/lancamento.html", comp=comp, empresa=empresa, linhas=linhas, pode_editar=pode,
        linhas_ajustes=linhas_ajustes,
        responsavel=resp, status=svc_fech.status_mes(empresa, comp), rotulos=svc_fech.ROTULOS,
        minhas=minhas, todas=todas, proxima=proxima, competencias=_competencias_para_seletor(comp),
        evolucao=svc_res.evolucao(empresa, comp, 8), motivos=MOTIVOS_AJUSTE,
        futura=comp > competencia_atual(),
    )


# ------------------------------------------------------------------ empresas

@bp.get("/empresas")
@exigir_usuario
def empresas():
    resp_id, carteira = _carteira()
    if request.args.get("carteira") is None:
        resp_id, carteira = None, "todos"
    incl = request.args.get("inativas", "1") == "1"
    lista = svc_emp.listar_empresas(resp_id, competencia_atual(), incluir_inativas=incl, busca=request.args.get("busca"))
    from ..responsaveis import provedor_configurado
    return render_template(
        "faturamento/empresas.html", empresas=lista, usuarios=svc_emp.usuarios_ativos(),
        carteira=carteira, incl=incl, busca=request.args.get("busca", ""),
        responsavel_atual=svc_emp.responsavel_atual, provedor=provedor_configurado().nome,
        inicio_padrao=competencia_padrao(), competencias=_competencias_para_seletor(competencia_padrao()),
    )


@bp.route("/empresas/nova", methods=["GET", "POST"])
@bp.route("/empresas/<int:eid>", methods=["GET", "POST"])
@exigir_usuario
def empresa_form(eid: int | None = None):
    empresa = db.session.get(Empresa, eid) if eid else None
    if eid and empresa is None:
        abort(404)
    tipos = svc_emp.tipos_ativos()
    usuarios = svc_emp.usuarios_ativos()
    if request.method == "POST":
        f = request.form
        tipo_ids = [int(x) for x in f.getlist("tipos")]
        try:
            if empresa is None:
                resp = db.session.get(Usuario, f.get("responsavel_id", type=int) or 0) or usuario_atual()
                empresa = svc_emp.criar_empresa(f.get("nome", ""), resp, usuario_atual(), cnpj=f.get("cnpj"),
                                                tipo_ids=tipo_ids, ativa=f.get("ativa") == "1")
            else:
                svc_emp.atualizar_empresa(empresa, usuario_atual(), nome=f.get("nome", ""), cnpj=f.get("cnpj", ""),
                                          ativa=f.get("ativa") == "1", tipo_ids=tipo_ids)
                novo = db.session.get(Usuario, f.get("responsavel_id", type=int) or 0)
                if novo:
                    inicio = competencia(f.get("inicio")) if f.get("inicio") else competencia_padrao()
                    svc_emp.definir_responsavel(empresa, novo, inicio, usuario_atual())
            db.session.commit()
            flash(f"{empresa.nome} salva.", "sucesso")
            return redirect(url_for("faturamento.empresas"))
        except (RegraViolada, ValorInvalido) as exc:
            db.session.rollback()
            for m in getattr(exc, "mensagens", [str(exc)]):
                flash(m, "erro")
            if eid:
                empresa = db.session.get(Empresa, eid)
    historico = aud.listar(empresa_id=empresa.id, limite=30) if empresa else []
    return render_template(
        "faturamento/empresa_form.html", empresa=empresa, tipos=tipos, usuarios=usuarios,
        responsavel=svc_emp.responsavel_atual(empresa) if empresa else usuario_atual(),
        inicio_padrao=competencia_padrao(), competencias=_competencias_para_seletor(competencia_padrao()),
        historico=historico,
    )


# ------------------------------------------------------------------ histórico

@bp.get("/historico")
@exigir_usuario
def historico():
    regs = aud.listar(empresa_id=request.args.get("empresa", type=int), usuario_id=request.args.get("usuario", type=int))
    return render_template("faturamento/historico.html", registros=regs,
                           empresas=svc_emp.listar_empresas(None, competencia_atual(), True),
                           usuarios=svc_emp.usuarios_ativos(), carregar=aud.carregar,
                           empresa_id=request.args.get("empresa", type=int),
                           usuario_id=request.args.get("usuario", type=int))
