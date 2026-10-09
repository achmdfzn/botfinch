// lib/validate.ts — validator input API, gaya cleanValue di lib/settings.ts.
// Tiap fungsi kembalikan nilai bersih, atau undefined bila input tidak valid.
// Konvensi: null/absen pada field opsional = pakai default, bukan error.
import type { EmbedField } from "@/lib/db";

export const DISCORD_ID_RE = /^\d{5,25}$/;
const URL_RE = /^https?:\/\//i;
const COLOR_RE = /^[0-9A-Fa-f]{6}$/;

/** String biasa, dibatasi panjang (tanpa trim paksa pada hasil selain spasi ujung). */
export function str(v: unknown, max: number, required = false): string | undefined {
  if (typeof v !== "string") return undefined;
  const s = v.trim();
  if (required && s.length === 0) return undefined;
  return s.length <= max ? s : undefined;
}

/** String opsional: absen/null = fallback, selain itu harus string dalam batas. */
export function optStr(v: unknown, max: number, fallback = ""): string | undefined {
  if (v === undefined || v === null) return fallback;
  return str(v, max);
}

/** ID Discord (channel, role, message, user). */
export function discordId(v: unknown): string | undefined {
  const s = typeof v === "string" ? v.trim() : "";
  return DISCORD_ID_RE.test(s) ? s : undefined;
}

/** URL opsional: kosong = "", selain itu harus http(s) dan dalam batas panjang. */
export function httpUrl(v: unknown, max = 500): string | undefined {
  if (v === undefined || v === null) return "";
  if (typeof v !== "string") return undefined;
  const s = v.trim();
  if (s === "") return "";
  if (s.length > max || !URL_RE.test(s)) return undefined;
  return s;
}

/** Warna hex 6 char (huruf besar OK), dinormalisasi ke uppercase. */
export function hexColor(v: unknown, fallback: string): string | undefined {
  if (v === undefined || v === null || v === "") return fallback;
  if (typeof v !== "string") return undefined;
  const s = v.trim();
  return COLOR_RE.test(s) ? s.toUpperCase() : undefined;
}

/** Array field embed, maks 10: tiap {name≤256, value≤1024, inline? bool}. */
export function embedFields(v: unknown): EmbedField[] | undefined {
  if (v === undefined || v === null) return [];
  if (!Array.isArray(v) || v.length > 10) return undefined;
  const out: EmbedField[] = [];
  for (const f of v) {
    if (!f || typeof f !== "object") return undefined;
    const o = f as Record<string, unknown>;
    const name = str(o.name, 256, true);
    const value = str(o.value, 1024, true);
    if (name === undefined || value === undefined) return undefined;
    if (o.inline !== undefined && typeof o.inline !== "boolean") return undefined;
    out.push(
      typeof o.inline === "boolean" ? { name, value, inline: o.inline } : { name, value },
    );
  }
  return out;
}

/** interval_minutes: absen/null = null, selain itu int 5..43200. */
export function intervalMinutes(v: unknown): number | null | undefined {
  if (v === undefined || v === null) return null;
  if (typeof v !== "number" || !Number.isInteger(v) || v < 5 || v > 43200) return undefined;
  return v;
}

/** run_at: absen/null/kosong = null, selain itu harus string ISO valid. */
export function isoDateTime(v: unknown): string | null | undefined {
  if (v === undefined || v === null || v === "") return null;
  if (typeof v !== "string") return undefined;
  const s = v.trim();
  return Number.isNaN(Date.parse(s)) ? undefined : s;
}
