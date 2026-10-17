"use client";
/* Janela modal (dialog nativo: foco preso, Esc fecha, fundo escurecido). */
import { useEffect, useRef } from "react";
import { Icone } from "./Icone";

export function Janela({ aberta, aoFechar, titulo, subtitulo, children, rodape, largura }: {
  aberta: boolean; aoFechar: () => void; titulo: React.ReactNode; subtitulo?: React.ReactNode;
  children: React.ReactNode; rodape?: React.ReactNode; largura?: number;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (aberta && !d.open) d.showModal();
    if (!aberta && d.open) d.close();
  }, [aberta]);
  return (
    <dialog ref={ref} className="janela" onClose={aoFechar} onCancel={(e) => { e.preventDefault(); aoFechar(); }}
            style={largura ? { width: `min(${largura}px, calc(100vw - 32px))` } : undefined} aria-label={typeof titulo === "string" ? titulo : undefined}>
      {aberta ? (
        <div className="flex max-h-[calc(100vh-48px)] flex-col">
          <div className="flex items-start justify-between gap-3 border-b border-[var(--line)] px-5 py-4">
            <div className="min-w-0">
              <h2 className="text-[18px] font-semibold">{titulo}</h2>
              {subtitulo ? <p className="text-[13px] text-[var(--ink-3)]">{subtitulo}</p> : null}
            </div>
            <button type="button" className="btn btn-quiet btn-icon" onClick={aoFechar} aria-label="Fechar"><Icone nome="fechar" /></button>
          </div>
          <div className="flex flex-col gap-4 overflow-y-auto px-5 py-4">{children}</div>
          {rodape ? <div className="flex flex-wrap justify-end gap-2 border-t border-[var(--line)] px-5 py-3">{rodape}</div> : null}
        </div>
      ) : null}
    </dialog>
  );
}
