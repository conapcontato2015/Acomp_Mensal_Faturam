"""Classe de rota usada por todas as rotas do faturamento.

Concentra o que toda requisição precisa, para que o router funcione igual sozinho (``servidor.py``) e
incluído no FastAPI do Conap Ferramentas (``app.include_router(router)``), sem middleware extra:

- uma sessão de banco própria por requisição (aberta antes, fechada depois — com rollback do que
  não foi confirmado);
- erros de regra viram JSON ``{"erro": ..., "mensagens": [...]}`` (422; 403 para carteira alheia);
- proteção contra CSRF: escrita só com corpo JSON, ou upload com o cabeçalho ``X-Requested-With``
  (formulários de outros sites não conseguem enviar nenhum dos dois).
"""
from __future__ import annotations

import functools
import inspect
from typing import Any, Callable

from fastapi import HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from ..db import abrir_escopo, db, fechar_escopo
from ..services import RegraViolada, SemPermissao
from ..util import ValorInvalido
from .json import RespostaJSON, para_json

METODOS_ESCRITA = {"POST", "PUT", "PATCH", "DELETE"}


def _resposta_erro(mensagens, status: int, codigo: str) -> Response:
    if isinstance(mensagens, str):
        mensagens = [mensagens]
    return RespostaJSON({"erro": codigo, "mensagens": list(mensagens)}, status_code=status)


def _pedido_seguro(request: Request) -> bool:
    if request.method not in METODOS_ESCRITA:
        return True
    tipo = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if tipo == "application/json":
        return True
    if tipo == "multipart/form-data" and request.headers.get("x-requested-with"):
        return True
    # DELETE e PUT sem corpo: aceitos com o cabeçalho do front
    return not tipo and bool(request.headers.get("x-requested-with"))


def _converter_retorno(endpoint: Callable) -> Callable:
    """Converte o retorno (dict/list) para o formato da API antes do FastAPI serializar.

    Sem isso o ``jsonable_encoder`` do FastAPI transformaria Decimal em float.
    """
    if inspect.iscoroutinefunction(endpoint):
        @functools.wraps(endpoint)
        async def assincrono(*args, **kwargs) -> Any:
            r = await endpoint(*args, **kwargs)
            return para_json(r) if isinstance(r, (dict, list)) else r
        return assincrono

    @functools.wraps(endpoint)
    def sincrono(*args, **kwargs) -> Any:
        r = endpoint(*args, **kwargs)
        return para_json(r) if isinstance(r, (dict, list)) else r
    return sincrono


class RotaFaturamento(APIRoute):
    def __init__(self, path: str, endpoint: Callable, **kwargs) -> None:
        super().__init__(path, _converter_retorno(endpoint), **kwargs)

    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def tratar(request: Request) -> Response:
            if not _pedido_seguro(request):
                return _resposta_erro("Envie o corpo como JSON (Content-Type: application/json).", 415,
                                      "tipo_conteudo")
            token = abrir_escopo()
            try:
                return await original(request)
            except SemPermissao as exc:
                db.session.rollback()
                return _resposta_erro(exc.mensagens, 403, "somente_leitura")
            except RegraViolada as exc:
                db.session.rollback()
                return _resposta_erro(exc.mensagens, 422, "regra_violada")
            except ValorInvalido as exc:
                db.session.rollback()
                return _resposta_erro(str(exc), 400, "valor_invalido")
            except RequestValidationError as exc:
                msgs = []
                for e in exc.errors():
                    campo = ".".join(str(x) for x in e.get("loc", ())[1:]) or "corpo"
                    msgs.append(f"{campo}: {e.get('msg', 'valor inválido')}")
                return _resposta_erro(msgs or ["Requisição inválida."], 400, "parametro_invalido")
            except HTTPException as exc:
                db.session.rollback()
                if isinstance(exc.detail, dict) and "mensagens" in exc.detail:
                    return RespostaJSON(exc.detail, status_code=exc.status_code, headers=exc.headers)
                raise
            finally:
                fechar_escopo(token)

        return tratar
