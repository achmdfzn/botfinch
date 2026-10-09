# PRD — Finch (Discord Bot)

> Product Requirements Document. Baca ini dulu sebelum nambah fitur.

## 1. Ringkasan

**Finch** adalah bot Discord untuk server **Pioneer Outpost Nusa** (komunitas game milik Fauzan).
Tujuannya: menjaga server tetap bersih dari spam, menyambut member baru secara otomatis,
dan meringankan kerja moderator — tanpa bot yang terasa "kaku".

## 2. Masalah yang diselesaikan

- Chat rame → spam dan flood message mengganggu obrolan.
- Member baru datang tanpa disapa, tidak tahu harus baca rules di mana.
- Moderator kewalahan menghapus pesan satu per satu.
- Server rawan disusupi raider / tukang sebar invite server lain (nuke ringan).
- Tidak ada jejak audit: siapa yang di-moderasi, kapan, kenapa.

## 3. Target pengguna

| Peran      | Kebutuhan                                   |
|------------|----------------------------------------------|
| Member     | Chat nyaman, tahu perintah bot, disambut saat join |
| Moderator  | Hapus pesan massal cepat, dapat peringatan spam otomatis |
| Admin (Fauzan) | Config gampang (via `.env`), fitur bisa ditambah per-cog |

## 4. Fitur v1 (sudah jalan ✅)

| Fitur | Perintah / Trigger | Kriteria diterima |
|-------|-------------------|-------------------|
| Cek status | `!ping` atau `/ping` | Bot balas "Pong!" + latency |
| Sapaan | `!halo` atau `/halo` | Bot menyapa balik dengan mention |
| Info server | `!serverinfo` atau `/serverinfo` | Embed: owner, jumlah member, channel, tanggal dibuat, boost |
| Daftar perintah | `!bantuan` atau `/bantuan` | Embed berisi semua perintah (bagian moderator hanya tampil untuk mod) |
| Welcome message | Member join | Pesan sambutan di channel welcome / system channel |
| Anti-spam | Otomatis | >5 pesan dalam 5 detik → pesan spam dihapus + peringatan + auto-mute (`MUTE_DURATION_MINUTES`). Admin/mod bebas filter |
| Cek level | `!level` atau `/level` | Embed estetik dengan progress bar `█░` berdasarkan XP dari SQLite |
| Leaderboard | `!leaderboard` atau `/leaderboard` | Papan peringkat 10 member teratas (dengan medali 🥇🥈🥉) |
| Anti-invite-link | Otomatis | Link `discord.gg` / `discord.com/invite` dihapus + peringatan; tercatat di mod-log. Bisa dimatikan via `ANTI_INVITE=false` |
| Bersihkan chat | `!bersihkan <n>` atau `/bersihkan <n>` (khusus mod) | Embed konfirmasi ⚠️ dengan tombol ✅/❌ (ephemeral untuk slash), hapus 1-100 pesan, tercatat di mod-log |
| Verifikasi member | Join + tombol ✅ (panel persistent) | Member baru dapat role "Belum Verifikasi" (tidak bisa chat); klik tombol **Verifikasi** di panel → dapat role "Member". Panel dipasang sekali via `/verifikasi`, tetap jalan setelah restart. Verifikasi tercatat di mod-log |
| Kartu rank | `/rank` atau `!rank [@user]` | Kartu PNG ala MEE6: avatar lingkaran, badge level, progress bar XP, peringkat server |
| Mod-log | Otomatis | Spam, invite-link, `!bersihkan`, verifikasi, member keluar → embed timestamp di channel log |
| Tiket support | `/panel-tiket` + tombol | Channel privat per laporan (maks 1 terbuka/user); tutup → transcript .txt ke mod-log |
| Giveaway | `/giveaway <durasi> <pemenang> <hadiah>` | Tombol "Ikut" (toggle), undi otomatis saat habis, tombol "Reroll"; survive restart |
| Self-roles | `/panel-role` + select menu | Member pasang/lepas role sendiri; daftar dari `SELF_ROLES` |
| Polling | `/poll "tanya" "a, b" [durasi]` | Vote tombol 2–5 opsi, hasil real-time, tutup otomatis/manual |
| Starboard | Reaksi ⭐ otomatis | Pesan capai ambang ⭐ dipajang di channel khusus |
| Auto-mod kata kasar | Otomatis | Filter `BAD_WORDS` → warning; batas warning → auto-mute |
| AFK | `/afk [alasan]` | Status pergi; mention → balasan otomatis; kirim pesan → kembali |
| Pengingat | `/remind <durasi> <pesan>` | DM saat tiba (fallback channel); list & batal via ID |
| Role reward | Otomatis per level | Config `LEVEL_ROLES="5:Aktif,10:Veteran"` |
| Welcome card | Otomatis saat join | Kartu PNG: avatar + nama + nomor member |
| Server stats | Otomatis | 3 voice channel: total/manusia/bot, update tiap 10 menit |
| Temp voice | Join lobby `➕ Buat Room` | Auto-buat `🔊・<nama>-room`, pindah member, kosong → hapus. Owner: `/vc-lock`, `/vc-unlock`, `/vc-limit`, `/vc-rename` |
| Saran | `/saran <teks>` / kelola status | Kirim ke `SARAN_CHANNEL_ID` + vote 👍👎; mod: `/saran-status <id> <diterima/ditolak/dipertimbangkan>` → edit embed + mod-log |
| Notifikasi YouTube | Otomatis via RSS | Poll `youtube.com/feeds/videos.xml?channel_id=` → kirim embed video baru ke `YT_NOTIFY_CHANNEL_ID` |
| Voice XP | Otomatis di voice | Nongkrong di voice dapat XP per menit (`VOICE_XP_PER_MIN`) |
| Invite Tracker | `/invites` & `/invite-lb` | Lacak siapa mengundang siapa, top 10 inviter server |

