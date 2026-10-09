# Changelog Finch

Format: tiap perubahan dicatat di bawah `Unreleased`, pindah ke versi
bertanggal saat rilis ke server.

## Unreleased

### Baru — dashboard web penuh: leaderboard, self-roles, responder, giveaway (2026-10-08)
- `dashboard_sync`: snapshot kini kirim daftar role, top 10 level/koin, dan
  giveaway aktif. Pull pindah ke `GET /api/guilds/{id}/sync` (pengaturan mentah +
  self-roles + auto-responder + permintaan giveaway pending).
- Tabel lokal baru `dashboard_selfroles`; permintaan giveaway dari web dieksekusi
  via cog Giveaway lalu di-ack ke dashboard.
- Wiring pengaturan baru per-server:
  - Leveling: `leveling_xp_rate` (25–400%), `leveling_announce_channel_id`,
    `leveling_roles` (JSON level → role_id, via `beri_role_reward`).
  - AutoMod: kill switch kini juga mematikan filter kata kasar (sebelumnya lolos);
    toggle per-aturan `automod_spam/invites/caps/badwords`, filter caps baru,
    `automod_mute_minutes`, `automod_log_channel_id`.
  - Welcome: `welcome_message` (template {user}/{server}). DM selamat datang
    DIHAPUS total (welcome hanya ke channel: `welcome_channel_id` → env →
    system channel). Key lama `welcome_dm` tidak dipakai lagi.
  - Goodbye baru per-server: `goodbye_enabled` (default "1"), `goodbye_channel_id`
    (fallback: system channel), `goodbye_message` (template {user}/{server});
    dikirim sebagai embed teal standar Finch.
  - Ekonomi: `economy_daily` (nominal tetap), `economy_work_min/max`.
- `modlog.log_event` terima `channel_id` opsional (override per-guild).
- `selfroles.py`: reaction add/remove untuk self-role dashboard
  (select-menu `/panel-role` lama tidak berubah).
- `responder.py`: `/respon-add` dan `/respon-del` mirror ke dashboard bila
  dikonfigurasi; sync = dashboard sumber utama (full replace per 5 menit).
- 6 test baru (`emoji_cocok`, caps filter, setting int) → 281 tests lolos.
- Endpoint dashboard mentah tanpa merge default: default ditentukan di code bot.

### Baru — sinkronisasi dashboard web Next.js (2026-10-08)
- Cog `dashboard_sync`: push snapshot (server/member/channel) tiap 5 menit ke
  `DASHBOARD_URL/api/ingest`, pull pengaturan per-server tiap 5 menit ke tabel
  lokal `dashboard_settings`. Mati total kalau `DASHBOARD_URL`/`DASHBOARD_SECRET` kosong.
- Helper `get_guild_setting(guild_id, key, default)`; di-wiring ke:
  Welcome (`welcome_enabled` + `welcome_channel_id` per-server, override `.env`),
  Leveling (`leveling_enabled`), AutoMod (`automod_enabled`),
  Ekonomi (`economy_enabled` via `cog_check` + pesan ramah).
- Config baru: `DASHBOARD_URL`, `DASHBOARD_SECRET` (lihat `.env.example`).
  Secret tidak pernah di-hardcode; bot <-> dashboard pakai Bearer timing-safe.
- 5 regression test baru → 275 tests lolos.

### Diubah — UI modern emoji diet (2026-10-08)
Aturan baru (lihat `src/utils/embeds.py`): 1 warna brand teal untuk semua embed (hijau/merah hanya semantik sukses/gagal); emoji maks 1 per judul, nama field & value teks polos; 🪙 dipertahankan sebagai simbol mata uang.
- 91 nama field dibersihkan dari emoji; footer menjadi "Finch".
- `tabel()` baru: leaderboard & top-koin kini tabel monospace (ganti daftar emoji & medali).
- Tombol berlabel teks: "Ya, bersihkan"/"Batal", "Setuju"/"Tidak setuju" (saran); reaksi vote 👍👎 dihapus (vote via tombol).
- `/status`: teks polos ("Online — semua sistem berjalan normal").
- `level_embed`: tanpa emoji.

