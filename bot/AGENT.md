# AGENT.md — Panduan Kerja di Repo Finch

> File ini untuk AI coding assistant (dan manusia) yang mau ubah-ubah kode bot.
> Baca ini sebelum nulis atau refactor kode.

## Cara jalanin (local)

```bash
pip install -r requirements.txt
cp .env.example .env   # lalu isi DISCORD_TOKEN
python main.py
```

Cek berhasil: terminal menampilkan `✅ Finch#xxxx udah online dan siap!`.
Log tersimpan di `logs/finch.log`.

## Struktur

```
main.py                # entry point tipis: validasi config → jalanin bot
src/
├── bot.py             # class FinchBot: intents, setup_hook (auto-load cog), event
├── config.py          # Settings dataclass; baca .env, dipakai semua modul
├── store.py           # persistensi SQLite (data/finch.db)
├── cogs/
│   ├── general.py     # perintah umum (!status, !userinfo, !serverinfo, !bantuan) — hybrid slash
│   ├── moderation.py  # anti-spam (auto-mute) + anti-invite + !bersihkan (semua di-log)
│   ├── verification.py# panel + tombol persistent: klik "Verifikasi" → role verified
│   ├── leveling.py    # sistem Level/XP chat
│   ├── voicexp.py     # XP dari voice channel
│   ├── leaderboard.py # papan peringkat member
│   ├── tickets.py     # tiket support + transcript
│   ├── giveaway.py    # giveaway + tombol ikut/reroll
│   ├── economy.py     # sistem koin: /saldo, /daily, /kerja, /transfer, /top-koin, /rep (UI horizontal)
│   ├── minigames.py   # coinflip, slot, tebak-angka, trivia (taruhan/koin)
│   ├── shop.py        # /shop, /buy — beli role pakai koin
│   ├── counting.py    # counting channel + /counting-reset
│   ├── quests.py      # /quest harian + tombol klaim
│   ├── selfroles.py   # panel self-role
│   ├── polls.py       # polling tombol
│   ├── starboard.py   # starboard
│   ├── afk.py         # status AFK
│   ├── reminders.py   # pengingat
│   ├── serverstats.py # counter member di voice channel
│   ├── automod.py     # filter kata kasar + warn
│   ├── tempvc.py      # temporary voice channel
│   ├── saran.py       # /saran ke channel saran
│   ├── report.py      # context menu "Laporkan ke Mod"
│   ├── youtube.py     # notifikasi YouTube via RSS
│   ├── invites.py     # invite tracker
│   ├── season.py      # season XP + reset + hadiah top 3
│   ├── achievement.py # /achievement — lencana otomatis
│   ├── responder.py   # auto-responder custom (mod)
│   ├── birthday.py    # /ultah + pengumuman + bonus koin
│   ├── sticky.py      # sticky message per channel
│   ├── bump.py        # /bump + deteksi DISBOARD
│   ├── events.py      # /event + RSVP + reminder
│   ├── profil.py      # /profil gabungan
│   └── twitch.py      # notifikasi Twitch live
└── utils/
    ├── embeds.py      # helper embed biar tampilan konsisten
    ├── filters.py     # logika teks murni (invite-link, parse_durasi), ada unit test
    ├── modlog.py      # log_event(): catat kejadian ke channel mod-log
    ├── views.py       # TimeoutSafeView: disable tombol kedaluwarsa
    ├── rankcard.py    # kartu /rank + welcome PNG (Pillow)
    ├── economy.py     # logika koin terpusat (akun, klaim, transfer, peringkat, rep, trivia), ada unit test
    ├── quests.py      # quest harian (progres + klaim), ada unit test
    ├── achievement.py # definisi & cek achievement otomatis, ada unit test
    └── xp.py          # tambah_xp() + beri_role_reward() terpusat
tests/                 # unit test: python -m unittest discover tests
data/                  # data runtime (db dsb.), gitignored
logs/                  # finch.log, gitignored
```

## Konvensi kode

1. **Satu fitur = satu cog.** File baru di `src/cogs/`, class `commands.Cog`, wajib ada fungsi
   `async def setup(bot)` di akhir file — `FinchBot.setup_hook` auto-load semua file `.py` di `src/cogs/`.
