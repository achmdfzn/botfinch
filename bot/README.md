# 🤖 Finch — Discord Bot

Bot Discord serbaguna pakai Python (`discord.py`) — bisa dipasang di semua server.
Fitur bawaan: perintah `!status` / `!userinfo` / `!bantuan`, pesan selamat datang,
anti-spam dasar, dan `!bersihkan` buat moderator. Semua perintah support
slash command (`/status`, `/userinfo`, `/bersihkan`, dll).

## Struktur

```
discord-bot-finch/
├── main.py             # entry point →  python main.py
├── src/
│   ├── bot.py          # class FinchBot (intents, event, auto-load cog)
│   ├── config.py       # semua setting dari .env, terpusat di sini
│   ├── store.py        # persistensi SQLite di data/finch.db
│   ├── cogs/
│   │   ├── general.py      # perintah umum (!status, !userinfo, !serverinfo)
│   │   ├── moderation.py   # anti-spam + anti-invite + bersihkan
│   │   ├── verification.py # verifikasi member (panel + tombol, persistent)
│   │   ├── leveling.py     # sistem Level/XP + /rank kartu gambar
│   │   ├── leaderboard.py  # papan peringkat member
│   │   ├── tickets.py      # tiket support (channel privat + transcript)
│   │   ├── giveaway.py     # giveaway otomatis + reroll
│   │   ├── selfroles.py    # self-roles via select menu
│   │   ├── polls.py        # polling voting tombol
│   │   ├── starboard.py    # pesan berbintang ⭐ dipajang otomatis
│   │   ├── automod.py      # filter kata kasar + warning + auto-mute
│   │   ├── afk.py          # status AFK + balasan mention
│   │   ├── reminders.py    # pengingat via DM
│   │   ├── serverstats.py  # counter member (voice channel auto-update)
│   │   ├── tempvc.py       # temp voice channel mabar
│   │   ├── saran.py        # sistem saran
│   │   └── report.py       # laporkan ke mod (context menu)
│   └── utils/
│       ├── rankcard.py     # generator kartu rank PNG (Pillow)
│       └── views.py        # TimeoutSafeView (tombol mati visual saat timeout)
│       ├── embeds.py   # helper embed biar tampilan konsisten
│       ├── filters.py  # deteksi link invite (murni, ada unit test)
│       └── modlog.py   # catat kejadian ke channel mod-log
├── tests/              # unit test (python -m unittest discover tests)
├── data/               # data runtime (database dsb.) — tidak di-commit
├── logs/               # finch.log — tidak di-commit
├── requirements.txt
├── .env.example        # contoh config (copy jadi .env)
├── README.md           # panduan setup (file ini)
├── PRD.md              # kebutuhan produk & roadmap
├── AGENT.md            # panduan ngoding buat AI assistant
├── ARCHITECTURE.md     # desain teknis & alur sistem
└── CHANGELOG.md        # riwayat perubahan
```

## Langkah setup

### 1. Buat bot di Discord Developer Portal
1. Buka https://discord.com/developers/applications → **New Application**, beri nama `Finch`.
2. Masuk menu **Bot** → **Reset Token** → **Copy** tokennya.
3. ✅ **Cek berhasil:** token kecopy (bentuknya string panjang, ~70 karakter). Simpan sementara di notepad.

### 2. Aktifkan Privileged Intents
1. Masih di menu **Bot**, scroll ke **Privileged Gateway Intents**.
2. Nyalakan **MESSAGE CONTENT INTENT** dan **SERVER MEMBERS INTENT** → **Save Changes**.
3. ✅ **Cek berhasil:** kedua toggle berwarna hijau/ON.

### 3. Invite bot ke server kamu
1. Masuk menu **OAuth2** → **URL Generator**.
2. Centang scope: `bot`.
3. Centang permission: `Send Messages`, `Manage Messages`, `Manage Roles`, `Read Message History`, `Embed Links`, `Add Reactions`.
4. Buka URL yang muncul di browser → pilih server kamu → **Authorize**. Ulangi untuk tiap server yang mau dipasangi Finch.
5. ✅ **Cek berhasil:** nama Finch muncul di daftar member server (status offline, wajar sebelum dijalankan).

