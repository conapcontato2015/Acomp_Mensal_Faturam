import { Suspense } from "react";
import { Carregando } from "@/components/ui";
import { EmpresaForm } from "./EmpresaForm";

export default function Pagina() {
  return <Suspense fallback={<Carregando />}><EmpresaForm /></Suspense>;
}
