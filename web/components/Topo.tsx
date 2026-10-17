"use client";
/* Barra do topo no estilo do Conap Ferramentas. Só existe quando o Faturamento roda sozinho (no PC):
   dentro da plataforma, o topo é o dela. */
import Link from "next/link";
import { BASE } from "@/lib/usar";
import { Icone } from "./Icone";
import { useSessao } from "./Sessao";

export function Topo() {
  const { sessao, usuario, trocarUsuario } = useSessao();
  return (
    <header className="sticky top-0 z-30 border-b border-[var(--line)] bg-[color-mix(in_srgb,var(--surface)_88%,transparent)] backdrop-blur nao-imprimir">
      <div className="mx-auto flex h-14 max-w-[1440px] items-center gap-4 px-4 sm:px-6">
        <Link href={`${BASE}/`} className="flex items-center gap-3" aria-label="Início do Faturamento">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo-conap.png" alt="CONAP" className="h-6 w-auto dark:hidden" />
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo-conap-branco.png" alt="" className="hidden h-6 w-auto dark:block" />
          <span className="hidden border-l border-[var(--line)] pl-3 font-display text-[15px] font-semibold text-[var(--ink-2)] sm:inline">Ferramentas</span>
        </Link>
        <span className="flex-1" />
        {usuario ? (
          <div className="flex items-center gap-2">
            <span className="grid h-8 w-8 place-items-center rounded-full bg-[var(--brand-soft)] font-display text-[14px] font-semibold text-[var(--brand)]" aria-hidden="true">
              {usuario.nome.slice(0, 1).toUpperCase()}
            </span>
            <span className="hidden text-[14px] leading-tight sm:block">
              <span className="block font-medium">{usuario.nome}</span>
              <span className="block text-[12px] text-[var(--ink-3)]">Faturamento · v{sessao?.versao}</span>
            </span>
            {sessao?.modoAuth === "local" ? (
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => void trocarUsuario()} title="Trocar usuário">
                <Icone nome="sair" tamanho={16} /> <span className="hidden sm:inline">Trocar</span>
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    </header>
  );
}
