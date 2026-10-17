"use client";
/* Importar a planilha antiga (FATURAMENTO_V2.xlsx, aba DADOS): prévia, confirmação e histórico de
   importações (cada uma pode ser desfeita). */
import Link from "next/link";
import { useState } from "react";
import { useAviso } from "@/components/Avisos";
import { Icone } from "@/components/Icone";
import { Janela } from "@/components/Janela";
import { useSessao } from "@/components/Sessao";
import { Cabecalho, CaixaErro, Carregando, Grupo, Metrica } from "@/components/ui";
import { api, enviarArquivo, ErroApi } from "@/lib/api";
import { dataHora, inteiro, moeda } from "@/lib/formato";
import type { Competencia, Usuario } from "@/lib/tipos";
import { rota, useDados } from "@/lib/usar";

interface Aviso { texto: string; destaque: boolean }
interface ImportacaoFeita {
  id: number; data: string; arquivo: string; desfeita: boolean; usuario: Usuario | null; responsavel: Usuario | null; fonte: string;
  empresasCriadas: number; lancamentosCriados: number; lancamentosAlterados: number; ajustesCriados: number; avisos: Aviso[]; nAvisosDestaque: number;
}
interface RespLista { importacoes: ImportacaoFeita[]; usuarios: Usuario[]; opcaoOutras: string; cruzamento: boolean }
interface Somas { qtde: number; valor: string; qtdeCanc: number; valorCanc: string }
interface Previa {
  token: string; arquivo: string; aba: string; linhaCabecalho: number; linhasLidas: number; linhasVazias: number;
  nLancamentos: number; nAjustes: number; competencias: Competencia[]; avisos: Aviso[];
  empresas: { original: string; nome: string; nova: boolean; competencias: string[]; primeira: Competencia; ultima: Competencia; nLancamentos: number; nAjustes: number; tipos: string[] }[];
  totais: { competencia: Competencia; lancamentos: number; empresas: number; entradas: Somas; saidas: Somas }[];
  conflitos: { iguais: number; alterar: number; bateu: number };
  outrasCarteiras: { linhas: number; empresas: number }; responsavel: Usuario | null; opcaoOutras: string;
}