### Hasil audit pasca-revamp (2026-10-08)
Audit bug: 0 kritis, 0 sedang, 3 rendah — semua diperbaiki:
- Help menyebut `youtube`/`tempvc`/`laporkan` seolah slash command → diganti nama command asli (`vc-lock`, notif otomatis, klik-kanan).
- `tabel()` kini sadar lebar emoji (padding tidak meleset di kolom berisi 🪙).
- `serverstats.update_stats`: guard per-guild, satu guild error tidak membunuh loop.
Audit zombie: bersih (0 unused import, 0 fungsi/konstanta mati, 40/40 cog ter-load).

### Diperbaiki — error handler anti-crash (2026-10-08)
- **Root cause:** error hybrid-slash (`/bantuan`) masuk ke `on_command_error`, dan `ctx.send(ephemeral=True)` di dalamnya crash lagi dengan `40060 Interaction has already been acknowledged` karena interaction sudah di-ack/mati — user tidak dapat pesan error apa-apa, log ketumpuk traceback ganda.
- `on_command_error` kini pakai `_respon_error_aman`: cek `interaction is None` → `is_done()` → followup vs response, semua dibungkus try/except `HTTPException`. Error handler tidak akan pernah ikut crash.
- `on_app_command_error` juga dibungkus try/except.
- `/bantuan`: pengiriman respon awal dibungkus try/except — interaction mati (10062) dicatat sebagai warning, bukan crash.
- Sweep seluruh cog: pola `original_response()` (polls, views) sudah di-guard; `_reply` moderasi sudah cek `is_done()`; callback tombol masing-masing respon sekali.
- 4 regression test baru untuk `_respon_error_aman`.

### Diubah — bot publik multi-server (2026-10-08)
- Finch bukan lagi bot khusus satu server: seluruh branding "Pioneer Outpost Nusa" digenerikkan (footer embed, pesan welcome/DM, README, bio).
- `GUILD_ID=0` (atau kosong) = mode publik: slash command di-sync global ke semua server (±1 jam muncul di server baru). Isi GUILD_ID hanya untuk mode 1 server (sync instan).
- Dashboard lokal: top 10 level/koin kini agregat semua guild (sebelumnya cuma `guilds[0]`).
- `.env.example` + README diperbarui dengan panduan invite ke banyak server.

### Diperbaiki — audit bug+zombie putaran 2 (2026-10-08)
Audit 2 agen independen: 13 sedang + 13 rendah, 0 kritis — semua diperbaiki.
- **Koin (7 sedang):** `_akhiri` giveaway ditandai selesai SEBELUM pengumuman + guard anti-overlap antar iterasi loop (anti double payout); reroll koin guarded increment atomik (anti bypass 1x); escrow host dikembalikan bila channel giveaway dihapus; pool rutin yang kalah race → giveaway dibatalkan (tidak mencetak koin); cooldown trivia dicatat sebelum kirim soal (anti double-claim); escrow lelang dikembalikan bila pemenang/role tidak valid.
- **Loop task (3 sedang):** `cek_rutin`, `cek_event_rutin`, `cek_poll`, `cek_reminder`, `check_mutes` — blok DB awal dibungkus try/except + per-row diisolasi, satu error tidak membunuh loop selamanya.
- **Lainnya (3 sedang):** tiket yatim (channel dihapus manual) tidak lagi memblokir tiket baru; auto-mute: warning di-reset hanya bila mute berhasil; tempvc: cooldown ditandai sebelum `create_voice_channel` (anti 2 room yatim).
- **Rendah (13):** gaji tandai periode dulu baru bayar; escrow g_koin dikembalikan bila posting gagal; settlement lelang baca bid terbaru + guarded; starboard klaim atomik sebelum posting; clan war filter minggu berjalan + cleanup minggu lama; tutup tiket guarded (anti transcript ganda); `/remind` validasi ≤1500 karakter + `fetch_user` fallback; rutin (reminder/poll) yang channel-nya hilang dihapus setelah 20x gagal; `_ticket_locks` di-evict saat tiket ditutup; baris tempvc yatim dibersihkan; kuis bersihkan state saat `CancelledError`; `tree.sync` guild dibungkus (GUILD_ID salah tidak crash startup).
- **Zombie:** `import datetime` mati di moderasi_plus.py dihapus; `acak_kata` duplikat (minigames+turnamen) disentralkan ke `src/utils/teks.py::acak_huruf`; contoh usang `halo` di AGENT.md diperbarui.
- 7 regression test baru (`tests/test_audit_fix.py`) untuk pola guarded-update.

