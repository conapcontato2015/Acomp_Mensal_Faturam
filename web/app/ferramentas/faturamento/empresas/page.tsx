import { Suspense } from "react";
import { Carregando } from "@/components/ui";
import { Empresas } from "./Empresas";

export default function Pagina() {
  return <Suspense fallback={<Carregando />}><Empresas /></Suspense>;
}
