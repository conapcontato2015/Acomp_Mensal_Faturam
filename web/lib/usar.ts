"use client";
/* Hooks das telas: carregar dados da API e ler/escrever filtros na URL. */
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ErroApi } from "./api";

export const BASE = "/ferramentas/faturamento";

export function rota(caminho = "", params: Record<string, string | number | null | undefined | (string | number)[]> = {}): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => u.append(k, String(x)));
    else u.append(k, String(v));
  }
  const limpo = caminho.replace(/^\/+|\/+$/g, "");
  const s = u.toString();
  return `${BASE}/${limpo ? limpo + "/" : ""}${s ? "?" + s : ""}`;
}

export interface Estado<T> {
  dados: T | null;
  erro: ErroApi | null;
  carregando: boolean;
  recarregar: () => Promise<void>;
  setDados: (d: T | null | ((atual: T | null) => T | null)) => void;
}

/** Busca ``caminho`` na API sempre que ele muda (null = não busca). */
export function useDados<T>(caminho: string | null): Estado<T> {
  const [dados, setDados] = useState<T | null>(null);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const [carregando, setCarregando] = useState<boolean>(!!caminho);
  const atual = useRef<string | null>(caminho);
  atual.current = caminho;

  const carregar = useCallback(async () => {
    if (!caminho) { setCarregando(false); return; }
    setCarregando(true);
    try {
      const d = await api<T>(caminho);
      if (atual.current === caminho) { setDados(d); setErro(null); }
    } catch (e) {
      if (atual.current === caminho) setErro(e instanceof ErroApi ? e : new ErroApi(0, "erro", [String(e)]));
    } finally {
      if (atual.current === caminho) setCarregando(false);
    }
  }, [caminho]);

  useEffect(() => { void carregar(); }, [carregar]);
  return { dados, erro, carregando, recarregar: carregar, setDados };
}

/** Filtros na URL (?competencia=…&carteira=…): ler e trocar sem recarregar a página. */
export function useFiltros() {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const get = (k: string) => sp.get(k) ?? "";
  const getAll = (k: string) => sp.getAll(k);
  const set = (mudancas: Record<string, string | number | null | undefined | (string | number)[]>) => {
    const u = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(mudancas)) {
      u.delete(k);
      if (v === null || v === undefined || v === "") continue;
      if (Array.isArray(v)) v.forEach((x) => u.append(k, String(x)));
      else u.set(k, String(v));
    }
    const s = u.toString();
    router.replace(`${pathname}${s ? "?" + s : ""}`, { scroll: false });
  };
  return { get, getAll, set, params: sp };
}
