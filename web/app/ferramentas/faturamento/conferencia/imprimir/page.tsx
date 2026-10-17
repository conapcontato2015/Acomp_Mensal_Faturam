import { Suspense } from "react";
import { Carregando } from "@/components/ui";
import { Imprimir } from "./Imprimir";

export default function Pagina() {
  return <Suspense fallback={<Carregando />}><Imprimir /></Suspense>;
}
