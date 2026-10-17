import { Suspense } from "react";
import { Carregando } from "@/components/ui";
import { Tipos } from "./Tipos";

export default function Pagina() {
  return <Suspense fallback={<Carregando />}><Tipos /></Suspense>;
}