### 4. Install Python & library
1. Pastikan Python 3.10+ terinstall: jalankan `python --version` di terminal.
2. Di folder project ini, jalankan:
   ```
   pip install -r requirements.txt
   ```
3. ✅ **Cek berhasil:** tidak ada error merah, perintah `pip show discord.py` menampilkan versi.

### 5. Isi token
1. Copy file `.env.example` menjadi `.env`.
2. Buka `.env`, ganti `isi_token_bot_kamu_di_sini` dengan token dari langkah 1.
3. (Opsional) Isi `WELCOME_CHANNEL_ID` dengan ID channel welcome.
   Cara dapat ID: di Discord nyalakan **User Settings → Advanced → Developer Mode**,
   lalu klik kanan channel → **Copy Channel ID**.
4. ✅ **Cek berhasil:** file `.env` ada dan `DISCORD_TOKEN` sudah terisi, bukan teks contoh lagi.
5. ⚠️ Jangan pernah share file `.env` / token ke siapapun.

### 6. Jalankan bot
```
python main.py
```
atau auto-restart (Windows) via:
```
run.bat
```
atau via Linux/VPS:
```
chmod +x run.sh
./run.sh
```
✅ **Cek berhasil:** di terminal muncul `✅ Finch#xxxx udah online dan siap!` dan status bot di Discord jadi online (hijau). Log juga tersimpan di `logs/finch.log`.

### 7. Tes di server
Kirim di channel: `!status` atau `/status`
✅ **Cek berhasil:** bot membalas embed status (latency + uptime + jumlah server).
Coba juga: `/help` (UI dropdown interaktif), `/rank` (kartu rank bergambar), `/leaderboard` (tombol Prev/Next), `/bersihkan 5` (UI konfirmasi ✅/❌ untuk mod).

## Setup verifikasi member & mod-log (disarankan)

Biar member baru wajib verifikasi sebelum bisa chat, dan semua aksi moderasi tercatat.

### 1. Buat channel khusus
Buat channel `#verifikasi` dan `#mod-log` (klik kanan kategori → Create Channel → Text Channel).
1. ✅ **Cek berhasil:** kedua channel muncul di daftar channel server.

### 2. Buat dua role
Buka **Server Settings → Roles → Create Role**, buat:
- `Belum Verifikasi`
- `Member`

(Nama bisa diganti, tapi harus sama persis dengan `UNVERIFIED_ROLE_NAME` / `VERIFIED_ROLE_NAME` di `.env`.)
2. ✅ **Cek berhasil:** kedua role muncul di daftar Roles.

### 3. Naikkan posisi role bot
Di daftar Roles yang sama, **drag role Finch ke ATAS** `Member` dan `Belum Verifikasi`.
Ini wajib — Discord menolak bot mengatur role yang posisinya lebih tinggi.
3. ✅ **Cek berhasil:** urutan dari atas: Finch, lalu Member, lalu Belum Verifikasi.

### 4. Kunci permission channel
Untuk **setiap channel chat** (klik kanan channel → Edit Channel → Permissions → pilih role `Belum Verifikasi`):
- `Send Messages` → ❌ (deny)

Khusus channel `#verifikasi`, untuk role `Belum Verifikasi`:
- `View Channel` → ✅, `Read Message History` → ✅, `Send Messages` → ❌
- `Use Application Commands` → ✅ (biar tombol bisa diklik)

