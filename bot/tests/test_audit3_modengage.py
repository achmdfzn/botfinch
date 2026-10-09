"""Regresi audit-3 TRACK MODERASI & ENGAGEMENT (worker B, gelombang-1).

Bug yang diperbaiki di gelombang ini:
1. sosial._cooldown_klaim — klaim cooldown atomik (anti double-post confess /
   double-klaim bonus nikah saat dua command dieksekusi nyaris bersamaan).
2. starboard._sync — entri basi (pesan starboard dihapus manual) dulu membuat
   update count berhenti selamanya; sekarang posting ulang.
3. moderation.on_member_join (anti-raid) & moderasi_plus.on_member_join
   (auto-lockdown) — dulu mengabaikan toggle automod_enabled; sekarang hormat.
4. moderasi_plus.cek_sla — satu baris gagal kirim log tidak membunuh loop 30-menit.
5. leveling.bersih_cooldown — _reaction_cooldown dulu tidak pernah di-evict.
6. tempvc.bersih_yatim (BARU) — channel yatim saat bot down/crash dibersihkan.
7. voicexp.top_voice — dulu tanpa cog_check; kini ikut leveling/economy toggle.

Pola: DB terisolasi per test via store.DB_PATH -> tmp dir (seperti test_giveaway.py).
Cog yang __init__-nya menyalakan tasks.loop dibuat via __new__ agar tidak
butuh event loop yang berjalan.
"""
import asyncio
import datetime
import sqlite3
import tempfile
from collections import defaultdict, deque
from unittest.mock import AsyncMock, MagicMock, patch

import discord

import src.store as store
from src.cogs import leveling as leveling_mod
from src.cogs import sosial as sosial_mod
from src.cogs.moderasi_plus import ModerasiPlus
from src.cogs.moderation import Moderation
from src.cogs.starboard import Starboard
from src.cogs.tempvc import TempVC
from src.cogs.voicexp import VoiceXP
from src.store import get_connection

GID = 515003  # guild id khusus file test ini


# ---------- util DB terisolasi ----------

def _db_baru():
    tmp = tempfile.mkdtemp()
    orig = store.DB_PATH
    store.DB_PATH = type(orig)(f"{tmp}/t.db")
    store.init_db()
    with get_connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS dashboard_settings ("
            " guild_id INTEGER NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,"
            " PRIMARY KEY (guild_id, key))"
        )
        conn.commit()
    return orig


def _db_kembali(orig):
    store.DB_PATH = orig


def _set(key, value):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO dashboard_settings (guild_id, key, value)"
            " VALUES (?, ?, ?)",
            (GID, str(key), str(value)),
        )
        conn.commit()


def _iso_menit_lalu(menit):
    return (
        discord.utils.utcnow() - datetime.timedelta(minutes=menit)
    ).isoformat()


# =====================================================================
# 1. _cooldown_klaim atomik
# =====================================================================

def _conn_klaim():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE cooldown_aksi (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL,"
        " aksi TEXT NOT NULL, terakhir TEXT NOT NULL,"
        " PRIMARY KEY (user_id, guild_id, aksi))"
    )
    return conn


class TestCooldownKlaim:
    def test_klaim_pertama_berhasil(self):
        conn = _conn_klaim()
        assert sosial_mod._cooldown_klaim(conn, 1, 7, "confess", 300) is True

    def test_klaim_kedua_langsung_gagal(self):
        conn = _conn_klaim()
        assert sosial_mod._cooldown_klaim(conn, 1, 7, "confess", 300) is True
        # klaim kedua dalam masa cooldown -> kalah
        assert sosial_mod._cooldown_klaim(conn, 1, 7, "confess", 300) is False

    def test_klaim_setelah_kedaluwarsa_berhasil(self):
        conn = _conn_klaim()
        assert sosial_mod._cooldown_klaim(conn, 1, 7, "confess", 300) is True
        # mundurkan `terakhir` 10 menit -> cooldown habis
        lama = (
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(minutes=10)
        ).isoformat()
        conn.execute("UPDATE cooldown_aksi SET terakhir = ?", (lama,))
        conn.commit()
        assert sosial_mod._cooldown_klaim(conn, 1, 7, "confess", 300) is True

    def test_sisa_positif_setelah_klaim(self):
        conn = _conn_klaim()
        sosial_mod._cooldown_klaim(conn, 1, 7, "confess", 300)
        sisa = sosial_mod._cooldown_sisa(conn, 1, 7, "confess", 300)
        assert sisa > 0

    def test_guild_dan_user_independen(self):
        conn = _conn_klaim()
        assert sosial_mod._cooldown_klaim(conn, 1, 7, "confess", 300) is True
        assert sosial_mod._cooldown_klaim(conn, 2, 7, "confess", 300) is True
        assert sosial_mod._cooldown_klaim(conn, 1, 8, "confess", 300) is True


