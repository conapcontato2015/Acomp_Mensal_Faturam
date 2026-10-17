"use client";
/* Conferência: relatório SEFAZ (com ajustes) × sistema contábil. Um cartão por empresa; clique no selo
   quando a linha bater. Marca na hora e desfaz se o servidor recusar. */
import Link from "next/link";
import { useState } from "react";
import { useAviso } from "@/components/Avisos";
import { Icone } from "@/components/Icone";
import { SeletorEmpresas } from "@/components/SeletorEmpresas";
import { useSessao } from "@/components/Sessao";
import { AvisoLeitura, BarraFiltros, Cabecalho, CaixaErro, Carregando, KpiProgresso, Metrica, SeletorCarteira, SeletorCompetencia } from "@/components/ui";
import { api, ErroApi, qs, urlApi } from "@/lib/api";
import { confete } from "@/lib/confete";
import { inteiro, moeda } from "@/lib/formato";
import type { CartaoConferencia, Linha, ProgressoConferencia, Referencias, RespConferencia, Usuario } from "@/lib/tipos";
import { rota, useDados, useFiltros } from "@/lib/usar";

const VISTAS = [{ chave: "todas", rotulo: "Todas as empresas" }, { chave: "pendencia", rotulo: "Só com pendência" }] as const;

export function Conferencia() {
  const { usuario } = useSessao();
  const f = useFiltros();
  const competencia = f.get("competencia"), carteira = f.get("carteira"), vista = f.get("vista") || "todas";
  const empresas = f.getAll("empresa");
  const ref = useDados<Referencias>(`/referencias${qs({ competencia })}`);
  const conf = useDados<RespConferencia>(`/conferencia${qs({ competencia, carteira, vista, empresa: empresas })}`);
  const d = conf.dados;
  const params = d ? { competencia: d.competencia.valor, carteira: d.carteira, empresa: d.escolhidas } : {};

  return (
    <>
      <Cabecalho titulo={d ? `Conferência · ${d.competencia.extenso}` : "Conferência"}
                 descricao="Relatório SEFAZ (com ajustes) × sistema contábil. Clique no círculo quando a linha bater."
                 acoes={d ? <>
                   <a className="btn" href={urlApi(`/conferencia/excel${qs(params)}`)}><Icone nome="excel" /> Excel</a>
                   <a className="btn" target="_blank" rel="noopener" href={rota("conferencia/imprimir", params)}><Icone nome="imprimir" /> PDF</a>
                 </> : null} />

      {conf.erro ? <CaixaErro mensagens={conf.erro.mensagens} onTentar={() => void conf.recarregar()} /> : null}
      {!d && conf.carregando ? <Carregando /> : null}
      {d && ref.dados ? (
        <Corpo key={`${d.competencia.valor}|${d.carteira}|${d.vista}|${d.escolhidas.join(",")}|${d.geradoEm}`} d={d} refs={ref.dados}
               eu={usuario} filtros={f} />
      ) : null}
    </>
  );
}

function recontar(c: CartaoConferencia): CartaoConferencia {
  const linhas = c.blocos.flatMap((b) => b.linhas);
  const bateram = linhas.filter((l) => l.bateu).length;
  return { ...c, total: linhas.length, bateram, faltam: linhas.length - bateram, tudoBateu: linhas.length > 0 && bateram === linhas.length };
}

function ajustarResumo(p: ProgressoConferencia, antes: CartaoConferencia, depois: CartaoConferencia): ProgressoConferencia {
  const bateram = p.bateram + (depois.bateram - antes.bateram);
  let { empresasOk, empresasPendentes } = p;
  if (antes.tudoBateu !== depois.tudoBateu) {
    empresasOk += depois.tudoBateu ? 1 : -1;
    empresasPendentes += depois.tudoBateu ? -1 : 1;
  }
  return { ...p, bateram, empresasOk, empresasPendentes, percentual: p.linhas ? Math.round((bateram / p.linhas) * 100) : 0 };
}

