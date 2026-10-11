"""API REST (JSON) em /api/faturamento/v1.

Competência sempre como "AAAA-MM"; valores monetários como texto decimal ("395464.73").
As telas usam a mesma camada de serviço — nenhuma regra fica só aqui.
"""
from __future__ import annotations

from flask import abort, jsonify, request

from .. import api_bp
from ..extensions import db
from ..identidade import definir_usuario, exigir_usuario_api, modo_local, usuario_atual
from ..models import Ajuste, Empresa, Lancamento, TipoDocumento, Usuario
from ..services import RegraViolada, SemPermissao
from ..services import auditoria as aud
from ..services import empresas as svc_emp
from ..services import fechamento as svc_fech
from ..services import lancamentos as svc_lanc
from ..services import resumo as svc_res
from ..util import ValorInvalido, comp_iso, competencia, competencia_padrao


def _dec(v):
    return None if v is None else str(v)


def _usuario_json(u: Usuario | None):
    return None if u is None else {"id": u.id, "nome": u.nome}


def _tipo_json(t: TipoDocumento):
    return {"id": t.id, "codigo": t.codigo, "nome": t.nome, "modelo": t.modelo, "sentido": t.sentido, "ordem": t.ordem}


def _empresa_json(e: Empresa):
    return {
        "id": e.id, "nome": e.nome, "cnpj": e.cnpj, "ativa": e.ativa, "external_id": e.external_id,
        "responsavel": _usuario_json(svc_emp.responsavel_atual(e)),
        "tipos": [t.id for t in e.tipos],
        "historico_responsaveis": [
            {"usuario": _usuario_json(v.usuario), "inicio": comp_iso(v.inicio), "origem": v.origem,
             "registrado_em": v.registrado_em.isoformat(timespec="seconds")}
            for v in e.historico_responsaveis
        ],
    }


def _ajuste_json(a: Ajuste):
    return {"id": a.id, "grupo": a.grupo, "qtde": a.qtde, "valor": _dec(a.valor), "motivo": a.motivo,
            "observacao": a.observacao, "criado_por": _usuario_json(a.criado_por),
            "criado_em": a.criado_em.isoformat(timespec="seconds")}


def _lanc_json(l: Lancamento | None, tipo: TipoDocumento):
    base = {"tipo": _tipo_json(tipo)}
    if l is None:
        base.update({"id": None, "qtde_autor": None, "valor_autor": None, "qtde_canc": None, "valor_canc": None,
                     "ajustes": [], "total_qtde_autor": 0, "total_valor_autor": "0.00", "total_qtde_canc": 0,
                     "total_valor_canc": "0.00", "bateu": False})
        return base
    base.update({
        "id": l.id, "qtde_autor": l.qtde_autor, "valor_autor": _dec(l.valor_autor),
        "qtde_canc": l.qtde_canc, "valor_canc": _dec(l.valor_canc),
        "ajustes": [_ajuste_json(a) for a in l.ajustes],
        "total_qtde_autor": l.total_qtde_autor, "total_valor_autor": _dec(l.total_valor_autor),
        "total_qtde_canc": l.total_qtde_canc, "total_valor_canc": _dec(l.total_valor_canc),
        "bateu": l.bateu, "bateu_por": _usuario_json(l.bateu_por),
    })
    return base


def _comp_arg(nome="competencia"):
    v = request.args.get(nome)
    try:
        return competencia(v) if v else competencia_padrao()
    except ValorInvalido as exc:
        abort(_erro(str(exc), 400))


def _erro(msg, status=422, codigo="regra_violada"):
    resp = jsonify({"erro": codigo, "mensagens": msg if isinstance(msg, list) else [msg]})
    resp.status_code = status
    return resp


@api_bp.errorhandler(RegraViolada)
def _regra(exc: RegraViolada):
    if isinstance(exc, SemPermissao):
        return _erro(exc.mensagens, 403, "somente_leitura")
    db.session.rollback()
    return _erro(exc.mensagens, 422)