### Ditambah — ganti ping/halo + UI help kompak (2026-10-08)
- `!ping` → **`!status`/`/status`**: embed status bot ala bot populer (📶 latency, ⏱️ uptime, 🖥️ jumlah server). Uptime dihitung dari `FinchBot.start_time`.
- `!halo` → **`!userinfo`/`/userinfo [@user]`**: info member ala whois (avatar thumbnail, username, ID, akun dibuat, tanggal gabung, roles).
- **UI `/bantuan` kompak ramah HP**: command dikelompokkan per kategori jadi sedikit field berisi chip (bukan satu field per command), embed tidak lagi menjulur panjang ke bawah di layar HP.

### Ditambah (Tahap 12) — 36 fitur, UI grup command
- **Grup slash command** (10 grup, 93 top-level — di bawah batas 100 Discord): `/dagang` (13 sub), `/game` (10), `/lomba` (9), `/clan` (5), `/nikah` (4), `/gelar` (4), `/pet` (3), `/rutin` (3), `/grafik` (2), `/job` (2). Ketik nama grup saja → bantuan subcommand.
- **Ekonomi+** (`src/cogs/ekonomi_plus.py`): `/dagang trade` (tanpa escrow di muka — potong saat diterima, anti hangus saat restart), toko item consumable + inventory (`toko/tas/pakai`), pinjaman berbunga + auto-debit (`pinjam/lunasi/info-pinjaman`), deposito (`deposito/info-deposito`, anti panen 2x), saham simulasi (`saham/beli/jual`, loop harga), peti misteri harian (`peti`). 19 tabel baru di `store.py`.
- **Turnamen & game sosial** (`src/cogs/turnamen.py`): turnamen susun-kata persisten (`buat/ikut/main/jawab/info`), kuis multiplayer (`kuis/kuis-jawab`), adu cepat, ship deterministik.
- **Sosial & leveling** (`src/cogs/sosial.py`): job/class + bonus pasif, nikah + bonus harian (klaim cooldown persisten di DB), confess anonim (cooldown persisten), clan + clan war mingguan (peserta persisten, settlement aman), gelar/title, `/top-prestige`. Reaction XP + voice level roles (`LEVEL_ROLES_VOICE`).
- **Moderasi+** (`src/cogs/moderasi_plus.py`): auto-lockdown (≥8 join/60 dtk, snapshot permission), log voice, `/warn-list`, `/tiket-kategori`, `/faq`, SLA tiket (alert bila tanpa balasan mod > `TIKET_SLA_JAM` jam; reset hanya oleh balasan mod; status alert persisten di DB).
- **Engagement** (`src/cogs/engagement.py`): pet (adopsi/XP/ganti nama), quest guild mingguan, bump reward, pertanyaan harian, `/hof` (LIMIT 50).
- **Utilitas** (`src/cogs/utilitas.py`): dashboard web lokal (`DASHBOARD_PORT`), backup DB harian ke channel, `/grafik level|voice`, `/embed-buat` (anti cross-guild), `/rutin` (event berulang), `/saran-top` (voting persisten).
- **UI modern** (`src/utils/embeds.py`): embed berwarna per kategori + timestamp + footer konsisten, progress bar, `error_embed`/`sukses_embed`, `koin_text`.
- Config baru: `TRADE_TIMEOUT`, `PINJAMAN_*`, `DEPOSITO_PILIHAN`, `SAHAM_UPDATE_MENIT`, `TURNAMEN_HADIAH`, `KUIS_*`, `JOB_*`, `NIKAH_BONUS_HARIAN`, `CLAN_BIAYA`, `CLAN_WAR_HADIAH`, `CONFESS_CHANNEL_ID`, `PET_HARGA`, `QUEST_GUILD_*`, `DAILYQ_*`, `BUMP_KOIN`, `TIKET_SLA_JAM`, `DASHBOARD_PORT`, `BACKUP_CHANNEL_ID`, `LEVEL_ROLES_VOICE` (lihat `.env.example`).
- Util baru: `src/utils/consumable.py`, `src/utils/job.py`, `src/utils/waktu.py` (`parse_iso` tersentral).