function Corpo({ d, refs, eu, filtros: f }: { d: RespConferencia; refs: Referencias; eu: Usuario | null; filtros: ReturnType<typeof useFiltros> }) {
  const avisar = useAviso();
  const [cartoes, setCartoes] = useState(d.cartoes);
  const [prog, setProg] = useState<ProgressoConferencia>(d.progresso);
  const [ocupados, setOcupados] = useState<Set<number>>(new Set());
  const comp = d.competencia.valor;

  // Troca o estado das linhas de um cartão e atualiza o resumo do topo pela diferença.
  const aplicar = (c: CartaoConferencia, novo: (l: Linha) => boolean): CartaoConferencia => {
    const depois = recontar({ ...c, blocos: c.blocos.map((b) => ({ ...b, linhas: b.linhas.map((l) => ({ ...l, bateu: novo(l) })) })) });
    setCartoes((cs) => cs.map((x) => (x.empresa.id === c.empresa.id ? depois : x)));
    setProg((p) => ajustarResumo(p, c, depois));
    return depois;
  };

  const mudar = async (c: CartaoConferencia, novo: (l: Linha) => boolean, chamada: () => Promise<unknown>, alvo: Element | null) => {
    if (ocupados.has(c.empresa.id)) return;
    setOcupados((o) => new Set(o).add(c.empresa.id));
    const depois = aplicar(c, novo);
    try {
      await chamada();
      if (!c.tudoBateu && depois.tudoBateu) confete(alvo); // parabéns: a empresa fechou
    } catch (e) {
      aplicar(depois, (l) => c.blocos.flatMap((b) => b.linhas).find((x) => x.id === l.id)?.bateu ?? l.bateu);
      avisar(e instanceof ErroApi ? e.mensagens.join(" ") : "Não foi possível salvar a conferência.", "erro");
    } finally {
      setOcupados((o) => { const n = new Set(o); n.delete(c.empresa.id); return n; });
    }
  };

  const selo = (c: CartaoConferencia, l: Linha, alvo: Element) =>
    void mudar(c, (x) => (x.id === l.id ? !l.bateu : x.bateu), () => api(`/lancamentos/${l.id}/bateu`, "PUT", { bateu: !l.bateu }), alvo);
  const todas = (c: CartaoConferencia, alvo: Element) => {
    const novo = !c.tudoBateu;
    void mudar(c, () => novo, () => api(`/conferencia/${c.empresa.id}/${comp}/bateu`, "PUT", { bateu: novo }), alvo);
  };

  const nomes = new Map(d.opcoes.map((o) => [o.id, o.nome]));
  const todosCarteira = d.carteira === "todos";

  return (
    <>
      {d.somenteLeitura ? <AvisoLeitura dono={todosCarteira ? "todas as pessoas" : d.nomeCarteira} /> : null}

      <div className="grid gap-4 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]">
        <KpiProgresso rotulo="Linhas que bateram" valor={prog.bateram} total={prog.linhas} percentual={prog.percentual} />
        <Metrica icone="ok" rotulo="Empresas 100% conferidas" valor={inteiro(prog.empresasOk)} tom="ok" />
        <Metrica icone="alerta" rotulo="Empresas com linha a conferir" valor={inteiro(prog.empresasPendentes)} tom={prog.empresasPendentes ? "warn" : undefined} />
      </div>

      <BarraFiltros>
        <SeletorCarteira rotulo="Carteira" valor={d.carteira} usuarios={refs.usuarios} eu={eu} onChange={(v) => f.set({ carteira: v, empresa: null })} />
        <SeletorCompetencia valor={comp} opcoes={refs.competencias} onChange={(v) => f.set({ competencia: v })} />
        {d.opcoes.length ? <SeletorEmpresas opcoes={d.opcoes} escolhidas={d.escolhidas} aoAplicar={(ids) => f.set({ empresa: ids })} /> : null}
        <div className="ml-auto flex flex-wrap gap-2" role="group" aria-label="Mostrar">
          {VISTAS.map((v) => (
            <button key={v.chave} type="button" className="chip" aria-pressed={d.vista === v.chave} onClick={() => f.set({ vista: v.chave === "todas" ? null : v.chave })}>{v.rotulo}</button>
          ))}
        </div>
      </BarraFiltros>

      {d.escolhidas.length ? (
        <div className="flex flex-wrap items-center gap-2" aria-label="Empresas exibidas">
          <span className="text-[13px] text-[var(--ink-3)]">Exibindo:</span>
          {d.escolhidas.map((id) => (
            <button key={id} type="button" className="chip" title={`Tirar ${nomes.get(id)}`} onClick={() => f.set({ empresa: d.escolhidas.filter((x) => x !== id) })}>
              {nomes.get(id)} <Icone nome="fechar" tamanho={14} /><span className="sr-only">(remover)</span>
            </button>
          ))}
          <button type="button" className="btn btn-quiet btn-sm" onClick={() => f.set({ empresa: null })}>Mostrar todas</button>
        </div>
      ) : null}

      {cartoes.length ? (
        <>
          <div className="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(min(440px,100%),1fr))]">
            {cartoes.map((c) => (
              <Cartao key={c.empresa.id} c={c} mostrarResp={todosCarteira} ocupado={ocupados.has(c.empresa.id)} competencia={comp}
                      aoSelo={(l, alvo) => selo(c, l, alvo)} aoTodas={(alvo) => todas(c, alvo)} />
            ))}
          </div>
          <p className="text-[13px] text-[var(--ink-3)]">
            Valores já incluem ajustes. Em &quot;Ver detalhes&quot;: cancelados, ajustes e subtotais por sentido (entradas e saídas nunca se somam).
          </p>
        </>
      ) : d.haLancamentos ? (
        <div className="card vazio">
          Todas as linhas de {d.competencia.curta} já foram conferidas nesta carteira.{" "}
          <button type="button" className="underline" onClick={() => f.set({ vista: null })}>Ver todas as empresas</button>.
        </div>
      ) : (
        <div className="card vazio">
          Nenhum lançamento com movimento em {d.competencia.curta} nesta carteira.{" "}
          <Link className="underline" href={rota("", { competencia: comp, carteira: d.carteira })}>Ir para o painel do mês</Link>.
        </div>
      )}
    </>
  );
}