def _empresa_ou_404(eid: int) -> Empresa:
    e = db.session.get(Empresa, eid)
    if e is None:
        abort(_erro("Empresa não encontrada.", 404, "nao_encontrado"))
    return e


def _substituto() -> bool:
    j = request.get_json(silent=True) or {}
    return bool(j.get("substituto")) or request.args.get("substituto") in ("1", "true")


# --------------------------------------------------------------------- índice / sessão

@api_bp.get("/")
def indice():
    from flask import current_app
    rotas = sorted({(r.rule, ",".join(sorted(m for m in r.methods if m not in ("HEAD", "OPTIONS"))))
                    for r in current_app.url_map.iter_rules() if r.endpoint.startswith("faturamento_api.")})
    return jsonify({"servico": "faturamento", "versao": "v1", "rotas": [{"rota": r, "metodos": m} for r, m in rotas]})


@api_bp.get("/sessao")
def sessao_get():
    return jsonify({"usuario": _usuario_json(usuario_atual()), "modo_auth": "local" if modo_local() else "plataforma"})


@api_bp.post("/sessao")
def sessao_post():
    if not modo_local():
        return _erro("No modo plataforma o usuário vem do login.", 400, "modo_plataforma")
    j = request.get_json(silent=True) or {}
    u = db.session.get(Usuario, j.get("usuario_id")) if j.get("usuario_id") else None
    if u is None or not u.ativo:
        return _erro("Usuário inválido.", 400)
    definir_usuario(u)
    return jsonify({"usuario": _usuario_json(u)})


@api_bp.get("/usuarios")
def usuarios():
    return jsonify([_usuario_json(u) for u in svc_emp.usuarios_ativos()])


@api_bp.get("/tipos-documento")
def tipos():
    return jsonify([_tipo_json(t) for t in svc_emp.tipos_ativos()])


# --------------------------------------------------------------------- empresas

@api_bp.get("/empresas")
def empresas_listar():
    resp = request.args.get("responsavel", type=int)
    incl = request.args.get("incluir_inativas") in ("1", "true")
    comp = _comp_arg()
    return jsonify([_empresa_json(e) for e in svc_emp.listar_empresas(resp, comp, incl, request.args.get("busca"))])


@api_bp.post("/empresas")
@exigir_usuario_api
def empresas_criar():
    j = request.get_json(silent=True) or {}
    resp = db.session.get(Usuario, j.get("responsavel_id")) if j.get("responsavel_id") else usuario_atual()
    if resp is None:
        return _erro("Responsável inválido.", 400)
    e = svc_emp.criar_empresa(j.get("nome", ""), resp, usuario_atual(), cnpj=j.get("cnpj"),
                              tipo_ids=j.get("tipos") or [])
    db.session.commit()
    return jsonify(_empresa_json(e)), 201


@api_bp.get("/empresas/<int:eid>")
def empresas_detalhe(eid):
    return jsonify(_empresa_json(_empresa_ou_404(eid)))


@api_bp.put("/empresas/<int:eid>")
@exigir_usuario_api
def empresas_alterar(eid):
    e = _empresa_ou_404(eid)
    j = request.get_json(silent=True) or {}
    svc_emp.atualizar_empresa(e, usuario_atual(), nome=j.get("nome"), cnpj=j.get("cnpj"),
                              ativa=j.get("ativa"), tipo_ids=j.get("tipos"))
    db.session.commit()
    return jsonify(_empresa_json(e))


@api_bp.post("/empresas/<int:eid>/responsavel")
@exigir_usuario_api
def empresas_responsavel(eid):
    e = _empresa_ou_404(eid)
    j = request.get_json(silent=True) or {}
    novo = db.session.get(Usuario, j.get("usuario_id")) if j.get("usuario_id") else None
    if novo is None:
        return _erro("Usuário inválido.", 400)
    try:
        inicio = competencia(j["inicio"]) if j.get("inicio") else competencia_padrao()
    except ValorInvalido as exc:
        return _erro(str(exc), 400)
    mudou = svc_emp.definir_responsavel(e, novo, inicio, usuario_atual(), origem=j.get("origem") or "manual")
    db.session.commit()
    return jsonify({"alterado": mudou, "empresa": _empresa_json(e)})


