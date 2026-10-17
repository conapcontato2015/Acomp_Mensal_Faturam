import { Suspense } from "react";
import { Carregando } from "@/components/ui";
import { Importacao } from "./Importacao";

export default function Pagina() {
  return <Suspense fallback={<Carregando />}><Importacao /></Suspense>;
}
