"use client";
/* Peças de tela no padrão do Conap Ferramentas: cabeçalho, KPI, métricas, seletores, estados vazios. */
import type { Competencia, Sentido, Status, Usuario } from "@/lib/tipos";
import { CLASSE_SENTIDO, CLASSE_STATUS, ROTULO_STATUS } from "@/lib/tipos";
import { Icone } from "./Icone";

export function Cabecalho({ titulo, descricao, acoes, sobre }: { titulo: React.ReactNode; descricao?: React.ReactNode; acoes?: React.ReactNode; sobre?: React.ReactNode }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {sobre ? <div className="mb-1 text-[13px] text-[var(--ink-3)]">{sobre}</div> : null}
        <h1 className="text-[26px] font-semibold leading-tight text-[var(--ink)]">{titulo}</h1>
        {descricao ? <p className="mt-1 max-w-3xl text-[14px] text-[var(--ink-2)]">{descricao}</p> : null}
      </div>
      {acoes ? <div className="flex flex-wrap items-center gap-2">{acoes}</div> : null}
    </header>
  );
}

export function BarraFiltros({ children }: { children: React.ReactNode }) {
  return <section className="card flex flex-wrap items-end gap-3 p-4" aria-label="Filtros">{children}</section>;
}

export function SeletorCompetencia({ valor, opcoes, onChange, rotulo = "Competência" }: { valor: string; opcoes: Competencia[]; onChange: (v: string) => void; rotulo?: string }) {
  return (
    <label className="campo min-w-[140px]">
      <span>{rotulo}</span>
      <select className="entrada" value={valor} onChange={(e) => onChange(e.target.value)}>
        {opcoes.map((c) => <option key={c.valor} value={c.valor}>{c.curta}</option>)}
      </select>
    </label>
  );
}

export function SeletorCarteira({ valor, usuarios, eu, onChange, rotulo = "Carteira de" }: { valor: string; usuarios: Usuario[]; eu?: Usuario | null; onChange: (v: string) => void; rotulo?: string }) {
  return (
    <label className="campo min-w-[170px]">
      <span>{rotulo}</span>
      <select className="entrada" value={valor} onChange={(e) => onChange(e.target.value)}>
        {usuarios.map((u) => <option key={u.id} value={String(u.id)}>{u.nome}{eu && u.id === eu.id ? " (minha)" : ""}</option>)}
        <option value="todos">Todos</option>
      </select>
    </label>
  );
}

export function KpiProgresso({ rotulo, valor, total, percentual, detalhe }: { rotulo: string; valor: number; total: number; percentual: number; detalhe?: React.ReactNode }) {
  return (
    <div className="card card-sheen flex flex-col gap-3 p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <span className="text-[13px] font-medium text-[var(--ink-2)]">{rotulo}</span>
        <span className="text-[13px] text-[var(--ink-3)]">{detalhe}</span>
      </div>
      <div className="flex items-baseline gap-2">
        <span className="font-display text-[40px] font-semibold leading-none tabular-nums">{percentual}%</span>
        <span className="text-[14px] text-[var(--ink-2)] tabular-nums">{valor.toLocaleString("pt-BR")} de {total.toLocaleString("pt-BR")}</span>
      </div>
      <div className="barra" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percentual} aria-label={rotulo}>
        <span style={{ width: `${percentual}%` }} />
      </div>
    </div>
  );
}

export function Metrica({ icone, rotulo, valor, tom }: { icone?: string; rotulo: string; valor: React.ReactNode; tom?: "ok" | "warn" | "danger" | "info" | "brand" }) {
  const cor = tom ? `var(--${tom})` : "var(--ink)";
  const fundo = tom ? `var(--${tom}-soft)` : "var(--bg-soft)";
  return (
    <div className="card flex items-center gap-3 p-4">
      {icone ? <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl" style={{ background: fundo, color: cor }}><Icone nome={icone} /></span> : null}
      <div className="min-w-0">
        <div className="font-display text-[20px] font-semibold leading-tight tabular-nums [overflow-wrap:anywhere] sm:text-[24px]" style={{ color: cor }}>{valor}</div>
        <div className="text-[13px] text-[var(--ink-2)]">{rotulo}</div>
      </div>
    </div>
  );
}

export function PilulaStatus({ status }: { status: Status }) {
  return <span className={`badge ${CLASSE_STATUS[status]}`}>{ROTULO_STATUS[status]}</span>;
}

export function Carregando({ texto = "Carregando…" }: { texto?: string }) {
  return <div className="vazio" aria-busy="true">{texto}</div>;
}

export function CaixaErro({ mensagens, onTentar }: { mensagens: string[]; onTentar?: () => void }) {
  return (
    <div className="aviso aviso-danger" role="alert">
      <Icone nome="alerta" className="mt-0.5 shrink-0 text-[var(--danger)]" />
      <div className="flex-1">{mensagens.map((m, i) => <p key={i}>{m}</p>)}</div>
      {onTentar ? <button className="btn btn-sm" onClick={onTentar}>Tentar de novo</button> : null}
    </div>
  );
}

export function AvisoLeitura({ dono, substituto }: { dono: string; substituto?: React.ReactNode }) {
  return (
    <div className="aviso aviso-info" role="status">
      <Icone nome="info" className="mt-0.5 shrink-0 text-[var(--info)]" />
      <div className="flex flex-1 flex-wrap items-center justify-between gap-3">
        <span>Carteira de <strong>{dono}</strong>: você está vendo, somente leitura.</span>
        {substituto}
      </div>
    </div>
  );
}

export function Grupo({ titulo, children, acoes, className = "" }: { titulo?: React.ReactNode; children: React.ReactNode; acoes?: React.ReactNode; className?: string }) {
  return (
    <section className={`card overflow-hidden ${className}`}>
      {titulo || acoes ? (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--line)] px-4 py-3">
          {titulo ? <h2 className="text-[16px] font-semibold">{titulo}</h2> : <span />}
          {acoes}
        </div>
      ) : null}
      {children}
    </section>
  );
}

/** Etiqueta de um tipo de documento, colorida pelo sentido (entrada, saída, outros). */
export function TagTipo({ t }: { t: { nome: string; sentido: Sentido } }) {
  return <span className={`badge ${CLASSE_SENTIDO[t.sentido] ?? ""}`}>{t.nome}</span>;
}

/** Lista de um relatório de prévia (trocas, divergências…). Não aparece quando está vazia. */
export function ListaRelatorio({ titulo, itens, tom, children }: { titulo: string; itens: string[]; tom?: "warn" | "danger"; children?: React.ReactNode }) {
  if (!itens.length) return null;
  const lista = (
    <div className="flex flex-col gap-1.5">
      <h3 className="text-[14px] font-semibold">{titulo} <span className="font-normal text-[var(--ink-3)]">({itens.length})</span></h3>
      <ul className={`flex list-disc flex-col gap-0.5 pl-5 text-[13.5px] ${itens.length > 12 ? "max-h-[260px] overflow-y-auto" : ""}`}>
        {itens.map((x, i) => <li key={i}>{x}</li>)}
      </ul>
      {children}
    </div>
  );
  return tom ? <div className={`aviso aviso-${tom} block`}>{lista}</div> : lista;
}