# =====================================================================
# 2. Starboard: entri basi -> posting ulang (bukan stuck)
# =====================================================================

SRC_CH = 222
SB_CH = 99999


def _pesan(bintang, msg_id):
    msg = MagicMock()
    msg.id = msg_id
    msg.content = "halo dunia"
    msg.jump_url = "https://discord.com/channels/x/777"
    msg.created_at = datetime.datetime.now(datetime.timezone.utc)
    msg.author.bot = False
    msg.author.id = 4242
    msg.author.display_avatar.url = "https://cdn.discordapp.com/x.png"
    msg.attachments = []
    reaksi = MagicMock()
    reaksi.emoji = "⭐"
    reaksi.count = bintang
    msg.reactions = [reaksi]
    return msg


def _text_channel(cid, msg=None, sb_msg=None, fetch_raises=None):
    ch = MagicMock(spec=discord.TextChannel)
    ch.id = cid
    ch.mention = f"<#{cid}>"
    if fetch_raises is not None:
        ch.fetch_message = AsyncMock(side_effect=fetch_raises)
    else:
        ch.fetch_message = AsyncMock(return_value=msg or sb_msg)
    baru = MagicMock()
    baru.id = 31337
    ch.send = AsyncMock(return_value=baru)
    return ch, baru


def _payload(msg_id):
    p = MagicMock()
    p.emoji = "⭐"
    p.guild_id = GID
    p.message_id = msg_id
    p.channel_id = SRC_CH
    return p


def _pengaturan(koin=0):
    stub = MagicMock()
    stub.starboard_channel_id = 0
    stub.starboard_min = 3
    stub.starboard_koin = koin
    return patch("src.config.settings", new=stub)


class TestStarboardRepost:
    def _siap(self, msg_id, sb_lama_id, fetch_raises=None, sb_msg=None):
        orig = _db_baru()
        _set("starboard_enabled", "1")
        _set("starboard_channel_id", str(SB_CH))
        _set("starboard_threshold", "3")
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO starboard (message_id, starboard_msg_id, channel_id)"
                " VALUES (?, ?, ?)",
                (msg_id, sb_lama_id, SRC_CH),
            )
            conn.commit()
        msg = _pesan(5, msg_id)
        ch_src, _ = _text_channel(SRC_CH, msg=msg)
        sb_ch, sb_baru = _text_channel(SB_CH, sb_msg=sb_msg, fetch_raises=fetch_raises)
        bot = MagicMock()
        guild = MagicMock()
        peta = {SRC_CH: ch_src, SB_CH: sb_ch}
        guild.get_channel = MagicMock(side_effect=lambda cid: peta.get(cid))
        bot.get_guild = MagicMock(return_value=guild)
        return orig, Starboard(bot), sb_ch, sb_baru

    def test_entri_basi_posting_ulang(self):
        """Pesan starboard dihapus manual -> _sync posting ulang, DB di-update."""
        notfound = discord.NotFound(MagicMock(), MagicMock())
        orig, cog, sb_ch, sb_baru = self._siap(777001, 555000, fetch_raises=notfound)
        try:
            with _pengaturan():
                asyncio.run(cog._sync(_payload(777001)))
            sb_ch.send.assert_called_once()
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT starboard_msg_id FROM starboard WHERE message_id = ?",
                    (777001,),
                ).fetchone()
            assert row[0] == sb_baru.id
        finally:
            _db_kembali(orig)

    def test_pesan_masih_ada_hanya_edit(self):
        """Jalur normal tidak berubah: pesan ada -> edit, bukan posting baru."""
        sb_lama = MagicMock()
        sb_lama.edit = AsyncMock()
        orig, cog, sb_ch, _ = self._siap(777002, 555001, sb_msg=sb_lama)
        try:
            with _pengaturan():
                asyncio.run(cog._sync(_payload(777002)))
            sb_lama.edit.assert_called_once()
            sb_ch.send.assert_not_called()
        finally:
            _db_kembali(orig)


