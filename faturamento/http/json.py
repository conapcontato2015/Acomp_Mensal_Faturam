"""Formato das respostas da API, no padrão do Conap Ferramentas.

- Chaves em português e camelCase (``qtdeAutor``, ``valorAutor``); no Python tudo segue snake_case e a
  conversão acontece só aqui, na borda.
- Valores monetários como texto decimal (``"1234.56"``), nunca float.
- Competência como ``"AAAA-MM"``; datas/horas ISO 8601.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

_RE_SNAKE = re.compile(r"_([a-z0-9])")
_RE_CAMEL = re.compile(r"(?<=[a-z0-9])([A-Z])")


def chave_camel(chave: str) -> str:
    """'qtde_autor' -> 'qtdeAutor'. Chaves que não são snake_case ficam como estão."""
    if not isinstance(chave, str) or "_" not in chave.strip("_"):
        return chave
    return _RE_SNAKE.sub(lambda m: m.group(1).upper(), chave.strip("_"))


def chave_snake(chave: str) -> str:
    """'qtdeAutor' -> 'qtde_autor'."""
    if not isinstance(chave, str):
        return chave
    return _RE_CAMEL.sub(lambda m: "_" + m.group(1).lower(), chave)


def para_json(valor: Any) -> Any:
    """Converte recursivamente: chaves para camelCase e tipos para JSON (Decimal -> texto)."""
    if isinstance(valor, dict):
        return {chave_camel(k): para_json(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple, set)):
        return [para_json(v) for v in valor]
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, datetime):
        return valor.isoformat(timespec="seconds")
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, BaseModel):
        return para_json(valor.model_dump())
    return valor


class RespostaJSON(JSONResponse):
    """Resposta padrão da API: aplica ``para_json`` (camelCase + decimais como texto)."""

    def render(self, content: Any) -> bytes:
        return json.dumps(para_json(content), ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class Entrada(BaseModel):
    """Corpo de requisição: aceita camelCase (padrão) e também snake_case."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


def dec(v) -> str | None:
    return None if v is None else str(v)
