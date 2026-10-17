"use client";
/* Quem está usando: no PC, a janela "Quem está usando?"; no Conap Ferramentas, o login da plataforma. */
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Sessao as TSessao, Usuario } from "@/lib/tipos";
import { Icone } from "./Icone";
import { CaixaErro, Carregando } from "./ui";

interface Ctx { sessao: TSessao | null; usuario: Usuario | null; recarregar: () => Promise<void>; trocarUsuario: () => Promise<void> }
const Contexto = createContext<Ctx>({ sessao: null, usuario: null, recarregar: async () => {}, trocarUsuario: async () => {} });

export function useSessao() {
  return useContext(Contexto);
}

export function ProvedorSessao({ children, topo }: { children: React.ReactNode; topo?: React.ReactNode }) {
  const [sessao, setSessao] = useState<TSessao | null>(null);
  const [erro, setErro] = useState<string[] | null>(null);

  const recarregar = useCallback(async () => {
    try {
      setSessao(await api<TSessao>("/sessao"));
      setErro(null);
    } catch (e) {
      setErro((e as { mensagens?: string[] }).mensagens ?? ["Não foi possível falar com o sistema."]);
    }
  }, []);

  const trocarUsuario = useCallback(async () => {
    await api("/sessao", "DELETE");
    await recarregar();
  }, [recarregar]);

  useEffect(() => {
    void recarregar();
    const semSessao = () => void recarregar();
    window.addEventListener("fat:sem-sessao", semSessao);
    return () => window.removeEventListener("fat:sem-sessao", semSessao);
  }, [recarregar]);

  const valor = { sessao, usuario: sessao?.usuario ?? null, recarregar, trocarUsuario };
  let conteudo: React.ReactNode = children;
  if (erro) conteudo = <div className="mx-auto max-w-xl p-6"><CaixaErro mensagens={erro} onTentar={() => void recarregar()} /></div>;
  else if (!sessao) conteudo = <Carregando />;
  else if (!sessao.usuario) conteudo = sessao.modoAuth === "local" ? <EscolherUsuario sessao={sessao} aoEntrar={recarregar} /> : <SemLoginPlataforma />;
  return <Contexto.Provider value={valor}>{topo}{conteudo}</Contexto.Provider>;
}

function EscolherUsuario({ sessao, aoEntrar }: { sessao: TSessao; aoEntrar: () => Promise<void> }) {
  const [enviando, setEnviando] = useState<number | null>(null);
  const [erro, setErro] = useState<string[] | null>(null);
  const entrar = async (u: Usuario) => {
    setEnviando(u.id);
    try {
      await api("/sessao", "POST", { usuarioId: u.id });
      await aoEntrar();
    } catch (e) {
      setErro((e as { mensagens?: string[] }).mensagens ?? ["Não foi possível entrar."]);
      setEnviando(null);
    }
  };
  return (
    <div className="mx-auto flex min-h-[60vh] max-w-xl flex-col justify-center gap-6 p-6">
      <div>
        <p className="text-[13px] font-medium text-[var(--brand)]">Faturamento</p>
        <h1 className="mt-1 text-[28px] font-semibold">Quem está usando?</h1>
        <p className="mt-1 text-[var(--ink-2)]">Os lançamentos e a carteira ficam associados ao nome escolhido.</p>
      </div>
      {erro ? <CaixaErro mensagens={erro} /> : null}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {sessao.usuarios.map((u) => (
          <button key={u.id} type="button" disabled={enviando !== null} onClick={() => void entrar(u)}
                  className="card card-hover flex items-center gap-3 p-4 text-left disabled:opacity-60">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-[var(--brand-soft)] font-display text-[18px] font-semibold text-[var(--brand)]">
              {u.nome.slice(0, 1).toUpperCase()}
            </span>
            <span className="flex-1 text-[16px] font-medium">{u.nome}</span>
            <Icone nome="seta" className="text-[var(--ink-3)]" />
          </button>
        ))}
      </div>
      <p className="text-[13px] text-[var(--ink-3)]">Sem senha: no Conap Ferramentas o usuário virá do login da plataforma.</p>
    </div>
  );
}

function SemLoginPlataforma() {
  return (
    <div className="mx-auto max-w-xl p-6">
      <CaixaErro mensagens={["Usuário não reconhecido. Entre pelo Conap Ferramentas e abra o Faturamento de novo."]} />
    </div>
  );
}
