"""Histórico de importações e o "desfazer" (hoje: cruzamento Domínio × SEFAZ).

A importação de planilha XLSX foi retirada do sistema: a carga inicial é feita fora dele. Ficam aqui só as
peças compartilhadas com o cruzamento: ler o resumo de uma importação, listá-las e desfazer uma.
``desfazer`` não destrói trabalho feito depois da importação (lançamentos conferidos ou alterados ficam).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from ..extensions import db
from ..models import Ajuste, Empresa, Fechamento, Importacao, Lancamento, Usuario, agora
from ..util import comp_curta
from . import RegraViolada, auditoria
from .lancamentos import CAMPOS


def _valores_lanc(l: Lancamento) -> dict:
    return {c: getattr(l, c) for c in CAMPOS}

def _json_valores(d: dict) -> dict:
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in d.items()}

def _marca(l: Lancamento) -> str | None:
    return l.alterado_em.isoformat() if l.alterado_em else None

def resumo(imp: Importacao) -> dict:
    try:
        return json.loads(imp.resumo or "{}")
    except ValueError:
        return {}

def listar() -> list[Importacao]:
    return list(db.session.scalars(select(Importacao).order_by(Importacao.data.desc(), Importacao.id.desc())))

def _editado_depois(l: Lancamento, imp: Importacao, marcas: dict | None) -> bool:
    """O lançamento foi mexido depois da importação (por alguém ou outra importação)?"""
    if marcas is not None and str(l.id) in marcas:
        return _marca(l) != marcas[str(l.id)]
    # Importações antigas (sem marcas no resumo): qualquer alteração bem depois da importação.
    return l.alterado_em is not None and l.alterado_em > imp.data + timedelta(seconds=5)

def desfazer(imp: Importacao, usuario: Usuario) -> dict:
    """Desfaz a importação sem destruir trabalho feito depois dela.

    - lançamentos criados por ela são apagados, exceto os conferidos ('Bateu'), os alterados depois
      da importação e os que ganharam ajustes que não vieram dela (esses ficam e são informados);
    - só os ajustes que ela criou (ids gravados no resumo) são removidos;
    - números que ela sobrescreveu voltam ao que eram, salvo se o lançamento foi alterado depois;
    - ajustes "Importado da planilha" que ela substituiu são recriados;
    - só quem fez a importação pode desfazê-la.
    """
    if imp.desfeita:
        raise RegraViolada("Esta importação já foi desfeita.")
    if usuario is None or imp.usuario_id != usuario.id:
        dono = imp.usuario.nome if imp.usuario else "outra pessoa"
        raise RegraViolada(f"Só {dono}, que fez a importação #{imp.id}, pode desfazê-la.")
    r = resumo(imp)
    marcas = r.get("marcas")
    ids_ajustes = set(r.get("ajustes_ids", []))
    out = {"removidos": 0, "mantidos_bateu": 0, "mantidos_editados": 0, "restaurados": 0,
           "ajustes_removidos": 0, "ajustes_recriados": 0, "empresas_removidas": 0, "editados": []}
    preservados: set[int] = set()

    def rot(l: Lancamento) -> str:
        return f"{l.empresa.nome} · {comp_curta(l.competencia)} · {l.tipo.nome}"

    def preservar(l: Lancamento) -> None:
        if l.id not in preservados:
            preservados.add(l.id)
            out["mantidos_editados"] += 1
            out["editados"].append(rot(l))

    for l in list(db.session.scalars(select(Lancamento).where(Lancamento.importacao_id == imp.id))):
        if l.bateu:
            out["mantidos_bateu"] += 1
            preservados.add(l.id)
            continue
        if _editado_depois(l, imp, marcas) or any(a.id not in ids_ajustes for a in l.ajustes):
            preservar(l)
            continue
        auditoria.registrar("fat_lancamento", "remover", usuario, registro_id=l.id, empresa_id=l.empresa_id,
                            antes=_valores_lanc(l), descricao=f"{rot(l)}: removido ao desfazer a importação #{imp.id}")
        db.session.delete(l)
        out["removidos"] += 1
    db.session.flush()

    # lançamentos que já existiam e foram alterados/ajustados pela importação
    pre_existentes: dict[int, Lancamento] = {}
    for lid in {a["id"] for a in r.get("alterados", [])} | {a["lancamento_id"] for a in r.get("ajustes_substituidos", [])}:
        l = db.session.get(Lancamento, lid)
        if l is not None:
            pre_existentes[lid] = l
    for aid in ids_ajustes:
        aj = db.session.get(Ajuste, aid)
        if aj is not None:
            pre_existentes.setdefault(aj.lancamento_id, aj.lancamento)
    intocaveis: set[int] = set()
    for lid, l in pre_existentes.items():
        if lid in preservados or l.bateu:
            intocaveis.add(lid)
        elif _editado_depois(l, imp, marcas):
            preservar(l)
            intocaveis.add(lid)

    for aid in sorted(ids_ajustes):
        aj = db.session.get(Ajuste, aid)
        if aj is None or aj.lancamento_id in intocaveis:
            continue
        lanc = aj.lancamento
        auditoria.registrar("fat_ajuste", "remover", usuario, registro_id=aj.id, empresa_id=lanc.empresa_id,
                            antes={"grupo": aj.grupo, "qtde": aj.qtde, "valor": aj.valor, "motivo": aj.motivo},
                            descricao=f"Ajuste removido ao desfazer a importação #{imp.id}")
        lanc.ajustes.remove(aj)
        out["ajustes_removidos"] += 1

    for alt in r.get("alterados", []):
        l = pre_existentes.get(alt["id"])
        if l is None or alt["id"] in intocaveis:
            continue
        antes = {c: (Decimal(v) if v is not None and c.startswith("valor") else v) for c, v in alt["antes"].items()}
        atual = _valores_lanc(l)
        for c in CAMPOS:
            setattr(l, c, antes.get(c))
        l.alterado_por_id = usuario.id
        l.alterado_em = agora()
        auditoria.registrar("fat_lancamento", "alterar", usuario, registro_id=l.id, empresa_id=l.empresa_id,
                            antes=atual, depois=antes,
                            descricao=f"{rot(l)}: números anteriores restaurados ao desfazer a importação #{imp.id}")
        out["restaurados"] += 1

    for sub in r.get("ajustes_substituidos", []):
        l = pre_existentes.get(sub["lancamento_id"])
        if l is None or sub["lancamento_id"] in intocaveis:
            continue
        aj = Ajuste(lancamento=l, grupo=sub["grupo"], qtde=sub["qtde"], valor=Decimal(sub["valor"]),
                    motivo=sub["motivo"], observacao=sub.get("observacao"), criado_por_id=sub.get("criado_por_id"))
        if sub.get("criado_em"):
            aj.criado_em = datetime.fromisoformat(sub["criado_em"])
        db.session.add(aj)
        db.session.flush()
        l.alterado_por_id = usuario.id
        l.alterado_em = agora()
        auditoria.registrar("fat_ajuste", "criar", usuario, registro_id=aj.id, empresa_id=l.empresa_id,
                            depois={"grupo": aj.grupo, "qtde": aj.qtde, "valor": aj.valor, "motivo": aj.motivo},
                            descricao=f"{rot(l)}: ajuste importado anterior recriado ao desfazer a importação #{imp.id}")
        out["ajustes_recriados"] += 1
    db.session.flush()

    for eid in r.get("empresas_criadas_ids", []):
        emp = db.session.get(Empresa, eid)
        if emp is None:
            continue
        resta = db.session.scalar(select(Lancamento.id).where(Lancamento.empresa_id == eid).limit(1))
        if resta is not None:
            continue
        for f in db.session.scalars(select(Fechamento).where(Fechamento.empresa_id == eid)):
            db.session.delete(f)
        auditoria.registrar("fat_empresa", "remover", usuario, registro_id=eid, empresa_id=eid,
                            antes={"nome": emp.nome}, descricao=f"Empresa {emp.nome} removida ao desfazer a importação #{imp.id}")
        db.session.delete(emp)
        out["empresas_removidas"] += 1

    imp.desfeita = True
    auditoria.registrar("fat_importacao", "desfazer", usuario, registro_id=imp.id,
                        depois={k: v for k, v in out.items() if k != "editados"},
                        descricao=f"Importação #{imp.id} ({imp.arquivo}) desfeita: {out['removidos']} lançamento(s) "
                                  f"removido(s), {out['restaurados']} restaurado(s), {out['mantidos_bateu']} mantido(s) por "
                                  f"já estarem conferidos, {out['mantidos_editados']} mantido(s) por terem sido "
                                  "alterados depois da importação")
    db.session.flush()
    return out
