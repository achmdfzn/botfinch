# Premium (Free/VIP) Botfinch

Dokumen ini menjelaskan desain, pengoperasian, dan keterbatasan sistem
paket Free/VIP Botfinch. Ringkasnya: setiap server (guild) punya satu
entitlement yang menentukan tier efektifnya, `free` atau `vip`. Perbedaan
kedua tier hanya pada batas jumlah resource yang bisa dibuat. Tidak ada
fitur yang dikunci total, tidak ada harga, dan tidak ada checkout di
dalam sistem ini.

## Ringkasan desain

- **Entitlement per-guild.** Satu baris entitlement untuk satu server.
  Tier tidak menempel ke user: member biasa di server VIP menikmati batas
  VIP selama mereka memakai fitur di server itu, dan server Free tetap
  Free walaupun ada member yang punya akses VIP di server lain.
- **Postgres adalah sumber kebenaran.** Dashboard (Vercel Postgres /
  Neon) menyimpan entitlement di tabel `guild_entitlements`. Semua
  keputusan mutasi (grant, extend, revoke) dan perhitungan tier efektif
  di dashboard membaca dan menulis tabel ini.
- **Bot menyimpan cache di SQLite.** Bot menyalin entitlement dari
  dashboard ke tabel lokal `guild_entitlement_cache` lewat sinkronisasi
  berkala (alur dashboard sync yang sudah ada), lalu menegakkan kuota
  dari cache itu di titik pembuatan resource di Discord.
- **Kebijakan stale cache.** Cache bot hanya dipercaya sampai umur
  `ENTITLEMENT_CACHE_MAX_AGE_SECONDS` (default 3600 detik, yaitu 1 jam)
  sejak terakhir diambil dari dashboard (`fetched_at`). Selama dashboard
  atau backend tidak bisa dihubungi, cache yang masih valid tetap dipakai
  sampai batas stale itu. Setelah cache melewati batas stale, tier
  efektif jatuh ke Free (fail-closed) sampai sinkronisasi berhasil lagi.
- **Owner bypass selalu jalan.** User yang ID Discord-nya terdaftar di
  `BOT_OWNER_IDS` selalu diperlakukan sebagai VIP di semua konteks,
  termasuk saat cache basi atau dashboard sedang down. Bypass ini
  bersifat personal (per-aktor), bukan per-server: lihat bagian
  BOT_OWNER_IDS di bawah.
- **Tier efektif dihitung, bukan disimpan mentah.** Sebuah baris hanya
  menghasilkan tier VIP bila tier-nya `vip`, statusnya `active`, sudah
  mulai (`starts_at` kosong atau sudah lewat), dan belum kedaluwarsa
  (`expires_at` kosong atau masih di masa depan). Selain itu Free.

## Tabel Free vs VIP

| Fitur (feature code)            | Free | VIP | Yang dihitung |
| ------------------------------- | ---: | ---: | ------------- |
| Perintah kustom (`custom_commands`)      | 10 | 100 | Baris perintah kustom tersimpan per server |
| Autoresponder (`autoresponders`)         | 10 | 100 | Baris auto-responder tersimpan per server |
| Giveaway aktif (`giveaways_active`)      | 3  | 25  | Giveaway yang sedang berjalan (belum berakhir) |
| Panel self-role (`selfrole_panels`)      | 3  | 25  | Panel self-role (pesan) per server |
| Pengumuman terjadwal aktif (`announcements_active`) | 3 | 25 | Pengumuman terjadwal yang aktif (enabled) |

Alasan tiap limit:

- Kelima fitur di atas adalah **resource yang terhitung dan tersimpan**:
  setiap barisnya menempati penyimpanan, dibaca bot secara berkala, dan
  sebagian (giveaway, pengumuman) menjalankan pekerjaan terjadwal di
  belakang layar. Membatasinya per tier menjaga biaya dan beban tetap
  sebanding dengan paket server.
- Angka Free sengaja cukup untuk server kecil sampai menengah, dan angka
  VIP sepuluh kali lipat atau lebih untuk server besar, jadi upgrade
  terasa sebagai kenaikan kapasitas, bukan pembukaan fitur.