2. **Hybrid slash (`!` + `/`).** Nama perintah lowercase Indonesia (`!bersihkan`/`/bersihkan`, bukan `!purge`).
   Pakai `@commands.hybrid_command(name="xxx", description="...")` agar command auto jadi prefix dan slash.
3. **Balasan ke user pakai Bahasa Indonesia santai** (lihat gaya di `general.py`).
   Jangan kaku kayak template dokumentasi.
4. **Permission check pakai decorator**, mis. `@commands.has_permissions(manage_messages=True)`.
5. **Jangan hardcode** ID channel / token / angka config — tambah field di `src/config.py`
   (`Settings`), baca via `config.settings`, dokumentasikan di `.env.example`.
6. Docstring singkat di tiap cog & command menjelaskan cara pakai.
7. Error yang user bisa picu (mis. `!bersihkan` tanpa argumen valid) harus ditangani
   dengan pesan ramah, bukan traceback.
8. Embed ke user pakai helper di `src/utils/embeds.py` biar konsisten.
9. Kejadian yang perlu diaudit (moderasi, join/leave, verifikasi) WAJIB lewat
   `await modlog.log_event(bot, ...)`, jangan kirim manual ke channel log.
10. Logika teks murni (regex, parsing) taruh di `src/utils/filters.py` +
    unit test — jangan campur dengan kode Discord API.

## Contoh nambah perintah baru

```python
# src/cogs/namafitur.py
from discord.ext import commands

class NamaFitur(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="contoh", description="Penjelasan singkat")
    async def contoh(self, ctx: commands.Context):
        """Penjelasan singkat: !contoh / /contoh"""
        await ctx.send(f"Halo, {ctx.author.mention}!")

async def setup(bot: commands.Bot):
    await bot.add_cog(NamaFitur(bot))
```

Restart bot — cog otomatis ke-load, tidak perlu edit file lain.

## Gotcha (jangan sampai keulang)

- **Privileged Intents**: `message_content` dan `members` harus ON di
  Discord Developer Portal → Bot → Privileged Gateway Intents, kalau tidak
  command & event member tidak jalan.
- **Jangan override `on_message` di `src/bot.py`** tanpa `await self.process_commands(message)` —
  kalau dilanggar, semua `!command` mati. Listener tambahan taruh di cog pakai
  `@commands.Cog.listener()`.
- Anti-spam di `moderation.py` skip user dengan `manage_messages` — jangan hapus logika ini
  tanpa ganti mekanisme whitelist.
- `requirements.txt` di-pin versinya; kalau upgrade `discord.py`, tes `!status` dulu.
- **Keamanan**: tidak ada token / secret dalam bentuk apa pun di kode, log, atau commit.
- **Batas 100 slash command**: top-level harus ≤100 (cek: load semua cog, `len([c for c in bot.commands if c.parent is None])`). Command baru masuk ke hybrid group yang ada.
- **Koin anti-race**: guarded flag di awal button handler; guarded `UPDATE ... WHERE balance >= ?` untuk jual-beli; jangan potong koin di muka untuk aksi yang butuh konfirmasi (trade) — potong saat dikonfirmasi.

## Cara tes

1. Jalankan `python main.py` (atau `run.bat` untuk auto-restart).
2. Di server Discord (pakai server test kalau ada): `!status` → harus dibalas embed status.
3. Tes slash: `/userinfo` → harusnya dibalas embed info member.
4. Cek leaderboard: `/leaderboard` → tampilkan top 10 member.
5. Cek level: `/level` → tampilkan status level XP dengan progress bar.
6. Untuk fitur moderasi: spam >5 pesan dalam 5 detik dari akun non-mod → pesan dihapus + peringatan muncul + di-mute.
7. Kalau nambah cog baru: pastikan tidak ada error import saat startup.

## Referensi produk

- Kebutuhan & roadmap: `PRD.md`
- Desain teknis: `ARCHITECTURE.md`
- Setup dari nol (buat manusia): `README.md`
- Riwayat perubahan: `CHANGELOG.md`
