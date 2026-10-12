"""Registro de quem mudou o quê e quando."""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select

from ..extensions import db
from ..models import Auditoria, Usuario


def _json(obj) -> str | None:
    if obj is None:
        return None

    def conv(o):
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        return str(o)

    return json.dumps(obj, default=conv, ensure_ascii=False)


def registrar(tabela: str, acao: str, usuario: Usuario | None, *, registro_id=None, empresa_id=None,
              antes=None, depois=None, descricao: str | None = None) -> Auditoria:
    reg = Auditoria(
        tabela=tabela, acao=acao, registro_id=registro_id, empresa_id=empresa_id,
        antes=_json(antes), depois=_json(depois), descricao=descricao,
        usuario_id=usuario.id if usuario else None,
        usuario_nome=usuario.nome if usuario else None,
    )
    db.session.add(reg)
    return reg


def listar(empresa_id: int | None = None, usuario_id: int | None = None,
           de: date | None = None, ate: date | None = None, limite: int = 300, deslocamento: int = 0) -> list[Auditoria]:
    q = select(Auditoria).order_by(Auditoria.data.desc(), Auditoria.id.desc())
    if empresa_id:
        q = q.where(Auditoria.empresa_id == empresa_id)
    if usuario_id:
        q = q.where(Auditoria.usuario_id == usuario_id)
    if de:
        q = q.where(Auditoria.data >= datetime(de.year, de.month, de.day))
    if ate:
        q = q.where(Auditoria.data < datetime(ate.year, ate.month, ate.day, 23, 59, 59))
    return list(db.session.scalars(q.offset(max(0, deslocamento)).limit(limite)))


def carregar(texto: str | None):
    if not texto:
        return None
    try:
        return json.loads(texto)
    except ValueError:
        return texto