- **Request embed TIDAK dibatasi.** Membuat embed lewat Embed Builder
  adalah request sekali jalan: bot mengirim pesan lalu selesai, tidak
  ada resource yang tersimpan dan terus dipelihara. Karena yang dibatasi
  sistem ini adalah resource tersimpan, embed tidak masuk katalog kuota.
- **Fitur keselamatan dan fitur inti TIDAK digate.** Moderasi, AutoMod,
  log, dan perintah inti lain tidak ada di katalog kuota dan tidak
  dikurangi untuk server Free. Keamanan server tidak pernah dijadikan
  barang dagangan.

## BOT_OWNER_IDS

`BOT_OWNER_IDS` adalah daftar ID Discord owner bot, dipisah koma:

```
BOT_OWNER_IDS=1531892469233487912,364980558893285377
```

Kedua ID di atas adalah ID publik owner bot Finch.

Cara mengatur:

- **Di bot:** isi `BOT_OWNER_IDS` di file `.env` bot (lihat
  `bot/.env.example`), lalu restart bot.
- **Di dashboard:** isi `BOT_OWNER_IDS` sebagai Environment Variable di
  Vercel (Project Settings, lalu Environment Variables), server-side
  saja. **JANGAN** memakai awalan `NEXT_PUBLIC_`: daftar owner adalah
  data server, tidak boleh ikut terkirim ke browser. Setelah mengubah
  env di Vercel, redeploy agar nilai baru terbaca.
- Nilai yang sama harus terpasang di kedua tempat. Bot memakainya untuk
  bypass dan penjagaan perintah `/vip`; dashboard memakainya untuk
  penjagaan API admin dan panel `/dashboard/admin/premium`.

Sifat owner bypass:

- **Personal, bukan per-server.** Bypass mengikuti orangnya: owner bot
  memakai batas VIP di server mana pun. Kehadiran owner bot di sebuah
  server TIDAK membuat server itu VIP untuk semua membernya; entitlement
  server tersebut tidak berubah.
- **Selalu jalan.** Bypass tidak tergantung cache entitlement maupun
  status dashboard.

Tiga peran yang berbeda, jangan tertukar:

- **Owner bot:** ID-nya ada di `BOT_OWNER_IDS`. Satu-satunya peran yang
  bisa grant/extend/revoke VIP, membuka panel admin premium, dan memakai
  bypass personal.
- **Pemilik server Discord (guild owner):** pemilik sebuah server di
  Discord. Tidak otomatis jadi owner bot, tidak bisa mengubah
  entitlement, dan servernya tidak otomatis VIP.
- **Admin atau moderator server:** punya izin seperti Administrator atau
  Kelola Server di satu guild. Izin Discord itu tidak memberi hak apa
  pun atas entitlement; admin server tidak bisa menjalankan `/vip`.

## Cara owner memberikan, memperpanjang, dan mencabut VIP

Ada dua jalur resmi, keduanya khusus owner bot dan keduanya menulis ke
sumber kebenaran yang sama (Postgres dashboard) serta mencatat audit log:

1. **Perintah `/vip` di Discord** (respon ephemeral, hanya owner bot):
   - `/vip grant` dengan durasi hari opsional dan alasan.
   - `/vip extend` dengan durasi hari wajib dan alasan.
   - `/vip revoke` untuk mencabut.
   - `/vip status` dan `/vip list` untuk melihat keadaan.
   Mutasi dikirim bot ke endpoint internal dashboard; bot tidak menulis
   tier langsung ke cache-nya sendiri.
2. **Panel web `/dashboard/admin/premium`**: login dengan akun Discord
   owner, cari server (nama atau ID) atau isi guild ID manual, pilih
   server, lalu jalankan Grant / Extend / Revoke dengan durasi dan
   alasan. Panel juga menampilkan daftar entitlement dan riwayat audit
   per server. Akun yang bukan owner hanya melihat keadaan akses ditolak.

Semantik aksi:

- **Grant:** menetapkan tier `vip`, status `active`, mulai sekarang.
  Durasi kosong berarti VIP **permanen** (`expires_at` kosong). Permanen
  hanya terjadi lewat grant eksplisit tanpa durasi; tidak ada jalur lain
  yang diam-diam membuat VIP permanen.
