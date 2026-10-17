import { Suspense } from "react";
import { Carregando } from "@/components/ui";
import { Lancamento } from "./Lancamento";

export default function Pagina() {
  return <Suspense fallback={<Carregando />}><Lancamento /></Suspense>;
}
