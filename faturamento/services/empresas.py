"""Cadastro de empresas e carteira (responsável)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select

from ..extensions import db
from ..models import (
    ORIGEM_MANUAL, Empresa, EmpresaResponsavel, TipoDocumento, Usuario,
)
from ..util import competencia_atual, normalizar_nome, so_digitos
from . import RegraViolada
from . import auditoria


def usuarios_ativos() -> list[Usuario]:
    return list(db.session.scalars(select(Usuario).where(Usuario.ativo.is_(True)).order_by(Usuario.nome)))


def tipos_ativos() -> list[TipoDocumento]:
    return list(db.session.scalars(select(TipoDocumento).where(TipoDocumento.ativo.is_(True)).order_by(TipoDocumento.ordem)))


def buscar_por_nome(nome: str) -> Empresa | None:
    alvo = normalizar_nome(nome)
    for e in db.session.scalars(select(Empresa)):
        if normalizar_nome(e.nome) == alvo:
            return e
    return None


def buscar_por_cnpj(cnpj: str) -> Empresa | None:
    c = so_digitos(cnpj)
    if not c:
        return None
    return db.session.scalar(select(Empresa).where(Empresa.cnpj == c))


def responsavel_atual(empresa: Empresa) -> Usuario | None:
    vinc = empresa.responsavel_em(competencia_atual()) or (empresa.historico_responsaveis[0] if empresa.historico_responsaveis else None)
    return vinc.usuario if vinc else None


def responsavel_em(empresa: Empresa, comp: date) -> Usuario | None:
    vinc = empresa.responsavel_em(comp)
    if vinc is None and empresa.historico_responsaveis:
        # Antes do primeiro vínculo registrado vale o mais antigo (carteira original).
        vinc = empresa.historico_responsaveis[-1]
    return vinc.usuario if vinc else None


def _validar_cnpj(cnpj: str | None, empresa_id: int | None = None) -> str | None:
    c = so_digitos(cnpj)
    if not c:
        return None
    if len(c) != 14:
        raise RegraViolada("CNPJ deve ter 14 dígitos.")
    outra = db.session.scalar(select(Empresa).where(Empresa.cnpj == c))
    if outra and outra.id != empresa_id:
        raise RegraViolada(f"CNPJ já cadastrado para {outra.nome}.")
    return c


def _validar_nome(nome: str, empresa_id: int | None = None) -> str:
    nome = " ".join((nome or "").split())
    if not nome:
        raise RegraViolada("Informe o nome da empresa.")
    outra = buscar_por_nome(nome)
    if outra and outra.id != empresa_id:
        raise RegraViolada(f"Já existe uma empresa chamada {outra.nome}.")
    return nome


def criar_empresa(nome: str, responsavel: Usuario, usuario: Usuario | None, *, cnpj: str | None = None,
                  tipo_ids: list[int] | None = None, inicio: date | None = None,
                  origem: str = ORIGEM_MANUAL, ativa: bool = True) -> Empresa:
    empresa = Empresa(nome=_validar_nome(nome), cnpj=_validar_cnpj(cnpj), ativa=ativa)
    if tipo_ids:
        empresa.tipos = list(db.session.scalars(select(TipoDocumento).where(TipoDocumento.id.in_(tipo_ids))))
    db.session.add(empresa)
    db.session.flush()
    db.session.add(EmpresaResponsavel(
        empresa=empresa, usuario_id=responsavel.id, inicio=inicio or date(2000, 1, 1),
        origem=origem, registrado_por_id=usuario.id if usuario else None,
    ))
    auditoria.registrar("fat_empresa", "criar", usuario, registro_id=empresa.id, empresa_id=empresa.id,
                        depois={"nome": empresa.nome, "cnpj": empresa.cnpj, "responsavel": responsavel.nome},
                        descricao=f"Empresa {empresa.nome} cadastrada")
    db.session.flush()
    return empresa


def atualizar_empresa(empresa: Empresa, usuario: Usuario | None, *, nome: str | None = None,
                      cnpj: str | None = None, ativa: bool | None = None,
                      tipo_ids: list[int] | None = None) -> Empresa:
    antes = {"nome": empresa.nome, "cnpj": empresa.cnpj, "ativa": empresa.ativa,
             "tipos": [t.nome for t in empresa.tipos]}
    if nome is not None:
        empresa.nome = _validar_nome(nome, empresa.id)
    if cnpj is not None:
        empresa.cnpj = _validar_cnpj(cnpj, empresa.id)
    if ativa is not None:
        empresa.ativa = bool(ativa)
    if tipo_ids is not None:
        empresa.tipos = list(db.session.scalars(select(TipoDocumento).where(TipoDocumento.id.in_(tipo_ids)).order_by(TipoDocumento.ordem)))
    depois = {"nome": empresa.nome, "cnpj": empresa.cnpj, "ativa": empresa.ativa,
              "tipos": [t.nome for t in empresa.tipos]}
    if antes != depois:
        auditoria.registrar("fat_empresa", "alterar", usuario, registro_id=empresa.id, empresa_id=empresa.id,
                            antes=antes, depois=depois, descricao=f"Cadastro de {empresa.nome} alterado")
    db.session.flush()
    return empresa


def definir_responsavel(empresa: Empresa, novo: Usuario, inicio: date, registrado_por: Usuario | None,
                        origem: str = ORIGEM_MANUAL) -> bool:
    """Troca a carteira a partir de ``inicio``. Retorna False se nada mudou.

    Qualquer usuário pode trocar (decisão de 11/10/2026). A troca fica no histórico.
    """
    vigente = empresa.responsavel_em(inicio)
    if vigente is not None and vigente.usuario_id == novo.id:
        return False
    mesmo_inicio = next((v for v in empresa.historico_responsaveis if v.inicio == inicio), None)
    anterior_nome = vigente.usuario.nome if vigente else None
    if mesmo_inicio is not None:
        mesmo_inicio.usuario_id = novo.id
        mesmo_inicio.origem = origem
        mesmo_inicio.registrado_por_id = registrado_por.id if registrado_por else None
    else:
        empresa.historico_responsaveis.append(EmpresaResponsavel(
            usuario_id=novo.id, inicio=inicio, origem=origem,
            registrado_por_id=registrado_por.id if registrado_por else None,
        ))
    auditoria.registrar(
        "fat_empresa_responsavel", "trocar_responsavel", registrado_por, empresa_id=empresa.id,
        antes={"responsavel": anterior_nome}, depois={"responsavel": novo.nome, "inicio": inicio, "origem": origem},
        descricao=f"Responsável de {empresa.nome}: {anterior_nome or '—'} → {novo.nome} a partir de {inicio:%m/%Y} ({origem})",
    )
    db.session.flush()
    db.session.expire(empresa, ["historico_responsaveis"])
    return True


def listar_empresas(responsavel_id: int | None = None, comp: date | None = None,
                    incluir_inativas: bool = False, busca: str | None = None) -> list[Empresa]:
    """Empresas da carteira de ``responsavel_id`` na competência (None = todas)."""
    comp = comp or competencia_atual()
    q = select(Empresa).order_by(Empresa.nome)
    if not incluir_inativas:
        q = q.where(Empresa.ativa.is_(True))
    empresas = list(db.session.scalars(q))
    if busca:
        alvo = normalizar_nome(busca)
        empresas = [e for e in empresas if alvo in normalizar_nome(e.nome) or (so_digitos(busca) and so_digitos(busca) in (e.cnpj or ""))]
    if responsavel_id is None:
        return empresas
    saida = []
    for e in empresas:
        resp = responsavel_em(e, comp)
        if resp is not None and resp.id == responsavel_id:
            saida.append(e)
    return saida
