import { Suspense } from "react";
import { Carregando } from "@/components/ui";
import { Cruzamento } from "./Cruzamento";

export default function Pagina() {
  return <Suspense fallback={<Carregando />}><Cruzamento /></Suspense>;
}
