# Kontrak Tema + i18n — Dashboard Finch

Fondasi untuk worker lain. Baca sebelum menyentuh halaman/komponen.

## 1. Sistem tema (Tailwind 4, CSS-variable based)

Token warna hidup di `app/globals.css`:

| Token (class)      | Dark (default) | Light (`html.light`) | Pakai untuk            |
|--------------------|----------------|----------------------|------------------------|
| `bg-ink`           | `#0b0d10`      | `#f7f8fa`            | background halaman     |
| `bg-panel`         | `#13161b`      | `#ffffff`            | kartu / panel          |
| `border-edge`      | `#23282f`      | `#e4e7ec`            | border, divider        |
| `text-fg`          | `#f4f4f5`      | `#14181d`            | teks utama             |
| `text-muted`       | `#a1a1aa`      | `#5b6470`            | teks sekunder          |
| `bg-brand` / `text-brand` | `#2EC4B6` (tetap di dua tema) | aksen satu-satunya |

Token diimplementasikan via `@theme inline` yang merujuk ke CSS var
(`--bg`, `--panel`, `--edge`, `--fg`, `--muted`, `--brand`), sehingga satu
class seperti `bg-panel` otomatis mengikuti tema aktif.

**Aturan keras:**

- Jangan hardcode warna (`bg-[#...]`, `text-white`, `bg-zinc-900`) kecuali
  pengecualian yang didokumentasikan di bawah.
- Jangan pakai `text-zinc-*` / `bg-zinc-*` lagi. Mapping migrasi:
  - `text-zinc-50`, `text-zinc-100`, `text-zinc-200`, `text-zinc-300` → `text-fg`
  - `text-zinc-400` → `text-muted`
  - `text-zinc-500` → `text-muted` (konteks: teks tersier; di light theme
    muted = `#5b6470`, kontras tetap aman)
  - `hover:text-zinc-100` / `hover:text-zinc-200` → `hover:text-fg`
  - `hover:text-zinc-300` → `hover:text-fg`
  - `ring-zinc-100` → `ring-fg`
  - `bg-ink`, `bg-panel`, `bg-edge`, `border-edge`, `divide-edge`,
    `bg-brand`, `text-brand`, `outline-brand` → **tidak berubah** (sudah
    theme-aware).
- Warna semantik sukses/gagal (`text-green-400`, `text-red-400`,
  `bg-red-500/10`, dsb.) **tetap** dipakai apa adanya, sama seperti bot.
- Pengecualian tercatat: `components/EmbedBuilder.tsx` memakai
  `bg-[#1e1f22]` / `bg-[#2b2d31]` untuk kotak *pratinjau embed*. Itu tiruan
  tampilan Discord yang warnanya tetap gelap; biarkan hardcoded (alasan:
  preview harus terlihat seperti di Discord, bukan mengikuti tema dasbor).
- Toggle tema: `components/ThemeToggle.tsx` (client). Menyimpan
  `localStorage 'finch-theme'`, class `light` di `<html>`. Script anti-FOUC
  di `app/layout.tsx` memasang class SEBELUM paint; jangan pindahkan.
- R-34: bila menambah warna/elemen baru, verifikasi di DUA tema.

## 2. Sistem i18n (ID default, EN)

- Kamus: `lib/i18n/id.ts` (sumber kebenaran) dan `lib/i18n/en.ts`.
  `en: Dict` (`Dict = typeof id`) membuat TypeScript **memaksa** struktur
  identik. Tambah key = wajib di dua file, atau build gagal.
- Namespace: `nav`, `auth`, `theme`, `lang`, `common`, `loading`, `errors`,
  `landing`, `dashboard`, `guild.{common,subnav,overview,modul,leaderboard,
  selfroles,responder,giveaway,embed,pengumuman,modlog}`, `settings`
  (termasuk `settings.modules.<key>.fields` untuk label/hint/placeholder
  SettingsForm).
- `lib/i18n/index.ts` (server only): `getLang()` baca cookie `finch-lang`,
  `getDict(lang)`, `fmt(tmpl, vars)` untuk interpolasi `{var}`.
- `lib/i18n/client.ts`: versi aman-client (`getDict`, `fmt`, tipe).
  **Jangan impor `@/lib/i18n` dari Client Component** (menarik
  `next/headers`, build error).

### Server Component

```tsx
import { getDict, getLang } from "@/lib/i18n";

export default async function Page() {
  const dict = getDict(await getLang());
  return <h1>{dict.dashboard.title}</h1>;
}
```

### Client Component

```tsx
"use client";
import { useI18n } from "@/components/I18nProvider";
import { fmt } from "@/lib/i18n/client";

export function Tombol({ n }: { n: number }) {
  const { dict } = useI18n();
  return <button>{fmt(dict.guild.selfroles.listTitle, { n })}</button>;
}
```

Ganti bahasa: `const { setLang } = useI18n(); setLang("en")` — tulis cookie
`finch-lang` (1 tahun) + localStorage + `document.documentElement.lang` +
`router.refresh()`. `<html lang>` awal di-set server di `app/layout.tsx`.

### Metadata per halaman (pola untuk worker)

Ganti `export const metadata = {...}` menjadi:

```tsx
import type { Metadata } from "next";
import { getDict, getLang } from "@/lib/i18n";

export async function generateMetadata(): Promise<Metadata> {
  const dict = getDict(await getLang());
  return { title: `${dict.dashboard.metaTitle} | Finch Dashboard` };
}
```

Judul memakai pola `{dict.<ns>.metaTitle} | Finch Dashboard` mengikuti
konvensi lama. Contoh sudah jalan: `app/layout.tsx` (`landing.metaTitle`,
`landing.metaDescription`).

### Keputusan penamaan (catat, jangan diubah sepihak)

- "Finch" dan "Discord" tidak pernah diterjemahkan.
- Nama fitur dipertahankan apa adanya di dua bahasa (istilah Discord/bot,
  menerjemahkan justru membingungkan): Self-roles, Giveaway, Mod Log,
  Embed, Auto-responder, Leaderboard, Starboard, AutoMod, Welcome, Leveling.
- Kata umum diterjemahkan: Modul→Modules, Pengaturan→Settings,
  Pengumuman→Announcements, Ekonomi→Economy, Server Saya→My Servers.
- Plural: dihindari total. Pola netral + `{n}` di dua bahasa
  (cth. `listTitle: "Daftar self-role ({n})"` / `"Self-role list ({n})"`).
  `fmt()` membiarkan placeholder tanpa pasangan apa adanya, jadi string
  berisi `{user}`/`{server}` untuk bot aman diteruskan mentah.
- Tanpa em dash (R-02) di string baru; dua em dash warisan di copy lama
  sudah dinormalisasi di kamus (`:` sebagai pengganti).

### Contoh referensi

`components/SiteHeader.tsx`: Server Component + `getLang()`/`getDict()`,
token semantik, `ThemeToggle` + `LangSwitcher` di nav,
`components/AuthButtons.tsx` memakai `useI18n()` internal (tanpa ubah props).
