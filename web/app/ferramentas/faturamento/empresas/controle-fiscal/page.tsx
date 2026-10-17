import { Suspense } from "react";
import { Carregando } from "@/components/ui";
import { ControleFiscal } from "./ControleFiscal";

export default function Pagina() {
  return <Suspense fallback={<Carregando />}><ControleFiscal /></Suspense>;
}
