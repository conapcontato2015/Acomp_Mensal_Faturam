"use client";
/* Importar do cruzamento Domínio × SEFAZ (hoje a versão do Manus; só lido): versão anterior × nova × atual,
   linha a linha, com prévia antes de gravar. Cada importação pode ser desfeita em Importações. */
import Link from "next/link";
import { useEffect, useState } from "react";
import { useAviso } from "@/components/Avisos";
import { Icone } from "@/components/Icone";
import { useSessao } from "@/components/Sessao";
import { BarraFiltros, Cabecalho, CaixaErro, Carregando, Metrica, SeletorCarteira, SeletorCompetencia } from "@/components/ui";
import { api, ErroApi, qs } from "@/lib/api";
import { dataHora, inteiro, moeda } from "@/lib/formato";
import type { Competencia, EmpresaResumo, TipoDocumento, Usuario } from "@/lib/tipos";
import { rota, useDados, useFiltros } from "@/lib/usar";

interface Numeros { qtdeAutor: number | null; valorAutor: string | null; qtdeCanc: number | null; valorCanc: string | null; ajQtde: number | null; ajValor: string | null }
interface LinhaCruz {
  chave: string; tipo: TipoDocumento; situacao: string; texto: string; mudouLa: boolean; bateu: boolean; selecionavel: boolean; marcada: boolean;
  anterior: Numeros | null; nova: Numeros | null; atual: Numeros | null; notas: { numero: string; serie: string | null; data: string; valor: string }[]; notasOmitidas: number;
}
interface PreviaCruz {
  token: string; competencia: Competencia; obtidoEm: string; obtidoEmLocal: string; aImportar: number; mudaramLa: number; mudaramLaBatidas: number;
  iguais: number; semDados: number;
  empresas: { empresa: EmpresaResumo; responsavel: Usuario | null; podeEditar: boolean; mudouLa: boolean; linhas: LinhaCruz[] }[];
  soLa: { razaoSocial: string; nomeFantasia: string | null; cnpj: string }[]; semCnpjAqui: EmpresaResumo[]; foraDoCruzamento: EmpresaResumo[];
}
interface RespInfo { configurado: boolean; competencia: Competencia; competencias: Competencia[] }

function Nums({ n }: { n: Numeros | null }) {
  if (!n) return <span className="text-[var(--ink-3)]">—</span>;
  return (
    <div className="tabular-nums">
      <div><strong>{inteiro(n.qtdeAutor)}</strong> · R$ {moeda(n.valorAutor)}</div>
      {n.qtdeCanc || Number(n.valorCanc) ? <div className="text-[12.5px] text-[var(--ink-3)]">canc. {inteiro(n.qtdeCanc)} · R$ {moeda(n.valorCanc)}</div> : null}
      {n.ajQtde ? <div className="text-[12.5px] text-[var(--brand)]">ajuste +{inteiro(n.ajQtde)} · R$ {moeda(n.ajValor)}</div> : null}
    </div>
  );
}

const CLASSE_SIT: Record<string, string> = { mudou_la: "badge-warn", igual: "badge-ok", novo: "badge-info", diferente: "badge-brand" };

