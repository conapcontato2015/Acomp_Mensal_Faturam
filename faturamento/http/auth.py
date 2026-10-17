"""Quem está usando o sistema.

- ``MODO_AUTH=local`` (rodando no PC): a pessoa escolhe o nome na tela "Quem está usando?" e ele fica
  num cookie assinado (``fat_usuario``). Sem senha, como antes.
- ``MODO_AUTH=plataforma`` (dentro do Conap Ferramentas): o usuário vem do **JWT** que a plataforma já
  emite (cookie ``JWT_COOKIE`` ou cabeçalho ``Authorization: Bearer``). Não há login próprio.
  Sem chave de JWT configurada, aceita o nome num cabeçalho (``AUTH_HEADER``) posto por um proxy.

As rotas só usam ``usuario_atual`` (opcional) ou ``exigir_usuario`` (obrigatório).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time

from fastapi import HTTPException, Request
from sqlalchemy import func, or_, select

from ..config import config
from ..db import db
from ..models import Usuario
from ..util import normalizar_nome

COOKIE_LOCAL = "fat_usuario"
VALIDADE_LOCAL = 60 * 60 * 24 * 30  # 30 dias


def modo_local() -> bool:
    return config.get("MODO_AUTH", "local") == "local"


# ------------------------------------------------------------------ cookie local assinado

def _assinatura(texto: str) -> str:
    chave = str(config.get("SECRET_KEY", "")).encode()
    dig = hmac.new(chave, texto.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(dig).decode().rstrip("=")


def valor_cookie_local(usuario: Usuario) -> str:
    corpo = f"{usuario.id}.{int(time.time())}"
    return f"{corpo}.{_assinatura(corpo)}"


def _usuario_do_cookie_local(valor: str | None) -> Usuario | None:
    if not valor or valor.count(".") != 2:
        return None
    uid, momento, assinatura = valor.split(".")
    corpo = f"{uid}.{momento}"
    if not hmac.compare_digest(assinatura, _assinatura(corpo)):
        return None
    if not (uid.isdigit() and momento.isdigit()) or time.time() - int(momento) > VALIDADE_LOCAL:
        return None
    return db.session.get(Usuario, int(uid))


def gravar_cookie_local(resposta, usuario: Usuario) -> None:
    resposta.set_cookie(COOKIE_LOCAL, valor_cookie_local(usuario), max_age=VALIDADE_LOCAL, httponly=True,
                        samesite="lax", path="/")


def apagar_cookie_local(resposta) -> None:
    resposta.delete_cookie(COOKIE_LOCAL, path="/")


# ------------------------------------------------------------------ plataforma (JWT)

def jwt_configurado() -> bool:
    return bool(config.get("JWT_SEGREDO") or config.get("JWT_CHAVE_PUBLICA"))


def _token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return request.cookies.get(config.get("JWT_COOKIE") or "token") or None


def _claims(token: str) -> dict | None:
    import jwt  # PyJWT

    algoritmo = config.get("JWT_ALGORITMO") or "HS256"
    chave = config.get("JWT_CHAVE_PUBLICA") if algoritmo.upper().startswith(("RS", "ES", "PS")) else config.get("JWT_SEGREDO")
    if not chave:
        return None
    try:
        return jwt.decode(token, chave, algorithms=[algoritmo], options={"require": ["exp"], "verify_aud": False})
    except jwt.PyJWTError:
        return None


def _usuario_por_identificador(ident: str) -> Usuario | None:
    ident = (ident or "").strip()
    if not ident:
        return None
    u = db.session.scalar(select(Usuario).where(or_(Usuario.external_id == ident,
                                                    func.lower(Usuario.nome) == ident.lower())))
    if u:
        return u
    alvo = normalizar_nome(ident)
    return next((c for c in db.session.scalars(select(Usuario)) if normalizar_nome(c.nome) == alvo), None)


def usuario_do_jwt(claims: dict) -> Usuario | None:
    """Casa o usuário do token: pelo id externo, depois pelo nome; cria se configurado para isso."""
    ident = claims.get(config.get("JWT_CAMPO_ID") or "sub")
    nome = claims.get(config.get("JWT_CAMPO_NOME") or "nome") or claims.get("name")
    ident = str(ident) if ident is not None else ""
    u = db.session.scalar(select(Usuario).where(Usuario.external_id == ident)) if ident else None
    if u is None and nome:
        u = _usuario_por_identificador(str(nome))
        if u is not None and not u.external_id and ident:
            u.external_id = ident  # liga o usuário daqui ao da plataforma na primeira entrada
            db.session.commit()
    if u is None and config.get("JWT_CRIAR_USUARIO", True) and (nome or ident):
        u = Usuario(nome=str(nome or ident)[:80], external_id=ident or None, ativo=True)
        db.session.add(u)
        db.session.commit()
    return u


# ------------------------------------------------------------------ ponto único

def usuario_atual(request: Request) -> Usuario | None:
    """Usuário da requisição (ou None). Guardado em ``request.state`` para não repetir a busca."""
    if hasattr(request.state, "fat_usuario"):
        return request.state.fat_usuario
    usuario = None
    if modo_local():
        usuario = _usuario_do_cookie_local(request.cookies.get(COOKIE_LOCAL))
    elif jwt_configurado():
        token = _token(request)
        claims = _claims(token) if token else None
        usuario = usuario_do_jwt(claims) if claims else None
    elif config.get("AUTH_HEADER"):
        usuario = _usuario_por_identificador(request.headers.get(config["AUTH_HEADER"], ""))
    if usuario is not None and not usuario.ativo:
        usuario = None
    request.state.fat_usuario = usuario
    return usuario


def exigir_usuario(request: Request) -> Usuario:
    """Dependência das rotas: sem usuário identificado responde 401."""
    u = usuario_atual(request)
    if u is None:
        msg = ("Escolha quem está usando o sistema." if modo_local()
               else "Usuário não reconhecido: entre pelo Conap Ferramentas.")
        raise HTTPException(status_code=401, detail={"erro": "usuario_nao_identificado", "mensagens": [msg]})
    return u