## 5. Fitur v2 (roadmap)

Prioritas dari atas ke bawah:

1. **Slash commands** — ✅ *Selesai* (Hybrid `!` dan `/`).
2. **Level / XP & Leaderboard** — ✅ *Selesai* (`src/cogs/leveling.py` & `src/cogs/leaderboard.py`).
3. **Auto-mute sementara** — ✅ *Selesai* (otomatis di-mute X menit jika spam).
4. **Auto-restart & Robust Logging** — ✅ *Selesai* (`run.bat`, `run.sh`, logging UTF-8 di `main.py`).
5. **Verifikasi tombol persistent** — ✅ *Selesai* (ganti reaksi ✅; panel dipasang via `/verifikasi`).
6. **Kartu rank bergambar** — ✅ *Selesai* (`/rank`, `src/utils/rankcard.py` + Pillow).
7. **Tiket support** — ✅ *Selesai* (`/panel-tiket`, channel privat + transcript).
8. **Giveaway otomatis** — ✅ *Selesai* (`/giveaway`, tombol ikut + reroll).
9. **Self-roles** — ✅ *Selesai* (`/panel-role`, select menu dari `SELF_ROLES`).
10. **Polling** — ✅ *Selesai* (`/poll`, tombol vote + tutup otomatis).
11. **Starboard** — ✅ *Selesai* (reaksi ⭐ → dipajang otomatis).
12. **Auto-mod kata kasar** — ✅ *Selesai* (filter + warning + auto-mute).
13. **AFK** — ✅ *Selesai* (`/afk`, auto-clear + balasan mention).
14. **Pengingat** — ✅ *Selesai* (`/remind`, DM + list/batal).
15. **Role reward per level** — ✅ *Selesai* (`LEVEL_ROLES`).
16. **Welcome card bergambar** — ✅ *Selesai* (otomatis saat join).
17. **Server stats counter** — ✅ *Selesai* (voice channel auto-update).
18. **Temp voice channel** — ✅ *Selesai* (`src/cogs/tempvc.py`, lobby `TEMPVC_LOBBY_ID` / `TEMPVC_CATEGORY_ID`).
19. **Sistem saran** — ✅ *Selesai* (`src/cogs/saran.py`, `/saran` + `/saran-status` → `SARAN_CHANNEL_ID`).
20. **Laporkan ke Mod (context menu)** — ✅ *Selesai* (`src/cogs/report.py`, klik kanan pesan → tiket).
21. **Notifikasi YouTube** — ✅ *Selesai* (`src/cogs/youtube.py`, poll RSS `YT_CHANNEL_ID` → `YT_NOTIFY_CHANNEL_ID`).
22. **Voice XP** — ✅ *Selesai* (`src/cogs/voicexp.py` + `src/utils/xp.py`, `VOICE_XP_PER_MIN`).
23. **Invite tracker** — ✅ *Selesai* (`src/cogs/invites.py`, `intents.invites` → `/invites`, `/invite-lb`).
24. **Dashboard web** — ganti setting tanpa edit `.env` (subsistem baru, jangan ditempel ke proses bot).

## 6. Batasan & non-fungsional

- Bahasa: Python 3.10+, library `discord.py`.
- Prefix perintah: `!` (v1). Bahasa balasan bot: santai, Indonesia.
- Privileged intents wajib ON di Developer Portal: **Message Content** + **Server Members**.
- Token bot **tidak boleh** masuk git / dishare. Config hanya lewat `.env`.
- Hosting: bot harus jalan 24/7 — keputusan hosting (VPS / Railway / Replit dsb.) belum diambil.
- Target respon perintah: < 3 detik di kondisi normal.

## 7. Risiko

- Discord API berubah / `discord.py` update breaking → pin versi di `requirements.txt`.
- Token bocor → bot diambil alih. Mitigasi: `.env` di `.gitignore`, reset token segera kalau bocor.
- Bot offline = semua fitur mati → butuh monitoring sederhana (mis. cron cek proses).

## 8. Kriteria "selesai" untuk v1

- [x] Semua perintah di §4 lolos tes manual di server (`!ping` dibalas).
- [x] Verifikasi end-to-end: akun tes join → dapat role unverified → klik tombol Verifikasi → dapat role Member.
- [x] Invite-link dari akun non-mod terhapus otomatis.
- [x] Semua aksi moderasi muncul di channel mod-log.
- [ ] Bot jalan stabil 24 jam tanpa crash di environment hosting final.
- [ ] README setup bisa diikuti dari nol tanpa tanya-tanya.
