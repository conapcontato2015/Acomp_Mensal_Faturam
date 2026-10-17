"""Sessão (quem está usando) e dados de referência usados por várias telas."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ... import __version__
from ...config import config
from ...db import db
from ...models import MOTIVOS_AJUSTE, SENTIDOS, Usuario
from ...services import empresas as svc_emp
from ...services import fechamento as svc_fech
from ...util import competencia_atual, competencia_padrao, comp_iso
from ..auth import apagar_cookie_local, exigir_usuario, gravar_cookie_local, modo_local, usuario_atual
from ..comum import comp_ou_padrao, competencias_para_seletor, comp_json, erro, tipo_json, usuario_json
from ..json import Entrada, RespostaJSON
from ..rota import RotaFaturamento

router = APIRouter(route_class=RotaFaturamento, default_response_class=RespostaJSON, tags=["sessão"])


def _recursos() -> dict:
    from ...responsaveis import provedor_configurado
    from ...services import cruzamento as svc_cruz

    return {
        "cruzamento": svc_cruz.configurado(),
        "controle_fiscal": bool(config.get("FOLHA_DATABASE_URL")),
        "empresas_fonte": config.get("EMPRESAS_FONTE", "local"),
        "provedor_responsaveis": provedor_configurado().nome,
    }


@router.get("/sessao")
def sessao(request: Request):
    """Quem está usando. No modo local também lista os nomes para a tela "Quem está usando?"."""
    u = usuario_atual(request)
    return {
        "usuario": usuario_json(u),
        "modo_auth": "local" if modo_local() else "plataforma",
        "usuarios": [usuario_json(x) for x in svc_emp.usuarios_ativos()] if modo_local() else [],
        "versao": __version__,
        "recursos": _recursos(),
    }


class EntradaSessao(Entrada):
    usuario_id: int


@router.post("/sessao")
def entrar(dados: EntradaSessao):
    if not modo_local():
        raise erro("No Conap Ferramentas o usuário vem do login da plataforma.", 400, "modo_plataforma")
    u = db.session.get(Usuario, dados.usuario_id)
    if u is None or not u.ativo:
        raise erro("Escolha um usuário da lista.", 400, "parametro_invalido")
    resposta = RespostaJSON({"usuario": usuario_json(u)})
    gravar_cookie_local(resposta, u)
    return resposta


@router.delete("/sessao")
def sair():
    resposta = RespostaJSON({"ok": True})
    apagar_cookie_local(resposta)
    return resposta


@router.get("/referencias")
def referencias(competencia: str | None = None, usuario: Usuario = Depends(exigir_usuario)):
    """Listas que quase toda tela usa: competências do seletor, usuários, tipos e motivos de ajuste."""
    comp = comp_ou_padrao(competencia)
    return {
        "competencia": comp_json(comp),
        "competencia_padrao": comp_iso(competencia_padrao()),
        "competencia_atual": comp_iso(competencia_atual()),
        "competencias": competencias_para_seletor(comp),
        "usuarios": [usuario_json(x) for x in svc_emp.usuarios_ativos()],
        "tipos": [tipo_json(t) for t in svc_emp.tipos_ativos()],
        "motivos_ajuste": [m for m in MOTIVOS_AJUSTE if m != "Importado da planilha"],
        "sentidos": [{"valor": k, "nome": v[0], "titulo": v[1]} for k, v in SENTIDOS.items()],
        "status": [{"valor": k, "rotulo": v} for k, v in svc_fech.ROTULOS.items()],
        "usuario": usuario_json(usuario),
    }