export function Cruzamento() {
  const f = useFiltros();
  const { sessao, usuario } = useSessao();
  const avisar = useAviso();
  const competencia = f.get("competencia"), carteira = f.get("carteira"), empresa = f.get("empresa"), ver = f.get("ver") === "1";
  const info = useDados<RespInfo>(`/cruzamento${qs({ competencia })}`);
  const busca = useDados<PreviaCruz>(info.dados?.configurado && ver ? `/cruzamento/previa${qs({ competencia, carteira, empresa })}` : null);
  const [marcadas, setMarcadas] = useState<Set<string>>(new Set());
  const [substituto, setSubstituto] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const p = busca.dados;

  useEffect(() => {
    if (!p) return;
    setMarcadas(new Set(p.empresas.flatMap((e) => e.linhas.filter((l) => l.marcada && l.selecionavel && e.podeEditar).map((l) => l.chave))));
  }, [p]);

  const alternar = (chave: string) => setMarcadas((m) => { const n = new Set(m); if (n.has(chave)) n.delete(chave); else n.add(chave); return n; });
  const aplicar = async () => {
    if (!p) return;
    setEnviando(true);
    try {
      const r = await api<{ resumo: Record<string, number> }>("/cruzamento/aplicar", "POST", { token: p.token, linhas: [...marcadas], substituto });
      const s = r.resumo;
      avisar(`Importado do cruzamento: ${s.lancamentosCriados} novo(s), ${s.lancamentosAlterados} alterado(s), ${s.ajustesCriados} ajuste(s).` +
             (s.ignoradosBateu ? ` ${s.ignoradosBateu} já conferido(s) ficaram como estavam.` : "") +
             (s.ignoradosOutraCarteira ? ` ${s.ignoradosOutraCarteira} de outra carteira não entraram.` : ""));
      f.set({ ver: null });
    } catch (e) { avisar(e instanceof ErroApi ? e.mensagens.join(" ") : String(e), "erro"); } finally { setEnviando(false); }
  };
  const cancelar = async () => {
    if (p) await api("/cruzamento/descartar", "POST", { token: p.token }).catch(() => undefined);
    f.set({ ver: null });
  };

  const d = info.dados;
  const nomeEmpresa = empresa && p ? p.empresas.find((e) => String(e.empresa.id) === empresa)?.empresa.nome : null;

  return (
    <>
      <Cabecalho sobre={<Link href={rota("importacao")} className="hover:underline">Importações</Link>} titulo="Importar do cruzamento Domínio × SEFAZ" />
      {info.erro ? <CaixaErro mensagens={info.erro.mensagens} /> : !d ? <Carregando /> : !d.configurado ? (
        <div className="aviso aviso-danger" role="alert">
          <Icone nome="alerta" className="mt-0.5 shrink-0 text-[var(--danger)]" />
          <div>
            <strong>Cruzamento: não configurado.</strong> No Manus, cadastre o segredo <code>FATURAMENTO_API_KEY</code> (um texto longo e aleatório) e publique o
            cruzamento. Depois coloque no arquivo <code>.env</code> do Faturamento <code>CRUZAMENTO_URL=https://endereço-do-cruzamento</code> e{" "}
            <code>CRUZAMENTO_API_KEY=</code> (a mesma chave cadastrada no Manus) e reinicie o Faturamento.
          </div>
        </div>
      ) : (
        <>
          <div className="aviso aviso-info" role="note">
            <Icone nome="info" className="mt-0.5 shrink-0 text-[var(--info)]" />
            <span>O cruzamento é <strong>só lido</strong>. Vêm de lá NF-e Entradas, NF-e Saídas e NFC-e (autorizadas e canceladas, pela data de emissão) e o{" "}
              <strong>ajuste sugerido</strong>: notas que estão no Domínio e não no relatório da SEFAZ. CT-e e NFS-e continuam manuais. A <strong>versão anterior</strong> é
              o que veio na última importação; cada importação fica guardada e pode ser desfeita em Importações. Linhas &quot;Bateu&quot; nunca são alteradas.</span>
          </div>
          <BarraFiltros>
            <SeletorCompetencia valor={d.competencia.valor} opcoes={d.competencias} onChange={(v) => f.set({ competencia: v, ver: null })} />
            {empresa ? (
              <>
                <div className="campo"><span>Empresa</span><span className="entrada flex items-center">{nomeEmpresa ?? `#${empresa}`}</span></div>
                <button type="button" className="btn" onClick={() => f.set({ empresa: null, ver: null })}>Todas da carteira</button>
              </>
            ) : sessao ? (
              <SeletorCarteira valor={carteira || String(usuario?.id ?? "")} usuarios={sessao.usuarios} eu={usuario} onChange={(v) => f.set({ carteira: v, ver: null })} />
            ) : null}
            <button className="btn btn-solid" type="button" disabled={busca.carregando} onClick={() => (ver ? void busca.recarregar() : f.set({ ver: 1 }))}>
              {busca.carregando ? "Buscando…" : p ? "Buscar de novo" : "Buscar no cruzamento"}
            </button>
          </BarraFiltros>
        </>
      )}

      {busca.erro ? <CaixaErro mensagens={busca.erro.mensagens} onTentar={() => void busca.recarregar()} /> : null}
      {ver && busca.carregando && !p ? <Carregando texto="Lendo o cruzamento…" /> : null}

      {p ? (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Metrica rotulo="A importar" valor={p.aImportar} tom="brand" />
            <Metrica rotulo="Mudaram lá desde a última importação" valor={p.mudaramLa} tom={p.mudaramLa ? "warn" : undefined} />
            <Metrica rotulo="Iguais ao lançado aqui" valor={p.iguais} tom="ok" />
            <Metrica rotulo="Sem relatório SEFAZ lá" valor={p.semDados} />
          </div>
          {p.mudaramLaBatidas ? (
            <div className="aviso aviso-warn" role="status"><Icone nome="alerta" className="mt-0.5 shrink-0 text-[var(--warn)]" />
              <span><strong>{p.mudaramLaBatidas} linha(s) já marcada(s) como &quot;Bateu&quot; mudaram no cruzamento depois da última importação.</strong> Elas não serão alteradas; confira se a mudança lá foi intencional.</span></div>
          ) : null}
          <span className="text-[13px] text-[var(--ink-3)]">Lido do cruzamento em {dataHora(p.obtidoEmLocal)} · nada foi gravado ainda.</span>

          {p.empresas.length ? p.empresas.map((ep) => (
            <section key={ep.empresa.id} className="card overflow-hidden" aria-label={ep.empresa.nome}>
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--line)] px-4 py-3">
                <div><strong>{ep.empresa.nome}</strong> <span className="text-[13px] text-[var(--ink-3)]">· {ep.empresa.cnpjFormatado} · {ep.responsavel?.nome ?? "sem responsável"}</span></div>
                <div className="flex gap-1.5">
                  {ep.mudouLa ? <span className="badge badge-warn">Mudou lá</span> : null}
                  {!ep.podeEditar ? <span className="badge">Carteira de {ep.responsavel?.nome ?? "outra pessoa"}</span> : null}
                </div>
              </div>
              {ep.linhas.length ? (
                <div className="rolagem">
                  <table className="tabela">
                    <thead><tr><th><span className="sr-only">Importar</span></th><th>Tipo</th><th>Versão anterior</th><th>Nova versão (lá)</th><th>Atual aqui</th><th>Situação</th></tr></thead>
                    <tbody>
                      {ep.linhas.map((l) => (
                        <tr key={l.chave} className="align-top">
                          <td className="w-10"><input type="checkbox" className="check" checked={marcadas.has(l.chave)} disabled={!l.selecionavel}
                                                      aria-label={`Importar ${ep.empresa.nome} · ${l.tipo.nome}`} onChange={() => alternar(l.chave)} /></td>
                          <td className="whitespace-nowrap font-medium">{l.tipo.nome}</td>
                          <td><Nums n={l.anterior} /></td>
                          <td>
                            <Nums n={l.nova} />
                            {l.notas.length ? (
                              <details className="mt-1 text-[12.5px]">
                                <summary className="cursor-pointer">{l.notas.length + l.notasOmitidas} nota(s) só no Domínio</summary>
                                <div className="max-w-[420px]">{l.notas.map((n) => `${n.numero}${n.serie ? "/" + n.serie : ""} (${n.data}, R$ ${moeda(n.valor)})`).join(", ")}{l.notasOmitidas ? ` … e mais ${l.notasOmitidas}` : ""}</div>
                              </details>
                            ) : l.nova && l.nova.ajQtde === null ? <div className="text-[12.5px] text-[var(--ink-3)]">Domínio do mês não importado lá: sem ajuste sugerido</div> : null}
                          </td>
                          <td><Nums n={l.atual} />{l.bateu ? <span className="badge badge-ok mt-1">Bateu</span> : null}</td>
                          <td className="min-w-[180px]"><span className={`badge whitespace-normal ${l.mudouLa && l.bateu ? "badge-warn" : CLASSE_SIT[l.situacao] ?? ""}`}>{l.texto}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <div className="vazio !py-4">Nenhum dos tipos desta empresa vem do cruzamento.</div>}
            </section>
          )) : <div className="card vazio">Nenhuma empresa {empresa ? "" : "desta carteira "}foi encontrada no cruzamento pelo CNPJ.</div>}

          {p.empresas.length ? (
            <section className="card flex flex-wrap items-center justify-between gap-3 p-4">
              <label className="flex cursor-pointer items-center gap-2 text-[14px]">
                <input type="checkbox" className="check" checked={substituto} onChange={(e) => setSubstituto(e.target.checked)} />
                Importar como substituto (inclui linhas marcadas de carteiras de outras pessoas)
              </label>
              <div className="flex gap-2">
                <button className="btn" type="button" onClick={() => void cancelar()}>Cancelar</button>
                <button className="btn btn-solid" type="button" disabled={enviando || !marcadas.size} onClick={() => void aplicar()}>
                  {enviando ? "Importando…" : `Importar ${marcadas.size} linha(s) marcada(s)`}
                </button>
              </div>
            </section>
          ) : null}

          {p.soLa.length || p.foraDoCruzamento.length || p.semCnpjAqui.length ? (
            <section className="card flex flex-col gap-2.5 p-4 text-[13.5px]" aria-label="Empresas sem correspondência">
              {p.foraDoCruzamento.length ? <details><summary className="cursor-pointer"><strong>{p.foraDoCruzamento.length}</strong> empresa(s) daqui não estão no cruzamento (pelo CNPJ)</summary>
                <ul className="mt-1 list-disc pl-5">{p.foraDoCruzamento.map((e) => <li key={e.id}>{e.nome} · {e.cnpjFormatado}</li>)}</ul></details> : null}
              {p.semCnpjAqui.length ? <details><summary className="cursor-pointer"><strong>{p.semCnpjAqui.length}</strong> empresa(s) daqui sem CNPJ cadastrado (cadastre em Empresas para casar)</summary>
                <ul className="mt-1 list-disc pl-5">{p.semCnpjAqui.map((e) => <li key={e.id}>{e.nome}</li>)}</ul></details> : null}
              {p.soLa.length ? <details><summary className="cursor-pointer"><strong>{p.soLa.length}</strong> empresa(s) do cruzamento não cadastradas aqui (não são criadas)</summary>
                <ul className="mt-1 list-disc pl-5">{p.soLa.map((e) => <li key={e.cnpj}>{e.razaoSocial}{e.nomeFantasia ? ` (${e.nomeFantasia})` : ""} · {e.cnpj}</li>)}</ul></details> : null}
            </section>
          ) : null}
        </>
      ) : null}
    </>
  );
}