### Diperbaiki — audit Tahap 12 (3 sedang, 13 rendah)
- `TradeView`: guard `selesai` di awal handler + set sebelum operasi DB → anti double-click cetak koin
- `/dagang trade`: tanpa escrow di muka → koin tidak hangus saat restart
- `/game maling`: bonus job maling +10% kini benar dipakai
- Deposito: tandai `selesai=1` (guarded UPDATE) sebelum kredit → anti panen 2x
- `/clan buat` & `/gelar beli`: satu transaksi atomik (guarded UPDATE + INSERT) → koin tidak hangus saat crash
- Cooldown nikah-klaim & confess pindah ke DB (`cooldown_aksi`) → anti bypass via restart
- Clan war: peserta di DB (`clan_war_peserta`), settlement lalu hapus, payout per-anggota pakai try/except
- `/embed-buat`: tolak channel dari guild lain
- SLA tiket: hanya balasan non-owner yang me-reset timer; status alert di DB (`sla_warned`)
- `_cfg` getattr fallback dihapus → akses config langsung (typo langsung ketahuan)
- Zombie: 2 import mati dihapus (`asyncio` di moderasi_plus, `tambah_xp` di sosial, `time` di sosial); `_parse_iso` ×3 disatukan ke `src/utils/waktu.py`

### Ditambah (Tahap 11)
- Bank + bunga harian, daily streak, lotre mingguan, gaji role, lelang + escrow, minigame baru (blackjack/dadu/rps/maling/susun-kata), syarat giveaway, giveaway rutin + pool donasi, season + reset + hadiah, weekend XP 2x, prestige, top-voice, achievement otomatis, profil, auto-responder, birthday, sticky, bump, event + RSVP, rating tiket, goodbye DM, Twitch alerts, remind rutin, poll rutin, lockdown + snapshot, log edit/hapus, slowmode otomatis, anti-raid, reward invite/starboard.

### Ditambah (Tahap 10)
- Minigame koin (`coinflip/slot/tebak-angka/trivia`), shop (`/shop /buy`), counting channel, quest harian, reputasi (`/rep`), giveaway koin (`/g-koin`).

### Ditambah (Tahap 9)
- Ekonomi dasar: `/saldo /daily /kerja /transfer /top-koin`, bonus koin tiap naik level.

### Ditambah (Tahap 8)
- **Notifikasi YouTube otomatis** (`src/cogs/youtube.py`): Poll RSS YouTube tiap `YT_CHECK_MINUTES`. Post embed (judul + thumbnail + link) ke `YT_NOTIFY_CHANNEL_ID` + ping `YT_PING_ROLE_ID`. Anti-spam (seeded saat pertama kali jalan).
- **Voice XP** (`src/cogs/voicexp.py`): Member nongkrong di voice dapat XP per menit (`VOICE_XP_PER_MIN`). Butuh refactor `src/utils/xp.py` (tambah_xp) agar dipakai leveling chat & voice.
- **Invite tracker** (`src/cogs/invites.py`): Lacak invite code join member via `on_member_join`. Command `/invites [@user]` (cek invite sendiri/user) & `/invite-lb` (top 10 inviter). Butuh `intents.invites = True`.