- **Extend:** menambah durasi dari tanggal berakhir saat ini (atau dari
  sekarang bila tanggal berakhir lama sudah lewat). Durasi wajib diisi.
  Untuk guild yang masih Free atau belum punya baris entitlement, extend
  **diperlakukan seperti grant** dengan durasi tersebut, sesuai
  implementasi, karena tidak ada masa VIP yang bisa diperpanjang.
  Memperpanjang VIP yang sudah permanen tidak mengubahnya: tetap
  permanen.
- **Revoke:** status menjadi `revoked`; tier dan tanggal berakhir
  dibiarkan apa adanya agar riwayat pemberian tetap terlihat. Tier
  efektif menjadi Free setelah bot menyinkronkan cache berikutnya
  (paling lambat selewat batas stale cache, lihat Keterbatasan).

Setiap mutasi menulis satu baris ke `entitlement_audit_log` berisi aktor,
aksi, nilai sebelum dan sesudah (tier, status, tanggal berakhir), alasan,
dan waktu.

## Expiry dan downgrade

- Semua waktu disimpan sebagai `TIMESTAMPTZ` di Postgres dan diproses
  dalam **UTC**. Tanggal yang tampil di dashboard diformat mengikuti
  bahasa dan zona waktu perangkat pembaca, nilai simpannya tidak
  berubah.
- VIP yang melewati `expires_at` otomatis menjadi Free pada pembacaan
  berikutnya. **Tidak perlu restart** bot maupun dashboard: perhitungan
  tier efektif selalu membandingkan waktu sekarang dengan `expires_at`.
- **Data lama tidak dihapus saat downgrade.** Perintah kustom,
  autoresponder, giveaway, panel, dan pengumuman yang sudah terlanjur
  dibuat di atas kuota Free tetap tersimpan dan tetap bisa dipakai atau
  dihapus.
- Yang ditolak saat di atas kuota adalah **penambahan baru**: membuat
  resource baru di atas batas tier efektif akan ditolak sampai VIP aktif
  lagi, atau sampai jumlah resource diturunkan ke dalam batas.

## Skema database baru

`dashboard/schema.sql` menambah dua tabel (additive, memakai
`IF NOT EXISTS`, aman dijalankan berulang):

- `guild_entitlements`: satu baris per guild. Kolom utama: `guild_id`
  (primary key), `tier` (default `free`), `status` (default `active`),
  `source`, `starts_at`, `expires_at` (keduanya `TIMESTAMPTZ`, kosong
  berarti tanpa batas), `provider_entitlement_id` dan
  `provider_subscription_id` (disiapkan untuk integrasi pembayaran
  Discord di masa depan, sekarang kosong), `granted_by`, `note`,
  `bot_present`, serta cap waktu `first_seen_at`, `last_seen_at`,
  `created_at`, `updated_at`.
- `entitlement_audit_log`: log tiap mutasi. Kolom: `id`, `guild_id`,
  `actor_id`, `action` (grant/extend/revoke), `tier_before`,
  `tier_after`, `status_before`, `status_after`, `expires_before`,
  `expires_after`, `reason`, `created_at`, plus indeks per guild.

Langkah manual menjalankan skema (dilakukan owner, sekali):

1. Buka dashboard Neon, masuk ke proyek database dashboard, buka
   **SQL Editor**.
2. Buka file `dashboard/schema.sql` dari repo, salin seluruh isinya.
3. Tempel ke SQL Editor dan jalankan. Karena semua statement memakai
   `IF NOT EXISTS`, menjalankan ulang file yang sama aman dan tidak
   menimpa data yang sudah ada.
4. Selesai. Tidak ada migrasi data: guild yang belum punya baris
   diperlakukan sebagai Free, dan barisnya terdaftar otomatis saat bot
   atau dashboard berikutnya melihat guild itu.

Catatan: skema ini TIDAK dijalankan otomatis oleh kode dan tidak boleh
dijalankan ke produksi oleh siapa pun selain owner secara manual lewat
langkah di atas.

## Ringkasan env baru

Bot (`.env` bot):