function Selo({ l, pode, aoClicar }: { l: Linha; pode: boolean; aoClicar: (alvo: Element) => void }) {
  return (
    <button type="button" disabled={!pode} aria-pressed={l.bateu} onClick={(e) => aoClicar(e.currentTarget)}
            aria-label={`${l.tipo.nome}: ${l.bateu ? "bateu (clique para desmarcar)" : "a conferir (clique quando bater)"}`}
            title={l.bateu && l.bateuPor ? `Marcado por ${l.bateuPor.nome}` : undefined}
            className={`grid h-8 w-8 shrink-0 place-items-center rounded-full border-2 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand)] disabled:cursor-not-allowed ${
              l.bateu ? "border-[var(--ok)] bg-[var(--ok)] text-white" : "border-[var(--line-strong)] bg-[var(--surface)] text-transparent enabled:hover:border-[var(--ok)] enabled:hover:text-[var(--ok)]"}`}>
      <Icone nome="ok" tamanho={16} />
    </button>
  );
}

const CAB = "py-1.5 text-[11.5px] font-semibold uppercase tracking-[.05em] text-[var(--ink-3)]";
const BATIDA = "bg-[color-mix(in_srgb,var(--ok-soft)_55%,transparent)]";

function Cartao({ c, mostrarResp, ocupado, competencia, aoSelo, aoTodas }: {
  c: CartaoConferencia; mostrarResp: boolean; ocupado: boolean; competencia: string;
  aoSelo: (l: Linha, alvo: Element) => void; aoTodas: (alvo: Element) => void;
}) {
  const [detalhe, setDetalhe] = useState(false);
  const [veredito, setVeredito] = useState<HTMLSpanElement | null>(null);
  const pode = c.podeEditar && !ocupado;
  return (
    <article aria-label={c.empresa.nome}
             className={`card flex flex-col overflow-hidden border-t-[3px] ${c.tudoBateu ? "border-t-[var(--ok)]" : "border-t-[var(--warn)]"}`}>
      <header className="flex items-start justify-between gap-3 px-4 pb-2 pt-3">
        <div className="min-w-0">
          <h2 className="text-[16px] font-semibold leading-snug">
            <Link className="hover:underline" href={rota("lancamento", { empresa: c.empresa.id, competencia })}>{c.empresa.nome}</Link>
          </h2>
          {mostrarResp && c.responsavel ? <span className="text-[12.5px] text-[var(--ink-3)]">{c.responsavel}</span> : null}
        </div>
        <span ref={setVeredito} className={`badge ${c.tudoBateu ? "badge-ok" : "badge-warn"}`}>
          {c.tudoBateu ? "✓ Tudo bateu" : c.faltam === 1 ? "Falta 1" : `Faltam ${c.faltam}`}
        </span>
      </header>

      {!detalhe ? (
        <table className="w-full text-[14px]">
          <tbody>
            {c.blocos.map((b) => [
              <tr key={`t-${b.sentido}`}>
                <td className="w-14" />
                <th className={`${CAB} text-left`}>{b.titulo}</th>
                <th className={`${CAB} text-right`}>Qtde</th>
                <th className={`${CAB} pr-4 text-right`}>Valor (R$)</th>
              </tr>,
              ...b.linhas.map((l) => (
                <tr key={l.id ?? l.tipo.id} className={`border-t border-[var(--line)] ${l.bateu ? BATIDA : ""}`}>
                  <td className="py-1.5 pl-4"><Selo l={l} pode={pode} aoClicar={(alvo) => aoSelo(l, veredito ?? alvo)} /></td>
                  <td className="py-1.5 font-medium">
                    {l.tipo.nome}
                    {l.ajustes.length ? <span className="ml-1.5 cursor-help text-[12px] font-semibold text-[var(--brand)]" title={l.dicaAjuste}>±aj</span> : null}
                  </td>
                  <td className="py-1.5 text-right tabular-nums">{inteiro(l.totalQtdeAutor)}</td>
                  <td className="py-1.5 pr-4 text-right font-semibold tabular-nums">{moeda(l.totalValorAutor)}</td>
                </tr>
              )),
            ])}
          </tbody>
        </table>
      ) : (
        <div className="rolagem">
          <table className="w-full min-w-[560px] text-[13px]">
            <thead>
              <tr className="border-b border-[var(--line)]">
                <th className="w-14" /><th className={`${CAB} text-left`}>Tipo</th><th className={`${CAB} text-right`}>Qtde aut.</th>
                <th className={`${CAB} text-right`}>Valor aut.</th><th className={`${CAB} text-right`}>Canc.</th>
                <th className={`${CAB} text-right`}>Valor canc.</th><th className={`${CAB} pr-4 text-right`}>Ajuste</th>
              </tr>
            </thead>
            <tbody>
              {c.blocos.map((b) => [
                <tr key={`s-${b.sentido}`}><td /><td colSpan={6} className={`${CAB} !pb-0.5 !pt-2.5`}>{b.titulo}</td></tr>,
                ...b.linhas.map((l) => (
                  <tr key={l.id ?? l.tipo.id} className={`border-t border-[var(--line)] ${l.bateu ? BATIDA : ""}`}>
                    <td className="py-1.5 pl-4"><Selo l={l} pode={pode} aoClicar={(alvo) => aoSelo(l, veredito ?? alvo)} /></td>
                    <td className="py-1.5 font-medium">{l.tipo.nome}</td>
                    <td className="text-right tabular-nums">{inteiro(l.totalQtdeAutor)}</td>
                    <td className="text-right font-semibold tabular-nums">{moeda(l.totalValorAutor)}</td>
                    <td className="text-right tabular-nums text-[var(--ink-3)]">{l.totalQtdeCanc ? inteiro(l.totalQtdeCanc) : "—"}</td>
                    <td className="text-right tabular-nums text-[var(--ink-3)]">{Number(l.totalValorCanc) ? moeda(l.totalValorCanc) : "—"}</td>
                    <td className="whitespace-nowrap pr-4 text-right tabular-nums text-[var(--brand)]" title={l.ajustes.length ? l.dicaAjuste : undefined}>{l.ajusteCurto}</td>
                  </tr>
                )),
                <tr key={`sub-${b.sentido}`} className="border-t border-[var(--line)] bg-[var(--bg-soft)] font-semibold">
                  <td /><td className="whitespace-nowrap py-1.5">Subtotal {b.nomeSubtotal}</td>
                  <td className="text-right tabular-nums">{inteiro(b.subtotal.qtdeAutor)}</td>
                  <td className="text-right tabular-nums">{moeda(b.subtotal.valorAutor)}</td>
                  <td className="text-right tabular-nums">{b.subtotal.qtdeCanc ? inteiro(b.subtotal.qtdeCanc) : "—"}</td>
                  <td className="text-right tabular-nums">{Number(b.subtotal.valorCanc) ? moeda(b.subtotal.valorCanc) : "—"}</td>
                  <td />
                </tr>,
              ])}
            </tbody>
          </table>
        </div>
      )}

      <footer className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-[var(--line)] px-4 py-2.5">
        <button type="button" className="btn btn-quiet btn-sm" aria-expanded={detalhe} onClick={() => setDetalhe(!detalhe)}>
          {detalhe ? "Ocultar detalhes" : "Ver detalhes"}<span className="hidden sm:inline">{detalhe ? "" : " (cancelados, ajustes, subtotais)"}</span>
        </button>
        <button type="button" className="btn btn-sm whitespace-nowrap" disabled={!pode} onClick={(e) => aoTodas(veredito ?? e.currentTarget)}>
          {c.tudoBateu ? "Desmarcar todas" : "Marcar todas"}
        </button>
      </footer>
    </article>
  );
}
