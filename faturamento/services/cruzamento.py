"""Importação dos números do mês a partir do cruzamento Domínio × SEFAZ (sistema online, no Manus).

Fluxo:

1. ``buscar(comp)`` lê o cruzamento (rota ``faturamento.resumoMensal``, só leitura, com chave).
2. ``montar_previa(...)`` compara, por empresa e tipo, três colunas: a **versão anterior** (o que veio
   do cruzamento na última importação aplicada), a **nova versão** (o que está lá agora) e o **atual aqui**
   (o lançamento). Nada é gravado.
3. ``aplicar(...)`` grava só as linhas escolhidas, como uma ``Importacao`` (aparece em Importar planilha,
   com "Desfazer"), e guarda a nova versão de cada empresa em ``FonteVersao``.

Regras:
- Empresas casadas pelo **CNPJ**. As que só existem lá são listadas, nunca criadas.
- Tipos trazidos: NF-e Entradas, NF-e Saídas e NFC-e. CT-e e NFS-e continuam manuais.
- Linha "Bateu" nunca é alterada. Carteira de outra pessoa só com "como substituto".
- Tipo sem relatório da SEFAZ importado lá para o mês: não traz nada (zero lá não é zero de verdade).
- Ajuste sugerido = notas do Domínio ausentes no relatório da SEFAZ, com motivo próprio
  (``MOTIVO_CRUZAMENTO``); reimportar troca só esse ajuste, nunca os digitados à mão.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import current_app
from sqlalchemy import select

from ..extensions import db
from ..models import (
    GRUPO_AUTOR, MOTIVO_CRUZAMENTO, Ajuste, Empresa, FonteVersao, Importacao, Lancamento, TipoDocumento,
    Usuario, agora,
)
from ..util import ValorInvalido, comp_curta, comp_iso, competencia, competencia_atual, fmt_moeda, so_digitos
from . import RegraViolada, auditoria
from .empresas import atualizar_empresa, responsavel_em
from .importacao import _json_valores, _marca, _valores_lanc
from .lancamentos import CAMPOS, limpar_sem_movimento

FONTE = "cruzamento"
NOME_FONTE = "Cruzamento Domínio × SEFAZ"
ROTA = "/api/trpc/faturamento.resumoMensal"
VERSAO_API = 1
USER_AGENT = "Mozilla/5.0 (compatible; Faturamento-CONAP)"

# tipo lá -> código do tipo de documento aqui
MAPA_TIPOS = {"NF_ENTRADA_TODAS": "NFE_ENT", "NF_SAIDA_TODAS": "NFE_SAI", "NFCE_AUTORIZADA": "NFCE"}

LIMITE_OBSERVACAO = 1500


class ErroCruzamento(RegraViolada):
    """Falha ao falar com o cruzamento (configuração, rede, chave)."""


# ====================================================================== leitura do cruzamento

def configurado() -> bool:
    cfg = current_app.config
    return bool(cfg.get("CRUZAMENTO_URL") and cfg.get("CRUZAMENTO_API_KEY"))


def _baixar(url: str, headers: dict, timeout: int) -> tuple[int, bytes]:
    """GET simples. Separado para os testes poderem trocar."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (URL vem do .env)
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read() or b""


