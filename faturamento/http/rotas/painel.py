"""Painel do mês: status de cada empresa da carteira, progresso e alertas de variação."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ...models import Usuario
from ...services import resumo as svc_res
from .. import comum
from ..auth import exigir_usuario
from ..json import RespostaJSON
from ..rota import RotaFaturamento

router = APIRouter(route_class=RotaFaturamento, default_response_class=RespostaJSON, tags=["painel"])

STATUS = ("pendente", "preenchido", "sem_movimento")


@router.get("/painel")
def painel(competencia: str | None = None, carteira: str | None = None, status: str = "todos",
           usuario: Usuario = Depends(exigir_usuario)):
    comp = comum.comp_ou_padrao(competencia)
    resp_id, carteira_sel = comum.carteira(carteira, usuario)
    linhas = svc_res.painel(comp, resp_id)
    contagem = {s: sum(1 for l in linhas if l.status == s) for s in STATUS}
    visiveis = [l for l in linhas if l.status == status] if status in STATUS else linhas
    total = len(linhas)
    feitos = contagem["preenchido"] + contagem["sem_movimento"]
    return {
        "competencia": comum.comp_json(comp),
        "carteira": carteira_sel,
        "somente_leitura": resp_id != usuario.id,
        "filtro_status": status if status in STATUS else "todos",
        "total": total,
        "feitos": feitos,
        "progresso": round(feitos / total * 100) if total else 0,
        "contagem": {"pendente": contagem["pendente"], "preenchido": contagem["preenchido"],
                     "semMovimento": contagem["sem_movimento"]},
        "alertas": sum(1 for l in linhas if l.alerta),
        "empresas": [{
            "empresa": comum.empresa_resumo(l.empresa),
            "status": l.status,
            "status_anterior": l.status_anterior,
            "tipos_usados": l.tipos_usados,
            "tipos_lancados": l.tipos_lancados,
            "entradas": l.entradas,
            "saidas": l.saidas,
            "linhas": l.linhas,
            "bateram": l.bateram,
            "variacao_saidas": l.variacao_saidas,
            "alerta": l.alerta,
        } for l in visiveis],
    }
