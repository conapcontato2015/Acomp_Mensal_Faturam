import { Suspense } from "react";
import { Carregando } from "@/components/ui";
import { Responsaveis } from "./Responsaveis";

export default function Pagina() {
  return <Suspense fallback={<Carregando />}><Responsaveis /></Suspense>;
}