# =====================================================================
# 3. Toggle automod untuk anti-raid & auto-lockdown (on_member_join)
# =====================================================================

class TestAutomodToggleJoin:
    def _member(self, guild, uid):
        m = MagicMock()
        m.id = uid
        m.guild = guild
        m.timeout = AsyncMock()
        return m

    def test_anti_raid_mati_saat_automod_off(self):
        orig = _db_baru()
        _set("automod_enabled", "0")
        try:
            cog = Moderation.__new__(Moderation)
            cog.bot = MagicMock()
            import src.cogs.moderation as mod

            mod._join_riwayat.clear()
            guild = MagicMock()
            guild.id = GID
            guild.edit = AsyncMock()
            with patch.object(mod.modlog, "log_event", new=AsyncMock()):
                for i in range(10):
                    asyncio.run(cog.on_member_join(self._member(guild, 100 + i)))
            guild.edit.assert_not_called()
        finally:
            _db_kembali(orig)

    def test_anti_raid_jalan_saat_automod_on(self):
        orig = _db_baru()
        try:
            cog = Moderation.__new__(Moderation)
            cog.bot = MagicMock()
            import src.cogs.moderation as mod

            mod._join_riwayat.clear()
            guild = MagicMock()
            guild.id = GID
            guild.edit = AsyncMock()
            with patch.object(mod.modlog, "log_event", new=AsyncMock()):
                for i in range(5):
                    asyncio.run(cog.on_member_join(self._member(guild, 200 + i)))
            guild.edit.assert_called_once()  # verification level dinaikkan
        finally:
            _db_kembali(orig)

    def test_auto_lockdown_mati_saat_automod_off(self):
        orig = _db_baru()
        _set("automod_enabled", "0")
        try:
            cog = ModerasiPlus.__new__(ModerasiPlus)
            cog.bot = MagicMock()
            cog._join_riwayat = defaultdict(lambda: deque(maxlen=50))
            cog._lockdown_terakhir = {}
            cog._auto_lockdown = AsyncMock()
            guild = MagicMock()
            guild.id = GID
            for i in range(12):
                asyncio.run(cog.on_member_join(self._member(guild, 300 + i)))
            cog._auto_lockdown.assert_not_called()
        finally:
            _db_kembali(orig)

    def test_auto_lockdown_jalan_saat_automod_on(self):
        orig = _db_baru()
        try:
            cog = ModerasiPlus.__new__(ModerasiPlus)
            cog.bot = MagicMock()
            cog._join_riwayat = defaultdict(lambda: deque(maxlen=50))
            cog._lockdown_terakhir = {}
            cog._auto_lockdown = AsyncMock()
            guild = MagicMock()
            guild.id = GID
            for i in range(8):
                asyncio.run(cog.on_member_join(self._member(guild, 400 + i)))
            cog._auto_lockdown.assert_called_once()
        finally:
            _db_kembali(orig)


# =====================================================================
# 4. cek_sla tahan banting: 1 baris gagal tidak membunuh loop
# =====================================================================

class TestCekSlaTahanBanting:
    def test_loop_tetap_hidup_walau_log_gagal(self):
        orig = _db_baru()
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO tickets (channel_id, guild_id, owner_id, closed,"
                    " created_at, balas_terakhir) VALUES (?, ?, ?, 0, ?, ?)",
                    (9001, GID, 5, _iso_menit_lalu(60 * 30), _iso_menit_lalu(60 * 30)),
                )
                conn.commit()
            cog = ModerasiPlus.__new__(ModerasiPlus)
            cog.bot = MagicMock()
            import src.cogs.moderasi_plus as mp

            with patch.object(
                mp.modlog, "log_event", new=AsyncMock(side_effect=RuntimeError("boom"))
            ):
                # tidak boleh raise: exception per-baris ditangkap di dalam loop
                asyncio.run(cog.cek_sla.coro(cog))
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT 1 FROM sla_warned WHERE channel_id = ?", (9001,)
                ).fetchone()
            assert row is not None  # tetap ditandai, anti alert ganda
        finally:
            _db_kembali(orig)


# =====================================================================
# 5. bersih_cooldown evict _reaction_cooldown juga
# =====================================================================

