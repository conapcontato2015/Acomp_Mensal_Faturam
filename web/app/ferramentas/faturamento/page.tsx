import { Suspense } from "react";
import { Carregando } from "@/components/ui";
import { Painel } from "./Painel";

export default function Pagina() {
  return <Suspense fallback={<Carregando />}><Painel /></Suspense>;
}
