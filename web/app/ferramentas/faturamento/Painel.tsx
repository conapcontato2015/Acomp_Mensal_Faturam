"use client";
/* Painel do mês: status de cada empresa da carteira, progresso, alertas de variação das saídas. */
import Link from "next/link";
import { useSessao } from "@/components/Sessao";
import { AvisoLeitura, BarraFiltros, Cabecalho, CaixaErro, Carregando, Grupo, KpiProgresso, Metrica, PilulaStatus, SeletorCarteira, SeletorCompetencia } from "@/components/ui";
import { Icone } from "@/components/Icone";
import { qs } from "@/lib/api";
import { moeda } from "@/lib/formato";
import type { Competencia, EmpresaResumo, Referencias, Status } from "@/lib/tipos";
import { ROTULO_STATUS } from "@/lib/tipos";
import { rota, useDados, useFiltros } from "@/lib/usar";

interface LinhaPainel {
  empresa: EmpresaResumo; status: Status; statusAnterior: Status; tiposUsados: number; tiposLancados: number;
  entradas: string | null; saidas: string | null; linhas: number; bateram: number; variacaoSaidas: number | null; alerta: string | null;
}
interface RespPainel {
  competencia: Competencia; carteira: string; somenteLeitura: boolean; filtroStatus: string; total: number; feitos: number;
  progresso: number; contagem: { pendente: number; preenchido: number; semMovimento: number }; alertas: number; empresas: LinhaPainel[];
}

const FILTROS: { chave: string; rotulo: string }[] = [
  { chave: "todos", rotulo: "Todas" }, { chave: "pendente", rotulo: "Pendentes" },
  { chave: "preenchido", rotulo: "Preenchidas" }, { chave: "sem_movimento", rotulo: "Sem movimento" },
];

export function Painel() {
  const { usuario } = useSessao();
  const f = useFiltros();
  const comp = f.get("competencia");
  const carteira = f.get("carteira");
  const status = f.get("status") || "todos";
  const ref = useDados<Referencias>(`/referencias${qs({ competencia: comp })}`);
  const painel = useDados<RespPainel>(`/painel${qs({ competencia: comp, carteira, status })}`);
  const p = painel.dados;
  const dono = p && ref.dados ? (p.carteira === "todos" ? "todas as pessoas" : ref.dados.usuarios.find((u) => String(u.id) === p.carteira)?.nome ?? "—") : "";

  return (
    <>
      <Cabecalho titulo={p ? `Painel · ${p.competencia.extenso}` : "Painel do mês"}
                 descricao="Situação de cada empresa da carteira no mês: lançada, sem movimento ou pendente."
                 acoes={p ? <Link className="btn" href={rota("importacao/cruzamento", { competencia: p.competencia.valor, carteira: p.carteira, ver: 1 })}
                                  title="Compara o cruzamento Domínio × SEFAZ com a última versão importada e com o lançado aqui">
                   <Icone nome="nuvem" /> Verificar cruzamento</Link> : null} />

      {ref.dados && p ? (
        <BarraFiltros>
          <SeletorCompetencia valor={p.competencia.valor} opcoes={ref.dados.competencias} onChange={(v) => f.set({ competencia: v })} />
          <SeletorCarteira valor={p.carteira} usuarios={ref.dados.usuarios} eu={usuario} onChange={(v) => f.set({ carteira: v })} />
        </BarraFiltros>
      ) : null}

      {painel.erro ? <CaixaErro mensagens={painel.erro.mensagens} onTentar={() => void painel.recarregar()} /> : null}
      {!p && painel.carregando ? <Carregando /> : null}

      {p ? (
        <>
          {p.somenteLeitura ? <AvisoLeitura dono={dono} /> : null}
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,2fr)]">
            <KpiProgresso rotulo="Empresas concluídas no mês" valor={p.feitos} total={p.total} percentual={p.progresso}
                          detalhe="preenchidas + sem movimento" />
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 xl:grid-cols-2 2xl:grid-cols-4">
              <Metrica icone="painel" rotulo="Empresas ativas" valor={p.total} />
              <Metrica icone="ok" rotulo="Preenchidas" valor={p.contagem.preenchido} tom="ok" />
              <Metrica icone="historico" rotulo="Sem movimento" valor={p.contagem.semMovimento} />
              <Metrica icone="alerta" rotulo="Pendentes" valor={p.contagem.pendente} tom="warn" />
            </div>
          </div>

          {p.alertas ? (
            <div className="aviso aviso-warn" role="status">
              <Icone nome="alerta" className="mt-0.5 shrink-0 text-[var(--warn)]" />
              <span><strong>{p.alertas} empresa(s) com variação fora do padrão nas saídas.</strong> Confira os números destacados abaixo.</span>
            </div>
          ) : null}

          <Grupo titulo="Empresas" acoes={
            <div className="flex flex-wrap gap-2" role="group" aria-label="Filtrar por status">
              {FILTROS.map((x) => (
                <button key={x.chave} type="button" className="chip" aria-pressed={status === x.chave} onClick={() => f.set({ status: x.chave === "todos" ? null : x.chave })}>
                  {x.rotulo}
                </button>
              ))}
            </div>}>
            {p.empresas.length ? (
              <div className="rolagem">
                <table className="tabela">
                  <thead><tr>
                    <th>Empresa</th><th>Status</th><th>Tipos lançados</th><th className="num">Entradas (R$)</th>
                    <th className="num">Saídas (R$)</th><th>Bateu</th><th>Mês anterior</th><th><span className="sr-only">Ação</span></th>
                  </tr></thead>
                  <tbody>
                    {p.empresas.map((l) => (
                      <tr key={l.empresa.id}>
                        <td className="font-medium">
                          {l.empresa.nome}
                          {l.alerta ? <div className="mt-0.5 flex items-center gap-1 text-[12.5px] font-medium text-[var(--warn)]"><Icone nome="alerta" tamanho={14} />{l.alerta}</div> : null}
                        </td>
                        <td><PilulaStatus status={l.status} /></td>
                        <td className="text-[var(--ink-2)] tabular-nums">{l.tiposLancados} de {l.tiposUsados}</td>
                        <td className="num">{moeda(l.entradas)}</td>
                        <td className="num">{moeda(l.saidas)}</td>
                        <td className="whitespace-nowrap tabular-nums">
                          {l.linhas ? <span className="font-semibold" style={{ color: l.bateram === l.linhas ? "var(--ok)" : "var(--warn)" }}>{l.bateram} de {l.linhas}</span> : <span className="text-[var(--ink-3)]">—</span>}
                        </td>
                        <td className="text-[var(--ink-3)]">{ROTULO_STATUS[l.statusAnterior]}</td>
                        <td className="text-right">
                          <Link className="btn btn-sm" href={rota("lancamento", { empresa: l.empresa.id, competencia: p.competencia.valor })}>
                            {l.status === "pendente" ? "Lançar" : "Abrir"}
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="vazio">
                Nenhuma empresa {status !== "todos" ? "com esse status" : "nesta carteira"}.{" "}
                {!p.total ? <><Link className="underline" href={rota("empresas")}>Cadastre empresas</Link> ou <Link className="underline" href={rota("importacao")}>importe a planilha</Link>.</> : null}
              </div>
            )}
          </Grupo>
        </>
      ) : null}
    </>
  );
}
