import type { Metadata } from "next";
import { Suspense } from "react";
import { ProvedorAvisos } from "@/components/Avisos";
import { Casca } from "@/components/Casca";
import { ProvedorSessao } from "@/components/Sessao";
import { Topo } from "@/components/Topo";
import { Carregando } from "@/components/ui";

export const metadata: Metadata = { title: "Faturamento" };

/* Dentro do Conap Ferramentas o topo é o da plataforma: defina NEXT_PUBLIC_DENTRO_DA_PLATAFORMA=1. */
const SOZINHO = process.env.NEXT_PUBLIC_DENTRO_DA_PLATAFORMA !== "1";

export default function LayoutFaturamento({ children }: { children: React.ReactNode }) {
  return (
    <ProvedorAvisos>
      <ProvedorSessao topo={SOZINHO ? <Topo /> : null}>
        <Suspense fallback={<Carregando />}>
          <Casca>{children}</Casca>
        </Suspense>
      </ProvedorSessao>
    </ProvedorAvisos>
  );
}