# --------------------------------------------------------------------- lançamentos

@api_bp.get("/lancamentos")
def lancamentos_mes():
    e = _empresa_ou_404(request.args.get("empresa", type=int) or 0)
    comp = _comp_arg()
    linhas = svc_lanc.carregar_mes(e, comp)
    return jsonify({
        "empresa": _empresa_json(e), "competencia": comp_iso(comp),
        "status": svc_fech.status_mes(e, comp),
        "pode_editar": svc_lanc.pode_editar(usuario_atual(), e, comp),
        "linhas": [_lanc_json(l.lancamento, l.tipo) for l in linhas],
    })


@api_bp.put("/lancamentos/<int:eid>/<comp>")
@exigir_usuario_api
def lancamentos_gravar(eid, comp):
    e = _empresa_ou_404(eid)
    try:
        c = competencia(comp)
    except ValorInvalido as exc:
        return _erro(str(exc), 400)
    j = request.get_json(silent=True) or {}
    res = svc_lanc.salvar_mes(e, c, j.get("linhas") or [], usuario_atual(), substituto=bool(j.get("substituto")))
    db.session.commit()
    linhas = svc_lanc.carregar_mes(e, c)
    return jsonify({"alterados": res.alterados, "avisos": res.avisos, "status": svc_fech.status_mes(e, c),
                    "linhas": [_lanc_json(l.lancamento, l.tipo) for l in linhas]})


@api_bp.post("/lancamentos/<int:eid>/<comp>/<int:tipo_id>/ajustes")
@exigir_usuario_api
def ajustes_criar(eid, comp, tipo_id):
    e = _empresa_ou_404(eid)
    try:
        c = competencia(comp)
    except ValorInvalido as exc:
        return _erro(str(exc), 400)
    tipo = db.session.get(TipoDocumento, tipo_id) or abort(_erro("Tipo inexistente.", 404, "nao_encontrado"))
    j = request.get_json(silent=True) or {}
    svc_lanc.exigir_edicao(usuario_atual(), e, c, bool(j.get("substituto")))
    lanc = svc_lanc.obter_ou_criar(e, c, tipo, usuario_atual())
    aj = svc_lanc.adicionar_ajuste(lanc, j.get("grupo", "AUTOR"), j.get("qtde"), j.get("valor"), usuario_atual(),
                                   motivo=j.get("motivo"), observacao=j.get("observacao"), substituto=True)
    db.session.commit()
    return jsonify({"ajuste": _ajuste_json(aj), "lancamento": _lanc_json(lanc, tipo)}), 201


@api_bp.delete("/ajustes/<int:aid>")
@exigir_usuario_api
def ajustes_remover(aid):
    aj = db.session.get(Ajuste, aid) or abort(_erro("Ajuste não encontrado.", 404, "nao_encontrado"))
    lanc = aj.lancamento
    svc_lanc.remover_ajuste(aj, usuario_atual(), _substituto())
    db.session.commit()
    return jsonify({"lancamento": _lanc_json(lanc, lanc.tipo)})


@api_bp.put("/lancamentos/<int:lid>/bateu")
@exigir_usuario_api
def bateu(lid):
    lanc = db.session.get(Lancamento, lid) or abort(_erro("Lançamento não encontrado.", 404, "nao_encontrado"))
    j = request.get_json(silent=True) or {}
    svc_lanc.marcar_bateu(lanc, bool(j.get("bateu")), usuario_atual(), bool(j.get("substituto")))
    db.session.commit()
    return jsonify({"id": lanc.id, "bateu": lanc.bateu})