export function Importacao() {
  const lista = useDados<RespLista>("/importacoes");
  const { usuario } = useSessao();
  const avisar = useAviso();
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [resp, setResp] = useState<number | null>(null);
  const [previa, setPrevia] = useState<Previa | null>(null);
  const [outras, setOutras] = useState(false);
  const [erro, setErro] = useState<string[] | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [desfazer, setDesfazer] = useState<ImportacaoFeita | null>(null);
  const d = lista.dados;
  const respSel = resp ?? usuario?.id ?? d?.usuarios[0]?.id ?? 0;
  const falha = (e: unknown) => setErro(e instanceof ErroApi ? e.mensagens : [String(e)]);

  const verPrevia = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!arquivo) return;
    setEnviando(true); setErro(null);
    try { setPrevia(await enviarArquivo<Previa>("/importacoes/previa", { arquivo, responsavelId: String(respSel) })); setOutras(false); }
    catch (e) { falha(e); } finally { setEnviando(false); }
  };
  const cancelar = async () => {
    if (previa) await api("/importacoes/descartar", "POST", { token: previa.token }).catch(() => undefined);
    setPrevia(null);
  };
  const confirmar = async () => {
    if (!previa) return;
    setEnviando(true); setErro(null);
    try {
      const r = await api<{ resumo: Record<string, number | string[]> }>("/importacoes/confirmar", "POST", { token: previa.token, responsavelId: respSel, outrasCarteiras: outras });
      const s = r.resumo;
      avisar(`Importado: ${s.lancamentosCriados} lançamento(s) novo(s), ${s.lancamentosAlterados} alterado(s), ${s.ajustesCriados} ajuste(s), ${(s.empresasCriadas as string[]).length} empresa(s) criada(s).`);
      setPrevia(null); setArquivo(null);
      await lista.recarregar();
    } catch (e) { falha(e); } finally { setEnviando(false); }
  };
  const fazerDesfazer = async () => {
    if (!desfazer) return;
    setEnviando(true);
    try {
      await api(`/importacoes/${desfazer.id}/desfazer`, "POST", {});
      avisar(`Importação #${desfazer.id} desfeita.`);
      setDesfazer(null);
      await lista.recarregar();
    } catch (e) { avisar(e instanceof ErroApi ? e.mensagens.join(" ") : String(e), "erro"); } finally { setEnviando(false); }
  };

  if (previa) return <TelaPrevia p={previa} usuarios={d?.usuarios ?? []} resp={respSel} setResp={setResp} outras={outras} setOutras={setOutras}
                                  erro={erro} enviando={enviando} aoCancelar={() => void cancelar()} aoConfirmar={() => void confirmar()} />;

  return (
    <>
      <Cabecalho sobre="Fase de transição" titulo="Importar planilha antiga"
                 acoes={<>
                   <Link className="btn btn-solid" href={rota("importacao/cruzamento")}><Icone nome="nuvem" /> Importar do cruzamento Domínio × SEFAZ</Link>
                   <Link className="btn" href={rota("empresas/responsaveis")}>Importar responsáveis</Link>
                 </>} />
      <section className="card flex flex-col gap-4 p-5">
        <div className="aviso aviso-info" role="note">
          <Icone nome="info" className="mt-0.5 shrink-0 text-[var(--info)]" />
          <div>
            <strong>Como funciona.</strong> Envie a planilha <em>FATURAMENTO_V2.xlsx</em> (aba <strong>DADOS</strong>). Primeiro aparece uma <strong>prévia</strong> — nada é gravado até você confirmar.
            <ul className="mt-1.5 flex list-disc flex-col gap-0.5 pl-5 text-[13.5px]">
              <li>Colunas lidas pelo nome: EMPRESA, COMP., TIPO, QTDE_AUTOR, VALOR_AUTOR, AJUSTE_*, QTDE_CANC, VALOR_CANC. Os totais da planilha são ignorados (o sistema recalcula).</li>
              <li>Linhas sem nenhum número são puladas. Colunas AJUSTE_* viram ajustes com o motivo &quot;Importado da planilha&quot;.</li>
              <li>Empresas que ainda não existem são criadas na carteira do responsável escolhido abaixo.</li>
              <li>Lançamentos já marcados como &quot;Bateu&quot; nunca são alterados. Importar o mesmo arquivo de novo não duplica nada.</li>
            </ul>
          </div>
        </div>
        <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => void verPrevia(e)}>
          <label className="campo min-w-[280px] flex-1"><span>Planilha (.xlsx)</span>
            <input className="entrada" type="file" accept=".xlsx,.xlsm" required onChange={(e) => setArquivo(e.target.files?.[0] ?? null)} /></label>
          <label className="campo"><span>Responsável por estas empresas</span>
            <select className="entrada" value={respSel} onChange={(e) => setResp(Number(e.target.value))}>
              {(d?.usuarios ?? []).map((u) => <option key={u.id} value={u.id}>{u.nome}</option>)}
            </select></label>
          <button className="btn btn-solid" type="submit" disabled={!arquivo || enviando}>{enviando ? "Lendo…" : "Ver prévia"}</button>
        </form>
        <span className="text-[13px] text-[var(--ink-3)]">Cada pessoa importa a própria planilha. O responsável vale para as empresas <strong>novas</strong>; empresas que já existem mantêm a carteira atual.</span>
      </section>
      {erro ? <CaixaErro mensagens={erro} /> : null}

      <Grupo titulo="Importações anteriores">
        {lista.erro ? <div className="p-4"><CaixaErro mensagens={lista.erro.mensagens} /></div> : !d ? <Carregando /> : d.importacoes.length ? (
          <div className="rolagem">
            <table className="tabela" aria-label="Importações anteriores">
              <thead><tr>
                <th className="num">#</th><th>Data</th><th>Feita por</th><th>Arquivo</th><th>Responsável</th>
                <th className="num">Empresas novas</th><th className="num">Lançamentos</th><th className="num">Ajustes</th><th>Avisos</th><th>Situação</th><th><span className="sr-only">Ações</span></th>
              </tr></thead>
              <tbody>
                {d.importacoes.map((i) => (
                  <tr key={i.id} className="align-top">
                    <td className="num">{i.id}</td>
                    <td className="whitespace-nowrap tabular-nums">{dataHora(i.data)}</td>
                    <td>{i.usuario?.nome ?? "—"}</td>
                    <td className="font-medium">{i.arquivo}{i.fonte === "cruzamento" ? <span className="badge badge-info ml-1.5">cruzamento</span> : null}</td>
                    <td>{i.responsavel?.nome ?? "—"}</td>
                    <td className="num">{i.empresasCriadas}</td>
                    <td className="num whitespace-nowrap">{i.lancamentosCriados} novos · {i.lancamentosAlterados} alt.</td>
                    <td className="num">{i.ajustesCriados}</td>
                    <td>
                      {i.avisos.length ? (
                        <details>
                          <summary className={`cursor-pointer whitespace-nowrap ${i.nAvisosDestaque ? "font-semibold text-[var(--warn)]" : ""}`}>{i.avisos.length} aviso(s)</summary>
                          <ul className="mt-1.5 flex max-w-[520px] list-disc flex-col gap-0.5 pl-5 text-[13px]">
                            {i.avisos.map((a, k) => <li key={k} className={a.destaque ? "font-semibold text-[var(--warn)]" : ""}>{a.texto}</li>)}
                          </ul>
                        </details>
                      ) : <span className="text-[var(--ink-3)]">—</span>}
                    </td>
                    <td>{i.desfeita ? <span className="badge">Desfeita</span> : <span className="badge badge-ok">Ativa</span>}</td>
                    <td className="text-right">{!i.desfeita ? <button className="btn btn-sm" type="button" onClick={() => setDesfazer(i)}>Desfazer</button> : null}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div className="vazio">Nenhuma importação feita ainda.</div>}
      </Grupo>

      <Janela aberta={!!desfazer} aoFechar={() => setDesfazer(null)} titulo={`Desfazer a importação #${desfazer?.id ?? ""}?`} subtitulo={desfazer?.arquivo}
              rodape={<>
                <button className="btn" type="button" onClick={() => setDesfazer(null)}>Não</button>
                <button className="btn btn-solid" type="button" disabled={enviando} onClick={() => void fazerDesfazer()}>Desfazer importação</button>
              </>}>
        <p className="text-[14px]">Os lançamentos criados por ela (exceto os já conferidos ou alterados depois) serão apagados e os números alterados voltam ao que eram. Fica registrado no histórico.</p>
      </Janela>
    </>
  );
}

function TelaPrevia({ p, usuarios, resp, setResp, outras, setOutras, erro, enviando, aoCancelar, aoConfirmar }: {
  p: Previa; usuarios: Usuario[]; resp: number; setResp: (n: number) => void; outras: boolean; setOutras: (b: boolean) => void;
  erro: string[] | null; enviando: boolean; aoCancelar: () => void; aoConfirmar: () => void;
}) {
  const novas = p.empresas.filter((e) => e.nova).length;
  const comps = p.competencias;
  const destaque = p.avisos.filter((a) => a.destaque).length;
  const c = p.conflitos;
  return (
    <>
      <Cabecalho sobre="Prévia da importação · nada foi gravado ainda" titulo={p.arquivo}
                 descricao={`Aba ${p.aba}, cabeçalho na linha ${p.linhaCabecalho} · ${p.linhasLidas} linhas lidas, ${p.linhasVazias} vazias puladas`} />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Metrica rotulo="Lançamentos" valor={inteiro(p.nLancamentos)} tom="brand" />
        <Metrica rotulo={`Empresas (${novas} nova(s))`} valor={p.empresas.length} />
        <Metrica rotulo={`Competências (${comps.length})`} valor={comps.length ? `${comps[0].curta} a ${comps[comps.length - 1].curta}` : "—"} />
        <Metrica rotulo="Ajustes" valor={p.nAjustes} />
        <Metrica rotulo={destaque ? `Avisos (${destaque} para corrigir)` : "Avisos"} valor={p.avisos.length} tom={p.avisos.length ? "warn" : undefined} />
      </div>

      {c.alterar || c.bateu || c.iguais ? (
        <div className="aviso aviso-info" role="status">
          <Icone nome="info" className="mt-0.5 shrink-0 text-[var(--info)]" />
          <span>Já existem no sistema: <strong>{c.iguais}</strong> lançamento(s) iguais (ficam como estão), <strong>{c.alterar}</strong> com números diferentes
            (serão substituídos pelos da planilha, com registro no histórico) e <strong>{c.bateu}</strong> já conferidos como &quot;Bateu&quot; (não serão alterados).</span>
        </div>
      ) : null}

      {p.avisos.length ? (
        <div className="aviso aviso-warn block" role="alert">
          <strong>Avisos da leitura ({p.avisos.length})</strong>
          <ul className="mt-1 flex max-h-[260px] list-disc flex-col gap-0.5 overflow-y-auto pl-5 text-[13.5px]">
            {p.avisos.map((a, i) => <li key={i} className={a.destaque ? "font-semibold" : ""}>{a.texto}</li>)}
          </ul>
          {destaque ? <p className="mt-1 text-[13px]">Os itens em negrito são importados assim mesmo (ou ignorados, quando indicado) e precisam ser conferidos no lançamento depois.</p> : null}
        </div>
      ) : null}

      {erro ? <CaixaErro mensagens={erro} /> : null}

      <section className="card flex flex-wrap items-end justify-between gap-4 p-4">
        <label className="campo"><span>Responsável pelas {novas} empresa(s) nova(s)</span>
          <select className="entrada" value={resp} onChange={(e) => setResp(Number(e.target.value))}>
            {usuarios.map((u) => <option key={u.id} value={u.id}>{u.nome}</option>)}
          </select></label>
        <div className="flex max-w-[560px] flex-col gap-1">
          {p.outrasCarteiras.linhas ? <span className="text-[13px] text-[var(--warn)]"><strong>{p.outrasCarteiras.linhas}</strong> lançamento(s) de {p.outrasCarteiras.empresas} empresa(s) são de carteiras de outras pessoas (ou vão para a carteira de outra pessoa) e só entram com a opção abaixo.</span> : null}
          <label className="flex cursor-pointer items-center gap-2 text-[14px]">
            <input type="checkbox" className="check" checked={outras} onChange={(e) => setOutras(e.target.checked)} /> {p.opcaoOutras}
          </label>
        </div>
        <div className="flex gap-2">
          <button className="btn" type="button" onClick={aoCancelar}>Cancelar</button>
          <button className="btn btn-solid" type="button" disabled={enviando} onClick={aoConfirmar}>{enviando ? "Importando…" : "Confirmar importação"}</button>
        </div>
      </section>

      <Grupo titulo="Empresas">
        <div className="rolagem">
          <table className="tabela" aria-label="Empresas da planilha">
            <thead><tr><th>Empresa</th><th>Situação</th><th>Competências</th><th className="num">Lançamentos</th><th className="num">Ajustes</th><th>Tipos</th></tr></thead>
            <tbody>
              {p.empresas.map((e) => (
                <tr key={e.original}>
                  <td className="font-medium">{e.nome}{e.nome.toUpperCase() !== e.original.toUpperCase() ? <div className="text-[12.5px] font-normal text-[var(--ink-3)]">na planilha: {e.original}</div> : null}</td>
                  <td>{e.nova ? <span className="badge badge-warn">Será criada</span> : <span className="badge badge-ok">Já existe</span>}</td>
                  <td className="whitespace-nowrap">{e.primeira.curta}{e.ultima.valor !== e.primeira.valor ? ` a ${e.ultima.curta}` : ""} <span className="text-[12.5px] text-[var(--ink-3)]">({e.competencias.length})</span></td>
                  <td className="num">{e.nLancamentos}</td>
                  <td className="num">{e.nAjustes || "—"}</td>
                  <td><div className="flex flex-wrap gap-1">{e.tipos.map((t) => <span key={t} className={`badge ${t.includes("Entradas") ? "badge-info" : "badge-brand"}`}>{t}</span>)}</div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Grupo>

      <Grupo titulo="Totais por competência" acoes={<span className="text-[13px] text-[var(--ink-3)]">Para conferir com a dinâmica da planilha. Já incluem os ajustes. Entradas e saídas não se somam.</span>}>
        <div className="rolagem">
          <table className="tabela" aria-label="Totais por competência">
            <thead><tr>
              <th>Competência</th><th className="num">Empresas</th><th className="num">Lançamentos</th><th className="num">Entradas qtde</th><th className="num">Entradas R$</th>
              <th className="num">Saídas qtde</th><th className="num">Saídas R$</th><th className="num">Canc. entradas</th><th className="num">Canc. saídas</th>
            </tr></thead>
            <tbody>
              {p.totais.map((t) => (
                <tr key={t.competencia.valor}>
                  <td>{t.competencia.curta}</td><td className="num">{t.empresas}</td><td className="num">{t.lancamentos}</td>
                  <td className="num">{inteiro(t.entradas.qtde)}</td><td className="num">{moeda(t.entradas.valor)}</td>
                  <td className="num">{inteiro(t.saidas.qtde)}</td><td className="num">{moeda(t.saidas.valor)}</td>
                  <td className="num whitespace-nowrap">{inteiro(t.entradas.qtdeCanc)} · {moeda(t.entradas.valorCanc)}</td>
                  <td className="num whitespace-nowrap">{inteiro(t.saidas.qtdeCanc)} · {moeda(t.saidas.valorCanc)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Grupo>
    </>
  );
}