class TestBersihCooldown:
    def test_reaction_cooldown_ikut_dievict(self):
        import time

        cog = leveling_mod.Leveling.__new__(leveling_mod.Leveling)
        cog.bot = MagicMock()
        lama = time.time() - 7200
        baru = time.time()
        simpan_xp = dict(leveling_mod._xp_cooldown)
        simpan_rx = dict(leveling_mod._reaction_cooldown)
        try:
            leveling_mod._xp_cooldown[(GID, 1)] = lama
            leveling_mod._reaction_cooldown[(GID, 2)] = lama
            leveling_mod._reaction_cooldown[(GID, 3)] = baru
            asyncio.run(cog.bersih_cooldown.coro(cog))
            assert (GID, 1) not in leveling_mod._xp_cooldown
            assert (GID, 2) not in leveling_mod._reaction_cooldown
            assert (GID, 3) in leveling_mod._reaction_cooldown  # masih segar
        finally:
            leveling_mod._xp_cooldown.clear()
            leveling_mod._xp_cooldown.update(simpan_xp)
            leveling_mod._reaction_cooldown.clear()
            leveling_mod._reaction_cooldown.update(simpan_rx)


# =====================================================================
# 6. bersih_yatim tempvc
# =====================================================================

class TestTempvcBersihYatim:
    def _voice(self, members):
        ch = MagicMock(spec=discord.VoiceChannel)
        ch.members = members
        ch.delete = AsyncMock()
        return ch

    def test_yatim_dibersihkan(self):
        orig = _db_baru()
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO tempvc (channel_id, owner_id, guild_id)"
                    " VALUES (1001, 11, ?)",
                    (GID,),
                )
                conn.execute(
                    "INSERT INTO tempvc (channel_id, owner_id, guild_id)"
                    " VALUES (1002, 12, ?)",
                    (GID,),
                )
                conn.execute(
                    "INSERT INTO tempvc (channel_id, owner_id, guild_id)"
                    " VALUES (1003, 13, ?)",
                    (GID,),
                )
                conn.commit()
            cog = TempVC.__new__(TempVC)
            bot = MagicMock()
            guild = MagicMock()
            ch_kosong = self._voice([])
            ch_isi = self._voice([MagicMock()])
            peta = {1001: None, 1002: ch_kosong, 1003: ch_isi}
            guild.get_channel = MagicMock(side_effect=lambda cid: peta.get(cid))
            bot.get_guild = MagicMock(return_value=guild)
            cog.bot = bot
            asyncio.run(cog.bersih_yatim.coro(cog))
            ch_kosong.delete.assert_called_once()  # yatim -> dihapus
            ch_isi.delete.assert_not_called()  # berpenghuni -> aman
            with get_connection() as conn:
                sisa = {
                    r[0]
                    for r in conn.execute("SELECT channel_id FROM tempvc").fetchall()
                }
            assert sisa == {1003}  # baris yatim ikut dibersihkan
        finally:
            _db_kembali(orig)


# =====================================================================
# 7. top-voice ikut toggle leveling/economy
# =====================================================================

def _ctx_guild(guild_id):
    ctx = MagicMock()
    ctx.guild.id = guild_id
    ctx.interaction = None
    ctx.send = AsyncMock()
    return ctx


class TestTopVoiceToggle:
    def _cog(self):
        cog = VoiceXP.__new__(VoiceXP)
        cog.bot = MagicMock()
        return cog

    def test_diblokir_bila_keduanya_mati(self):
        orig = _db_baru()
        _set("leveling_enabled", "0")
        _set("economy_enabled", "0")
        try:
            ctx = _ctx_guild(GID)
            hasil = asyncio.run(self._cog().cog_check(ctx))
            assert hasil is False
            ctx.send.assert_called_once()  # pesan penjelasan terkirim
        finally:
            _db_kembali(orig)

    def test_lolos_bila_leveling_aktif(self):
        orig = _db_baru()
        _set("economy_enabled", "0")  # leveling default "1"
        try:
            assert asyncio.run(self._cog().cog_check(_ctx_guild(GID))) is True
        finally:
            _db_kembali(orig)

    def test_lolos_bila_hanya_ekonomi_aktif(self):
        orig = _db_baru()
        _set("leveling_enabled", "0")
        try:
            assert asyncio.run(self._cog().cog_check(_ctx_guild(GID))) is True
        finally:
            _db_kembali(orig)

    def test_dm_selalu_lolos(self):
        orig = _db_baru()
        try:
            ctx = MagicMock()
            ctx.guild = None
            assert asyncio.run(self._cog().cog_check(ctx)) is True
        finally:
            _db_kembali(orig)
