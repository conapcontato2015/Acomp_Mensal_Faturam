"use client";
/* Escolher várias empresas com pesquisa (lista suspensa com caixas de marcar). */
import { useEffect, useRef, useState } from "react";
import { normalizar } from "@/lib/formato";

export interface OpcaoEmpresa { id: number; nome: string }

export function SeletorEmpresas({ opcoes, escolhidas, aoAplicar, rotulo = "Empresas" }: {
  opcoes: OpcaoEmpresa[]; escolhidas: number[]; aoAplicar: (ids: number[]) => void; rotulo?: string;
}) {
  const [aberto, setAberto] = useState(false);
  const [busca, setBusca] = useState("");
  const [marcadas, setMarcadas] = useState<Set<number>>(new Set(escolhidas));
  const caixa = useRef<HTMLDivElement>(null);
  const chave = escolhidas.join(",");

  useEffect(() => { setMarcadas(new Set(chave ? chave.split(",").map(Number) : [])); }, [chave]);
  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => { if (caixa.current && !caixa.current.contains(e.target as Node)) setAberto(false); };
    document.addEventListener("mousedown", fora);
    return () => document.removeEventListener("mousedown", fora);
  }, [aberto]);

  const termo = normalizar(busca);
  const visiveis = opcoes.filter((o) => !termo || normalizar(o.nome).includes(termo));
  const alternar = (id: number) => setMarcadas((m) => { const n = new Set(m); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const aplicar = () => { setAberto(false); setBusca(""); aoAplicar(opcoes.filter((o) => marcadas.has(o.id)).map((o) => o.id)); };

  return (
    <div ref={caixa} className="relative" onKeyDown={(e) => { if (e.key === "Escape") setAberto(false); }}>
      <label className="campo">
        <span>{rotulo}</span>
        <input type="search" className="entrada min-w-[260px]" value={busca} autoComplete="off" aria-expanded={aberto} aria-controls="painel-empresas"
               placeholder={escolhidas.length ? `${escolhidas.length} selecionada(s) — pesquisar…` : "Pesquisar e escolher empresas…"}
               onFocus={() => setAberto(true)} onChange={(e) => { setBusca(e.target.value); setAberto(true); }}
               onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); aplicar(); } }} />
      </label>
      {aberto ? (
        <div id="painel-empresas" className="card absolute left-0 top-[calc(100%+6px)] z-20 w-[min(420px,90vw)] shadow-[var(--shadow-md)]">
          <div className="flex max-h-[300px] flex-col overflow-y-auto p-2" role="group" aria-label="Escolher empresas">
            {visiveis.map((o) => (
              <label key={o.id} className="flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2 text-[14px] hover:bg-[var(--bg-soft)]">
                <input type="checkbox" className="check" checked={marcadas.has(o.id)} onChange={() => alternar(o.id)} /> {o.nome}
              </label>
            ))}
            {!visiveis.length ? <p className="p-2 text-[13px] text-[var(--ink-3)]">Nenhuma empresa com esse nome.</p> : null}
          </div>
          <div className="flex flex-wrap items-center gap-2 border-t border-[var(--line)] px-3 py-2">
            <button type="button" className="btn btn-quiet btn-sm" onClick={() => setMarcadas((m) => new Set([...m, ...visiveis.map((o) => o.id)]))}>Marcar as encontradas</button>
            <button type="button" className="btn btn-quiet btn-sm" onClick={() => setMarcadas(new Set())}>Limpar</button>
            <button type="button" className="btn btn-solid btn-sm ml-auto" onClick={aplicar}>Exibir</button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
