"use client";
/* Importações: atalho para o cruzamento Domínio × SEFAZ e o histórico de importações (cada uma pode ser desfeita).
   Não há importação de planilha XLSX: a carga inicial é feita fora do sistema. */
import Link from "next/link";
import { useState } from "react";
import { useAviso } from "@/components/Avisos";
import { Icone } from "@/components/Icone";
import { Janela } from "@/components/Janela";
import { Cabecalho, CaixaErro, Carregando, Grupo } from "@/components/ui";
import { api, ErroApi } from "@/lib/api";
import { dataHora } from "@/lib/formato";
import type { Usuario } from "@/lib/tipos";
import { rota, useDados } from "@/lib/usar";

interface Aviso { texto: string; destaque: boolean }
interface ImportacaoFeita {
  id: number; data: string; arquivo: string; desfeita: boolean; usuario: Usuario | null; responsavel: Usuario | null; fonte: string;
  empresasCriadas: number; lancamentosCriados: number; lancamentosAlterados: number; ajustesCriados: number; avisos: Aviso[]; nAvisosDestaque: number;
}
interface RespLista { importacoes: ImportacaoFeita[]; cruzamento: boolean }

export function Importacao() {
  const lista = useDados<RespLista>("/importacoes");
  const avisar = useAviso();
  const [enviando, setEnviando] = useState(false);
  const [desfazer, setDesfazer] = useState<ImportacaoFeita | null>(null);
  const d = lista.dados;

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

  return (
    <>
      <Cabecalho titulo="Importações" descricao="Tudo o que entrou no sistema por importação, com opção de desfazer."
                 acoes={<Link className="btn btn-solid" href={rota("importacao/cruzamento")}><Icone nome="nuvem" /> Importar do cruzamento Domínio × SEFAZ</Link>} />

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
