"use client";
/* Avisos rápidos (toast) no canto da tela. */
import { createContext, useCallback, useContext, useRef, useState } from "react";

type Tipo = "ok" | "erro" | "info";
interface Aviso { id: number; texto: string; tipo: Tipo }

const Contexto = createContext<(texto: string, tipo?: Tipo) => void>(() => {});

export function useAviso() {
  return useContext(Contexto);
}

export function ProvedorAvisos({ children }: { children: React.ReactNode }) {
  const [avisos, setAvisos] = useState<Aviso[]>([]);
  const seq = useRef(0);
  const avisar = useCallback((texto: string, tipo: Tipo = "ok") => {
    const id = ++seq.current;
    setAvisos((a) => [...a.slice(-3), { id, texto, tipo }]);
    setTimeout(() => setAvisos((a) => a.filter((x) => x.id !== id)), tipo === "erro" ? 8000 : 4000);
  }, []);
  return (
    <Contexto.Provider value={avisar}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex max-w-[min(440px,calc(100vw-32px))] flex-col gap-2" aria-live="polite" role="status">
        {avisos.map((a) => (
          <div key={a.id}
               className={`card px-4 py-3 text-sm shadow-[var(--shadow-md)] ${a.tipo === "erro" ? "border-[var(--danger)] bg-[var(--danger-soft)]" : a.tipo === "info" ? "bg-[var(--info-soft)]" : ""}`}>
            {a.tipo === "erro" ? <strong className="text-[var(--danger)]">Atenção: </strong> : null}{a.texto}
          </div>
        ))}
      </div>
    </Contexto.Provider>
  );
}
