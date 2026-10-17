import { Suspense } from "react";
import { Carregando } from "@/components/ui";
import { Plataforma } from "./Plataforma";

export default function Pagina() {
  return <Suspense fallback={<Carregando />}><Plataforma /></Suspense>;
}
