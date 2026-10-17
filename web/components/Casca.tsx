"use client";
/* Layout interno da ferramenta, como as demais do Conap Ferramentas: breadcrumb, sub-navegação lateral
   com as seções e o conteúdo. */
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { BASE } from "@/lib/usar";
import { Icone } from "./Icone";

export const SECOES = [
  { caminho: "", rotulo: "Painel do mês", icone: "painel" },
  { caminho: "lancamento", rotulo: "Lançamento", icone: "lancamento" },
  { caminho: "conferencia", rotulo: "Conferência", icone: "conferencia" },
  { caminho: "empresas", rotulo: "Empresas", icone: "empresas" },
  { caminho: "tipos-documento", rotulo: "Tipos de documento", icone: "tipos" },
  { caminho: "importacao", rotulo: "Importações", icone: "importar" },
  { caminho: "historico", rotulo: "Histórico", icone: "historico" },
] as const;

function secaoAtual(pathname: string) {
  const resto = pathname.replace(BASE, "").replace(/^\/+|\/+$/g, "").split("/")[0] ?? "";
  return SECOES.find((s) => s.caminho === resto) ?? SECOES[0];
}

export function Casca({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || BASE;
  const sp = useSearchParams();
  const atual = secaoAtual(pathname);
  // A competência escolhida acompanha a navegação entre as seções.
  const comp = sp.get("competencia");
  const link = (caminho: string) => `${BASE}/${caminho ? caminho + "/" : ""}${comp ? `?competencia=${comp}` : ""}`;
  // Folhas de impressão (…/imprimir/) aparecem sozinhas, sem o menu lateral.
  if (/\/imprimir\/?$/.test(pathname)) return <main className="px-4 py-5 sm:px-6 print:p-0" id="conteudo">{children}</main>;
  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 sm:px-6 lg:flex-row lg:gap-8">
      <aside className="nao-imprimir lg:w-[232px] lg:shrink-0">
        <nav aria-label="Seções do Faturamento" className="lg:sticky lg:top-20">
          <ol className="mb-3 hidden flex-wrap items-center gap-1 text-[13px] text-[var(--ink-3)] lg:flex" aria-label="Caminho">
            <li>Ferramentas</li><li aria-hidden="true">›</li>
            <li><Link href={`${BASE}/`} className="hover:text-[var(--ink)]">Faturamento</Link></li>
          </ol>
          <ul className="relative -mx-1 flex gap-1 overflow-x-auto pb-1 lg:mx-0 lg:flex-col lg:overflow-visible lg:pb-0">
            {SECOES.map((s) => {
              const ativa = s.caminho === atual.caminho;
              return (
                <li key={s.caminho} className="shrink-0">
                  <Link href={link(s.caminho)} aria-current={ativa ? "page" : undefined}
                        className={`flex items-center gap-3 rounded-[10px] px-3 py-2 text-[14px] font-medium transition-colors ${
                          ativa ? "bg-[var(--surface)] text-[var(--ink)] shadow-[0_0_0_1px_var(--line)]" : "text-[var(--ink-2)] hover:bg-[var(--bg-soft)] hover:text-[var(--ink)]"}`}>
                    <Icone nome={s.icone} className={ativa ? "text-[var(--brand)]" : ""} />
                    {s.rotulo}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      </aside>
      <main className="flex min-w-0 flex-1 flex-col gap-5" id="conteudo">
        <ol className="flex flex-wrap items-center gap-1 text-[13px] text-[var(--ink-3)] lg:hidden nao-imprimir" aria-label="Caminho">
          <li>Ferramentas</li><li aria-hidden="true">›</li><li>Faturamento</li><li aria-hidden="true">›</li>
          <li className="text-[var(--ink-2)]">{atual.rotulo}</li>
        </ol>
        {children}
      </main>
    </div>
  );
}
