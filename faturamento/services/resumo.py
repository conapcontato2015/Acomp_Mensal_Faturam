"""Consultas de leitura: painel do mês, conferência (resumo) e evolução mensal.

Regra: entradas e saídas nunca se somam. Subtotais só dentro do mesmo sentido.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from ..config import config
from ..extensions import db
from ..models import ENTRADA, ORDEM_SENTIDOS, SAIDA, SENTIDOS, Empresa, Fechamento, Lancamento
from ..util import comp_rotulo, somar_meses
from .empresas import listar_empresas, responsavel_em
from .fechamento import status_mes

ZERO = Decimal("0")


@dataclass
class Bloco:
    sentido: str
    linhas: list[Lancamento] = field(default_factory=list)

    @property
    def titulo(self) -> str:
        return SENTIDOS[self.sentido][1]

    @property
    def nome_subtotal(self) -> str:
        return SENTIDOS[self.sentido][2]

    @property
    def qtde_autor(self) -> int:
        return sum(l.total_qtde_autor for l in self.linhas)

    @property
    def valor_autor(self) -> Decimal:
        return sum((l.total_valor_autor for l in self.linhas), ZERO)

    @property
    def qtde_canc(self) -> int:
        return sum(l.total_qtde_canc for l in self.linhas)

    @property
    def valor_canc(self) -> Decimal:
        return sum((l.total_valor_canc for l in self.linhas), ZERO)


@dataclass
class CartaoEmpresa:
    empresa: Empresa
    responsavel_nome: str | None
    blocos: list[Bloco]

    @property
    def linhas(self) -> list[Lancamento]:
        return [l for b in self.blocos for l in b.linhas]

    @property
    def total(self) -> int:
        return len(self.linhas)

    @property
    def n_bateu(self) -> int:
        return sum(1 for l in self.linhas if l.bateu)

    @property
    def tudo_bateu(self) -> bool:
        return self.total > 0 and self.n_bateu == self.total

    @property
    def faltam(self) -> int:
        return self.total - self.n_bateu


def _lancamentos_por_empresa(comp: date, empresa_ids: list[int]) -> dict[int, list[Lancamento]]:
    if not empresa_ids:
        return {}
    res = defaultdict(list)
    q = select(Lancamento).where(Lancamento.competencia == comp, Lancamento.empresa_id.in_(empresa_ids))
    for l in db.session.scalars(q):
        res[l.empresa_id].append(l)
    return res


def conferencia(comp: date, responsavel_id: int | None, *, sentido: str | None = None,
                situacao: str | None = None, empresa_id: int | None = None) -> list[CartaoEmpresa]:
    """Cartões por empresa para a tela de conferência.

    situacao: None/'todas' | 'pendentes' (só linhas não conferidas) | 'conferidas'.
    """
    empresas = listar_empresas(responsavel_id, comp, incluir_inativas=True)
    if empresa_id:
        empresas = [e for e in empresas if e.id == empresa_id]
    por_emp = _lancamentos_por_empresa(comp, [e.id for e in empresas])
    cartoes = []
    for e in empresas:
        lancs = [l for l in por_emp.get(e.id, []) if l.tem_movimento]
        if not lancs:
            continue
        if sentido in SENTIDOS:
            lancs = [l for l in lancs if l.tipo.sentido == sentido]
        if situacao == "pendentes":
            lancs = [l for l in lancs if not l.bateu]
        elif situacao == "conferidas":
            lancs = [l for l in lancs if l.bateu]
        if not lancs:
            continue
        lancs.sort(key=lambda l: l.tipo.ordem)
        blocos = []
        for s in ORDEM_SENTIDOS:
            ls = [l for l in lancs if l.tipo.sentido == s]
            if ls:
                blocos.append(Bloco(s, ls))
        resp = responsavel_em(e, comp)
        cartoes.append(CartaoEmpresa(e, resp.nome if resp else None, blocos))
    return cartoes


def progresso_conferencia(comp: date, responsavel_id: int | None) -> dict:
    cartoes = conferencia(comp, responsavel_id)
    total = sum(c.total for c in cartoes)
    feitos = sum(c.n_bateu for c in cartoes)
    return {
        "linhas": total, "bateram": feitos,
        "percentual": round(feitos / total * 100) if total else 0,
        "empresas_ok": sum(1 for c in cartoes if c.tudo_bateu),
        "empresas_pendentes": sum(1 for c in cartoes if not c.tudo_bateu),
    }


@dataclass
class LinhaPainel:
    empresa: Empresa
    status: str
    tipos_usados: int
    tipos_lancados: int
    entradas: Decimal | None
    saidas: Decimal | None
    linhas: int
    bateram: int
    status_anterior: str
    variacao_saidas: float | None = None
    alerta: str | None = None


def painel(comp: date, responsavel_id: int | None) -> list[LinhaPainel]:
    empresas = listar_empresas(responsavel_id, comp)
    ids = [e.id for e in empresas]
    atual = _lancamentos_por_empresa(comp, ids)
    anterior_comp = somar_meses(comp, -1)
    anterior = _lancamentos_por_empresa(anterior_comp, ids)
    marcas = {}
    if ids:
        for f in db.session.scalars(select(Fechamento).where(Fechamento.empresa_id.in_(ids), Fechamento.competencia.in_([comp, anterior_comp]))):
            marcas[(f.empresa_id, f.competencia)] = f
    historico = _saidas_por_mes(ids, somar_meses(comp, -3), somar_meses(comp, -1))
    limite = config.get("LIMITE_VARIACAO", 0.5)
    linhas = []
    for e in empresas:
        lancs = {l.tipo_id: l for l in atual.get(e.id, [])}
        com_mov = [l for l in lancs.values() if l.tem_movimento]
        st = status_mes(e, comp, lancs, marcas.get((e.id, comp)))
        st_ant = status_mes(e, anterior_comp, {l.tipo_id: l for l in anterior.get(e.id, [])}, marcas.get((e.id, anterior_comp)))
        ent = sum((l.total_valor_autor for l in com_mov if l.tipo.sentido == ENTRADA), ZERO) if com_mov else None
        sai = sum((l.total_valor_autor for l in com_mov if l.tipo.sentido == SAIDA), ZERO) if com_mov else None
        lp = LinhaPainel(
            empresa=e, status=st, tipos_usados=len(e.tipos) or len(com_mov), tipos_lancados=len(com_mov),
            entradas=ent, saidas=sai, linhas=len(com_mov), bateram=sum(1 for l in com_mov if l.bateu),
            status_anterior=st_ant,
        )
        meses = [v for v in historico.get(e.id, {}).values() if v > 0]
        if sai is not None and len(meses) >= 2:
            media = sum(meses, ZERO) / len(meses)
            if media > 0:
                var = float(sai / media - 1)
                lp.variacao_saidas = var
                if abs(var) >= limite:
                    lp.alerta = f"Saídas {'+' if var >= 0 else ''}{var * 100:.0f}% contra a média dos 3 meses anteriores"
        linhas.append(lp)
    return linhas


def _saidas_por_mes(empresa_ids: list[int], de: date, ate: date) -> dict[int, dict[date, Decimal]]:
    res: dict[int, dict[date, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    if not empresa_ids:
        return res
    q = select(Lancamento).where(Lancamento.empresa_id.in_(empresa_ids), Lancamento.competencia >= de, Lancamento.competencia <= ate)
    for l in db.session.scalars(q):
        if l.tipo.sentido == SAIDA:
            res[l.empresa_id][l.competencia] += l.total_valor_autor
    return res


def evolucao(empresa: Empresa, ate: date, meses: int = 8) -> list[dict]:
    """Série mensal de entradas e saídas autorizadas, separando a parte vinda de ajuste."""
    de = somar_meses(ate, -(meses - 1))
    serie = {somar_meses(de, i): {"E": ZERO, "E_aj": ZERO, "S": ZERO, "S_aj": ZERO} for i in range(meses)}
    q = select(Lancamento).where(Lancamento.empresa_id == empresa.id, Lancamento.competencia >= de, Lancamento.competencia <= ate)
    for l in db.session.scalars(q):
        s = l.tipo.sentido
        if s not in ("E", "S"):  # "Outros" (ex.: recebimento de caixa) não entra no gráfico
            continue
        serie[l.competencia][s] += Decimal(l.valor_autor or 0)
        serie[l.competencia][s + "_aj"] += l.ajuste_valor_autor
    return [{"competencia": c, "rotulo": comp_rotulo(c), "entradas": v["E"], "entradas_ajuste": v["E_aj"],
             "saidas": v["S"], "saidas_ajuste": v["S_aj"]} for c, v in sorted(serie.items())]
