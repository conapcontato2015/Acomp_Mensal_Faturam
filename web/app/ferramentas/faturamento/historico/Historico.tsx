"use client";
/* Histórico: quem mudou o quê e quando (lançamentos, ajustes, conferência, cadastro, responsáveis). */
import { Cabecalho, CaixaErro, Carregando, Grupo } from "@/components/ui";
import { qs } from "@/lib/api";
import { dataHora } from "@/lib/formato";
import type { Usuario } from "@/lib/tipos";
import { useDados, useFiltros } from "@/lib/usar";

interface Mudanca { campo: string; antes: string | null; depois: string | null; tipo: "alterado" | "novo" | "removido" | "valor" }
interface RespHistorico {
  pagina: number; temProxima: boolean; filtro: { empresa: number | null; usuario: number | null };
  empresas: { id: number; nome: string }[]; usuarios: Usuario[];
  registros: { id: number; data: string; usuario: string | null; tabela: string; acao: string; empresaId: number | null; descricao: string | null; mudancas: Mudanca[] }[];
}

function Detalhe({ m }: { m: Mudanca[] }) {
  if (!m.length) return <span className="text-[var(--ink-3)]">—</span>;
  if (m.length === 1 && m[0].tipo === "valor") return <>{m[0].antes} → {m[0].depois}</>;
  return (
    <ul className="flex list-disc flex-col gap-0.5 pl-4">
      {m.map((x, i) => (
        <li key={i}>
          <span className="text-[var(--ink-3)]">{x.campo}:</span>{" "}
          {x.tipo === "novo" ? x.depois : x.tipo === "removido" ? <s>{x.antes}</s> : <>{x.antes} → <strong>{x.depois}</strong></>}
        </li>
      ))}
    </ul>
  );
}

export function Historico() {
  const f = useFiltros();
  const empresa = f.get("empresa"), usuario = f.get("usuario"), pagina = Number(f.get("pagina") || 1);
  const h = useDados<RespHistorico>(`/historico${qs({ empresa, usuario, pagina: pagina > 1 ? pagina : null })}`);
  const d = h.dados;
  return (
    <>
      <Cabecalho titulo="Histórico" descricao="Quem mudou o quê e quando: lançamentos, ajustes, conferência, cadastro e trocas de responsável."
                 acoes={d ? (
                   <>
                     <label className="campo min-w-[240px]"><span>Empresa</span>
                       <select className="entrada" value={empresa} onChange={(e) => f.set({ empresa: e.target.value, pagina: null })}>
                         <option value="">Todas</option>
                         {d.empresas.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}
                       </select></label>
                     <label className="campo min-w-[160px]"><span>Usuário</span>
                       <select className="entrada" value={usuario} onChange={(e) => f.set({ usuario: e.target.value, pagina: null })}>
                         <option value="">Todos</option>
                         {d.usuarios.map((u) => <option key={u.id} value={u.id}>{u.nome}</option>)}
                       </select></label>
                   </>
                 ) : null} />
      {h.erro ? <CaixaErro mensagens={h.erro.mensagens} onTentar={() => void h.recarregar()} /> : null}
      {!d ? (h.carregando ? <Carregando /> : null) : (
        <Grupo>
          {d.registros.length ? (
            <>
              <div className="rolagem">
                <table className="tabela">
                  <thead><tr><th>Data</th><th>Usuário</th><th>O que mudou</th><th>Detalhe</th></tr></thead>
                  <tbody>
                    {d.registros.map((r) => (
                      <tr key={r.id} className="align-top">
                        <td className="whitespace-nowrap text-[var(--ink-3)] tabular-nums">{dataHora(r.data)}</td>
                        <td>{r.usuario ?? "—"}</td>
                        <td className="font-medium">{r.descricao || r.acao}</td>
                        <td className="text-[13px]"><Detalhe m={r.mudancas} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {d.pagina > 1 || d.temProxima ? (
                <nav className="flex items-center gap-3 border-t border-[var(--line)] px-4 py-2.5 text-[13px]" aria-label="Páginas do histórico">
                  {d.pagina > 1 ? <button type="button" className="btn btn-quiet btn-sm" onClick={() => f.set({ pagina: d.pagina - 1 > 1 ? d.pagina - 1 : null })}>← Mais recentes</button> : null}
                  <span className="text-[var(--ink-3)]">Página {d.pagina}</span>
                  {d.temProxima ? <button type="button" className="btn btn-quiet btn-sm" onClick={() => f.set({ pagina: d.pagina + 1 })}>Mais antigas →</button> : null}
                </nav>
              ) : null}
            </>
          ) : <div className="vazio">Nenhuma alteração registrada{empresa || usuario ? " com esses filtros" : ""}{d.pagina > 1 ? " nesta página" : ""}.</div>}
        </Grupo>
      )}
    </>
  );
}
