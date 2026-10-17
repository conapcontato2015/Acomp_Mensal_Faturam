"""Peças comuns das rotas: parâmetros, erros e conversão dos objetos do banco para JSON."""
from __future__ import annotations

from datetime import date

from fastapi import HTTPException

from ..models import GRUPO_AUTOR, SENTIDOS, Ajuste, Empresa, Lancamento, TipoDocumento, Usuario
from ..services import empresas as svc_emp
from ..util import (
    ValorInvalido, comp_curta, comp_extenso, comp_iso, comp_rotulo, competencia, competencia_atual,
    competencia_padrao, fmt_inteiro, fmt_moeda, somar_meses,
)


# ------------------------------------------------------------------ erros

def erro(mensagens, status: int = 422, codigo: str = "regra_violada") -> HTTPException:
    if isinstance(mensagens, str):
        mensagens = [mensagens]
    return HTTPException(status_code=status, detail={"erro": codigo, "mensagens": list(mensagens)})


def nao_encontrado(texto: str) -> HTTPException:
    return erro(texto, 404, "nao_encontrado")


# ------------------------------------------------------------------ parâmetros

def comp_ou_padrao(valor: str | None) -> date:
    """Competência 'AAAA-MM' (ou 'MM/AAAA'); vazia = mês de trabalho padrão (o anterior)."""
    if not valor:
        return competencia_padrao()
    try:
        return competencia(valor)
    except ValorInvalido as exc:
        raise erro(str(exc), 400, "parametro_invalido") from exc


def carteira(valor: str | None, usuario: Usuario | None, padrao_todos: bool = False) -> tuple[int | None, str]:
    """Seletor de carteira: id do usuário ou 'todos'. Padrão: a do usuário da sessão."""
    if valor == "todos":
        return None, "todos"
    if valor and valor.isdigit():
        return int(valor), valor
    if padrao_todos or usuario is None:
        return None, "todos"
    return usuario.id, str(usuario.id)


def competencias_para_seletor(atual: date, n: int = 18) -> list[dict]:
    hoje = competencia_atual()
    lista = [somar_meses(hoje, -i) for i in range(n)]
    if atual not in lista:
        lista.append(atual)
    return [comp_json(c) for c in sorted(lista, reverse=True)]


# ------------------------------------------------------------------ conversões

def comp_json(c: date) -> dict:
    return {"valor": comp_iso(c), "curta": comp_curta(c), "extenso": comp_extenso(c), "rotulo": comp_rotulo(c)}


def usuario_json(u: Usuario | None) -> dict | None:
    return None if u is None else {"id": u.id, "nome": u.nome}


def tipo_json(t: TipoDocumento) -> dict:
    return {"id": t.id, "codigo": t.codigo, "nome": t.nome, "modelo": t.modelo, "sentido": t.sentido,
            "sentido_nome": SENTIDOS.get(t.sentido, SENTIDOS["S"])[0], "ordem": t.ordem, "ativo": t.ativo}


def empresa_resumo(e: Empresa) -> dict:
    return {"id": e.id, "nome": e.nome, "cnpj": e.cnpj, "cnpj_formatado": e.cnpj_formatado, "ativa": e.ativa}


def empresa_json(e: Empresa, com_historico: bool = True) -> dict:
    d = {**empresa_resumo(e), "external_id": e.external_id,
         "responsavel": usuario_json(svc_emp.responsavel_atual(e)),
         "tipos": [t.id for t in e.tipos]}
    if com_historico:
        d["historico_responsaveis"] = [
            {"usuario": usuario_json(v.usuario), "inicio": comp_iso(v.inicio), "inicio_curta": comp_curta(v.inicio),
             "origem": v.origem, "registrado_em": v.registrado_em}
            for v in e.historico_responsaveis
        ]
    return d


def ajuste_json(a: Ajuste) -> dict:
    return {"id": a.id, "grupo": a.grupo, "qtde": a.qtde, "valor": a.valor, "motivo": a.motivo,
            "observacao": a.observacao or "", "criado_por": usuario_json(a.criado_por), "criado_em": a.criado_em}


def lancamento_json(l: Lancamento | None, tipo: TipoDocumento) -> dict:
    """Uma linha (tipo de documento) do mês, com os números brutos, ajustes e totais."""
    base = {"tipo": tipo_json(tipo)}
    if l is None:
        base.update({"id": None, "qtde_autor": None, "valor_autor": None, "qtde_canc": None, "valor_canc": None,
                     "ajustes": [], "ajuste_qtde_autor": 0, "ajuste_valor_autor": "0.00", "ajuste_qtde_canc": 0,
                     "ajuste_valor_canc": "0.00", "total_qtde_autor": 0, "total_valor_autor": "0.00",
                     "total_qtde_canc": 0, "total_valor_canc": "0.00", "bateu": False, "bateu_por": None,
                     "tem_movimento": False, "dica_ajuste": "", "ajuste_curto": "—"})
        return base
    base.update({
        "id": l.id, "qtde_autor": l.qtde_autor, "valor_autor": l.valor_autor,
        "qtde_canc": l.qtde_canc, "valor_canc": l.valor_canc,
        "ajustes": [ajuste_json(a) for a in l.ajustes],
        "ajuste_qtde_autor": l.ajuste_qtde_autor, "ajuste_valor_autor": l.ajuste_valor_autor,
        "ajuste_qtde_canc": l.ajuste_qtde_canc, "ajuste_valor_canc": l.ajuste_valor_canc,
        "total_qtde_autor": l.total_qtde_autor, "total_valor_autor": l.total_valor_autor,
        "total_qtde_canc": l.total_qtde_canc, "total_valor_canc": l.total_valor_canc,
        "bateu": l.bateu, "bateu_por": usuario_json(l.bateu_por), "tem_movimento": l.tem_movimento,
        "dica_ajuste": dica_ajuste(l), "ajuste_curto": ajuste_curto(l),
    })
    return base


def dica_ajuste(l: Lancamento) -> str:
    """Texto do '±aj': o que o ajuste acrescentou ao número da SEFAZ."""
    partes = []
    for a in l.ajustes:
        grupo = "autorizadas" if a.grupo == GRUPO_AUTOR else "canceladas"
        partes.append(f"{'+' if (a.qtde or 0) >= 0 else ''}{fmt_inteiro(a.qtde or 0)} {grupo} "
                      f"(R$ {fmt_moeda(a.valor or 0)}): {a.motivo}")
    return "Inclui ajuste — " + "; ".join(partes) if partes else ""


def ajuste_curto(l: Lancamento) -> str:
    """'+61 · 1.295,50' (só a parte de autorizadas); '—' sem ajuste."""
    q, v = l.ajuste_qtde_autor, l.ajuste_valor_autor
    if not q and not v:
        return "—"
    return f"{'+' if q >= 0 else ''}{fmt_inteiro(q)} · {fmt_moeda(v)}"
