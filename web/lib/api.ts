/* Chamadas à API do Faturamento (/api/faturamento). Mesmo domínio: o cookie de sessão (local) ou o JWT da
   plataforma vão juntos. Escrita sempre em JSON (ou upload com X-Requested-With) — proteção contra CSRF. */

export const API = "/api/faturamento";

export class ErroApi extends Error {
  status: number;
  codigo: string;
  mensagens: string[];
  constructor(status: number, codigo: string, mensagens: string[]) {
    super(mensagens.join(" "));
    this.status = status;
    this.codigo = codigo;
    this.mensagens = mensagens;
  }
}

type Metodo = "GET" | "POST" | "PUT" | "DELETE";

async function tratar<T>(resp: Response): Promise<T> {
  let dados: unknown = null;
  const tipo = resp.headers.get("content-type") || "";
  if (tipo.includes("application/json")) {
    try { dados = await resp.json(); } catch { dados = null; }
  }
  if (!resp.ok) {
    const d = (dados || {}) as { erro?: string; mensagens?: string[] };
    const msgs = d.mensagens && d.mensagens.length ? d.mensagens : [`Erro ${resp.status} ao falar com o servidor.`];
    const erro = new ErroApi(resp.status, d.erro || "erro", msgs);
    if (resp.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("fat:sem-sessao"));
    }
    throw erro;
  }
  return dados as T;
}

export async function api<T = unknown>(caminho: string, metodo: Metodo = "GET", corpo?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", "X-Requested-With": "fetch" };
  if (corpo !== undefined) headers["Content-Type"] = "application/json";
  let resp: Response;
  try {
    resp = await fetch(API + caminho, {
      method: metodo,
      headers,
      credentials: "same-origin",
      cache: "no-store",
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
    });
  } catch {
    throw new ErroApi(0, "rede", ["Sem conexão com o sistema. Ele está aberto no computador?"]);
  }
  return tratar<T>(resp);
}

export async function enviarArquivo<T = unknown>(caminho: string, campos: Record<string, string | Blob>): Promise<T> {
  const fd = new FormData();
  for (const [k, v] of Object.entries(campos)) fd.append(k, v);
  let resp: Response;
  try {
    resp = await fetch(API + caminho, {
      method: "POST",
      body: fd,
      credentials: "same-origin",
      headers: { Accept: "application/json", "X-Requested-With": "fetch" },
    });
  } catch {
    throw new ErroApi(0, "rede", ["Sem conexão com o sistema. Ele está aberto no computador?"]);
  }
  return tratar<T>(resp);
}

/** Monta a query string ignorando vazios; listas viram parâmetros repetidos (?empresa=1&empresa=2). */
export function qs(params: Record<string, string | number | boolean | null | undefined | (string | number)[]>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => u.append(k, String(x)));
    else u.append(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}

/** URL de download (Excel, CSV) dentro da API. */
export const urlApi = (caminho: string) => API + caminho;
