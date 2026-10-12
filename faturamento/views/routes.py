"""Telas (HTML). Toda regra está em services/; aqui só se lê parâmetros e monta a página."""
from __future__ import annotations

import hmac
import re
import secrets
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import urlsplit

from flask import abort, flash, redirect, render_template, request, session, url_for

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
from ..util import (
    ValorInvalido, competencia, competencia_atual, competencia_padrao, fmt_inteiro, fmt_moeda, somar_meses,
)


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


# ------------------------------------------------------------------ CSRF (sem dependência externa)

CHAVE_CSRF = "fat_csrf"


@bp.app_template_global()
def csrf_token() -> str:
    """Token por sessão, posto em todo formulário POST (campo oculto ``csrf_token``)."""
    tok = session.get(CHAVE_CSRF)
    if not tok:
        tok = session[CHAVE_CSRF] = secrets.token_urlsafe(32)
    return tok


@bp.before_request
def _verificar_csrf():
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return None
    esperado = session.get(CHAVE_CSRF)
    enviado = request.form.get("csrf_token", "")
    if not esperado or not enviado or not hmac.compare_digest(str(esperado), str(enviado)):
        return ("Formulário expirado ou inválido. Volte, recarregue a página e tente de novo.", 400,
                {"Content-Type": "text/plain; charset=utf-8"})
    return None


def _destino_seguro(proximo: str | None) -> str:
    """Só caminhos locais ('/algo'); nada de '//host', '/\\host' ou URL com esquema/host."""
    padrao = url_for("faturamento.painel")
    if not proximo or not proximo.startswith("/") or proximo.startswith(("//", "/\\")):
        return padrao
    partes = urlsplit(proximo)
    if partes.scheme or partes.netloc or "\\" in proximo or any(ord(c) < 33 for c in proximo):
        return padrao
    return proximo


# ------------------------------------------------------------------ sessão

@bp.route("/entrar", methods=["GET", "POST"])
def escolher_usuario():
    if not modo_local():
        return redirect(url_for("faturamento.painel"))
    if request.method == "POST":
        u = db.session.get(Usuario, request.form.get("usuario_id", type=int) or 0)
        if u and u.ativo:
            definir_usuario(u)
            return redirect(_destino_seguro(request.args.get("proximo")))
        flash("Escolha um usuário.", "erro")
    return render_template("faturamento/entrar.html", usuarios=svc_emp.usuarios_ativos())


@bp.route("/sair", methods=["GET", "POST"])
def sair_view():
    # Sair só por POST (com token): um link/imagem de outro site não desloga ninguém.
    if request.method == "GET":
        return redirect(url_for("faturamento.painel"))
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

ALTURA_GRAFICO = 180  # px


def alturas_grafico(evolucao: list[dict], altura: int = ALTURA_GRAFICO) -> list[dict]:
    """Altura (px) dos segmentos de cada mês: base (SEFAZ) e ajuste por cima.

    Ajuste negativo reduz a base e não desenha segmento. Escala pelo maior total desenhado,
    então nenhuma barra passa de ``altura`` e nenhuma altura é negativa.
    """
    def partes(base, aj):
        base, aj = max(Decimal(base or 0), Decimal(0)), Decimal(aj or 0)
        return (max(base + aj, Decimal(0)), Decimal(0)) if aj < 0 else (base, aj)

    barras = [(partes(p["entradas"], p["entradas_ajuste"]), partes(p["saidas"], p["saidas_ajuste"])) for p in evolucao]
    maximo = max((b + a for par in barras for b, a in par), default=Decimal(0))
    esc = Decimal(altura) / maximo if maximo > 0 else Decimal(0)

    def px(v):
        return max(0, min(altura, int((v * esc).to_integral_value(rounding=ROUND_HALF_UP))))

    saida = []
    for (eb, ea), (sb, sa) in barras:
        e_base, s_base = px(eb), px(sb)
        saida.append({"e_base": e_base, "e_aj": min(px(ea), altura - e_base),
                      "s_base": s_base, "s_aj": min(px(sa), altura - s_base)})
    return saida