def _mensagem_de_erro(corpo: bytes) -> str:
    try:
        dados = json.loads(corpo.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return ""
    if isinstance(dados, list):
        dados = dados[0] if dados else {}
    erro = (dados or {}).get("error") or {}
    erro = erro.get("json", erro)
    return str(erro.get("message") or "")


def buscar(comp: date, cnpj: str | None = None) -> dict:
    """Lê o cruzamento para a competência (opcionalmente uma empresa). Lança ``ErroCruzamento``."""
    if not configurado():
        raise ErroCruzamento("Cruzamento não configurado: informe CRUZAMENTO_URL e CRUZAMENTO_API_KEY no .env.")
    cfg = current_app.config
    entrada = {"competencia": comp_iso(comp)}
    if cnpj:
        entrada["cnpj"] = so_digitos(cnpj)
    url = f"{cfg['CRUZAMENTO_URL']}{ROTA}?input={urllib.parse.quote(json.dumps({'json': entrada}))}"
    # O Cloudflare do Manus barra o User-Agent padrão do Python (erro 1010 / HTTP 403).
    headers = {"Authorization": f"Bearer {cfg['CRUZAMENTO_API_KEY']}", "Accept": "application/json",
               "User-Agent": USER_AGENT}
    try:
        status, corpo = _baixar(url, headers, int(cfg.get("CRUZAMENTO_TIMEOUT", 90)))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        motivo = getattr(exc, "reason", exc)
        raise ErroCruzamento(f"Não foi possível falar com o cruzamento ({motivo}). Confira a internet e o "
                             "CRUZAMENTO_URL no .env.") from exc
    if status == 401:
        raise ErroCruzamento("O cruzamento recusou a chave: CRUZAMENTO_API_KEY precisa ser igual à "
                             "FATURAMENTO_API_KEY cadastrada no Manus.")
    if status == 404:
        raise ErroCruzamento("O cruzamento ainda não tem a rota de integração: publique a versão mais nova no Manus.")
    if status != 200:
        msg = _mensagem_de_erro(corpo) or f"resposta HTTP {status}"
        raise ErroCruzamento(f"O cruzamento respondeu com erro: {msg}")
    try:
        dados = json.loads(corpo.decode("utf-8"))["result"]["data"]["json"]
    except (ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
        raise ErroCruzamento("Resposta do cruzamento em formato inesperado.") from exc
    if dados.get("versao") != VERSAO_API:
        raise ErroCruzamento(f"Versão da integração diferente (lá {dados.get('versao')}, aqui {VERSAO_API}).")
    if dados.get("competencia") != comp_iso(comp):
        raise ErroCruzamento("O cruzamento devolveu outra competência.")
    return dados


# ====================================================================== números

def _dec(v) -> Decimal:
    try:
        return Decimal(str(v if v is not None else "0")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


@dataclass
class Numeros:
    qtde_autor: int | None
    valor_autor: Decimal | None
    qtde_canc: int | None
    valor_canc: Decimal | None
    aj_qtde: int | None = None      # None = sem informação de ajuste (Domínio não importado lá)
    aj_valor: Decimal | None = None

    def base(self) -> dict:
        return {"qtde_autor": self.qtde_autor, "valor_autor": self.valor_autor,
                "qtde_canc": self.qtde_canc, "valor_canc": self.valor_canc}

    def _comparavel(self) -> tuple:
        # Campo em branco aqui equivale a zero lá: não é diferença (ex.: canceladas nunca preenchidas).
        return (self.qtde_autor or 0, self.valor_autor or Decimal("0.00"),
                self.qtde_canc or 0, self.valor_canc or Decimal("0.00"))

    def mesma_base(self, outro: "Numeros | None") -> bool:
        return outro is not None and self._comparavel() == outro._comparavel()

    def mesmo_ajuste(self, outro: "Numeros | None") -> bool:
        if outro is None:
            return False
        if self.aj_qtde is None or outro.aj_qtde is None:
            return True  # sem informação de um dos lados: não conta como diferença
        return (self.aj_qtde, self.aj_valor) == (outro.aj_qtde, outro.aj_valor)

    def iguais(self, outro: "Numeros | None") -> bool:
        return self.mesma_base(outro) and self.mesmo_ajuste(outro)

    @property
    def zerado(self) -> bool:
        return not any([self.qtde_autor, self.valor_autor, self.qtde_canc, self.valor_canc, self.aj_qtde, self.aj_valor])


def numeros_da_fonte(tipo: dict) -> Numeros | None:
    """Entrada de um tipo como veio do cruzamento -> Numeros (None se o relatório SEFAZ não foi importado)."""
    if not tipo.get("sefazImportado"):
        return None
    aut = tipo.get("autorizadas") or {}
    can = tipo.get("canceladas") or {}
    falta = tipo.get("faltaSefaz") or {}
    com_ajuste = bool(tipo.get("dominioImportado"))
    return Numeros(
        qtde_autor=int(aut.get("qtde") or 0), valor_autor=_dec(aut.get("valor")),
        qtde_canc=int(can.get("qtde") or 0), valor_canc=_dec(can.get("valor")),
        aj_qtde=int(falta.get("qtde") or 0) if com_ajuste else None,
        aj_valor=_dec(falta.get("valor")) if com_ajuste else None,
    )


def _ajustes_cruzamento(lanc: Lancamento) -> list[Ajuste]:
    return [a for a in lanc.ajustes if a.grupo == GRUPO_AUTOR and a.motivo == MOTIVO_CRUZAMENTO]


def numeros_do_lancamento(lanc: Lancamento | None) -> Numeros | None:
    if lanc is None:
        return None
    aj = _ajustes_cruzamento(lanc)
    return Numeros(
        qtde_autor=lanc.qtde_autor, valor_autor=_dec(lanc.valor_autor) if lanc.valor_autor is not None else None,
        qtde_canc=lanc.qtde_canc, valor_canc=_dec(lanc.valor_canc) if lanc.valor_canc is not None else None,
        aj_qtde=sum(a.qtde or 0 for a in aj), aj_valor=_dec(sum((Decimal(a.valor or 0) for a in aj), Decimal(0))),
    )


def assinatura(entrada: dict) -> str:
    """Impressão digital dos números de uma empresa (ignora data de geração e lista de importações)."""
    partes = []
    for t in sorted(entrada.get("tipos", []), key=lambda t: t.get("tipo", "")):
        n = numeros_da_fonte(t)
        partes.append([t.get("tipo"), None if n is None else [
            n.qtde_autor, str(n.valor_autor), n.qtde_canc, str(n.valor_canc), n.aj_qtde,
            None if n.aj_valor is None else str(n.aj_valor)]])
    return hashlib.sha256(json.dumps(partes, sort_keys=True).encode()).hexdigest()


# ====================================================================== versões

def ultima_versao(empresa_id: int, comp: date) -> FonteVersao | None:
    """Última versão importada (aplicada e não desfeita) da empresa na competência."""
    return db.session.scalar(
        select(FonteVersao).join(Importacao, FonteVersao.importacao_id == Importacao.id)
        .where(FonteVersao.empresa_id == empresa_id, FonteVersao.competencia == comp,
               FonteVersao.fonte == FONTE, Importacao.desfeita.is_(False))
        .order_by(FonteVersao.obtida_em.desc(), FonteVersao.id.desc())
    )


def _tipos_da_versao(v: FonteVersao | None) -> dict[str, dict]:
    if v is None:
        return {}
    try:
        return {t["tipo"]: t for t in json.loads(v.dados).get("tipos", [])}
    except (ValueError, KeyError, TypeError):
        return {}


# ====================================================================== prévia

SIT_IGUAL = "igual"
SIT_NOVO = "novo"
SIT_DIFERENTE = "diferente"
SIT_MUDOU_LA = "mudou_la"
SIT_BATEU = "bateu"
SIT_SEM_DADOS = "sem_dados"
SIT_ZERO = "zero"

TEXTOS = {
    SIT_IGUAL: "Igual ao lançado aqui",
    SIT_NOVO: "Ainda não lançado aqui",
    SIT_DIFERENTE: "Diferente do lançado aqui",
    SIT_MUDOU_LA: "Mudou lá desde a última importação",
    SIT_BATEU: "Já está como “Bateu” aqui — não será alterado",
    SIT_SEM_DADOS: "Relatório da SEFAZ do mês não importado lá",
    SIT_ZERO: "Sem notas lá no mês",
}


@dataclass
class Linha:
    chave: str
    tipo: TipoDocumento
    anterior: Numeros | None
    nova: Numeros | None
    atual: Numeros | None
    situacao: str
    mudou_la: bool = False          # nova versão diferente da anterior importada
    bateu: bool = False
    notas: list[dict] = field(default_factory=list)
    notas_omitidas: int = 0

    @property
    def texto(self) -> str:
        if self.situacao == SIT_BATEU and self.mudou_la:
            return "Mudou lá; já está como “Bateu” aqui — não será alterado"
        if self.situacao == SIT_IGUAL and self.mudou_la:
            return "Mudou lá, mas já está igual aqui"
        return TEXTOS[self.situacao]

    @property
    def selecionavel(self) -> bool:
        return self.situacao in (SIT_NOVO, SIT_DIFERENTE, SIT_MUDOU_LA, SIT_ZERO)

    @property
    def marcada(self) -> bool:
        return self.situacao in (SIT_NOVO, SIT_DIFERENTE, SIT_MUDOU_LA)


@dataclass
class EmpresaPrevia:
    empresa: Empresa
    responsavel: Usuario | None
    pode_editar: bool
    linhas: list[Linha]
    entrada: dict

    @property
    def mudou_la(self) -> bool:
        return any(l.mudou_la for l in self.linhas)

    @property
    def pendentes(self) -> int:
        return sum(1 for l in self.linhas if l.marcada)


@dataclass
class Previa:
    comp: date
    obtido_em: str
    empresas: list[EmpresaPrevia]
    so_la: list[dict]                  # empresas do cruzamento sem CNPJ correspondente aqui
    sem_cnpj_aqui: list[Empresa]       # empresas daqui (no filtro) sem CNPJ: não têm como casar
    fora_do_cruzamento: list[Empresa]  # empresas daqui (no filtro), com CNPJ, que não estão lá

    @property
    def linhas(self) -> list[Linha]:
        return [l for e in self.empresas for l in e.linhas]

    def contar(self, situacao: str) -> int:
        return sum(1 for l in self.linhas if l.situacao == situacao)

    @property
    def a_importar(self) -> int:
        return sum(1 for l in self.linhas if l.marcada)

    @property
    def mudaram_la(self) -> int:
        return sum(1 for l in self.linhas if l.mudou_la)

    @property
    def mudaram_la_batidas(self) -> int:
        return sum(1 for l in self.linhas if l.mudou_la and l.bateu)


def _situacao(nova: Numeros | None, atual: Numeros | None, anterior: Numeros | None, bateu: bool) -> tuple[str, bool]:
    mudou_la = nova is not None and anterior is not None and not nova.iguais(anterior)
    if nova is None:
        return SIT_SEM_DADOS, False
    if atual is not None and nova.iguais(atual):
        return SIT_IGUAL, mudou_la
    if bateu:
        return SIT_BATEU, mudou_la
    if atual is None:
        return (SIT_ZERO if nova.zerado else SIT_NOVO), mudou_la
    return (SIT_MUDOU_LA if mudou_la else SIT_DIFERENTE), mudou_la


def montar_previa(dados: dict, comp: date, resp_id: int | None, usuario: Usuario | None,
                  empresa_id: int | None = None) -> Previa:
    """Compara o que veio do cruzamento com o que está aqui. Não grava nada."""
    tipos = {t.codigo: t for t in db.session.scalars(select(TipoDocumento))}
    por_cnpj = {so_digitos(e.get("cnpj")): e for e in dados.get("empresas", []) if so_digitos(e.get("cnpj"))}
    nossas = list(db.session.scalars(select(Empresa).where(Empresa.ativa.is_(True)).order_by(Empresa.nome)))
    if empresa_id is not None:
        nossas = [e for e in nossas if e.id == empresa_id]
    cnpjs_aqui = {e.cnpj for e in db.session.scalars(select(Empresa)) if e.cnpj}

    def no_filtro(emp: Empresa) -> bool:
        if resp_id is None:
            return True
        r = responsavel_em(emp, comp)
        return r is not None and r.id == resp_id

    empresas: list[EmpresaPrevia] = []
    sem_cnpj: list[Empresa] = []
    fora: list[Empresa] = []
    for emp in nossas:
        if not no_filtro(emp):
            continue
        if not emp.cnpj:
            sem_cnpj.append(emp)
            continue
        entrada = por_cnpj.get(emp.cnpj)
        if entrada is None:
            fora.append(emp)
            continue
        lancs = {l.tipo_id: l for l in db.session.scalars(
            select(Lancamento).where(Lancamento.empresa_id == emp.id, Lancamento.competencia == comp))}
        anteriores = _tipos_da_versao(ultima_versao(emp.id, comp))
        ids_tipos_emp = {t.id for t in emp.tipos}
        linhas: list[Linha] = []
        for t in entrada.get("tipos", []):
            tipo = tipos.get(MAPA_TIPOS.get(t.get("tipo"), ""))
            if tipo is None:
                continue
            nova = numeros_da_fonte(t)
            lanc = lancs.get(tipo.id)
            atual = numeros_do_lancamento(lanc)
            ant_t = anteriores.get(t.get("tipo"))
            anterior = numeros_da_fonte(ant_t) if ant_t else None
            # Tipo que a empresa não usa e sem nada lá nem aqui: não polui a prévia.
            if tipo.id not in ids_tipos_emp and lanc is None and (nova is None or nova.zerado):
                continue
            situacao, mudou = _situacao(nova, atual, anterior, bool(lanc and lanc.bateu))
            falta = t.get("faltaSefaz") or {}
            linhas.append(Linha(
                chave=f"{emp.id}:{tipo.codigo}", tipo=tipo, anterior=anterior, nova=nova, atual=atual,
                situacao=situacao, mudou_la=mudou, bateu=bool(lanc and lanc.bateu),
                notas=list(falta.get("notas") or []) if t.get("dominioImportado") else [],
                notas_omitidas=int(falta.get("notasOmitidas") or 0),
            ))
        linhas.sort(key=lambda l: l.tipo.ordem)
        resp = responsavel_em(emp, comp)
        empresas.append(EmpresaPrevia(empresa=emp, responsavel=resp,
                                      pode_editar=usuario is not None and resp is not None and resp.id == usuario.id,
                                      linhas=linhas, entrada=entrada))
    so_la = [] if empresa_id is not None else [
        {"razao_social": e.get("razaoSocial") or "", "nome_fantasia": e.get("nomeFantasia"), "cnpj": c}
        for c, e in sorted(por_cnpj.items(), key=lambda kv: kv[1].get("razaoSocial") or "") if c not in cnpjs_aqui
    ]
    return Previa(comp=comp, obtido_em=dados.get("geradoEm", ""), empresas=empresas, so_la=so_la,
                  sem_cnpj_aqui=sem_cnpj, fora_do_cruzamento=fora)


# ====================================================================== guarda da leitura entre as telas

def _pasta() -> Path:
    p = Path(current_app.config["DADOS_DIR"]) / "cruzamento"
    p.mkdir(parents=True, exist_ok=True)
    return p


def guardar(dados: dict) -> str:
    """Guarda a leitura para aplicar exatamente o que foi visto na prévia."""
    pasta = _pasta()
    limite = time.time() - 24 * 3600
    for velho in pasta.glob("*.json"):
        if velho.stat().st_mtime < limite:
            velho.unlink(missing_ok=True)
    token = secrets.token_urlsafe(24)
    (pasta / f"{token}.json").write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    return token


def carregar(token: str) -> dict:
    if not token or len(token) > 64 or not token.replace("-", "").replace("_", "").isalnum():
        raise ValorInvalido("Prévia inválida. Busque os números de novo.")
    arq = _pasta() / f"{token}.json"
    if not arq.exists():
        raise ValorInvalido("Prévia expirada. Busque os números de novo.")
    return json.loads(arq.read_text(encoding="utf-8"))


def descartar(token: str) -> None:
    try:
        carregar(token)
        (_pasta() / f"{token}.json").unlink(missing_ok=True)
    except (ValorInvalido, OSError):
        pass


# ====================================================================== aplicação

def _observacao(notas: list[dict], omitidas: int, imp_id: int) -> str:
    lista = ", ".join(f"{n.get('numero')}" + (f"/{n.get('serie')}" if n.get("serie") else "") for n in notas)
    txt = f"{NOME_FONTE}, importação #{imp_id}. Notas no Domínio sem par no relatório da SEFAZ: {lista or '—'}"
    if omitidas:
        txt += f" (+{omitidas} não listadas)"
    return txt if len(txt) <= LIMITE_OBSERVACAO else txt[:LIMITE_OBSERVACAO - 1] + "…"


def _aplicar_ajuste(lanc: Lancamento, linha: Linha, usuario: Usuario, imp: Importacao, rotulo: str, r: dict) -> bool:
    """Troca o ajuste do cruzamento pelo novo. Devolve True se mexeu."""
    nova = linha.nova
    existentes = _ajustes_cruzamento(lanc)
    if len(existentes) == 1 and existentes[0].qtde == nova.aj_qtde and Decimal(existentes[0].valor) == nova.aj_valor:
        return False
    if not existentes and nova.aj_qtde == 0 and nova.aj_valor == 0:
        return False
    for a in existentes:
        r["ajustes_substituidos"].append({
            "lancamento_id": lanc.id, "grupo": a.grupo, "qtde": a.qtde, "valor": str(a.valor),
            "motivo": a.motivo, "observacao": a.observacao, "criado_por_id": a.criado_por_id,
            "criado_em": a.criado_em.isoformat() if a.criado_em else None,
        })
        auditoria.registrar("fat_ajuste", "remover", usuario, registro_id=a.id, empresa_id=lanc.empresa_id,
                            antes={"grupo": a.grupo, "qtde": a.qtde, "valor": a.valor, "motivo": a.motivo},
                            descricao=f"Ajuste do cruzamento substituído em {rotulo} (importação #{imp.id})")
        lanc.ajustes.remove(a)
        r["ajustes_removidos"] += 1
    if nova.aj_qtde or nova.aj_valor:
        aj = Ajuste(lancamento=lanc, grupo=GRUPO_AUTOR, qtde=nova.aj_qtde, valor=nova.aj_valor,
                    motivo=MOTIVO_CRUZAMENTO, criado_por_id=usuario.id,
                    observacao=_observacao(linha.notas, linha.notas_omitidas, imp.id))
        db.session.add(aj)
        db.session.flush()
        r["ajustes_criados"] += 1
        r["ajustes_ids"].append(aj.id)
        auditoria.registrar("fat_ajuste", "criar", usuario, registro_id=aj.id, empresa_id=lanc.empresa_id,
                            depois={"grupo": GRUPO_AUTOR, "qtde": nova.aj_qtde, "valor": nova.aj_valor,
                                    "motivo": MOTIVO_CRUZAMENTO},
                            descricao=f"Ajuste +{nova.aj_qtde} / R$ {fmt_moeda(nova.aj_valor)} em {rotulo} "
                                      f"({NOME_FONTE}, importação #{imp.id})")
    lanc.alterado_por_id = usuario.id
    lanc.alterado_em = agora()
    return True


def aplicar(dados: dict, chaves: set[str], usuario: Usuario, *, substituto: bool = False) -> Importacao:
    """Grava as linhas escolhidas (uma transação; quem chama faz commit/rollback).

    A situação de cada linha é recalculada com o banco de agora: se alguém marcou "Bateu" entre a prévia e a
    confirmação, a linha não é alterada.
    """
    if usuario is None:
        raise RegraViolada("Usuário da sessão não identificado.")
    comp = competencia(dados.get("competencia", ""))
    if comp > competencia_atual():
        raise RegraViolada("Não é possível lançar competência futura.")
    if not chaves:
        raise RegraViolada("Marque ao menos uma linha para importar.")
    previa = montar_previa(dados, comp, None, usuario)
    escolhidas = [(e, l) for e in previa.empresas for l in e.linhas if l.chave in chaves]
    if not escolhidas:
        raise RegraViolada("Nenhuma das linhas marcadas está mais disponível. Busque os números de novo.")

    imp = Importacao(arquivo=f"{NOME_FONTE} · {comp_curta(comp)}", usuario_id=usuario.id, responsavel_id=usuario.id)
    db.session.add(imp)
    db.session.flush()
    r = {
        "fonte": FONTE, "empresas_criadas": [], "empresas_criadas_ids": [], "empresas_existentes": 0,
        "tipos_adicionados": [], "lancamentos_criados": 0, "lancamentos_alterados": 0, "sem_mudanca": 0,
        "ignorados_bateu": 0, "ignorados_outra_carteira": 0, "ajustes_criados": 0, "ajustes_removidos": 0,
        "ajustes_ids": [], "alterados": [], "ajustes_substituidos": [], "marcas": {}, "avisos": [],
    }
    avisos = r["avisos"]
    tocados: dict[int, Lancamento] = {}
    empresas_gravadas: dict[int, dict] = {}

    for ep, linha in escolhidas:
        emp, tipo = ep.empresa, linha.tipo
        rotulo = f"{emp.nome} · {comp_curta(comp)} · {tipo.nome}"
        if not linha.selecionavel:
            if linha.situacao == SIT_BATEU:
                r["ignorados_bateu"] += 1
                avisos.append({"texto": f"{rotulo}: já está como 'Bateu' — não alterado", "linha": None,
                               "destaque": True})
            else:
                r["sem_mudanca"] += 1
            continue
        if not ep.pode_editar and not substituto:
            r["ignorados_outra_carteira"] += 1
            dono = ep.responsavel.nome if ep.responsavel else "outra pessoa"
            avisos.append({"texto": f"{rotulo}: carteira de {dono} — não importado (marque “como substituto”)",
                           "linha": None, "destaque": True})
            continue
        base = linha.nova.base()
        if tipo.id not in {t.id for t in emp.tipos}:
            atualizar_empresa(emp, usuario, tipo_ids=sorted({t.id for t in emp.tipos} | {tipo.id}))
            r["tipos_adicionados"].append(f"{emp.nome}: {tipo.nome}")

        lanc = db.session.scalar(select(Lancamento).where(
            Lancamento.empresa_id == emp.id, Lancamento.competencia == comp, Lancamento.tipo_id == tipo.id))
        if lanc is None:
            resp = responsavel_em(emp, comp)
            lanc = Lancamento(empresa_id=emp.id, competencia=comp, tipo_id=tipo.id, criado_por_id=usuario.id,
                              responsavel_id=resp.id if resp else None, importacao_id=imp.id, **base)
            db.session.add(lanc)
            db.session.flush()
            r["lancamentos_criados"] += 1
            tocados[lanc.id] = lanc
            auditoria.registrar("fat_lancamento", "criar", usuario, registro_id=lanc.id, empresa_id=emp.id,
                                depois=base, descricao=f"{rotulo} ({NOME_FONTE}, importação #{imp.id})")
        elif _valores_lanc(lanc) != base:
            antes = _valores_lanc(lanc)
            for c in CAMPOS:
                setattr(lanc, c, base[c])
            lanc.alterado_por_id = usuario.id
            lanc.alterado_em = agora()
            r["lancamentos_alterados"] += 1
            r["alterados"].append({"id": lanc.id, "antes": _json_valores(antes)})
            tocados[lanc.id] = lanc
            auditoria.registrar("fat_lancamento", "alterar", usuario, registro_id=lanc.id, empresa_id=emp.id,
                                antes=antes, depois=base,
                                descricao=f"{rotulo}: números do {NOME_FONTE} (importação #{imp.id})")
        elif linha.nova.aj_qtde is None or linha.nova.mesmo_ajuste(linha.atual):
            r["sem_mudanca"] += 1

        # Ajuste sugerido: só quando o Domínio do mês foi importado lá.
        if linha.nova.aj_qtde is not None and _aplicar_ajuste(lanc, linha, usuario, imp, rotulo, r):
            tocados[lanc.id] = lanc
        if lanc.id in tocados:
            limpar_sem_movimento(emp, comp, usuario)
        empresas_gravadas[emp.id] = ep.entrada

    # Versão gravada de cada empresa que teve linha aplicada (base da comparação na próxima leitura).
    for eid, entrada in empresas_gravadas.items():
        db.session.add(FonteVersao(empresa_id=eid, competencia=comp, fonte=FONTE, usuario_id=usuario.id,
                                   importacao_id=imp.id, assinatura=assinatura(entrada),
                                   dados=json.dumps(entrada, ensure_ascii=False)))
    db.session.flush()
    r["marcas"] = {str(lid): _marca(l) for lid, l in tocados.items()}
    r["empresas_existentes"] = len(empresas_gravadas)
    r["n_avisos"] = len(avisos)
    r["n_avisos_destaque"] = sum(1 for a in avisos if a.get("destaque"))
    r["competencias"] = [comp_iso(comp), comp_iso(comp)]
    r["obtido_em"] = dados.get("geradoEm")
    r["responsavel"] = usuario.nome
    imp.resumo = json.dumps(r, ensure_ascii=False)
    auditoria.registrar("fat_importacao", "importar", usuario, registro_id=imp.id,
                        depois={k: v for k, v in r.items()
                                if k not in ("avisos", "alterados", "ajustes_ids", "ajustes_substituidos", "marcas")},
                        descricao=f"Importação #{imp.id} do {NOME_FONTE} ({comp_curta(comp)}): "
                                  f"{r['lancamentos_criados']} lançamento(s) novo(s), {r['lancamentos_alterados']} "
                                  f"alterado(s), {r['ajustes_criados']} ajuste(s), {len(empresas_gravadas)} empresa(s)")
    db.session.flush()
    return imp
