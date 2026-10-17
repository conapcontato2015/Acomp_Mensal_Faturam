"""Cadastro de empresas vindo do Conap Ferramentas (base geral, alimentada pelos clientes da Domínio).

Hoje (``EMPRESAS_FONTE=local``) as empresas são cadastradas aqui mesmo. Quando o Faturamento entrar na
plataforma, troca-se para ``EMPRESAS_FONTE=plataforma``:

- o cadastro geral é **só lido** (``PLATAFORMA_DATABASE_URL``; sessão em modo somente leitura);
- tabela e colunas são configuráveis (``PLATAFORMA_EMPRESAS_TABELA`` e ``PLATAFORMA_EMPRESAS_COLUNAS``,
  ex.: ``nome=razao_social;cnpj=cnpj;ativa=ativo``), porque o mapeamento final ainda será definido;
- cada empresa daqui fica ligada à de lá por ``external_id = "plat:<id>"`` (depois pelo CNPJ, depois pelo
  nome — esses casos aparecem na prévia para conferir);
- nome, CNPJ e situação passam a vir de lá; aqui continuam só o que é do faturamento: tipos de
  documento usados e responsável (carteira);
- empresas novas da plataforma podem ser criadas aqui na sincronização, na carteira escolhida.

Com a fonte "plataforma" ativa, a tela de Empresas não deixa mudar nome/CNPJ/situação à mão.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import column, create_engine, select, table
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.pool import NullPool

from ..config import config
from ..extensions import db
from ..models import ORIGEM_INTEGRACAO, Empresa, Usuario
from ..util import ValorInvalido, competencia_padrao, nome_exibicao, normalizar_nome, so_digitos
from . import RegraViolada, auditoria
from .empresas import criar_empresa

PREFIXO_ID = "plat:"
CAMPOS = ("id", "nome", "cnpj", "ativa")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
TIMEOUT_CONEXAO = 5


def fonte_plataforma() -> bool:
    return config.get("EMPRESAS_FONTE", "local") == "plataforma"


def exigir_cadastro_local(campo: str = "o cadastro") -> None:
    """Bloqueia edição de nome/CNPJ/situação quando o cadastro vem da plataforma."""
    if fonte_plataforma():
        raise RegraViolada(f"Com o cadastro de empresas vindo do Conap Ferramentas, {campo} é mantido lá. "
                           "Aqui só se escolhem os tipos de documento e o responsável.")


def mapa_colunas(texto: str | None) -> dict[str, str]:
    """'nome=razao_social;ativa=ativo' -> {'id': 'id', 'nome': 'razao_social', 'cnpj': 'cnpj', 'ativa': 'ativo'}."""
    mapa = {c: c for c in CAMPOS}
    for parte in (texto or "").split(";"):
        if "=" not in parte:
            continue
        aqui, la = (x.strip() for x in parte.split("=", 1))
        if aqui in mapa and la:
            mapa[aqui] = la
    for nome in [*mapa.values()]:
        if not _IDENT.match(nome):
            raise ValorInvalido(f"Nome de coluna inválido em PLATAFORMA_EMPRESAS_COLUNAS: {nome!r}")
    return mapa


def _tabela(nome: str):
    partes = nome.split(".")
    if not 1 <= len(partes) <= 2 or not all(_IDENT.match(p) for p in partes):
        raise ValorInvalido(f"Nome de tabela inválido em PLATAFORMA_EMPRESAS_TABELA: {nome!r}")
    return partes[-1], (partes[0] if len(partes) == 2 else None)


def _engine(url_texto: str):
    try:
        url = make_url(url_texto)
    except ArgumentError as exc:
        raise ValorInvalido("PLATAFORMA_DATABASE_URL inválida.") from exc
    opcoes: dict = {"poolclass": NullPool}
    if url.get_backend_name() == "postgresql":
        opcoes["connect_args"] = {"connect_timeout": TIMEOUT_CONEXAO,
                                  "options": "-c default_transaction_read_only=on"}
    elif url.get_backend_name() == "sqlite" and url.database and url.database != ":memory:":
        url = url.set(database=f"file:{url.database}", query={"mode": "ro", "uri": "true"})
    return create_engine(url, **opcoes)


def ler_empresas(url: str | None = None, tabela: str | None = None, colunas: str | None = None) -> list[dict]:
    """Empresas do cadastro geral: [{'id': '12', 'nome': ..., 'cnpj': '14 dígitos' | None, 'ativa': bool}]."""
    url = url if url is not None else config.get("PLATAFORMA_DATABASE_URL", "")
    if not url:
        raise ValorInvalido("Cadastro do Conap Ferramentas não configurado: informe PLATAFORMA_DATABASE_URL no .env.")
    mapa = mapa_colunas(colunas if colunas is not None else config.get("PLATAFORMA_EMPRESAS_COLUNAS", ""))
    nome_tab, esquema = _tabela(tabela or config.get("PLATAFORMA_EMPRESAS_TABELA") or "empresas")
    t = table(nome_tab, *(column(c) for c in dict.fromkeys(mapa.values())), schema=esquema)
    consulta = select(*(t.c[mapa[c]].label(c) for c in CAMPOS))
    engine = _engine(url)
    try:
        with engine.connect() as conn:
            linhas = conn.execute(consulta).mappings().all()
            conn.rollback()
    except (SQLAlchemyError, ImportError) as exc:
        detalhe = str(getattr(exc, "orig", None) or exc).strip().splitlines()
        raise ValorInvalido("Não foi possível ler o cadastro de empresas do Conap Ferramentas: "
                            f"{detalhe[0] if detalhe else exc.__class__.__name__}.") from exc
    finally:
        engine.dispose()
    saida = []
    for ln in linhas:
        if ln["id"] is None or not str(ln["nome"] or "").strip():
            continue
        ativa = ln["ativa"]
        if isinstance(ativa, str):
            ativa = ativa.strip().lower() in ("1", "true", "t", "s", "sim", "ativo", "ativa", "a")
        saida.append({"id": str(ln["id"]).strip(), "nome": " ".join(str(ln["nome"]).split()),
                      "cnpj": so_digitos(ln["cnpj"]) or None, "ativa": True if ativa is None else bool(ativa)})
    return saida


@dataclass
class RelatorioPlataforma:
    vinculadas: list[str] = field(default_factory=list)      # ligadas agora (por CNPJ ou nome)
    casadas_pelo_nome: list[str] = field(default_factory=list)
    atualizadas: list[str] = field(default_factory=list)     # nome/CNPJ/situação trazidos de lá
    novas: list[str] = field(default_factory=list)           # existem lá e não aqui
    criadas: list[str] = field(default_factory=list)
    so_aqui: list[str] = field(default_factory=list)         # existem aqui e não lá
    sem_mudanca: int = 0
    lidas: int = 0
    erros: list[str] = field(default_factory=list)

    def como_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def sincronizar(registrado_por: Usuario | None, *, aplicar: bool = False, criar_novas: bool = False,
                responsavel_novas: Usuario | None = None, dados: list[dict] | None = None) -> RelatorioPlataforma:
    """Compara o cadastro geral com o daqui. ``aplicar=False`` = prévia (nada é gravado)."""
    rel = RelatorioPlataforma()
    try:
        externas = dados if dados is not None else ler_empresas()
    except ValorInvalido as exc:
        rel.erros.append(str(exc))
        return rel
    rel.lidas = len(externas)
    locais = list(db.session.scalars(select(Empresa).order_by(Empresa.nome)))
    por_ext = {e.external_id: e for e in locais if e.external_id}
    por_cnpj = {e.cnpj: e for e in locais if e.cnpj}
    por_nome = {normalizar_nome(e.nome): e for e in locais}
    usadas: set[int] = set()

    for x in externas:
        chave = PREFIXO_ID + x["id"]
        emp = por_ext.get(chave)
        como = None
        if emp is None and x["cnpj"] and x["cnpj"] in por_cnpj:
            emp, como = por_cnpj[x["cnpj"]], "cnpj"
        if emp is None and normalizar_nome(x["nome"]) in por_nome:
            emp, como = por_nome[normalizar_nome(x["nome"])], "nome"
        if emp is not None and emp.id in usadas:
            emp = None  # já casada com outra empresa de lá: trata como nova
        if emp is None:
            rel.novas.append(f"{x['nome']}" + (f" · {x['cnpj']}" if x["cnpj"] else ""))
            if aplicar and criar_novas:
                if responsavel_novas is None:
                    raise RegraViolada("Escolha o responsável pelas empresas novas.")
                nova = criar_empresa(_nome_livre(x["nome"]), responsavel_novas, registrado_por,
                                     cnpj=x["cnpj"] if x["cnpj"] not in por_cnpj else None,
                                     inicio=competencia_padrao(), origem=ORIGEM_INTEGRACAO, ativa=x["ativa"])
                nova.external_id = chave
                rel.criadas.append(nova.nome)
            continue
        usadas.add(emp.id)
        if como == "nome":
            rel.casadas_pelo_nome.append(f"{emp.nome} ↔ {x['nome']}")
        mudancas = []
        if emp.external_id != chave:
            if como:
                rel.vinculadas.append(f"{emp.nome} (pelo {'CNPJ' if como == 'cnpj' else 'nome'})")
            mudancas.append("vínculo")
        if x["cnpj"] and emp.cnpj != x["cnpj"]:
            mudancas.append("CNPJ")
        if normalizar_nome(emp.nome) != normalizar_nome(x["nome"]):
            mudancas.append("nome")
        if emp.ativa != x["ativa"]:
            mudancas.append("situação")
        if not mudancas:
            rel.sem_mudanca += 1
            continue
        if [m for m in mudancas if m != "vínculo"]:
            rel.atualizadas.append(f"{emp.nome}: {', '.join(m for m in mudancas if m != 'vínculo')}")
        if aplicar:
            antes = {"nome": emp.nome, "cnpj": emp.cnpj, "ativa": emp.ativa, "external_id": emp.external_id}
            emp.external_id = chave
            if x["cnpj"] and emp.cnpj != x["cnpj"]:
                outra = por_cnpj.get(x["cnpj"])
                if outra is None or outra.id == emp.id:
                    emp.cnpj = x["cnpj"]
            if normalizar_nome(emp.nome) != normalizar_nome(x["nome"]):
                emp.nome = _nome_livre(x["nome"], emp.id)
            emp.ativa = x["ativa"]
            auditoria.registrar("fat_empresa", "sincronizar_plataforma", registrado_por, registro_id=emp.id,
                                empresa_id=emp.id, antes=antes,
                                depois={"nome": emp.nome, "cnpj": emp.cnpj, "ativa": emp.ativa,
                                        "external_id": emp.external_id},
                                descricao=f"{emp.nome}: cadastro atualizado pelo Conap Ferramentas "
                                          f"({', '.join(mudancas)})")
    rel.so_aqui = [e.nome for e in locais if e.id not in usadas and e.ativa]
    if aplicar:
        db.session.flush()
    return rel


def _nome_livre(nome: str, empresa_id: int | None = None) -> str:
    """Nome de exibição único (o cadastro geral pode repetir razão social entre matriz e filial)."""
    base = nome_exibicao(nome)[:150]
    existentes = {normalizar_nome(e.nome): e.id for e in db.session.scalars(select(Empresa))}
    candidato, n = base, 2
    while normalizar_nome(candidato) in existentes and existentes[normalizar_nome(candidato)] != empresa_id:
        candidato = f"{base} ({n})"
        n += 1
    return candidato
