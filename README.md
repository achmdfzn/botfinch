# Finch — Bot Discord + Dashboard Web

Satu repo untuk semuanya.

```
finch/
  bot/         Bot Discord (Python, discord.py) — jalan di PC/server kamu
  dashboard/   Dashboard web (Next.js) — deploy ke Vercel
  branding/    Avatar, banner, dan bio bot (dipakai keduanya)
```

## Mulai cepat

### 1. Bot

```
cd bot
cp .env.example .env   # isi token & setting, JANGAN commit .env
pip install -r requirements.txt
python main.py
```

Sukses kalau log menulis `Finch udah online dan siap!`.

### 2. Dashboard

```
cd dashboard
npm install
cp .env.example .env.local   # isi manual, JANGAN commit
npm run dev                  # coba lokal di http://localhost:3000
```

Deploy ke Vercel: import repo ini, set **Root Directory** ke `dashboard`,
isi Environment Variables (lihat `dashboard/README.md`), jalankan
`dashboard/schema.sql` sekali di Vercel Postgres.

### 3. Sambungkan keduanya

Di `.env` bot:

```
DASHBOARD_URL=https://namaproyek.vercel.app
DASHBOARD_SECRET=<sama dengan yang di Vercel>
```

Restart bot. Dalam 5 menit, landing page dashboard menampilkan angka server.

### 4. Premium (Free/VIP)

Tiap server punya paket Free atau VIP; bedanya hanya batas jumlah resource
(perintah kustom, autoresponder, giveaway aktif, panel self-role, pengumuman
aktif). Aktivasi VIP dilakukan manual oleh owner bot lewat perintah `/vip`
di Discord atau panel `/dashboard/admin/premium`. Detail desain, cara
grant/extend/revoke, dan env `BOT_OWNER_IDS`: lihat `PREMIUM.md`.

## Dokumen penting

- `bot/README.md` — panduan bot
- `bot/CHANGELOG.md` — riwayat perubahan bot
- `PREMIUM.md` — sistem paket Free/VIP (desain, batas fitur, cara owner grant)
- `dashboard/README.md` — panduan deploy dashboard (langkah + cek berhasil)
- `dashboard/DESIGN.md` — arah visual (Anti-Slop)
- `dashboard/DELIVERY_GATE.md` — laporan kepatuhan Anti-Slop

## Keamanan

Jangan pernah commit `.env` / `.env.local`, jangan paste token atau secret ke chat.
Kalau secret bocor, ganti di semua tempat lalu restart.
