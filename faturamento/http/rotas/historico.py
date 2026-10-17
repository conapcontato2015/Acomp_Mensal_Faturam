"""Histórico: quem mudou o quê e quando."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...models import Usuario
from ...services import auditoria as aud
from ...services import empresas as svc_emp
from ...util import competencia_atual
from .. import comum
from ..auth import exigir_usuario
from ..json import RespostaJSON
from ..rota import RotaFaturamento

router = APIRouter(route_class=RotaFaturamento, default_response_class=RespostaJSON, tags=["histórico"])

POR_PAGINA = 50


@router.get("/historico")
def historico(empresa: int | None = None, usuario_id: int | None = Query(default=None, alias="usuario"), pagina: int = 1,
              usuario: Usuario = Depends(exigir_usuario)):
    pagina = max(1, pagina)
    regs = aud.listar(empresa_id=empresa, usuario_id=usuario_id, limite=POR_PAGINA + 1,
                      deslocamento=(pagina - 1) * POR_PAGINA)
    return {
        "pagina": pagina,
        "tem_proxima": len(regs) > POR_PAGINA,
        "filtro": {"empresa": empresa, "usuario": usuario_id},
        "empresas": [{"id": e.id, "nome": e.nome} for e in svc_emp.listar_empresas(None, competencia_atual(), True)],
        "usuarios": [comum.usuario_json(u) for u in svc_emp.usuarios_ativos()],
        "registros": [{
            "id": r.id, "data": r.data, "usuario": r.usuario_nome, "tabela": r.tabela, "acao": r.acao,
            "empresa_id": r.empresa_id, "descricao": r.descricao,
            "mudancas": aud.diferencas(aud.carregar(r.antes), aud.carregar(r.depois)),
        } for r in regs[:POR_PAGINA]],
    }
