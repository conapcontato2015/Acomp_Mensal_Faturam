"""Registro de quem mudou o quê e quando."""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select

from ..extensions import db
from ..models import Auditoria, Usuario
from ..util import fmt_inteiro, fmt_moeda


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


# ------------------------------------------------------------------ exibição do histórico

_CHAVES_COMPETENCIA = {"inicio", "competencia", "competencias"}
_RE_DATA = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_RE_DATA_HORA = re.compile(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(:\d{2}(\.\d+)?)?")
_RE_COMP = re.compile(r"(\d{4})-(\d{2})")
_RE_MOEDA = re.compile(r"-?\d+\.\d{2}")


def chave_oculta(chave) -> bool:
    """Chaves internas que não interessam a quem lê o histórico (listas de ids etc.)."""
    k = str(chave)
    return k.endswith("_ids") or k.startswith("_") or k in ("marcas",)


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


def diferencas(antes, depois) -> list[dict]:
    """O que mudou num registro, já formatado em pt-BR: [{campo, antes, depois, tipo}].

    tipo: 'alterado' | 'novo' | 'removido' | 'valor' (quando não são dicionários).
    """
    if isinstance(antes, dict) or isinstance(depois, dict):
        a = antes if isinstance(antes, dict) else {}
        d = depois if isinstance(depois, dict) else {}
        saida = []
        for k in dict.fromkeys([*a.keys(), *d.keys()]):
            if chave_oculta(k):
                continue
            if k not in a:
                if d[k] is not None:
                    saida.append({"campo": k, "antes": None, "depois": fmt_historico(d[k], k), "tipo": "novo"})
            elif k not in d:
                saida.append({"campo": k, "antes": fmt_historico(a[k], k), "depois": None, "tipo": "removido"})
            elif a[k] != d[k]:
                saida.append({"campo": k, "antes": fmt_historico(a[k], k), "depois": fmt_historico(d[k], k),
                              "tipo": "alterado"})
        return saida
    if antes is None and depois is None:
        return []
    return [{"campo": "", "antes": fmt_historico(antes), "depois": fmt_historico(depois), "tipo": "valor"}]
