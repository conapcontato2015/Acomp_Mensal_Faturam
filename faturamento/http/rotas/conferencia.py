"""Conferência: relatório SEFAZ (com ajustes) × sistema contábil, por empresa. Excel e dados para o PDF."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from ...models import Usuario
from ...services import empresas as svc_emp
from ...services import exportacao as svc_exp
from ...services import lancamentos as svc_lanc
from ...services import resumo as svc_res
from ...util import agora
from .. import comum
from ..auth import exigir_usuario
from ..json import RespostaJSON
from ..rota import RotaFaturamento

router = APIRouter(route_class=RotaFaturamento, default_response_class=RespostaJSON, tags=["conferência"])


def _ids(valores: list[str] | None) -> set[int]:
    """?empresa=1&empresa=4 ou ?empresa=1,4. Vazio = todas."""
    ids: set[int] = set()
    for v in valores or []:
        for parte in str(v).split(","):
            if parte.strip().isdigit():
                ids.add(int(parte))
    return ids


def _nome_carteira(resp_id: int | None) -> str:
    if resp_id is None:
        return "Todas as pessoas"
    return next((u.nome for u in svc_emp.usuarios_ativos() if u.id == resp_id), "—")


def _dados(comp: date, resp_id: int | None, escolhidas: set[int]) -> dict:
    todos = svc_res.conferencia(comp, resp_id)
    # Seleção que não pertence a esta carteira/competência é ignorada (mostra todas).
    validas = escolhidas & {c.empresa.id for c in todos}
    cartoes = [c for c in todos if not validas or c.empresa.id in validas]
    total = sum(c.total for c in cartoes)
    bateram = sum(c.n_bateu for c in cartoes)
    return {
        "cartoes": cartoes,
        "opcoes": [{"id": c.empresa.id, "nome": c.empresa.nome} for c in todos],
        "validas": validas,
        "progresso": {
            "linhas": total, "bateram": bateram,
            "percentual": round(bateram / total * 100) if total else 0,
            "empresas_ok": sum(1 for c in cartoes if c.tudo_bateu),
            "empresas_pendentes": sum(1 for c in cartoes if not c.tudo_bateu),
        },
    }


def _cartao_json(c: svc_res.CartaoEmpresa, pode: bool) -> dict:
    return {
        "empresa": comum.empresa_resumo(c.empresa),
        "responsavel": c.responsavel_nome,
        "pode_editar": pode,
        "total": c.total, "bateram": c.n_bateu, "faltam": c.faltam, "tudo_bateu": c.tudo_bateu,
        "blocos": [{
            "sentido": b.sentido, "titulo": b.titulo, "nome_subtotal": b.nome_subtotal,
            "subtotal": {"qtde_autor": b.qtde_autor, "valor_autor": b.valor_autor,
                         "qtde_canc": b.qtde_canc, "valor_canc": b.valor_canc},
            "linhas": [comum.lancamento_json(l, l.tipo) for l in b.linhas],
        } for b in c.blocos],
    }


@router.get("/conferencia")
def conferencia(competencia: str | None = None, carteira: str | None = None, vista: str = "todas",
                empresa: list[str] | None = Query(default=None), usuario: Usuario = Depends(exigir_usuario)):
    comp = comum.comp_ou_padrao(competencia)
    resp_id, carteira_sel = comum.carteira(carteira, usuario)
    vista = "pendencia" if vista == "pendencia" else "todas"
    dados = _dados(comp, resp_id, _ids(empresa))
    somente_leitura = resp_id != usuario.id
    cartoes = dados["cartoes"]
    visiveis = [c for c in cartoes if not c.tudo_bateu] if vista == "pendencia" else cartoes
    return {
        "competencia": comum.comp_json(comp),
        "carteira": carteira_sel,
        "nome_carteira": _nome_carteira(resp_id),
        "vista": vista,
        "somente_leitura": somente_leitura,
        "progresso": dados["progresso"],
        "opcoes": dados["opcoes"],
        "escolhidas": sorted(dados["validas"]),
        "ha_lancamentos": bool(cartoes),
        "gerado_em": agora(),
        "cartoes": [_cartao_json(c, not somente_leitura and svc_lanc.pode_editar(usuario, c.empresa, comp))
                    for c in visiveis],
    }


@router.get("/conferencia/excel", response_class=Response)
def conferencia_excel(competencia: str | None = None, carteira: str | None = None,
                      empresa: list[str] | None = Query(default=None), usuario: Usuario = Depends(exigir_usuario)):
    comp = comum.comp_ou_padrao(competencia)
    resp_id, _ = comum.carteira(carteira, usuario)
    conteudo = svc_exp.planilha_conferencia(comp, _dados(comp, resp_id, _ids(empresa))["cartoes"])
    nome = svc_exp.nome_arquivo_conferencia(comp)
    return Response(conteudo, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"', "Cache-Control": "no-store"})