@api_bp.put("/conferencia/<int:eid>/<comp>")
@exigir_usuario_api
def bateu_empresa(eid, comp):
    e = _empresa_ou_404(eid)
    c = competencia(comp)
    j = request.get_json(silent=True) or {}
    n = svc_lanc.marcar_bateu_empresa(e, c, bool(j.get("bateu")), usuario_atual(), bool(j.get("substituto")))
    db.session.commit()
    return jsonify({"alterados": n})


@api_bp.put("/fechamentos/<int:eid>/<comp>")
@exigir_usuario_api
def fechamento(eid, comp):
    e = _empresa_ou_404(eid)
    c = competencia(comp)
    j = request.get_json(silent=True) or {}
    status = j.get("status")
    if status not in ("sem_movimento", "pendente"):
        return _erro("status deve ser 'sem_movimento' ou 'pendente'.", 400)
    novo = svc_fech.marcar_sem_movimento(e, c, usuario_atual(), status == "sem_movimento", bool(j.get("substituto")))
    db.session.commit()
    return jsonify({"status": novo})


# --------------------------------------------------------------------- leitura agregada

@api_bp.get("/painel")
def painel():
    comp = _comp_arg()
    resp = request.args.get("responsavel", type=int)
    return jsonify({"competencia": comp_iso(comp), "empresas": [{
        "empresa": {"id": l.empresa.id, "nome": l.empresa.nome}, "status": l.status,
        "tipos_usados": l.tipos_usados, "tipos_lancados": l.tipos_lancados,
        "entradas": _dec(l.entradas), "saidas": _dec(l.saidas), "linhas": l.linhas, "bateram": l.bateram,
        "status_anterior": l.status_anterior, "variacao_saidas": l.variacao_saidas, "alerta": l.alerta,
    } for l in svc_res.painel(comp, resp)]})


@api_bp.get("/resumo")
def resumo():
    comp = _comp_arg()
    resp = request.args.get("responsavel", type=int)
    cartoes = svc_res.conferencia(comp, resp, sentido=request.args.get("sentido"),
                                  situacao=request.args.get("situacao"), empresa_id=request.args.get("empresa", type=int))
    return jsonify({
        "competencia": comp_iso(comp),
        "progresso": svc_res.progresso_conferencia(comp, resp),
        "empresas": [{
            "empresa": {"id": c.empresa.id, "nome": c.empresa.nome}, "responsavel": c.responsavel_nome,
            "bateram": c.n_bateu, "total": c.total,
            "blocos": [{
                "sentido": b.sentido, "subtotal": {"qtde_autor": b.qtde_autor, "valor_autor": _dec(b.valor_autor),
                                                   "qtde_canc": b.qtde_canc, "valor_canc": _dec(b.valor_canc)},
                "linhas": [_lanc_json(l, l.tipo) for l in b.linhas],
            } for b in c.blocos],
        } for c in cartoes],
    })


@api_bp.get("/evolucao")
def evolucao():
    e = _empresa_ou_404(request.args.get("empresa", type=int) or 0)
    ate = _comp_arg("ate")
    meses = max(1, min(36, request.args.get("meses", 8, type=int)))
    return jsonify([{**p, "competencia": comp_iso(p["competencia"]),
                     **{k: _dec(p[k]) for k in ("entradas", "entradas_ajuste", "saidas", "saidas_ajuste")}}
                    for p in svc_res.evolucao(e, ate, meses)])


@api_bp.get("/auditoria")
def auditoria():
    regs = aud.listar(empresa_id=request.args.get("empresa", type=int), usuario_id=request.args.get("usuario", type=int))
    return jsonify([{"id": r.id, "data": r.data.isoformat(timespec="seconds"), "usuario": r.usuario_nome,
                     "tabela": r.tabela, "acao": r.acao, "descricao": r.descricao,
                     "antes": aud.carregar(r.antes), "depois": aud.carregar(r.depois)} for r in regs])
