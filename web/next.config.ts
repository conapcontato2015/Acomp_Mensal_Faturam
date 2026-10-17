import type { NextConfig } from "next";

/**
 * Local: `npm run build` gera o export estático em `out/`, servido pelo FastAPI (servidor.py) em
 * /ferramentas/faturamento — o mesmo caminho da ferramenta no Conap Ferramentas.
 * Em desenvolvimento (`npm run dev`), /api é encaminhado ao FastAPI local (porta 5000).
 */
const desenvolvimento = process.env.NODE_ENV !== "production";
const api = process.env.FATURAMENTO_API ?? "http://127.0.0.1:5000";

const config: NextConfig = {
  output: desenvolvimento ? undefined : "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
  poweredByHeader: false,
  ...(desenvolvimento
    ? { async rewrites() { return [{ source: "/api/:caminho*", destination: `${api}/api/:caminho*` }]; } }
    : {}),
};

export default config;
