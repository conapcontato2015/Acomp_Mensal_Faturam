"""Sincronização com o Controle Fiscal (outro sistema da CONAP, no mesmo PC).

Traz de lá, SÓ LENDO o banco dele, o responsável de cada empresa e dados de cadastro:

- Empresas são casadas pelo CNPJ; depois pelo código já vinculado (``external_id = cf:<codigo>``);
  por último pelo nome (sem acento/maiúsculas) — essas aparecem na prévia como "casada pelo nome — confira".
- Responsável: mesma regra da importação por planilha (vale a partir da competência escolhida, origem
  "integração", nada muda se já for a mesma pessoa).
- CNPJ: preenchido aqui só quando está vazio; CNPJ diferente é listado, nunca sobrescrito.
- Código: vira ``external_id = cf:<codigo>`` quando vazio.
- Ativa/inativa: só listada como divergência, nunca alterada. "Sem movimento" não é importado.
- Empresas que só existem no Controle Fiscal são apenas contadas (não são criadas aqui).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select

from ..extensions import db
from ..models import ORIGEM_INTEGRACAO, Empresa, Usuario
from ..responsaveis import ProvedorControleFiscal, _achar_usuario
from ..util import ValorInvalido, competencia_padrao, normalizar_nome
from . import auditoria
from .empresas import definir_responsavel, responsavel_em

FONTE = "Controle Fiscal"
PREFIXO_ID = "cf:"


@dataclass
class RelatorioControleFiscal:
    trocas: list[str] = field(default_factory=list)
    sem_mudanca: int = 0
    cnpjs_preenchidos: list[str] = field(default_factory=list)
    codigos_vinculados: list[str] = field(default_factory=list)
    cnpj_divergente: list[str] = field(default_factory=list)
    ativa_divergente: list[str] = field(default_factory=list)
    casadas_pelo_nome: list[str] = field(default_factory=list)
    repetidas: list[str] = field(default_factory=list)
    nao_encontradas: list[str] = field(default_factory=list)
    sem_responsavel_la: list[str] = field(default_factory=list)
    responsaveis_sem_correspondencia: list[str] = field(default_factory=list)
    so_no_controle_fiscal: int = 0
    lidas: int = 0
    erros: list[str] = field(default_factory=list)

    @property
    def tem_alteracoes(self) -> bool:
        return bool(self.trocas or self.cnpjs_preenchidos or self.codigos_vinculados)

    @property
    def divergencias(self) -> int:
        return len(self.cnpj_divergente) + len(self.ativa_divergente) + len(self.casadas_pelo_nome) + len(self.repetidas)

    def como_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def provedor() -> ProvedorControleFiscal | None:
    """Provedor montado com FOLHA_DATABASE_URL / FOLHA_MAPA_RESPONSAVEIS; None se não configurado."""
    return ProvedorControleFiscal.do_config()


def sincronizar(prov: ProvedorControleFiscal, registrado_por: Usuario | None, inicio: date | None = None,
                aplicar: bool = False) -> RelatorioControleFiscal:
    """Compara o Controle Fiscal com o Faturamento. ``aplicar=False`` = prévia (nada é gravado)."""
    rel = RelatorioControleFiscal()
    inicio = inicio or competencia_padrao()
    try:
        atribs = prov.buscar()
    except ValorInvalido as exc:
        rel.erros.append(str(exc))
        return rel
    rel.lidas = len(atribs)

    empresas = list(db.session.scalars(select(Empresa).order_by(Empresa.nome)))
    por_cnpj = {e.cnpj: e for e in empresas if e.cnpj}
    por_id_externo = {e.external_id: e for e in empresas if e.external_id}
    por_nome = {normalizar_nome(e.nome): e for e in empresas}
    casadas: dict[int, str] = {}  # empresa.id -> rótulo de quem casou no Controle Fiscal

    for a in atribs:
        rotulo = a.empresa or a.cnpj or (f"código {a.codigo}" if a.codigo else "sem nome")
        if a.codigo:
            rotulo_cf = f"{rotulo} (cód. {a.codigo})"
        else:
            rotulo_cf = rotulo
        id_externo = f"{PREFIXO_ID}{a.codigo}" if a.codigo else None

        empresa, pelo_nome = None, False
        if a.cnpj:
            empresa = por_cnpj.get(a.cnpj)
        if empresa is None and id_externo:
            empresa = por_id_externo.get(id_externo)
        if empresa is None and a.empresa:
            empresa = por_nome.get(normalizar_nome(a.empresa))
            pelo_nome = empresa is not None
        if empresa is None:
            rel.so_no_controle_fiscal += 1
            continue
        if empresa.id in casadas:
            rel.repetidas.append(f"{empresa.nome}: casou com {casadas[empresa.id]} e também com {rotulo_cf} "
                                 "no Controle Fiscal — só a primeira foi usada")
            continue
        casadas[empresa.id] = rotulo_cf
        if pelo_nome:
            rel.casadas_pelo_nome.append(f"{empresa.nome} ↔ {rotulo_cf}: casada pelo nome — confira")

        # ---------------------------------------------------------------- dados de cadastro
        antes, depois = {}, {}
        if a.cnpj and len(a.cnpj) == 14:
            if not empresa.cnpj:
                outra = por_cnpj.get(a.cnpj)
                if outra is not None and outra.id != empresa.id:
                    rel.cnpj_divergente.append(
                        f"{empresa.nome}: o CNPJ do Controle Fiscal ({_fmt_cnpj(a.cnpj)}) já está em {outra.nome} aqui")
                else:
                    rel.cnpjs_preenchidos.append(f"{empresa.nome}: {_fmt_cnpj(a.cnpj)}")
                    antes["cnpj"], depois["cnpj"] = None, a.cnpj
                    por_cnpj[a.cnpj] = empresa
            elif empresa.cnpj != a.cnpj:
                rel.cnpj_divergente.append(
                    f"{empresa.nome}: aqui {empresa.cnpj_formatado}, no Controle Fiscal {_fmt_cnpj(a.cnpj)} (não alterado)")
        elif a.cnpj and empresa.cnpj and empresa.cnpj != a.cnpj:
            rel.cnpj_divergente.append(
                f"{empresa.nome}: aqui {empresa.cnpj_formatado}, no Controle Fiscal {a.cnpj} (não alterado)")

        if id_externo and not empresa.external_id:
            outra = por_id_externo.get(id_externo)
            if outra is None:
                rel.codigos_vinculados.append(f"{empresa.nome}: código {a.codigo}")
                antes["external_id"], depois["external_id"] = None, id_externo
                por_id_externo[id_externo] = empresa

        if a.ativo is False and empresa.ativa:
            rel.ativa_divergente.append(f"{empresa.nome}: inativa no Controle Fiscal e ativa aqui")
        elif a.ativo is True and not empresa.ativa:
            rel.ativa_divergente.append(f"{empresa.nome}: ativa no Controle Fiscal e inativa aqui")

        if aplicar and depois:
            if "cnpj" in depois:
                empresa.cnpj = depois["cnpj"]
            if "external_id" in depois:
                empresa.external_id = depois["external_id"]
            auditoria.registrar(
                "fat_empresa", "alterar", registrado_por, registro_id=empresa.id, empresa_id=empresa.id,
                antes=antes, depois=depois,
                descricao=f"Cadastro de {empresa.nome} completado com dados do {FONTE}",
            )
            db.session.flush()

        # ---------------------------------------------------------------- responsável
        if not (a.responsavel or "").strip():
            rel.sem_responsavel_la.append(empresa.nome)
            continue
        usuario = _achar_usuario(a.responsavel)
        if usuario is None:
            rel.responsaveis_sem_correspondencia.append(f"{a.responsavel} ({empresa.nome})")
            continue
        atual = responsavel_em(empresa, inicio)
        if atual is not None and atual.id == usuario.id:
            rel.sem_mudanca += 1
            continue
        rel.trocas.append(f"{empresa.nome}: {atual.nome if atual else '—'} → {usuario.nome}")
        if aplicar:
            definir_responsavel(empresa, usuario, inicio, registrado_por, origem=ORIGEM_INTEGRACAO, fonte=FONTE)

    for e in empresas:
        if e.id not in casadas:
            rel.nao_encontradas.append(e.nome + ("" if e.ativa else " (inativa)"))
    return rel


def _fmt_cnpj(c: str) -> str:
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}" if len(c) == 14 else c
