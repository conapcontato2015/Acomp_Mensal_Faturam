"""Cadastro de tipos de documento (o que aparece em "Tipos de documento usados" e no lançamento)."""
from __future__ import annotations

import re

from sqlalchemy import func, select

from ..extensions import db
from ..models import SENTIDOS, Lancamento, TipoDocumento, Usuario, fat_empresa_tipo
from ..util import normalizar_nome
from . import RegraViolada, auditoria


def listar() -> list[TipoDocumento]:
    """Todos (ativos e inativos), na ordem de exibição."""
    return list(db.session.scalars(select(TipoDocumento).order_by(TipoDocumento.ordem, TipoDocumento.id)))


def uso(tipo: TipoDocumento) -> dict:
    """Quantas empresas usam o tipo e quantos lançamentos já existem nele."""
    empresas = db.session.scalar(select(func.count()).select_from(fat_empresa_tipo)
                                 .where(fat_empresa_tipo.c.tipo_id == tipo.id)) or 0
    lancs = db.session.scalar(select(func.count()).select_from(Lancamento).where(Lancamento.tipo_id == tipo.id)) or 0
    return {"empresas": empresas, "lancamentos": lancs}


def _nome(nome: str, tipo_id: int | None = None) -> str:
    nome = " ".join((nome or "").split())
    if not nome:
        raise RegraViolada("Informe o nome do tipo de documento.")
    if len(nome) > 60:
        raise RegraViolada("O nome do tipo pode ter até 60 caracteres.")
    alvo = normalizar_nome(nome)
    for t in db.session.scalars(select(TipoDocumento)):
        if t.id != tipo_id and normalizar_nome(t.nome) == alvo:
            raise RegraViolada(f"Já existe um tipo chamado {t.nome}.")
    return nome


def _sentido(sentido: str | None) -> str:
    if sentido not in SENTIDOS:
        raise RegraViolada("Escolha se o tipo é Entrada, Saída ou Outros.")
    return sentido


def _ordem(ordem) -> int:
    try:
        n = int(str(ordem).strip())
    except (TypeError, ValueError):
        raise RegraViolada("A ordem deve ser um número inteiro.") from None
    if not 0 <= n <= 9999:
        raise RegraViolada("A ordem deve estar entre 0 e 9999.")
    return n


def _codigo_novo(nome: str) -> str:
    base = re.sub(r"[^A-Z0-9]+", "_", normalizar_nome(nome)).strip("_")[:24] or "TIPO"
    existentes = set(db.session.scalars(select(TipoDocumento.codigo)))
    codigo, n = base, 2
    while codigo in existentes:
        codigo = f"{base}_{n}"
        n += 1
    return codigo


def criar(nome: str, sentido: str, usuario: Usuario | None, *, modelo: str | None = None,
          ordem=None) -> TipoDocumento:
    nome = _nome(nome)
    sentido = _sentido(sentido)
    if ordem in (None, ""):
        ordem = (db.session.scalar(select(func.max(TipoDocumento.ordem))) or 0) + 10
    tipo = TipoDocumento(codigo=_codigo_novo(nome), nome=nome, modelo=" ".join((modelo or nome).split())[:20],
                         sentido=sentido, ordem=_ordem(ordem), ativo=True)
    db.session.add(tipo)
    db.session.flush()
    auditoria.registrar("fat_tipo_documento", "criar", usuario, registro_id=tipo.id,
                        depois={"nome": tipo.nome, "sentido": SENTIDOS[sentido][0], "ordem": tipo.ordem},
                        descricao=f"Tipo de documento {tipo.nome} criado ({SENTIDOS[sentido][0]})")
    return tipo


def atualizar(tipo: TipoDocumento, usuario: Usuario | None, *, nome: str | None = None, sentido: str | None = None,
              modelo: str | None = None, ordem=None, ativo: bool | None = None) -> TipoDocumento:
    antes = {"nome": tipo.nome, "modelo": tipo.modelo, "sentido": SENTIDOS.get(tipo.sentido, ("?",))[0],
             "ordem": tipo.ordem, "ativo": tipo.ativo}
    if nome is not None:
        tipo.nome = _nome(nome, tipo.id)
    if modelo is not None:
        tipo.modelo = " ".join(modelo.split())[:20] or tipo.modelo
    if ordem not in (None, ""):
        tipo.ordem = _ordem(ordem)
    if ativo is not None:
        tipo.ativo = bool(ativo)
    if sentido is not None and sentido != tipo.sentido:
        sentido = _sentido(sentido)
        if uso(tipo)["lancamentos"]:
            raise RegraViolada("Este tipo já tem lançamentos: o sentido não pode mudar, para não misturar "
                               "entradas, saídas e outros nos totais. Crie um novo tipo e inative este.")
        tipo.sentido = sentido
    depois = {"nome": tipo.nome, "modelo": tipo.modelo, "sentido": SENTIDOS.get(tipo.sentido, ("?",))[0],
              "ordem": tipo.ordem, "ativo": tipo.ativo}
    if antes != depois:
        auditoria.registrar("fat_tipo_documento", "alterar", usuario, registro_id=tipo.id, antes=antes,
                            depois=depois, descricao=f"Tipo de documento {tipo.nome} alterado")
    db.session.flush()
    return tipo