### Ditambah (Tahap 7)
- **Temp Voice Channel** (`src/cogs/tempvc.py`): join lobby `TEMPVC_LOBBY_ID` → auto-buat channel privat `🔊・<nama>-room` (di kategori `TEMPVC_CATEGORY_ID` jika diisi), pindah member, beri hak kelola (`manage_channels`). Kosong → hapus otomatis + hapus DB. Command owner: `/vc-lock` (deny connect @everyone), `/vc-unlock`, `/vc-limit <1-99>`, `/vc-rename <nama>`. Nonaktif jika `TEMPVC_LOBBY_ID=0`.
- **Sistem Saran** (`src/cogs/saran.py`): `/saran <teks>` (maks 500 char) kirim embed ke `SARAN_CHANNEL_ID` + reaksi 👍👎, simpan DB `suggestions(message_id, guild_id, author_id, text, status)`. `/saran-status <message_id> <status>` (mod `manage_messages`) status `diterima/ditolak/dipertimbangkan` → edit embed warna + `modlog.log_event`.
- **Context Menu "Laporkan ke Mod"** (`src/cogs/report.py`): klik kanan pesan → Apps → Laporkan ke Mod. Cari tiket terbuka pelapor di `tickets`; kalau belum ada buat baru via `buat_tiket(guild, member)` (refactor dari `tickets._buat_tiket`). Kirim embed laporan (isi, author, channel asal, jump link, pelapor) ke channel tiket. Balas ephemeral "✅ Laporan dikirim ke <tiket>".
- Config baru: `TEMPVC_LOBBY_ID`, `TEMPVC_CATEGORY_ID`, `SARAN_CHANNEL_ID` (`src/config.py`, `.env.example`). Tabel DB baru: `tempvc`, `suggestions` (`src/store.py`).

### Diperbaiki — audit fix (utama, banyak: TempVC orphan, invite, DB, izin, validasi, zombie)
- `src/cogs/tempvc.py`: cegah channel yatim saat `move_to` gagal (hapus channel), limit 1 room/owner + cooldown 30s
- `src/cogs/invites.py`: hanya catat inviter jika tepat 1 code naik (0 atau >1 → NULL)
- `src/cogs/youtube.py`: hapus `temp_seed` tidak terpakai, retensi `yt_posts` 90 hari, seed asli tanpa posting
- `src/config.py` `validate()`: tolak `prefix` kosong, angka negatif, `YT_CHECK_MINUTES < 1`
- `src/store.py` + `src/cogs/moderation.py`: `mutes` PK `(user_id, guild_id)` + query + `_riwayat` key `(guild_id, user_id)`
- `src/bot.py`: `on_app_command_error` tambah `app_commands.CheckFailure`; tambah `on_command_error`; `init_db` raise
- Tombol: guard `interaction.user.bot` di `tickets.py`, `giveaway.py`, `polls.py`; `verification.py` sudah ada
- `src/utils/xp.py`: `BEGIN IMMEDIATE` tangkap `sqlite3.OperationalError` spesifik
- `src/store.py`: `invites_log` PK `(user_id, guild_id)` + migrasi; hapus tabel `audit_logs` tidak terpakai
- Zombie: `src/utils/embeds.py` `error_embed` dibuang; `import logging` mati di 4 cog; `self.bot` assignment-only dibuang; `saran.py` helper tak pakai; `report.py` var `created` buang; `voicexp.py` cog import dibersihkan → `beri_role_reward` di `src/utils/xp.py`
- `src/cogs/report.py`: `buat_tiket` kini pakai `laporan` param (embed laporan); `tickets.py` guard lock per user mencegah klik ganda
- `src/cogs/general.py` `serverinfo` guard DM; `moderation.py` `bersihkan` proteksi channel `if i` fix
- `src/cogs/giveaway.py` + `polls.py`: tolak durasi > 30 hari (MAX 30d)
- `src/cogs/leaderboard.py` leak conn → `with`; `src/utils/modlog.py` → `HTTPException`; Refactor `src/utils/xp.py`: `_cek_role_reward` pindah jadi `beri_role_reward(member, level)`
- Docs: `README.md` invite limitasi + warning GUILD_ID + cara YT_CHANNEL_ID; `ARCHITECTURE.md`/`AGENT.md` disegar; `.env.example` + `CHANGELOG.md` update

