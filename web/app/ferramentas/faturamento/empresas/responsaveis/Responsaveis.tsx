"use client";
/* Importar responsáveis por planilha (CNPJ/EMPRESA + RESPONSAVEL [+ INICIO]): prévia e depois aplicar. */
import Link from "next/link";
import { useState } from "react";
import { useAviso } from "@/components/Avisos";
import { Icone } from "@/components/Icone";
import { Cabecalho, CaixaErro, Carregando, ListaRelatorio, Metrica } from "@/components/ui";
import { api, enviarArquivo, ErroApi, urlApi } from "@/lib/api";
import type { Competencia } from "@/lib/tipos";
import { rota, useDados } from "@/lib/usar";

interface Relatorio { alteradas: string[]; semMudanca: number; empresasNaoEncontradas: string[]; responsaveisNaoEncontrados: string[]; erros: string[] }
interface RespInfo { provedor: string; inicioPadrao: Competencia; competencias: Competencia[] }
interface RespPrevia { token: string | null; arquivo: string; inicio: Competencia; relatorio: Relatorio }

export function Responsaveis() {
  const info = useDados<RespInfo>("/responsaveis");
  const avisar = useAviso();
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [inicio, setInicio] = useState("");
  const [previa, setPrevia] = useState<RespPrevia | null>(null);
  const [erro, setErro] = useState<string[] | null>(null);
  const [enviando, setEnviando] = useState(false);
  const d = info.dados;
  if (info.erro) return <CaixaErro mensagens={info.erro.mensagens} />;
  if (!d) return <Carregando />;
  const ini = inicio || d.inicioPadrao.valor;

  const verPrevia = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!arquivo) return;
    setEnviando(true); setErro(null); setPrevia(null);
    try { setPrevia(await enviarArquivo<RespPrevia>("/responsaveis/previa", { arquivo, inicio: ini })); }
    catch (e) { setErro(e instanceof ErroApi ? e.mensagens : [String(e)]); }
    finally { setEnviando(false); }
  };
  const aplicar = async () => {
    if (!previa?.token) return;
    setEnviando(true);
    try {
      const r = await api<{ relatorio: Relatorio }>("/responsaveis/confirmar", "POST", { token: previa.token, inicio: previa.inicio.valor });
      avisar(`${r.relatorio.alteradas.length} troca(s) de responsável aplicada(s).`);
      setPrevia(null);
    } catch (e) { setErro(e instanceof ErroApi ? e.mensagens : [String(e)]); }
    finally { setEnviando(false); }
  };
  const rel = previa?.relatorio;

  return (
    <>
      <Cabecalho sobre={<Link href={rota("empresas")} className="hover:underline">Empresas</Link>} titulo="Importar responsáveis"
                 acoes={<a className="btn" href={urlApi("/responsaveis/modelo.csv")}><Icone nome="excel" /> Baixar modelo (.csv com a carteira atual)</a>} />
      <div className="aviso aviso-info" role="note">
        <Icone nome="info" className="mt-0.5 shrink-0 text-[var(--info)]" />
        {d.provedor === "manual" ? (
          <span><strong>Integração de responsáveis: não configurada (manual).</strong> A carteira é trocada na tela de Empresas ou por esta planilha.
            Quando houver um sistema externo de responsáveis (ou o login do Conap Ferramentas), esta tela fica só para correções em lote.</span>
        ) : <span><strong>Integração de responsáveis: {d.provedor}.</strong> Os responsáveis vêm do sistema externo; use a planilha só para correções em lote.</span>}
      </div>

      <section className="card flex flex-col gap-4 p-5">
        <div>
          <h2 className="mb-1.5 text-[16px] font-semibold">Formato esperado</h2>
          <p className="text-[14px] text-[var(--ink-2)]">Arquivo <strong>.xlsx</strong> (primeira aba) ou <strong>.csv</strong> (separado por <code>;</code> ou <code>,</code>), com os nomes das colunas na primeira linha:</p>
          <ul className="mt-2 flex list-disc flex-col gap-1 pl-5 text-[13.5px]">
            <li><strong>CNPJ</strong> ou <strong>EMPRESA</strong> — pelo menos uma; o CNPJ tem prioridade, o nome é comparado sem acentos/maiúsculas.</li>
            <li><strong>RESPONSAVEL</strong> — nome de quem cuida.</li>
            <li><strong>INICIO</strong> (opcional) — competência a partir da qual vale (AAAA-MM ou MM/AAAA). Em branco: usa a competência escolhida abaixo.</li>
          </ul>
          <p className="mt-2 text-[13px] text-[var(--ink-3)]">Dica: baixe o modelo, que já vem com todas as empresas e o responsável atual — mude só as linhas que precisar.</p>
        </div>
        <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => void verPrevia(e)}>
          <label className="campo min-w-[280px] flex-1"><span>Planilha (.xlsx ou .csv)</span>
            <input className="entrada" type="file" accept=".xlsx,.xlsm,.csv,.txt" required onChange={(e) => { setArquivo(e.target.files?.[0] ?? null); setPrevia(null); }} /></label>
          <label className="campo"><span>Sem INICIO, vale a partir de</span>
            <select className="entrada" value={ini} onChange={(e) => setInicio(e.target.value)}>
              {d.competencias.map((c) => <option key={c.valor} value={c.valor}>{c.curta}</option>)}
            </select></label>
          <button className="btn btn-solid" type="submit" disabled={!arquivo || enviando}>{enviando && !previa ? "Lendo…" : "Ver prévia"}</button>
        </form>
      </section>

      {erro ? <CaixaErro mensagens={erro} /> : null}

      {previa && rel ? (
        <section className="card flex flex-col gap-4 p-5" aria-label="Prévia">
          <div><span className="text-[13px] text-[var(--ink-3)]">Prévia · nada foi alterado ainda</span><h2 className="text-[16px] font-semibold">{previa.arquivo}</h2></div>
          {rel.erros.length ? <CaixaErro mensagens={["Não foi possível ler a planilha.", ...rel.erros]} /> : (
            <>
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <Metrica rotulo="Serão trocadas" valor={rel.alteradas.length} tom="brand" />
                <Metrica rotulo="Sem mudança" valor={rel.semMudanca} />
                <Metrica rotulo="Empresas não encontradas" valor={rel.empresasNaoEncontradas.length} tom={rel.empresasNaoEncontradas.length ? "warn" : undefined} />
                <Metrica rotulo="Responsáveis não encontrados" valor={rel.responsaveisNaoEncontrados.length} tom={rel.responsaveisNaoEncontrados.length ? "warn" : undefined} />
              </div>
              <ListaRelatorio titulo="Trocas" itens={rel.alteradas} />
              <ListaRelatorio titulo="Linhas que serão ignoradas" tom="warn"
                              itens={[...rel.empresasNaoEncontradas.map((e) => `Empresa não cadastrada: ${e}`), ...rel.responsaveisNaoEncontrados.map((r) => `Responsável desconhecido: ${r}`)]} />
              {previa.token ? (
                <div className="flex justify-end gap-2">
                  <button className="btn" type="button" onClick={() => setPrevia(null)}>Cancelar</button>
                  <button className="btn btn-solid" type="button" disabled={enviando} onClick={() => void aplicar()}>Aplicar {rel.alteradas.length} troca(s)</button>
                </div>
              ) : <div className="aviso aviso-info">Nenhuma troca a aplicar.</div>}
            </>
          )}
        </section>
      ) : null}
    </>
  );
}
