import Link from "next/link";

/* A raiz só leva para a ferramenta (o servidor.py também redireciona). */
export default function Raiz() {
  return (
    <main className="vazio">
      <meta httpEquiv="refresh" content="0; url=/ferramentas/faturamento/" />
      <Link href="/ferramentas/faturamento/" className="btn btn-solid">Abrir o Faturamento</Link>
    </main>
  );
}
