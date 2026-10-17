import { Suspense } from "react";
import { Carregando } from "@/components/ui";
import { Conferencia } from "./Conferencia";

export default function Pagina() {
  return <Suspense fallback={<Carregando />}><Conferencia /></Suspense>;
}
