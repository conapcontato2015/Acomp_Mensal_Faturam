"""Tela de conferência (relatório SEFAZ com ajustes × sistema contábil) e exportações."""
from __future__ import annotations

from datetime import date, datetime

from flask import Response, render_template, request

from .. import bp
from ..identidade import exigir_usuario, usuario_atual
from ..models import GRUPO_AUTOR, Lancamento
from ..services import empresas as svc_emp
from ..services import exportacao as svc_exp
from ..services import lancamentos as svc_lanc
from ..services import resumo as svc_res
from ..util import fmt_inteiro, fmt_moeda
from .routes import _carteira, _comp, _competencias_para_seletor


def _dica_ajuste(l: Lancamento) -> str:
    """Texto do tooltip '±aj': o que o ajuste acrescentou ao número da SEFAZ."""
    partes = []
    for a in l.ajustes:
        grupo = "autorizadas" if a.grupo == GRUPO_AUTOR else "canceladas"
        partes.append(f"{'+' if (a.qtde or 0) >= 0 else ''}{fmt_inteiro(a.qtde or 0)} {grupo} "
                      f"(R$ {fmt_moeda(a.valor or 0)}): {a.motivo}")
    return "Inclui ajuste — " + "; ".join(partes) if partes else ""


def _ajuste_curto(l: Lancamento) -> str:
    """'+61 · 1.295,50' (só a parte de autorizadas); '—' sem ajuste."""
    q, v = l.ajuste_qtde_autor, l.ajuste_valor_autor
    if not q and not v:
        return "—"
    return f"{'+' if q >= 0 else ''}{fmt_inteiro(q)} · {fmt_moeda(v)}"


def _nome_carteira(resp_id: int | None) -> str:
    if resp_id is None:
        return "Todas as pessoas"
    for u in svc_emp.usuarios_ativos():
        if u.id == resp_id:
            return u.nome
    return "—"


def _dados(comp: date, resp_id: int | None) -> dict:
    cartoes = svc_res.conferencia(comp, resp_id)
    total = sum(c.total for c in cartoes)
    bateram = sum(c.n_bateu for c in cartoes)
    return {
        "cartoes": cartoes,
        "progresso": {
            "linhas": total, "bateram": bateram,
            "percentual": round(bateram / total * 100) if total else 0,
            "empresas_ok": sum(1 for c in cartoes if c.tudo_bateu),
            "empresas_pendentes": sum(1 for c in cartoes if not c.tudo_bateu),
        },
    }


@bp.get("/conferencia")
@exigir_usuario
def conferencia():
    comp = _comp()
    resp_id, carteira = _carteira()
    vista = "pendencia" if request.args.get("vista") == "pendencia" else "todas"
    usuario = usuario_atual()
    dados = _dados(comp, resp_id)
    somente_leitura = resp_id != usuario.id
    cartoes = dados["cartoes"]
    visiveis = [c for c in cartoes if not c.tudo_bateu] if vista == "pendencia" else cartoes
    editaveis = {c.empresa.id for c in cartoes
                 if not somente_leitura and svc_lanc.pode_editar(usuario, c.empresa, comp)}
    return render_template(
        "faturamento/conferencia.html", comp=comp, carteira=carteira, resp_id=resp_id, vista=vista,
        cartoes=visiveis, ha_lancamentos=bool(cartoes), progresso=dados["progresso"],
        somente_leitura=somente_leitura, editaveis=editaveis, nome_carteira=_nome_carteira(resp_id),
        usuarios=svc_emp.usuarios_ativos(), competencias=_competencias_para_seletor(comp),
        dica_ajuste=_dica_ajuste, ajuste_curto=_ajuste_curto,
    )


@bp.get("/conferencia/excel")
@exigir_usuario
def conferencia_excel():
    comp = _comp()
    resp_id, _ = _carteira()
    conteudo = svc_exp.planilha_conferencia(comp, svc_res.conferencia(comp, resp_id))
    nome = svc_exp.nome_arquivo_conferencia(comp)
    return Response(
        conteudo,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nome}"', "Cache-Control": "no-store"},
    )


@bp.get("/conferencia/imprimir")
@exigir_usuario
def conferencia_imprimir():
    comp = _comp()
    resp_id, carteira = _carteira()
    dados = _dados(comp, resp_id)
    return render_template(
        "faturamento/conferencia_impressao.html", comp=comp, carteira=carteira,
        cartoes=dados["cartoes"], progresso=dados["progresso"], nome_carteira=_nome_carteira(resp_id),
        gerado_em=datetime.now(), dica_ajuste=_dica_ajuste, ajuste_curto=_ajuste_curto,
    )
