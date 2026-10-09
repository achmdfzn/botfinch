// Modul aman-untuk-client: tidak mengimpor next/headers.
// Komponen "use client" impor dari "@/lib/i18n/client", BUKAN dari "@/lib/i18n".
import { id } from "./id";
import { en } from "./en";

export type Lang = "id" | "en";
export type Dict = typeof id;

const DICTS: Record<Lang, Dict> = { id, en };

export { id, en };

/** Ambil kamus untuk bahasa tertentu. Fallback ke 'id' bila tidak dikenal. */
export function getDict(lang: Lang): Dict {
  return DICTS[lang] ?? DICTS.id;
}

/**
 * Interpolasi sederhana: fmt("Halo {name}", { name: "Finch" }).
 * Placeholder tanpa pasangan dibiarkan apa adanya (aman untuk string
 * seperti "Selamat datang {user}" yang diteruskan mentah ke bot).
 */
export function fmt(tmpl: string, vars: Record<string, string | number>): string {
  return tmpl.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}
