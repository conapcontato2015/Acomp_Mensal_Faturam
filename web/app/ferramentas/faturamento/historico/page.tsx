import { Suspense } from "react";
import { Carregando } from "@/components/ui";
import { Historico } from "./Historico";

export default function Pagina() {
  return <Suspense fallback={<Carregando />}><Historico /></Suspense>;
}