(Jadi member baru cuma bisa baca + klik tombol di #verifikasi, tidak bisa chat di mana pun.)
4. ✅ **Cek berhasil:** di Permissions tiap channel, kolom `Belum Verifikasi` menampilkan ❌ pada Send Messages.

### 5. Isi config
Di `.env`, isi:
```
VERIFY_CHANNEL_ID=<ID channel #verifikasi>
MOD_LOG_CHANNEL_ID=<ID channel #mod-log>
```
(Cara dapat ID: Developer Mode ON → klik kanan channel → Copy Channel ID.)
5. ✅ **Cek berhasil:** kedua nilai terisi angka, bukan 0.

### 6. Restart bot
`Ctrl+C` di terminal, lalu `python main.py` lagi.
6. ✅ **Cek berhasil:** di log muncul `Cog dimuat: src.cogs.verification`.

### 7. Pasang panel verifikasi (sekali saja)
Ketik `/verifikasi` di Discord (khusus moderator) → bot memasang panel + tombol **Verifikasi** di #verifikasi.
Panel ini persistent: tombol tetap berfungsi walau bot restart.
7. ✅ **Cek berhasil:** di #verifikasi muncul embed "🔐 Verifikasi Dulu Yuk!" dengan tombol hijau.

### 8. Tes dengan akun kedua
1. Join server pakai akun lain → otomatis dapat role `Belum Verifikasi`.
2. Coba chat di channel umum → harusnya ditolak (tidak bisa kirim).
3. Klik tombol **Verifikasi** di #verifikasi → dapat role `Member`, role lama dicabut.
4. ✅ **Cek berhasil:** akun tes bisa chat, dan di #mod-log muncul "✅ Member terverifikasi".

## Fitur komunitas: tiket, giveaway, self-roles

### Tiket support
1. (Opsional) Buat kategori channel "TIKET", isi `TICKET_CATEGORY_ID` di `.env` (klik kanan kategori → Copy Category ID).
2. Ketik `/panel-tiket` (khusus mod, sekali saja) → panel + tombol "Buat Tiket" terpasang.
3. User klik tombol → channel privat `tiket-<nama>` dibuat (hanya user + moderator yang bisa lihat). Maksimal 1 tiket terbuka per user.
4. Di dalam tiket, klik "Tutup Tiket" → transcript (.txt) dikirim ke #mod-log, channel dihapus otomatis setelah 5 detik.
- ✅ **Cek berhasil:** channel tiket hanya terlihat oleh pembuka + mod; setelah ditutup ada file transcript di #mod-log.

### Giveaway
Ketik `/giveaway 10m 1 Nitro sebulan` (khusus mod) → bot memposting undian + tombol "Ikut".
- Format durasi: `30s`, `10m`, `2h`, `1d` (minimal 10 detik).
- Pemenang diundi otomatis saat waktu habis; kalau tidak ada peserta giveaway hangus dengan sopan.
- Setelah selesai ada tombol "Reroll" (khusus mod) untuk undi ulang.
- ✅ **Cek berhasil:** pemenang diumumkan otomatis di channel + tombol "Ikut" berganti jadi "Reroll".

### Self-roles
1. Di `.env`: `SELF_ROLES="Pioneer,Notifikasi Event,Mabar"` (nama role harus sudah dibuat di server, pisahkan dengan koma).
2. Restart bot, lalu ketik `/panel-role` (khusus mod, sekali saja).
3. Member pilih dari menu → role dipasang; pilih lagi → role dilepas.
- ✅ **Cek berhasil:** role bertambah/berkurang di profil member setelah pilih menu.

## Fitur lanjutan: poll, starboard, auto-mod

### Polling
Ketik `!poll "mabar jam berapa?" "19.00, 20.00, 21.00" 1h` (atau `/poll`):
- 2–5 opsi, pisahkan koma. Durasi opsional (`10m`, `1h`, `1d`); kosongkan = tutup manual.
- 1 suara per orang, bisa ganti pilihan. Hasil update real-time di embed.
- Pembuat poll / moderator bisa tutup manual via tombol "Tutup".
- ✅ **Cek berhasil:** vote tercatat + embed menampilkan jumlah suara.

### Starboard
1. Buat channel `#starboard`, isi `STARBOARD_CHANNEL_ID` di `.env` (opsional: `STARBOARD_MIN`, default 3).
2. Member kasih reaksi ⭐ ke pesan → saat mencapai ambang, pesan dipajang otomatis di #starboard.
3. Jumlah ⭐ di-update otomatis; kalau turun di bawah ambang, postingan dicabut.
- ✅ **Cek berhasil:** pesan dengan 3+ ⭐ muncul di #starboard lengkap dengan link "Lihat pesan asli".

### Auto-mod kata kasar
- Daftar kata di `BAD_WORDS` (ada bawaan, bisa dioverride total). Pesan yang kena → dihapus + warning.
- Warning ke-`WARN_MAX` (default 3) → auto-mute `MUTE_DURATION_MINUTES` (pakai Discord timeout, persisten).
- Moderator (Manage Messages) tidak kena filter.
- `/warnings [@user]` cek warning, `/reset-warn @user` reset (khusus mod).
- ✅ **Cek berhasil:** akun tes kirim kata kasar → pesan hilang + warning 1/3; setelah 3x → ke-mute.

## Utilitas: AFK & pengingat

### AFK
Ketik `!afk makan dulu` (atau `/afk`):
- Status tersimpan; kirim pesan apa pun → AFK otomatis mati ("selamat datang kembali").
- Orang yang mention kamu → bot membalas "💤 ... sedang AFK: alasan".
- ✅ **Cek berhasil:** akun AFK di-mention akun lain → muncul balasan otomatis.

### Pengingat
Ketik `!remind 10m cek oven` (atau `/remind`):
- Bot mengirim **DM** saat waktunya tiba (kalau DM ketutup, fallback mention di channel).
- Format durasi: `30s`, `10m`, `2h`, `1d` (10 detik – 30 hari).
- `/remind-list` lihat yang aktif, `/remind-batal <id>` batalkan.
- ✅ **Cek berhasil:** `/remind 30s tes` → 30 detik kemudian DM masuk.

## Tahap 7: temp voice, saran, laporkan ke mod

### Temp voice channel (mabar dadakan)
1. Buat 1 **voice channel** sebagai lobby, mis. `➕ Buat Room`.
2. (Opsional) Buat **kategori** tempat room privat dibuat.
3. Isi `.env`: `TEMPVC_LOBBY_ID` (ID lobby), `TEMPVC_CATEGORY_ID` (ID kategori, kosongkan = root).
4. Restart bot → member join lobby → otomatis dibuat `🔊・<nama>-room`, member dipindah, diberi hak `manage_channels`. Kosong → hapus otomatis.
5. Di dalam room, owner bisa: `/vc-lock` (kunci, deny connect @everyone), `/vc-unlock`, `/vc-limit <1-99>` (0 = tak terbatas), `/vc-rename <nama>`.
- ✅ **Cek berhasil:** join lobby → room tercipta + pindah; leave sampai kosong → channel hilang; `/vc-lock` kunci, `/vc-limit 2` batasi.

### Sistem saran
1. Buat channel `#saran`, isi `SARAN_CHANNEL_ID` di `.env`, restart bot.
2. Member: `/saran <teks>` (maks 500 char) → embed di #saran + reaksi 👍👎, simpan DB `suggestions`.
3. Mod (`manage_messages`): `/saran-status <message_id> <diterima|ditolak|dipertimbangkan>` → edit embed (warna + status) + catat mod-log.
- ✅ **Cek berhasil:** `/saran haloo` muncul di #saran + bisa divote; `/saran-status 123 diterima` → embed berubah hijau.

### Laporkan ke Mod (context menu)
Klik kanan pesan mana pun → **Apps → Laporkan ke Mod** (hanya di server).
- Bot cari tiket terbuka pelapor di tabel `tickets`; kalau belum ada → buat baru via `buat_tiket` (reuse `tickets.py`).
- Kirim embed 🚨 "Laporan" ke channel tiket: isi pesan (maks 1000 char), author, channel asal, **jump link**, pelapor. Balas ephemeral: "✅ Laporan dikirim ke <tiket>".
- ✅ **Cek berhasil:** klik kanan → tiket kebentuk (atau pakai yang sudah ada) + embed laporan lengkap + jump link bisa diklik.

## Tahap 8: YouTube, Voice XP, Invite Tracker

### Notifikasi YouTube
1. Siapkan `YT_CHANNEL_ID` (ID channel YouTube, lihat di YouTube Studio) dan buat channel Discord `#notif-youtube`.
2. Isi `.env`: `YT_CHANNEL_ID`, `YT_NOTIFY_CHANNEL_ID` (ID channel Discord), `YT_CHECK_MINUTES` (default 15), `YT_PING_ROLE_ID` (opsional).
3. Restart bot. Check pertama hanya seed (tidak posting). Video baru setelahnya akan dipost embed (judul + link + thumbnail + mention role).
4. Keterbatasan: butuh koneksi RSS YouTube; jika error jaringan, log warning, coba lagi interval berikutnya.
- ✅ **Cek berhasil:** upload video baru → ≤15 menit muncul embed lengkap di channel notif; restart tidak posting ulang.

### Voice XP
Otomatis — member join voice → catat waktu; leave → hitung menit (bulat bawah, <1 menit diabaikan) → tambah `VOICE_XP_PER_MIN` via `src/utils/xp.py`. Level-up kirim ke system channel. Bot diabaikan. Restart bot mereset sesi voice yang sedang berjalan.
- ✅ **Cek berhasil:** join 3 menit → XP nambah sesuai rate; level-up terkirim.

### Invite Tracker
Butuh `intents.invites = True` (sudah ditambah di `src/bot.py`).
- Cache invite `guild_id -> {code: uses}` diisi saat `on_ready` + update `on_invite_create/delete`.
- `on_member_join`: bandingkan uses → ketemu code yang dipakai → catat `invites_log(user_id, guild_id, inviter_id, code)`. Jika vanity/terhapus → inviter NULL.
- `/invites [@user]`: jumlah invite valid + info pengundang. `/invite-lb`: top 10 inviter (medali 🥇🥈🥉).
- ⚠️ Keterbatasan: jika bot offline saat beberapa orang join sekaligus, bisa 0 atau >1 code naik → inviter dicatat NULL ("tidak diketahui"). `guild.invites()` juga rawan rate-limit saat wave join.
- ⚠️ GUILD_ID toggle: jangan toggle `GUILD_ID` bolak-balik (global → guild). Bisa duplikat command 2x. Bersihkan: `python -m scripts.clean_guild_commands` (atau hapus manual di Developer Portal).
- ✅ **Cek berhasil:** undang via invite → join tercatat ke inviter yang benar; `/invite-lb` tampil.

### Notifikasi YouTube — cara dapat `YT_CHANNEL_ID`
- Buka channel YouTube → **Settings** → YouTube Studio → **Channel → Advanced** → `Channel ID` (24 char `UC...`). Atau buka `https://www.youtube.com/channel/UC...` & copy ID.
- Seeded saat pertama jalan: semua video di RSS tidak diposting; hanya video baru setelahnya yang muncul.

## Tahap 9: Economy (sistem koin 🪙)

Sistem koin per server. Semua tampilan pakai **UI horizontal** (field kesamping, bukan list vertikal panjang).

- `/saldo [@user]` — cek koin: 3 kolom kesamping (💰 Saldo | 🏆 Peringkat | 📥 Total diperoleh).
- `/daily` — klaim koin harian acak (default 100–300, cooldown 24 jam).
- `/kerja` — kerja dapat koin acak (default 50–200, cooldown default 1 jam).
- `/transfer @user <jumlah>` — kirim koin ke member lain (validasi: bukan bot/diri sendiri, saldo cukup).
- `/top-koin` — 10 terkaya dalam 2 kolom kesamping (1–5 | 6–10).
- **Bonus level-up:** tiap naik level otomatis dapat koin (default 50, `ECONOMY_LEVEL_BONUS`).
- Config di `.env`: `ECONOMY_START_BALANCE` (saldo awal, default 100), `ECONOMY_DAILY_MIN/MAX`, `ECONOMY_WORK_MIN/MAX`, `ECONOMY_WORK_COOLDOWN` (detik), `ECONOMY_LEVEL_BONUS`.
- ✅ **Cek berhasil:** `/daily` → koin nambah; klaim lagi → pesan cooldown; `/transfer` → saldo berpindah; naik level → pesan "+50 🪙 koin".

## Tahap 10: Mini-games, Shop, Counting, Quest, Rep, Giveaway Koin

Semua terhubung ke sistem koin Tahap 9. UI tetap horizontal (field kesamping).

### Mini-games
- `/coinflip <taruhan> <kepala|ekor>` — menang 2x. `/slot <taruhan>` — 3 sehati 5x (💎 8x, 7️⃣ 10x), 2 sehati 2x. `/tebak-angka <taruhan> <1-10>` — tepat dapat 9x.
- `/trivia` — kuis 4 tombol (30 detik), benar +koin (default 100, cooldown 5 menit).
- Batas taruhan: `ECONOMY_MIN_BET` (10), `ECONOMY_MAX_BET` (5000).

### Shop
- Isi `.env`: `SHOP_ITEMS="VIP:5000,Warna Emas:2500"` (nama role:harga). Role harus sudah dibuat di server & role bot di atasnya.
- `/shop` lihat daftar, `/buy <nama>` beli → role dipasang, koin dipotong (gagal pasang role = koin kembali).

### Counting channel
- Isi `.env`: `COUNTING_CHANNEL_ID`. Member berhitung 1,2,3... — salah/2x beruntun → pesan dihapus + peringatan. Kelipatan 100 dirayakan 🎉. Mod: `/counting-reset`.

### Quest harian
- `/quest` — 3 misi kesamping: 💬 kirim 25 pesan (+150), 🗣️ voice 30 menit (+200), 🎁 klaim /daily (+50). Reset tiap hari (UTC).
- Progres otomatis; tombol "🎁 Klaim" muncul kalau ada yang selesai.

### Reputasi & Giveaway koin
- `/rep @user` — kasih 1 reputasi (1x per 24 jam per pemberi). Tampil di `/saldo`.
- `/g-koin <durasi> <jumlah> [pemenang]` (khusus mod) — giveaway berhadiah koin. Koin host dipotong di awal (escrow); pemenang otomatis dikredit; tanpa peserta = refund ke host. Reroll giveaway koin dibatasi 1x (anti cetak koin).
- ✅ **Cek berhasil:** `/slot 100` → menang/kalah sesuai; `/buy VIP` → role nempel; counting salah → dihapus; `/quest` → progres jalan; `/g-koin 1m 100 1` → pemenang +100 koin otomatis.

## Tahap 11: Bank, Season, Achievement & 30+ fitur

### 💰 Economy+
- **Bank**: `/bank` (cek), `/deposit <jumlah|all>`, `/withdraw <jumlah|all>` — bunga harian `BANK_BUNGA_HARIAN`% (default 2%).
- **Daily streak**: `/daily` beruntun → bonus = streak × 5 koin (maks 150). Streak tampil di embed.
- **Lotre**: `/lotre-beli [jumlah]` (tiket `LOTRE_HARGA_TIKET`), `/lotre-info`. Undian tiap Senin 00:00 UTC — pemenang bawa pulang seluruh pool.
- **Gaji**: isi `GAJI_ROLES="Moderator:500,VIP:200"` → pemilik role digaji tiap 7 hari otomatis.
- **Lelang**: `/lelang <nama_role> <harga_awal> <durasi>` (mod) → `/bid <jumlah>` → pemenang bayar & dapat role.

### 🎮 Mini-games+
- `/blackjack <taruhan>` — tombol Hit/Stand, blackjack 2.5x, menang 2x.
- `/dadu <taruhan> <1-6>` (tepat 5x), `/rps <taruhan> <gunting|batu|kertas>` (menang 2x).
- `/maling @user` — 60% berhasil curi 10% saldo target (maks 1000); gagal = denda 150. Cooldown `MALING_COOLDOWN`.
- `/susun-kata` — tebak kata acak, tercepat di channel +`SUSUNKATA_REWARD` koin.
- `/trivia-top` — leaderboard pemenang trivia.

### 🎁 Giveaway+
- **Syarat ikut**: `/giveaway` & `/g-koin` punya param `min_level`, `min_koin`, `role` — yang tak memenuhi syarat ditolak saat klik Ikut.
- `/g-role <durasi> <role> [pemenang]` (mod) — pemenang otomatis dapat role.
- `/donasi-koin <jumlah>` — sumbang ke pool server. `/g-rutin <interval> <pemenang> <hadiah> [koin]` (mod) — giveaway otomatis berulang; hadiah koin diambil dari pool. `/g-rutin-list`, `/g-rutin-hapus`.

### 📊 Leveling+
- **Season**: tiap `SEASON_HARI` (default 90) XP di-reset; top 3 dapat 1000/500/250 koin. `/season` lihat info.
- **Weekend boost**: XP 2x tiap Sabtu–Minggu (`XP_WEEKEND_BOOST=0` untuk matikan).
- `/prestige` — syarat level 30: reset ke level 1, prestige +1 (tampil di `/profil`).
- `/top-voice` — leaderboard menit voice. Voice juga kasih koin (`VOICE_KOIN_PER_MIN`).

### 🏅 Achievement & Profil
- Lencana otomatis: level 10/25/50, sultan koin, streak 7/30, trivia 10x, invite 5, rep 10. `/achievement` lihat koleksi.
- `/profil [@user]` — level, koin, rep, prestise + badge, horizontal.

### 🛡️ Moderasi+
- `/lockdown` & `/unlockdown` (admin) — kunci/buka semua channel saat raid.
- Log pesan **diedit & dihapus** otomatis ke mod-log.
- **Slowmode otomatis**: channel membludak (>20 pesan/30 dtk) → slowmode 10 dtk selama 5 menit.
- **Anti-raid**: ≥5 join/60 dtk → verification level naik + peringatan mod-log.

### 💬 Komunitas+
- **Auto-responder**: `/respon-add <trigger> <respons>` (mod), `/respon-del`, `/respon-list`.
- **Birthday**: `/ultah DD-MM` → diumumkan + bonus `ULTAH_KOIN` tiap tahun.
- **Sticky**: `/sticky-set <teks>` (mod) — pesan selalu nempel di bawah channel.
- **Bump**: `/bump` cek cooldown; otomatis catat saat DISBOARD "Bump done".
- **Event**: `/event` (mod) + tombol RSVP Hadir/Tidak/Mungkin + reminder otomatis H-1 jam. `/event-list`.
- **Tiket rating**: setelah tiket ditutup, pembuka diminta rating 1–5 via DM. `/tiket-rating` (mod).
- **Goodbye** + **welcome DM** otomatis.
- **Reward perilaku**: invite valid +`INVITE_KOIN`, starboard +`STARBOARD_KOIN`.

### 🔔 Utilitas+
- `/remind-rutin`, `/poll-rutin` — pengingat & polling berulang otomatis (interval min 1 jam).
- **Twitch**: notif live seperti YouTube (`TWITCH_CLIENT_ID/SECRET/CHANNEL` di `.env`).

## Sentuhan akhir: role reward, welcome card, server stats

### Role reward per level
Di `.env`: `LEVEL_ROLES="5:Aktif,10:Veteran,20:Sepuh"` (nama role harus sudah ada di server).
Member otomatis dapat role saat levelnya tercapai (dicek tiap dapat XP).
Pastikan role bot **di atas** role reward di daftar Roles.
- ✅ **Cek berhasil:** akun tes capai level 5 → role "Aktif" muncul di profilnya.

### Welcome card bergambar
Otomatis — tiap member baru join, bot mengirim kartu bergambar (avatar + nama + nomor member) ke channel welcome (`WELCOME_CHANNEL_ID`).
- ✅ **Cek berhasil:** join pakai akun tes → kartu muncul di channel welcome.

### Server stats counter
1. Buat 3 **voice channel** (boleh di kategori paling atas), mis. namanya sementara `stats-1` dst.
2. Isi ID-nya di `.env`: `STATS_TOTAL_ID`, `STATS_HUMAN_ID`, `STATS_BOT_ID`.
3. Restart bot → nama channel berubah otomatis jadi `👥 Semua: 123`, `🧑 Manusia: 120`, `🤖 Bot: 3`, update tiap 10 menit + tiap ada yang join/keluar.
- ✅ **Cek berhasil:** nama ketiga channel berubah sesuai jumlah member.

## Ekonomi & game (grup command)

Mulai Tahap 12, command dikelompokkan ala bot modern (batas Discord: 100 slash command). Ketik grupnya saja (mis. `/dagang`) untuk lihat daftar subcommand.

### `/dagang` — ekonomi+
- `trade @user <koin>` — tawar tukar koin (tombol Terima/Tolak, potong saat diterima)
- `toko` / `tas` / `pakai` — beli, lihat, dan pakai item consumable (perisai anti-maling, boost XP, dll.)
- `pinjam <koin>` / `lunasi` / `info-pinjaman` — pinjaman berbunga harian + auto-debit
- `deposito <koin> <hari>` / `info-deposito` — kunci koin, panen + bunga
- `saham` / `beli` / `jual` — pasar saham simulasi (harga berubah tiap `SAHAM_UPDATE_MENIT`)
- `peti` — peti misteri harian (cooldown 20 jam)

### `/game` — minigames
`coinflip`, `slot`, `tebakangka`, `trivia`, `top`, `blackjack`, `dadu`, `rps`, `maling`, `susunkata` — semua pakai koin taruhan.

### `/lomba` — turnamen & kuis
`buat`/`ikut`/`main`/`jawab`/`info` (turnamen susun-kata, khusus mod untuk buat), `kuis` + `kuis-jawab` (kuis multiplayer), `aducepat` (rebutan jawab tercepat), `ship` (kecocokan 2 user, tanpa taruhan).

### `/job`, `/nikah`, `/clan`, `/gelar` — sosial
- `/job lihat` / `/job pilih <id>` — class dengan bonus pasif (kerja, XP, maling)
- `/nikah lamar @user` / `cerai` / `pasangan` / `klaim` — nikah + bonus harian pasangan
- `/clan buat <nama>` / `gabung` / `keluar` / `info` / `war` — clan + clan war mingguan (hadiah dibagi rata)
- `/gelar toko` / `beli` / `pasang` / `lepas` — gelar/title di profil
- `/confess <teks>` — pesan anonim ke channel khusus (cooldown 5 menit)
- `/top-prestige` — leaderboard gabungan level + koin + reputasi

### `/pet`, `/quest-guild`, `/hof` — engagement
- `/pet adopsi` / `info` / `ganti-nama` — pelihara pet, naik level dari XP chat
- `/quest-guild` — quest mingguan server (hadiah masuk pool giveaway)
- `/hof` — Hall of Fame starboard

### `/grafik`, `/rutin`, `/embed-buat`, `/saran-top` — utilitas
- `/grafik level` / `voice` — grafik aktivitas (butuh `pip install -r requirements.txt`)
- `/rutin buat` / `list` / `hapus` — event berulang (cron mini)
- `/embed-buat` — builder embed interaktif (modal)
- `/saran-top` — saran dengan vote terbanyak

### Moderasi+
- Auto-lockdown: ≥8 join/60 detik → server dikunci otomatis (snapshot permission, khusus mod buka)
- `/warn-list` — riwayat warning, `/tiket-kategori` — atur kategori tiket, `/faq` — jawab pertanyaan umum
- SLA tiket: tiket tanpa balasan mod > `TIKET_SLA_JAM` jam → alert ke mod-log
- Log voice (join/leave/move) ke mod-log
- ✅ **Cek berhasil:** `/dagang` menampilkan daftar subcommand; `/game coinflip 100 kepala` jalan.

## Dashboard & backup otomatis
- Dashboard web lokal: `DASHBOARD_PORT` (default 8080) → buka `http://localhost:8080` untuk statistik server (tidak terekspos ke internet).
- Backup DB harian otomatis ke channel Discord (`BACKUP_CHANNEL_ID`) — pastikan channel-nya privat.
- Semua config baru ada di `.env.example` (token tetap kosong — isi sendiri).

## Tambah fitur sendiri
Bikin file baru di `src/cogs/`, contoh tiru `src/cogs/general.py` (yang sudah hybrid), lalu restart bot — otomatis ke-load.
Mau ubah setting (prefix, ambang anti-spam, durasi mute)? Edit `.env`, lihat opsi di `.env.example`.
**Batas Discord: maksimal 100 top-level slash command** — kalau nambah banyak command, bungkus dalam `@commands.hybrid_group` seperti `/dagang` (lihat `src/cogs/ekonomi_plus.py`).

## Butuh bantuan?
Tanya Finch aja 😄
