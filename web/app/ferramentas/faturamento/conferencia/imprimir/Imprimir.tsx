"use client";
/* Folha da conferência para imprimir ou salvar em PDF (A4 deitado, duas empresas por linha). */
import { useEffect } from "react";
import { useSessao } from "@/components/Sessao";
import { CaixaErro, Carregando } from "@/components/ui";
import { qs } from "@/lib/api";
import { dataHora, inteiro, moeda } from "@/lib/formato";
import type { RespConferencia } from "@/lib/tipos";
import { useDados, useFiltros } from "@/lib/usar";

export function Imprimir() {
  const { usuario } = useSessao();
  const f = useFiltros();
  const conf = useDados<RespConferencia>(`/conferencia${qs({ competencia: f.get("competencia"), carteira: f.get("carteira"), vista: "todas", empresa: f.getAll("empresa") })}`);
  const d = conf.dados;
  useEffect(() => { if (d) document.title = `Conferência ${d.competencia.curta} · CONAP`; }, [d]);
  if (conf.erro) return <CaixaErro mensagens={conf.erro.mensagens} onTentar={() => void conf.recarregar()} />;
  if (!d) return <Carregando />;
  const p = d.progresso;

  return (
    <div className="folha mx-auto flex w-full max-w-[1100px] flex-col gap-4 rounded-[var(--radius-lg)] bg-[var(--surface)] p-6 text-[var(--ink)] sm:p-8 print:max-w-none print:rounded-none print:p-0">
      <style>{`@page { size: A4 landscape; margin: 12mm; }
        @media print { html, body { background: #fff !important; } .folha-cartoes { grid-template-columns: 1fr 1fr !important; gap: 10px !important; }
          .folha article { break-inside: avoid; } * { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }`}</style>
      <header className="flex flex-wrap items-start justify-between gap-5 border-b-[3px] border-[var(--brand)] pb-3">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/logo-conap.png" alt="CONAP" className="h-9 w-auto" />
        <div className="flex flex-col gap-0.5 text-right text-[13px] text-[var(--ink-3)]">
          <h1 className="mb-1 text-[22px] font-semibold text-[var(--ink)]">Conferência · {d.competencia.extenso}</h1>
          <span>Competência {d.competencia.curta} · Carteira: {d.nomeCarteira}</span>
          <span>Gerado em {dataHora(d.geradoEm)}{usuario ? ` por ${usuario.nome}` : ""}</span>
        </div>
      </header>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-6 text-[14px]">
          <span>Linhas que bateram: <strong className="tabular-nums">{inteiro(p.bateram)} de {inteiro(p.linhas)}</strong> ({p.percentual}%)</span>
          <span>Empresas 100% conferidas: <strong className="tabular-nums">{inteiro(p.empresasOk)}</strong></span>
          <span>Com linha a conferir: <strong className="tabular-nums">{inteiro(p.empresasPendentes)}</strong></span>
        </div>
        <button type="button" className="btn btn-solid nao-imprimir" onClick={() => window.print()}>Imprimir / salvar PDF</button>
      </div>

      {d.cartoes.length ? (
        <div className="folha-cartoes grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(min(500px,100%),1fr))]">
          {d.cartoes.map((c) => (
            <article key={c.empresa.id} className={`overflow-hidden rounded-xl border border-[var(--line)] border-t-[3px] ${c.tudoBateu ? "border-t-[var(--ok)]" : "border-t-[var(--warn)]"}`}>
              <header className="flex items-start justify-between gap-3 px-3.5 py-2.5">
                <h2 className="text-[15px] font-semibold">{c.empresa.nome}{c.responsavel ? <span className="block text-[12px] font-normal text-[var(--ink-3)]">{c.responsavel}</span> : null}</h2>
                <span className={`badge ${c.tudoBateu ? "badge-ok" : "badge-warn"}`}>{c.tudoBateu ? "✓ Tudo bateu" : c.faltam === 1 ? "Falta 1" : `Faltam ${c.faltam}`}</span>
              </header>
              <div className="rolagem">
                <table className="w-full border-collapse text-[12px] tabular-nums [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
                  <thead>
                    <tr className="border-b border-[var(--line)] text-[10.5px] text-[var(--ink-3)]">
                      <th className="px-1.5 py-1.5 text-left">Tipo</th><th className="px-1.5 text-right">Qtde aut.</th><th className="px-1.5 text-right">Valor aut.</th>
                      <th className="px-1.5 text-right">Canc.</th><th className="px-1.5 text-right">Valor canc.</th><th className="px-1.5 text-right">Ajuste</th><th className="px-1.5 text-right">Bateu</th>
                    </tr>
                  </thead>
                  <tbody>
                    {c.blocos.map((b) => [
                      <tr key={`s-${b.sentido}`}><td colSpan={7} className="px-1.5 pb-0 pt-2 text-[11px] font-semibold uppercase tracking-[.06em] text-[var(--ink-3)]">{b.titulo}</td></tr>,
                      ...b.linhas.map((l) => (
                        <tr key={l.id ?? l.tipo.id} className={`border-b border-[var(--line)] ${l.bateu ? "bg-[var(--ok-soft)]" : ""}`}>
                          <td className="whitespace-nowrap px-1.5 py-1">{l.tipo.nome}</td>
                          <td className="px-1.5 text-right">{inteiro(l.totalQtdeAutor)}</td>
                          <td className="px-1.5 text-right">{moeda(l.totalValorAutor)}</td>
                          <td className="px-1.5 text-right">{l.totalQtdeCanc ? inteiro(l.totalQtdeCanc) : "—"}</td>
                          <td className="px-1.5 text-right">{Number(l.totalValorCanc) ? moeda(l.totalValorCanc) : "—"}</td>
                          <td className="whitespace-nowrap px-1.5 text-right">{l.ajusteCurto}</td>
                          <td className="px-1.5 text-right">{l.bateu ? <span className="font-bold text-[var(--ok)]">✓ Sim</span> : <span className="font-semibold text-[var(--warn)]">Não</span>}</td>
                        </tr>
                      )),
                      <tr key={`sub-${b.sentido}`} className="bg-[var(--bg-soft)] font-semibold">
                        <td className="whitespace-nowrap px-1.5 py-1">Subtotal {b.nomeSubtotal}</td>
                        <td className="px-1.5 text-right">{inteiro(b.subtotal.qtdeAutor)}</td>
                        <td className="px-1.5 text-right">{moeda(b.subtotal.valorAutor)}</td>
                        <td className="px-1.5 text-right">{b.subtotal.qtdeCanc ? inteiro(b.subtotal.qtdeCanc) : "—"}</td>
                        <td className="px-1.5 text-right">{Number(b.subtotal.valorCanc) ? moeda(b.subtotal.valorCanc) : "—"}</td>
                        <td />
                        <td className="px-1.5 text-right">{b.linhas.filter((l) => l.bateu).length} de {b.linhas.length}</td>
                      </tr>,
                    ])}
                  </tbody>
                </table>
              </div>
            </article>
          ))}
        </div>
      ) : <div className="vazio">Nenhum lançamento com movimento em {d.competencia.curta} nesta carteira.</div>}

      <p className="text-[12px] text-[var(--ink-3)]">Valores do relatório da SEFAZ já com ajustes. Subtotais por sentido: entradas e saídas nunca se somam.</p>
    </div>
  );
}