@bp.get("/lancamento")
@exigir_usuario
def lancamento():
    comp = _comp()
    usuario = usuario_atual()
    empresa_id = request.args.get("empresa", type=int)
    minhas = svc_emp.listar_empresas(usuario.id, comp)
    todas = svc_emp.listar_empresas(None, comp)
    # Sem empresa escolhida, nada é carregado: a tela só pede a escolha.
    empresa = db.session.get(Empresa, empresa_id) if empresa_id else None
    if empresa is None:
        status = {e.id: svc_fech.status_mes(e, comp) for e in minhas}
        return render_template("faturamento/lancamento.html", comp=comp, empresa=None, minhas=minhas, todas=todas,
                               competencias=_competencias_para_seletor(comp), status_empresas=status,
                               rotulos=svc_fech.ROTULOS)
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
    evolucao = svc_res.evolucao(empresa, comp, 8)
    return render_template(
        "faturamento/lancamento.html", comp=comp, empresa=empresa, linhas=linhas, pode_editar=pode,
        linhas_ajustes=linhas_ajustes,
        responsavel=resp, status=svc_fech.status_mes(empresa, comp), rotulos=svc_fech.ROTULOS,
        minhas=minhas, todas=todas, proxima=proxima, competencias=_competencias_para_seletor(comp),
        evolucao=evolucao, grafico=alturas_grafico(evolucao), motivos=MOTIVOS_AJUSTE,
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
        try:
            try:
                tipo_ids = [int(x) for x in f.getlist("tipos")]
            except ValueError as exc:
                raise ValorInvalido("Tipo de documento inválido.") from exc
            if empresa is None:
                resp = db.session.get(Usuario, f.get("responsavel_id", type=int) or 0) or usuario_atual()
                empresa = svc_emp.criar_empresa(f.get("nome", ""), resp, usuario_atual(), cnpj=f.get("cnpj"),
                                                tipo_ids=tipo_ids, ativa=f.get("ativa") == "1")
            else:
                svc_emp.atualizar_empresa(empresa, usuario_atual(), nome=f.get("nome", ""), cnpj=f.get("cnpj", ""),
                                          ativa=f.get("ativa") == "1", tipo_ids=tipo_ids)
                novo = db.session.get(Usuario, f.get("responsavel_id", type=int) or 0)
                # Formulário salvo sem mexer em responsável nem competência: carteira fica como está.
                intocado = ("responsavel_original" in f and f.get("responsavel_id") == f.get("responsavel_original")
                            and f.get("inicio") == f.get("inicio_original"))
                if novo and not intocado:
                    inicio = competencia(f.get("inicio")) if f.get("inicio") else competencia_padrao()
                    atual = svc_emp.responsavel_em(empresa, inicio)
                    posteriores = any(v.inicio > inicio for v in empresa.historico_responsaveis)
                    if atual is None or novo.id != atual.id or (posteriores and svc_emp.responsavel_atual(empresa) != novo):
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

POR_PAGINA_HISTORICO = 50
_CHAVES_COMPETENCIA = {"inicio", "competencia", "competencias"}
_RE_DATA = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_RE_DATA_HORA = re.compile(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(:\d{2}(\.\d+)?)?")
_RE_COMP = re.compile(r"(\d{4})-(\d{2})")
_RE_MOEDA = re.compile(r"-?\d+\.\d{2}")


def chave_oculta(chave) -> bool:
    """Chaves internas que não interessam a quem lê o histórico (listas de ids etc.)."""
    k = str(chave)
    return k.endswith("_ids") or k.startswith("_") or k in ("marcas",)


@bp.app_template_filter("hist")
def fmt_historico(v, chave: str = "") -> str:
    """Valor do 'Detalhe' do histórico em pt-BR: datas, competências e moeda."""
    if v is None or v == "":
        return "—"
    if v is True:
        return "sim"
    if v is False:
        return "não"
    if isinstance(v, dict):
        partes = [f"{k}: {fmt_historico(x, k)}" for k, x in v.items() if not chave_oculta(k)]
        return ", ".join(partes) if partes else "—"
    if isinstance(v, (list, tuple)):
        sep = "; " if any(isinstance(x, dict) for x in v) else ", "
        return sep.join(fmt_historico(x, chave) for x in v) if v else "—"
    if isinstance(v, int):
        return fmt_inteiro(v)
    if isinstance(v, float):
        return fmt_moeda(v)
    t = str(v)
    comp = str(chave) in _CHAVES_COMPETENCIA
    if m := _RE_DATA_HORA.fullmatch(t):
        return f"{m[3]}/{m[2]}/{m[1]} {m[4]}:{m[5]}"
    if m := _RE_DATA.fullmatch(t):
        return f"{m[2]}/{m[1]}" if comp else f"{m[3]}/{m[2]}/{m[1]}"
    if comp and (m := _RE_COMP.fullmatch(t)):
        return f"{m[2]}/{m[1]}"
    if _RE_MOEDA.fullmatch(t):
        return fmt_moeda(Decimal(t))
    return t


@bp.get("/historico")
@exigir_usuario
def historico():
    pagina = max(1, request.args.get("pagina", 1, type=int) or 1)
    regs = aud.listar(empresa_id=request.args.get("empresa", type=int), usuario_id=request.args.get("usuario", type=int),
                      limite=POR_PAGINA_HISTORICO + 1, deslocamento=(pagina - 1) * POR_PAGINA_HISTORICO)
    tem_proxima = len(regs) > POR_PAGINA_HISTORICO
    return render_template("faturamento/historico.html", registros=regs[:POR_PAGINA_HISTORICO],
                           empresas=svc_emp.listar_empresas(None, competencia_atual(), True),
                           usuarios=svc_emp.usuarios_ativos(), carregar=aud.carregar, chave_oculta=chave_oculta,
                           empresa_id=request.args.get("empresa", type=int),
                           usuario_id=request.args.get("usuario", type=int),
                           pagina_hist=pagina, tem_proxima=tem_proxima)
