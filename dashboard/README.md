# Finch Dashboard (Next.js)

Dasbor web untuk bot Discord Finch: login Discord, pilih server yang kamu kelola,
atur modul per-server (Welcome, Leveling, Ekonomi, AutoMod, Starboard), dan tombol
invite bot. Lihat `DESIGN.md` untuk arah visual dan `DELIVERY_GATE.md` untuk laporan
kepatuhan Anti-Slop.

## Cara kerja

1. Bot Finch (di PC) mengirim snapshot (nama server, jumlah member, daftar channel,
   daftar role, top level/koin, giveaway aktif) tiap 5 menit ke `POST /api/ingest`
   dengan `DASHBOARD_SECRET`.
2. Dasbor menyimpan snapshot + pengaturan per-server di Vercel Postgres.
3. Kamu login pakai Discord, buka server yang kamu punya izin Kelola Server-nya,
   ubah pengaturan, tekan Simpan.
4. Bot mengambil semuanya tiap 5 menit ke `GET /api/guilds/[id]/sync`
   dengan secret yang sama, lalu menerapkannya.

## Fitur per-server

- **Pengaturan**: 5 modul (Welcome, Leveling, Ekonomi, AutoMod, Starboard) +
  detail tiap modul (kecepatan XP, role reward per level, aturan automod per-jenis,
  pesan welcome custom, nominal daily/kerja, dsb).
- **Leaderboard**: top level & top koin, diambil dari snapshot bot.
- **Self-roles**: tambah/hapus emoji → role pada pesan tertentu (reaksi).
- **Auto-responder**: tambah/hapus trigger → balasan.
- **Giveaway**: lihat yang aktif + buat baru dari web (bot mengeksekusi).

## Deploy ke Vercel (sekitar 15 menit)

### 1. Siapkan Discord OAuth2

1. Buka [Discord Developer Portal](https://discord.com/developers/applications) > aplikasi Finch > **OAuth2**.
2. Di **Redirects**, tambah: `https://NAMA-PROYEK.vercel.app/api/auth/callback/discord`
   (ganti NAMA-PROYEK dengan nama proyek Vercel-mu; untuk coba lokal tambah juga
   `http://localhost:3000/api/auth/callback/discord`).
3. Salin **Client ID** dan **Client Secret**. Client Secret itu secret: jangan paste di chat,
   langsung tempel di Environment Variables Vercel pada langkah 3.

Cek berhasil: redirect URI tersimpan di portal.

### 2. Deploy

1. Upload folder ini ke GitHub (repo privat boleh), lalu di Vercel: **Add New Project** > import repo.
2. Atau: `npx vercel` dari folder ini.

### 3. Environment Variables (Vercel > Settings > Environment Variables)

| Key | Isi |
|---|---|
| `AUTH_SECRET` | Acak 32+ karakter (`npx auth secret` untuk generate) |
| `DISCORD_CLIENT_ID` | Dari portal OAuth2 |
| `DISCORD_CLIENT_SECRET` | Dari portal OAuth2 |
| `NEXT_PUBLIC_DISCORD_CLIENT_ID` | Sama dengan Client ID (publik, dipakai tombol invite) |
| `POSTGRES_URL` | Dari Vercel Storage > Postgres > Connect (otomatis bila dibuat dari dashboard Vercel) |
| `DASHBOARD_SECRET` | Buat acak sendiri 32+ karakter. **Samakan** dengan `DASHBOARD_SECRET` di `.env` bot |

Cek berhasil: deploy hijau, buka URL > tombol "Masuk dengan Discord" membawa ke halaman
otorisasi Discord.

Troubleshooting: kalau "Masuk dengan Discord" menampilkan halaman error 500,
`AUTH_SECRET` belum terisi di Environment Variables.

### 4. Database

Vercel > Storage > Postgres > **Query**: paste isi `schema.sql`, jalankan.

Cek berhasil: tabel `snapshots` dan `guild_settings` ada.

### 5. Sambungkan bot

Di `.env` bot (PC), tambah:

```
DASHBOARD_URL=https://NAMA-PROYEK.vercel.app
DASHBOARD_SECRET=<sama dengan yang di Vercel>
```

Restart bot. Cek berhasil: log bot menulis `dashboard: snapshot terkirim (N server)`
dalam 5 menit; landing page dasbor menampilkan angka server.

### 6. Coba lokal (opsional)

```
npm install
cp .env.example .env.local   # isi manual, jangan commit
npm run dev
```

Buka `http://localhost:3000`.

## Keamanan

- `DASHBOARD_SECRET` tidak pernah tampil di chat atau repo. Kalau bocor, ganti di Vercel
  dan di `.env` bot, lalu restart keduanya.
- Endpoint bot (`/api/ingest`, `GET settings`) hanya menerima Bearer secret yang cocok
  (perbandingan timing-safe).
- Endpoint simpan (`PUT settings`) hanya untuk user yang terbukti punya izin Kelola Server
  di server tersebut (dicek live ke Discord API tiap request).