### Tahap 11 — Bank, Season, Achievement & 30+ fitur (2026-10-08, request Fauzan)
- Economy+: bank + bunga harian, daily streak, lotre mingguan, gaji role, lelang role.
- Mini-games+: blackjack, dadu, rps, maling, susun-kata, trivia-top.
- Giveaway+: syarat ikut (min level/koin/role), /g-role, /g-rutin + /donasi-koin (pool server).
- Leveling+: season + reset + hadiah, weekend XP 2x, /prestige, /top-voice, koin voice.
- Baru: achievement otomatis, /profil, auto-responder, birthday, sticky, bump, event+RSVP, tiket rating, goodbye + welcome DM, twitch alerts, /remind-rutin, /poll-rutin, /lockdown, log edit/hapus, slowmode otomatis, anti-raid, reward invite/starboard.
- 19 tabel DB baru + migrasi kolom; 16 config key baru; 53 unit test baru → 158 tests lolos.
- Audit Tahap 11: 4 zombie dibersihkan (`_get_lock`, `_sekarang_iso`, 2× `log` mati), duplikasi `_sekarang()` disatukan, silent-failure re-apply mute kini di-log.
- Audit bug (15 temuan diperbaiki): pool giveaway-rutin tidak lagi terkuras saat posting gagal (S1); followup setelah defer di /giveaway /g-koin /g-role (S2); pemenang season diurut level (S3); payout season atomik (S4); reward starboard sekali per pesan (S5); escrow saat /bid lelang (S6); /unlockdown kembalikan permission asli (S7); reminder event dikirim ulang jika gagal (R1); lock sticky anti-duplikat (R2); kredit ultah anti-2x (R3); tiket lotre dihapus sebelum undian (R4); weekend boost pakai WIB (R5); rating tiket persisten survive restart (R6); reward invite hanya join pertama (R7); reminder rutin retry jika gagal kirim (R8).
- Hotfix 2026-10-08: slash command muncul 2x di picker — setiap startup kini membersihkan sisa global commands di Discord (hanya sync ke guild).

### Tahap 10 — Mini-games, Shop, Counting, Quest, Rep, Giveaway Koin (2026-10-08, request Fauzan)
- `src/cogs/minigames.py` baru: `/coinflip`, `/slot`, `/tebak-angka`, `/trivia` (tombol, 30 detik, anti double-reward).
- `src/cogs/shop.py` baru: `/shop`, `/buy` (beli role pakai koin; refund otomatis kalau pasang role gagal).
- `src/cogs/counting.py` baru: counting channel + `/counting-reset` (mod).
- `src/cogs/quests.py` + `src/utils/quests.py` baru: `/quest` 3 misi harian + tombol klaim; hook di leveling/voicexp/daily.
- `src/cogs/economy.py`: `/rep` (cooldown 24 jam) + kolom reputasi di `/saldo`.
- `src/cogs/giveaway.py`: `/g-koin` (escrow host, kredit otomatis, refund tanpa peserta, reroll dibatasi 1x anti cetak koin).
- `src/store.py`: migrasi `prize_coins`, `reroll_count`, `rep`, `last_rep`, `last_trivia`; tabel baru `counting_state`, `quest_progress`.
- `src/config.py`: `ECONOMY_MIN/MAX_BET`, `ECONOMY_TRIVIA_REWARD/COOLDOWN`, `SHOP_ITEMS`, `COUNTING_CHANNEL_ID` + validasi.
- `tests/test_minigames.py`, `tests/test_quests.py` baru + 4 test rep/trivia di `test_economy.py` → 105 tests lolos.
- Audit Tahap 10: perbaiki 2 bug — (1) escrow `/g-koin` bocor saat `ctx.send` raise; (2) reroll giveaway koin tak terbatas = cetak koin (dibatasi 1x).

### Tahap 9 — Economy / sistem koin (2026-10-08, request Fauzan)
- `src/cogs/economy.py` baru: `/saldo`, `/daily`, `/kerja`, `/transfer`, `/top-koin` — semua UI horizontal (field inline kesamping).
- `src/utils/economy.py` baru: logika terpusat (akun, tambah/kurang koin, klaim daily & kerja ber-cooldown, peringkat, top).
- `src/store.py`: tabel `economy(user_id, guild_id, balance, total_earned, last_daily, last_work)`.
- `src/config.py`: `ECONOMY_START_BALANCE/MIN/MAX/WORK_COOLDOWN/LEVEL_BONUS` + validasi.
- `src/cogs/leveling.py`: bonus koin otomatis tiap naik level (+50 default).
- `tests/test_economy.py`: 12 unit test baru (akun, transfer, cooldown, peringkat).

