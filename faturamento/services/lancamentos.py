"""Lançamento mensal: números do relatório da SEFAZ, ajustes e marcação de "bateu"."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from ..extensions import db
from ..models import (
    GRUPO_AUTOR, GRUPO_CANC, MOTIVO_PADRAO_AJUSTE, STATUS_SEM_MOVIMENTO, Ajuste, Empresa,
    Fechamento, Lancamento, TipoDocumento, Usuario, agora,
)
from ..util import ValorInvalido, competencia_atual, comp_curta, fmt_moeda, parse_decimal, parse_inteiro
from . import RegraViolada, SemPermissao, auditoria
from .empresas import responsavel_em

CAMPOS = ("qtde_autor", "valor_autor", "qtde_canc", "valor_canc")


# ---------------------------------------------------------------- permissões

def pode_editar(usuario: Usuario | None, empresa: Empresa, comp: date) -> bool:
    if usuario is None:
        return False
    resp = responsavel_em(empresa, comp)
    return resp is not None and resp.id == usuario.id


def exigir_edicao(usuario: Usuario | None, empresa: Empresa, comp: date, substituto: bool = False) -> None:
    if usuario is None:
        raise SemPermissao("Usuário da sessão não identificado.")
    if substituto or pode_editar(usuario, empresa, comp):
        return
    resp = responsavel_em(empresa, comp)
    raise SemPermissao(
        f"{empresa.nome} é da carteira de {resp.nome if resp else 'outra pessoa'} em {comp_curta(comp)}. "
        "Visualização somente leitura — marque 'Lançar como substituto' se estiver cobrindo."
    )


# ---------------------------------------------------------------- leitura

def buscar(empresa_id: int, comp: date, tipo_id: int) -> Lancamento | None:
    return db.session.scalar(select(Lancamento).where(
        Lancamento.empresa_id == empresa_id, Lancamento.competencia == comp, Lancamento.tipo_id == tipo_id))


def lancamentos_do_mes(empresa: Empresa, comp: date) -> dict[int, Lancamento]:
    lancs = db.session.scalars(select(Lancamento).where(
        Lancamento.empresa_id == empresa.id, Lancamento.competencia == comp))
    return {l.tipo_id: l for l in lancs}


def tipos_do_mes(empresa: Empresa, comp: date, lancs: dict[int, Lancamento] | None = None) -> list[TipoDocumento]:
    """Tipos que a empresa usa + qualquer tipo que já tenha lançamento no mês."""
    lancs = lancs if lancs is not None else lancamentos_do_mes(empresa, comp)
    tipos = {t.id: t for t in empresa.tipos}
    for l in lancs.values():
        tipos.setdefault(l.tipo_id, l.tipo)
    return sorted(tipos.values(), key=lambda t: (t.sentido != "E", t.ordem))


@dataclass
class LinhaMes:
    tipo: TipoDocumento
    lancamento: Lancamento | None

    def __getattr__(self, nome):
        if nome in CAMPOS or nome.startswith(("total_", "ajuste_")) or nome in ("bateu", "ajustes", "tem_ajuste", "tem_movimento", "id"):
            l = self.__dict__.get("lancamento")
            if l is None:
                return [] if nome == "ajustes" else (False if nome in ("bateu", "tem_ajuste", "tem_movimento") else None)
            return getattr(l, nome)
        raise AttributeError(nome)


def carregar_mes(empresa: Empresa, comp: date) -> list[LinhaMes]:
    lancs = lancamentos_do_mes(empresa, comp)
    return [LinhaMes(t, lancs.get(t.id)) for t in tipos_do_mes(empresa, comp, lancs)]


# ---------------------------------------------------------------- gravação

@dataclass
class ResultadoGravacao:
    alterados: int = 0
    avisos: list[str] = field(default_factory=list)


def _normalizar_linha(bruta: dict, nome_tipo: str) -> tuple[dict, list[str]]:
    erros = []
    valores = {}
    for campo in CAMPOS:
        try:
            if campo.startswith("qtde"):
                v = parse_inteiro(bruta.get(campo))
            else:
                v = parse_decimal(bruta.get(campo))
        except ValorInvalido:
            erros.append(f"{nome_tipo}: '{bruta.get(campo)}' não é um número válido. Para corrigir uma diferença, use um ajuste.")
            v = None
        if v is not None and v < 0:
            erros.append(f"{nome_tipo}: números do relatório não podem ser negativos (use um ajuste negativo).")
        valores[campo] = v
    if (valores["qtde_autor"] is None) != (valores["valor_autor"] is None):
        erros.append(f"{nome_tipo} autorizadas: informe quantidade e valor juntos.")
    if (valores["qtde_canc"] is None) != (valores["valor_canc"] is None):
        erros.append(f"{nome_tipo} canceladas: informe quantidade e valor juntos.")
    return valores, erros


def salvar_mes(empresa: Empresa, comp: date, linhas: list[dict], usuario: Usuario, *,
               substituto: bool = False, importacao_id: int | None = None) -> ResultadoGravacao:
    """Grava as linhas do mês (upsert). ``linhas``: [{tipo_id, qtde_autor, valor_autor, qtde_canc, valor_canc}].

    Tudo ou nada: com qualquer erro, nada é gravado.
    """
    exigir_edicao(usuario, empresa, comp, substituto)
    if comp > competencia_atual():
        raise RegraViolada("Não é possível lançar competência futura.")

    lancs = lancamentos_do_mes(empresa, comp)
    tipos = {t.id: t for t in db.session.scalars(select(TipoDocumento))}
    erros: list[str] = []
    preparadas = []
    for bruta in linhas:
        try:
            tipo_id = int(bruta.get("tipo_id"))
        except (TypeError, ValueError):
            erros.append("Linha sem tipo de documento.")
            continue
        tipo = tipos.get(tipo_id)
        if tipo is None:
            erros.append(f"Tipo de documento {tipo_id} inexistente.")
            continue
        valores, e = _normalizar_linha(bruta, tipo.nome)
        erros.extend(e)
        preparadas.append((tipo, valores))
    if erros:
        raise RegraViolada(erros)

    resultado = ResultadoGravacao()
    resp = responsavel_em(empresa, comp)
    for tipo, valores in preparadas:
        lanc = lancs.get(tipo.id)
        if lanc is None:
            if all(v is None for v in valores.values()):
                continue
            lanc = Lancamento(empresa_id=empresa.id, competencia=comp, tipo_id=tipo.id,
                              criado_por_id=usuario.id, responsavel_id=resp.id if resp else None,
                              importacao_id=importacao_id)
            db.session.add(lanc)
            antes = None
        else:
            antes = {c: getattr(lanc, c) for c in CAMPOS}
            novos = {c: valores[c] for c in CAMPOS}
            if _iguais(antes, novos):
                continue
            if lanc.bateu:
                raise RegraViolada(f"{tipo.nome} está marcado como 'Bateu'. Desmarque antes de alterar os números.")
        for c in CAMPOS:
            setattr(lanc, c, valores[c])
        lanc.alterado_por_id = usuario.id
        lanc.alterado_em = agora()
        if lanc.qtde_canc and lanc.qtde_autor is not None and lanc.qtde_canc > lanc.qtde_autor:
            resultado.avisos.append(f"{tipo.nome}: mais canceladas que autorizadas (pode ser cancelamento de nota do mês anterior).")
        resultado.alterados += 1
        db.session.flush()
        auditoria.registrar("fat_lancamento", "criar" if antes is None else "alterar", usuario,
                            registro_id=lanc.id, empresa_id=empresa.id, antes=antes,
                            depois={c: valores[c] for c in CAMPOS},
                            descricao=f"{empresa.nome} · {comp_curta(comp)} · {tipo.nome}")
    if resultado.alterados:
        _limpar_sem_movimento(empresa, comp, usuario)
    db.session.flush()
    return resultado


def _iguais(a: dict, b: dict) -> bool:
    for c in CAMPOS:
        x, y = a.get(c), b.get(c)
        if x is None or y is None:
            if x is not y:
                return False
        elif Decimal(x) != Decimal(y):
            return False
    return True


def _limpar_sem_movimento(empresa: Empresa, comp: date, usuario: Usuario) -> None:
    f = db.session.scalar(select(Fechamento).where(Fechamento.empresa_id == empresa.id, Fechamento.competencia == comp))
    if f is not None and f.status == STATUS_SEM_MOVIMENTO:
        db.session.delete(f)
        auditoria.registrar("fat_fechamento", "desmarcar_sem_movimento", usuario, empresa_id=empresa.id,
                            descricao=f"{empresa.nome} · {comp_curta(comp)}: deixou de ser 'sem movimento' (houve lançamento)")


# ---------------------------------------------------------------- ajustes

def obter_ou_criar(empresa: Empresa, comp: date, tipo: TipoDocumento, usuario: Usuario) -> Lancamento:
    lanc = buscar(empresa.id, comp, tipo.id)
    if lanc is None:
        resp = responsavel_em(empresa, comp)
        lanc = Lancamento(empresa_id=empresa.id, competencia=comp, tipo_id=tipo.id,
                          criado_por_id=usuario.id, responsavel_id=resp.id if resp else None)
        db.session.add(lanc)
        db.session.flush()
    return lanc


def adicionar_ajuste(lanc: Lancamento, grupo: str, qtde, valor, usuario: Usuario, *,
                     motivo: str | None = None, observacao: str | None = None,
                     substituto: bool = False, verificar_permissao: bool = True) -> Ajuste:
    if verificar_permissao:
        exigir_edicao(usuario, lanc.empresa, lanc.competencia, substituto)
    grupo = (grupo or "").upper()
    if grupo not in (GRUPO_AUTOR, GRUPO_CANC):
        raise RegraViolada("Grupo do ajuste deve ser AUTOR (autorizadas) ou CANC (canceladas).")
    if lanc.bateu:
        raise RegraViolada(f"{lanc.tipo.nome} está marcado como 'Bateu'. Desmarque antes de ajustar.")
    try:
        q = parse_inteiro(qtde)
        v = parse_decimal(valor)
    except ValorInvalido as exc:
        raise RegraViolada(str(exc)) from exc
    if q is None or v is None:
        raise RegraViolada("Informe quantidade e valor do ajuste.")
    if q == 0 and v == 0:
        raise RegraViolada("Ajuste zerado não tem efeito.")
    motivo = (motivo or "").strip() or MOTIVO_PADRAO_AJUSTE
    observacao = (observacao or "").strip() or None
    if motivo.lower().startswith("outro") and not observacao:
        raise RegraViolada("Para o motivo 'Outro', descreva na observação.")
    aj = Ajuste(lancamento=lanc, grupo=grupo, qtde=q, valor=v, motivo=motivo[:160], observacao=observacao,
                criado_por_id=usuario.id)
    db.session.add(aj)
    lanc.alterado_por_id = usuario.id
    lanc.alterado_em = agora()
    db.session.flush()
    _limpar_sem_movimento(lanc.empresa, lanc.competencia, usuario)
    auditoria.registrar("fat_ajuste", "criar", usuario, registro_id=aj.id, empresa_id=lanc.empresa_id,
                        depois={"grupo": grupo, "qtde": q, "valor": v, "motivo": motivo, "observacao": observacao},
                        descricao=f"Ajuste {'+' if q >= 0 else ''}{q} / R$ {fmt_moeda(v)} em {lanc.empresa.nome} · "
                                  f"{comp_curta(lanc.competencia)} · {lanc.tipo.nome}")
    return aj


def remover_ajuste(aj: Ajuste, usuario: Usuario, substituto: bool = False) -> None:
    lanc = aj.lancamento
    exigir_edicao(usuario, lanc.empresa, lanc.competencia, substituto)
    if lanc.bateu:
        raise RegraViolada(f"{lanc.tipo.nome} está marcado como 'Bateu'. Desmarque antes de remover ajustes.")
    auditoria.registrar("fat_ajuste", "remover", usuario, registro_id=aj.id, empresa_id=lanc.empresa_id,
                        antes={"grupo": aj.grupo, "qtde": aj.qtde, "valor": aj.valor, "motivo": aj.motivo},
                        descricao=f"Ajuste removido de {lanc.empresa.nome} · {comp_curta(lanc.competencia)} · {lanc.tipo.nome}")
    lanc.ajustes.remove(aj)
    db.session.flush()


# ---------------------------------------------------------------- conferência

def marcar_bateu(lanc: Lancamento, valor: bool, usuario: Usuario, substituto: bool = False) -> Lancamento:
    exigir_edicao(usuario, lanc.empresa, lanc.competencia, substituto)
    valor = bool(valor)
    if lanc.bateu == valor:
        return lanc
    lanc.bateu = valor
    lanc.bateu_por_id = usuario.id if valor else None
    lanc.bateu_em = agora() if valor else None
    auditoria.registrar("fat_lancamento", "bateu" if valor else "desmarcar_bateu", usuario,
                        registro_id=lanc.id, empresa_id=lanc.empresa_id,
                        descricao=f"{lanc.empresa.nome} · {comp_curta(lanc.competencia)} · {lanc.tipo.nome}: "
                                  + ("bateu" if valor else "voltou para 'a conferir'"))
    db.session.flush()
    return lanc


def marcar_bateu_empresa(empresa: Empresa, comp: date, valor: bool, usuario: Usuario, substituto: bool = False) -> int:
    exigir_edicao(usuario, empresa, comp, substituto)
    n = 0
    for lanc in lancamentos_do_mes(empresa, comp).values():
        if lanc.tem_movimento and lanc.bateu != bool(valor):
            marcar_bateu(lanc, valor, usuario, substituto=True)
            n += 1
    return n
