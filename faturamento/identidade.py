"""Ponto único de identidade.

- MODO_AUTH=local: o usuário escolhe o nome numa janela (sem senha) e ele fica na sessão.
- MODO_AUTH=plataforma: o nome (ou external_id) vem de um cabeçalho HTTP posto pela
  plataforma/proxy de login (AUTH_HEADER, padrão X-Remote-User).

Nenhuma outra parte do sistema sabe de onde vem o usuário: todas chamam ``usuario_atual()``.
"""
from __future__ import annotations

from functools import wraps

from flask import current_app, g, jsonify, redirect, request, session, url_for
from sqlalchemy import func, or_, select

from .extensions import db
from .models import Usuario
from .util import normalizar_nome

CHAVE_SESSAO = "fat_usuario_id"


def modo_local() -> bool:
    return current_app.config.get("MODO_AUTH", "local") == "local"


def _buscar_por_identificador(ident: str) -> Usuario | None:
    ident = (ident or "").strip()
    if not ident:
        return None
    u = db.session.scalar(select(Usuario).where(or_(Usuario.external_id == ident, func.lower(Usuario.nome) == ident.lower())))
    if u:
        return u
    alvo = normalizar_nome(ident)
    for cand in db.session.scalars(select(Usuario)):
        if normalizar_nome(cand.nome) == alvo:
            return cand
    return None


def usuario_atual() -> Usuario | None:
    if "fat_usuario" in g:
        return g.fat_usuario
    usuario = None
    if modo_local():
        uid = session.get(CHAVE_SESSAO)
        if uid:
            usuario = db.session.get(Usuario, uid)
    else:
        usuario = _buscar_por_identificador(request.headers.get(current_app.config["AUTH_HEADER"], ""))
    if usuario is not None and not usuario.ativo:
        usuario = None
    g.fat_usuario = usuario
    return usuario


def definir_usuario(usuario: Usuario) -> None:
    session[CHAVE_SESSAO] = usuario.id
    session.permanent = True
    g.fat_usuario = usuario


def sair() -> None:
    session.pop(CHAVE_SESSAO, None)
    g.pop("fat_usuario", None)


def exigir_usuario(view):
    """Telas: sem usuário -> janela de escolha (modo local) ou 403 (modo plataforma)."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if usuario_atual() is None:
            if modo_local():
                return redirect(url_for("faturamento.escolher_usuario", proximo=request.full_path))
            return ("Usuário não reconhecido pela plataforma.", 403)
        return view(*args, **kwargs)

    return wrapper


def exigir_usuario_api(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if usuario_atual() is None:
            return jsonify({"erro": "usuario_nao_identificado",
                            "mensagem": "Defina o usuário da sessão (POST /sessao) ou envie o cabeçalho de login."}), 401
        return view(*args, **kwargs)

    return wrapper