### Diperbaiki — bug notif akhir giveaway (2026-10-08, laporan Fauzan)
- `src/cogs/giveaway.py` `_akhiri()`: pengumuman berakhir SEKARANG SELALU dikirim saat timer habis — termasuk kalau tidak ada peserta ("😢 Tidak ada peserta untuk ...") dan kalau pesan asli sudah dihapus (sebelumnya: sunyi total tanpa pengumuman). Kegagalan edit/kirim dicatat ke log (warning), tidak lagi ditelan diam-diam. Fallback `fetch_channel` bila channel tidak ada di cache.
- `tests/test_giveaway.py`: 2 regression test baru (pengumuman tetap terkirim saat pesan hilang & saat nol peserta).

### Diperbaiki — audit fix ronde 2 (2026-10-08, oleh Finch)
- `src/utils/filters.py`: `parse_durasi` pindah ke sini; `polls.py`/`reminders.py` tidak import cog lain lagi (`giveaway.py` re-export biar test lama tetap jalan; `import re` tak terpakai dibuang)
- `src/cogs/leveling.py`: eviction `_xp_cooldown` tiap 30 menit (entry >1 jam dibuang); `self.bot` assignment-only dibuang
- `src/cogs/moderation.py`: eviction `_riwayat` anti-spam di loop `check_mutes` (timestamp >1 jam dibuang)
- `src/bot.py`: hapus cabang `MissingRequiredArgument` yang mati untuk slash
- `AGENT.md`: peta struktur diperbarui (20 cog + 6 utils); verifikasi = tombol persistent
- `ARCHITECTURE.md`: hapus jejak `audit_logs`; verification = tombol; `src/utils` sebut `views/rankcard/xp`

### Diperbaiki
- Refactor `src/cogs/tickets.py`: `_buat_tiket(interaction)` kini wrapper tipis di atas `async def buat_tiket(guild, member, laporan=None)` yang bisa dipanggil programmatic (untuk fitur Laporan).

### Ditambah
- Migrasi Slash Command: Mendukung perintah hybrid `!` dan `/` (`src/cogs/general.py`, `src/cogs/moderation.py`).
- `/verifikasi`: Perintah manual untuk kirim instruksi verifikasi ke user (`src/cogs/verification.py`).
- `GUILD_ID` di `.env`: Optimasi sync slash command (instant saat development).
- Auto-mute: Spam berulang otomatis di-mute X menit (`MUTE_DURATION_MINUTES` di `.env`).
- `src/store.py`: Persistensi SQLite di `data/finch.db` (tabel `users`, `audit_logs`).
- `/level`: Perintah cek level & XP (`src/cogs/leveling.py`).
- `/leaderboard`: Papan peringkat member teratas (`src/cogs/leaderboard.py`).
- UI Embed Keren: Update `src/utils/embeds.py` + progress bar + medali 🥇🥈🥉 di leaderboard.
- Auto-Restart: Tambah `run.bat` (Windows) & `run.sh` (Linux) + logging crash di `main.py`.

### Diubah
- Perintah `!ping`, `!halo`, `!serverinfo`, `!bantuan`, `!bersihkan`, `!level`, `!leaderboard` kini support slash command (`!command` / `/command`).
- Refactor `main.py`: Logging UTF-8, error handler terpusat.

### Ditambah (Tahap 2 — UI)
- `/rank`: kartu rank bergambar ala MEE6 (`!rank` / `/rank [@user]`) — avatar lingkaran, badge level, progress bar, peringkat server. Dibuat dengan Pillow, tanpa butuh font eksternal (`src/utils/rankcard.py`, `src/cogs/leveling.py`).
- Verifikasi pakai tombol: panel verifikasi persistent (tombol hijau "Verifikasi", `custom_id` tetap) — dipasang sekali via `/verifikasi`, tetap berfungsi setelah bot restart. Menggantikan alur reaksi ✅ per-member (`src/cogs/verification.py`).
- `Pillow>=10.0.0` ditambahkan ke `requirements.txt`.

