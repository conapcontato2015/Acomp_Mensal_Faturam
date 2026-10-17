/* Formatação e leitura de números no padrão brasileiro (iguais às regras do servidor). */

export function moeda(v: number | string | null | undefined, vazio = "—"): string {
  if (v === null || v === undefined || v === "") return vazio;
  const n = typeof v === "string" ? Number(v) : v;
  if (Number.isNaN(n)) return vazio;
  return n.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function inteiro(v: number | string | null | undefined, vazio = "—"): string {
  if (v === null || v === undefined || v === "") return vazio;
  const n = typeof v === "string" ? Number(v) : v;
  if (Number.isNaN(n)) return vazio;
  return n.toLocaleString("pt-BR", { maximumFractionDigits: 0 });
}

/** "1.234,56", "1234,56", "1234.56", "6.370" (milhar) -> número; vazio -> null; inválido -> NaN. */
export function lerNumero(texto: string | null | undefined): number | null {
  if (texto === null || texto === undefined) return null;
  let t = String(texto).trim().replace(/R\$|\s/g, "");
  if (t === "") return null;
  if (!/^[-+]?[\d.,]+$/.test(t)) return NaN;
  if (t.includes(",")) t = t.replace(/\./g, "").replace(",", ".");
  else if ((t.match(/\./g) || []).length > 1) t = t.replace(/\./g, "");
  else if (/^[-+]?[1-9]\d*\.\d{3}$/.test(t)) t = t.replace(".", ""); // "6.370" é milhar; "0.125" é decimal
  const n = Number(t);
  if (Number.isNaN(n) || Math.abs(n) >= 1e13) return NaN;
  return n;
}

/** Quantidade: só inteiro (pontos apenas como milhar). null, número, NaN ou "fracao". */
export function lerInteiro(texto: string | null | undefined): number | null | "fracao" {
  if (texto === null || texto === undefined) return null;
  let t = String(texto).trim().replace(/\s/g, "");
  if (t === "") return null;
  if (/^[-+]?\d{1,3}(\.\d{3})+$/.test(t)) t = t.replace(/\./g, "");
  if (/^[-+]?\d+$/.test(t)) {
    const n = Number(t);
    return Math.abs(n) > 2147483647 ? NaN : n;
  }
  return Number.isNaN(lerNumero(t)) ? NaN : "fracao";
}

/** Valor da API ("1234.56" ou número) para o campo de edição ("1.234,56"). */
export function paraCampoMoeda(v: string | number | null | undefined): string {
  return v === null || v === undefined ? "" : moeda(v, "");
}

export function paraCampoInteiro(v: number | null | undefined): string {
  return v === null || v === undefined ? "" : inteiro(v, "");
}

const FUSO = "America/Fortaleza";

export function dataHora(iso: string | null | undefined): string {
  if (!iso) return "—";
  // A API devolve a hora de Fortaleza sem fuso ("2026-10-12T09:30:00"): mostra como está.
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (m) return `${m[3]}/${m[2]}/${m[1]} ${m[4]}:${m[5]}`;
  return new Date(iso).toLocaleString("pt-BR", { timeZone: FUSO });
}

export function data(iso: string | null | undefined): string {
  if (!iso) return "—";
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : iso;
}

export function hojeBr(): string {
  return new Date().toLocaleDateString("pt-BR", { timeZone: FUSO });
}

export function normalizar(t: string): string {
  return (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
}