| Nama | Wajib | Keterangan |
| ---- | ----- | ---------- |
| `BOT_OWNER_IDS` | Ya, untuk fitur owner | Daftar ID Discord owner bot, dipisah koma. |
| `ENTITLEMENT_CACHE_MAX_AGE_SECONDS` | Tidak | Umur maksimal cache entitlement bot dalam detik. Default 3600. |
| `PREMIUM_UPGRADE_URL` | Tidak | URL info upgrade yang ditampilkan bot pada pesan kuota penuh dan status premium. Kosong berarti bot hanya menampilkan teks hubungi owner. |

Dashboard (Vercel Environment Variables, server-side):

| Nama | Wajib | Keterangan |
| ---- | ----- | ---------- |
| `BOT_OWNER_IDS` | Ya, untuk panel dan API admin | Nilai yang sama persis dengan di bot. Tanpa awalan `NEXT_PUBLIC_`. |

## Pembayaran masa depan (belum diimplementasikan)

Kesimpulan riset dari dokumentasi resmi Discord:

- Sumber: <https://discord.com/developers/docs/monetization/overview>
  dan <https://discord.com/developers/docs/resources/entitlement>
  (terverifikasi terbaca saat riset fitur ini).
- Discord Premium Apps mendukung langganan **per-user dan per-guild**
  lewat SKU dan Entitlement. Objek Entitlement Discord membawa antara
  lain `guild_id`, `starts_at` dan `ends_at`, serta flag `deleted`,
  yang bentuknya cocok dengan kolom provider yang sudah disiapkan di
  `guild_entitlements`.
- Integrasi native itu **DITUNDA** sampai semua syarat kelayakan
  (eligibility) terpenuhi:
  - aplikasi terverifikasi (verified app) dan dimiliki oleh sebuah
    developer team;
  - owner team berusia minimal 18 tahun, dengan email terverifikasi
    dan 2FA aktif;
  - aplikasi punya slash commands;
  - aplikasi punya tautan Terms of Service dan Privacy Policy;
  - payout diatur lewat Stripe oleh team owner;
  - Monetization Terms disetujui.
- SKU juga harus dibuat lebih dulu di Developer Portal sebelum ada
  entitlement dari Discord yang bisa disinkronkan.
- Sampai semua itu siap, **grant manual oleh owner adalah jalur resmi
  satu-satunya**, dan memang itu yang diimplementasikan sekarang. Tidak
  ada harga, tombol beli, atau checkout di bot maupun dashboard.

## Keterbatasan yang diketahui

- **Audit log tidak atomik penuh dengan mutasi.** Penulisan baris
  entitlement dan baris audit adalah dua statement terpisah, karena
  `lib/db.ts` tidak punya helper transaksi. Crash persis di antara
  keduanya bisa menyisakan perubahan tanpa catatan audit. Urutannya
  disengaja: baris utama dulu, audit sesudahnya, jadi audit hilang
  lebih dapat diterima daripada audit untuk perubahan yang tidak pernah
  terjadi.
- **Revoke tidak selalu instan.** Bot menegakkan tier dari cache
  lokalnya. Bila bot sedang offline atau belum menyinkronkan, VIP hasil
  revoke masih terbaca sampai sinkronisasi berikutnya, dengan batas
  terburuk umur cache (`ENTITLEMENT_CACHE_MAX_AGE_SECONDS`, default
  1 jam) sebelum tier jatuh ke Free dengan sendirinya.
- **Hitungan panel self-role berbasis panel dashboard.** Panel self-role
  yang dibuat murni lokal di bot tidak persisten, jadi pemakaian
  `selfrole_panels` dihitung dari panel yang tercatat lewat dashboard.
- **Jalur mirror dashboard untuk autoresponder tidak melewati gate
  bot.** Kuota autoresponder ditegakkan di titik pembuatan lewat Discord
  (perintah bot). Baris yang tersinkron dari dashboard tidak dicek ulang
  oleh gate bot, jadi penegakan untuk jalur itu bergantung pada
  pembuatan di Discord. Sebaliknya, pengumuman terjadwal dari dashboard
  ditegakkan langsung di API dashboard saat pembuatan.
