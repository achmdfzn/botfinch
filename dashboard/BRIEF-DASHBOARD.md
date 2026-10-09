# Brief: Dashboard Web Finch (Next.js + Anti-Slop + Login Discord)

Disiapkan 2026-10-08 ~18:05 WIB untuk permintaan Fauzan di chat "bot discord finch".
`antislop.md` (719 baris, MIT, repo github.com/miqdadbadjuber/anti-slop, commit 388cbe3b6c37d5175b9f460015bb092ef9e34894) sudah terunduh ke folder proyek ini — pakai sebagai filter desain saat membangun (mode **"during"**, karena dashboard dibangun dari nol; bukan "after").

## Data yang tersedia (sudah terverifikasi dari kode bot)

- Bot jalan di PC Fauzan: `C:\xampp\htdocs\botfinch`, DB SQLite di `data\finch.db`.
- Dashboard bawaan bot (aiohttp) di `http://127.0.0.1:8080` dengan endpoint JSON **`GET /api/stats`** → `{ guilds, total_members, total_commands }` (lihat `~/workspace/discord-bot-finch/src/cogs/utilitas.py` baris 205–223).
- Tabel DB yang relevan: `users(user_id, level, xp)`, `economy(user_id, balance)`.
- Scaffold Next.js sudah ada di folder ini (Next 16.4.0, React 19, Tailwind 4).

Jalur termudah: Next.js jalan di PC yang sama (`localhost:3000`), API route-nya proxy ke `http://127.0.0.1:8080/api/stats`. Tidak perlu modul native SQLite di Next.js (hindari `better-sqlite3` = compile native di Windows = masalah).

## Scope yang jujur

- **v1 (bisa langsung):** landing page + tombol "Invite Bot" + login Discord + halaman statistik (server, member, command, top-10 level & koin agregat lintas guild — bot sudah publik, jangan cuma 1 server).
- **v2 (tunda):** toggle pengaturan per-server (economy, automod, welcome, starboard). Alasannya: config bot sekarang masih nilai global di `.env` (welcome channel, mod-log) — dashboard belum bisa menyimpan setting per-server sebelum config pindah ke DB. Ini sama dengan open thread `/setup` yang pernah ditawarkan.
- anti-slop = filter, bukan style guide. Direction visual tetap perlu keputusan Fauzan (warna brand teal Finch sudah ada dari refresh UI bot hari ini — pakai itu biar konsisten).

## Login Discord — checklist untuk Fauzan (Developer Portal)

1. Buka aplikasi Finch di Discord Developer Portal → **OAuth2**.
2. Tambah **Redirect URI**: persis `http://localhost:3000/api/auth/callback/discord` (Discord menolak kalau tidak sama persis).
3. Salin **CLIENT_ID** dan **CLIENT_SECRET** — CLIENT_SECRET adalah secret baru; **jangan paste di chat** (aturan yang sama seperti token bot: kirim via form/file, bukan chat).
4. Scope yang diminta: `identify` + `guilds`. Scope `guilds` dipakai untuk daftar server tempat user punya izin Manage Server (filter seperti dashboard MEE6/Dyno: cuma tampilkan server yang dia kelola).
5. Library: **Auth.js (next-auth v5)** provider Discord = jalur standar; atau OAuth2 manual tanpa dependensi. Rekomendasi: Auth.js.

## Tombol Invite Bot

URL standar OAuth2: `https://discord.com/oauth2/authorize?client_id=<CLIENT_ID>&permissions=<bitmask>&scope=bot%20applications.commands` — generate dari tab OAuth2 → URL Generator di Developer Portal. (Catatan: bot sudah publik & global-sync; invite ini untuk server baru.)

## SATU pertanyaan yang harus dijawab Fauzan sebelum auth dibangun

Dashboard di `localhost` cuma bisa dibuka dari PC-nya sendiri — **user lain tidak bisa login** karena redirect URI Discord harus publik.

- **Opsi A (lokal saja):** dashboard cuma untuk Fauzan pantau botnya. Redirect URI localhost, selesai.
- **Opsi B (publik, seperti bot publik):** perlu URL publik → Cloudflare Tunnel gratis dari PC-nya (`cloudflared tunnel`), redirect URI jadi `https://xxx.trycloudflare.com/api/auth/callback/discord`. Kalau URL tunnel berubah tiap restart, pakai quick tunnel = redirect URI ikut berubah (ribet) — solusi proper: domain sendiri atau tunnel dengan hostname tetap.

Keputusan ini mengubah kode auth, jadi tentukan dulu sebelum lanjut. Rekomendasi: mulai Opsi A (v1), naik ke B kalau dashboardnya memang mau dibuka publik.
