// Satu-satunya sumber kebenaran angka statistik landing page.
//
// Angka di bawah ini TERVERIFIKASI dari kode saat ini (2026-10-10),
// bukan karangan:
// - commands: 142 slash command (dihitung dengan _kumpulkan_perintah()
//   ASLI dari bot/src/cogs/general.py — dijalankan langsung di venv bot,
//   bukan AST: context menu & command hidden dikecualikan).
//   Breakdown: ekonomi 46, event 18, level 6, moderasi 11, server 9,
//   sosial 24, umum 18, utilitas 10.
// - plugins: 15 entri PLUGINS di dashboard/lib/plugins.ts (11 + 4 baru:
//   customcmd, slowmode, msglog, autopublish).
// - cogs: 44 file .py non-underscore di bot/src/cogs/.
//
// PENTING — koordinator audit: setiap ada fitur bot baru (command, cog,
// atau plugin bertambah/berkurang), angka di sini WAJIB di-refresh dari
// hasil verifikasi kode terbaru, bukan dari ingatan atau angka lama.
export const STATS = {
  commands: 142,
  plugins: 15,
  cogs: 44,
} as const;