### Ditambah (Tahap 3 — fitur komunitas)
- **Tiket support** (`src/cogs/tickets.py`): `/panel-tiket` pasang panel + tombol "Buat Tiket" (persistent) → channel privat `tiket-<nama>` (hanya user + mod); tombol "Tutup Tiket" kirim transcript .txt ke mod-log lalu hapus channel. Maks 1 tiket terbuka per user. Config: `TICKET_CATEGORY_ID`.
- **Giveaway** (`src/cogs/giveaway.py`): `/giveaway <durasi> <pemenang> <hadiah>` (format `30s`/`10m`/`2h`/`1d`) → tombol "Ikut" (toggle), undian otomatis tiap 30 detik, tombol "Reroll" setelah selesai. Data di SQLite → survive restart.
- **Self-roles** (`src/cogs/selfroles.py`): `/panel-role` pasang select menu persistent → member pasang/lepas role sendiri. Daftar role dari `SELF_ROLES` di `.env` (koma).
- `log_event` (`src/utils/modlog.py`) kini bisa kirim file (dipakai untuk transcript tiket).

### Ditambah (Tahap 4 — engagement & keamanan chat)
- **Polling** (`src/cogs/polls.py`): `/poll "pertanyaan" "opsi1, opsi2" [durasi]` — tombol vote per opsi (2–5), hasil real-time, 1 suara/orang (bisa ganti), tutup otomatis atau manual (host/mod). Data di SQLite → survive restart.
- **Starboard** (`src/cogs/starboard.py`): reaksi ⭐ mencapai `STARBOARD_MIN` (default 3) → pesan dipajang di channel starboard + jumlah update otomatis; turun di bawah ambang → dicabut. Config: `STARBOARD_CHANNEL_ID`.
- **Auto-mod kata kasar** (`src/cogs/automod.py` + `src/utils/filters.py`): pesan mengandung kata di `BAD_WORDS` → dihapus + warning; warning ke-`WARN_MAX` (default 3) → auto-mute (Discord timeout, persisten). Mod bypass. `/warnings` & `/reset-warn` (khusus mod).

### Ditambah (Tahap 5 — utilitas)
- **AFK** (`src/cogs/afk.py`): `/afk [alasan]` tandai pergi; kirim pesan apa pun → otomatis kembali; mention ke user AFK → bot balas statusnya.
- **Pengingat** (`src/cogs/reminders.py`): `/remind <durasi> <pesan>` → DM saat tiba (fallback mention channel); `/remind-list` & `/remind-batal <id>`. Data di SQLite → survive restart.

### Ditambah (Tahap 6 — 3 ide kecil)
- **Role reward per level** (`src/cogs/leveling.py`): role otomatis saat level tercapai, config `LEVEL_ROLES="5:Aktif,10:Veteran,20:Sepuh"`.
- **Welcome card bergambar** (`src/bot.py` + `src/utils/rankcard.py`): kartu PNG (avatar + nama + nomor member) dikirim ke channel welcome tiap ada yang join.
- **Server stats** (`src/cogs/serverstats.py`): 3 voice channel (`STATS_TOTAL_ID`, `STATS_HUMAN_ID`, `STATS_BOT_ID`) namanya update otomatis tiap 10 menit + saat join/keluar.

### Diperbaiki
- **Keamanan:** `.env.example` diperbarui mencakup semua key baru (`GUILD_ID`, `MUTE_DURATION_MINUTES`, `XP_PER_MESSAGE`, `XP_COOLDOWN_SECONDS`) + peringatan keras jangan sertakan `.env`/token di zip. (Token sempat ikut ke-zip — regenerate token di Developer Portal!)
- **Leaderboard & XP per-server:** tabel `users` kini pakai `guild_id` (composite PK `user_id, guild_id`); DB lama otomatis dimigrasi tanpa data hilang (`src/store.py`, `src/cogs/leveling.py`, `src/cogs/leaderboard.py`).
- **Tombol mati beneran mati:** `TimeoutSafeView` baru (`src/utils/views.py`) — leaderboard, help, dan konfirmasi bersihkan kini meng-update pesannya saat timeout, tombol jadi abu-abu alih-alih kelihatan bisa diklik.
- **Slash command tidak hilang tiap restart:** `setup_hook` tidak lagi menghapus global command setiap startup (dulu command sempat hilang ±1 jam setelah restart kalau `GUILD_ID` kosong).
