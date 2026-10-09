"""Test fondasi 'plugin system' + fitur paritas MEE6.

Toggle modul (key "*_enabled", "1"/"0", default "1" = perilaku lama):
- selfroles_enabled, giveaway_enabled, responder_enabled,
  announcements_enabled, embed_enabled. (starboard_enabled default "0" = OFF
  selaras dashboard; lihat test_starboard_default_off_selaras_dashboard.)
- Pull settings dashboard generik (tanpa allowlist) -> key baru otomatis tersimpan.

Fitur paritas MEE6:
- Welcome auto-role: `welcome_role_ids` (daftar ID dipisah koma) di on_member_join.
- Variabel responder: {user} {server} {member_count} {channel}.
- {member_count} di pesan welcome/goodbye & pengumuman terjadwal.

Jalanin: ~/workspace/.venv-finch/bin/python -m pytest tests/test_toggle_plugin.py -q
"""
import asyncio
import io
from unittest.mock import AsyncMock, MagicMock, patch

from src.bot import MENTIONS_PENGUMUMAN, FinchBot
from src.cogs.dashboard_sync import (
    TABEL_ANNOUNCEMENTS,
    TABEL_SETTINGS,
    DashboardSync,
    modul_aktif,
    parse_id_list,
    substitusi_pengumuman,
)
from src.cogs.giveaway import Giveaway
from src.cogs.responder import Responder
from src.cogs.selfroles import SelfRoles
from src.cogs.starboard import Starboard
from src.store import get_connection, init_db
from src.utils.variabel import substitusi_variabel

init_db()
with get_connection() as _c:
    _c.execute(TABEL_SETTINGS)
    _c.execute(TABEL_ANNOUNCEMENTS)
    _c.commit()

GID = 515000  # guild id khusus file test ini


def _set(key: str, value: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO dashboard_settings (guild_id, key, value)"
            " VALUES (?, ?, ?)",
            (GID, str(key), str(value)),
        )
        conn.commit()


def _bersih() -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM dashboard_settings WHERE guild_id = ?", (GID,))
        conn.execute("DELETE FROM autoresponder WHERE guild_id = ?", (GID,))
        conn.execute("DELETE FROM dashboard_announcements WHERE guild_id = ?", (str(GID),))
        conn.execute("DELETE FROM economy WHERE guild_id = ?", (GID,))
        conn.commit()


def _ctx():
    ctx = MagicMock()
    ctx.guild.id = GID
    ctx.send = AsyncMock()
    ctx.interaction = None
    return ctx


# ---------- helper modul_aktif / parse_id_list ----------

def test_modul_aktif_default_true():
    _bersih()
    assert modul_aktif(GID, "selfroles_enabled") is True


def test_modul_aktif_mati():
    _bersih()
    _set("selfroles_enabled", "0")
    assert modul_aktif(GID, "selfroles_enabled") is False


def test_modul_aktif_nyala():
    _bersih()
    _set("selfroles_enabled", "1")
    assert modul_aktif(GID, "selfroles_enabled") is True


def test_parse_id_list():
    assert parse_id_list("123, 456") == [123, 456]
    assert parse_id_list("123,abc, 789 ,") == [123, 789]
    assert parse_id_list("") == []
    assert parse_id_list(None) == []


# ---------- substitusi variabel ----------

def test_substitusi_variabel_semua():
    teks = substitusi_variabel(
        "Hai {user} di {server} ({member_count}) lewat {channel}!",
        user="<@7>",
        server="Srv",
        member_count=42,
        channel="<#9>",
    )
    assert teks == "Hai <@7> di Srv (42) lewat <#9>!"


def test_substitusi_variabel_tanpa_member_count():
    # placeholder {member_count} dibiarkan bila tidak diberikan
    assert substitusi_variabel("n={member_count}", user="u") == "n={member_count}"
    assert substitusi_variabel(None, user="u") == ""


def test_substitusi_pengumuman_member_count():
    assert substitusi_pengumuman("Srv {server} {date}", "X", member_count=10).count("{member_count}") == 0
    assert "{member_count}" not in substitusi_pengumuman("m={member_count}", "X", member_count=10)
    # kompatibel mundur: tanpa member_count tetap jalan
    assert "{server}" not in substitusi_pengumuman("s={server}", "X")


# ---------- selfroles toggle ----------

def test_selfroles_cog_check_mati():
    _bersih()
    _set("selfroles_enabled", "0")
    cog = SelfRoles(MagicMock())
    assert asyncio.run(cog.cog_check(_ctx())) is False


def test_selfroles_cog_check_nyala_default():
    _bersih()
    cog = SelfRoles(MagicMock())
    assert asyncio.run(cog.cog_check(_ctx())) is True


def test_selfroles_reaction_mati():
    _bersih()
    _set("selfroles_enabled", "0")
    bot = MagicMock()
    cog = SelfRoles(bot)
    payload = MagicMock()
    payload.guild_id = GID
    payload.user_id = 999
    asyncio.run(cog.on_raw_reaction_add(payload))
    asyncio.run(cog.on_raw_reaction_remove(payload))
    bot.get_guild.assert_not_called()


# ---------- giveaway toggle ----------

def test_giveaway_cog_check_mati():
    _bersih()
    _set("giveaway_enabled", "0")
    cog = Giveaway.__new__(Giveaway)  # tanpa start loop
    ctx = _ctx()
    assert asyncio.run(Giveaway.cog_check(cog, ctx)) is False
    ctx.send.assert_called_once()


def test_giveaway_cog_check_nyala():
    _bersih()
    cog = Giveaway.__new__(Giveaway)
    assert asyncio.run(Giveaway.cog_check(cog, _ctx())) is True


def test_proses_giveaway_mati_ack_failed():
    _bersih()
    _set("giveaway_enabled", "0")
    bot = MagicMock()
    sync = DashboardSync(bot)
    sync._ack_giveaway = AsyncMock()
    guild = MagicMock()
    guild.id = GID
    asyncio.run(sync._proses_giveaway(guild, [{"id": 1, "channel_id": "5"}]))
    sync._ack_giveaway.assert_called_once()
    args = sync._ack_giveaway.call_args[0]
    assert args[2] == "failed"
    assert "dimatikan" in args[3]


# ---------- embed toggle ----------

def test_proses_embed_mati_ack_failed():
    _bersih()
    _set("embed_enabled", "0")
    bot = MagicMock()
    sync = DashboardSync(bot)
    sync._ack_embed = AsyncMock()
    guild = MagicMock()
    guild.id = GID
    asyncio.run(
        sync._proses_embed(guild, [{"id": 2, "channel_id": "5", "title": "x"}])
    )
    sync._ack_embed.assert_called_once()
    args = sync._ack_embed.call_args[0]
    assert args[2] == "failed"
    assert "dimatikan" in args[3]


# ---------- announcements toggle ----------

def _guild_announce_mock():
    ch = MagicMock()
    ch.send = AsyncMock()
    g = MagicMock()
    g.id = GID
    g.name = "Server Tes"
    g.member_count = 77
    g.get_channel = MagicMock(return_value=ch)
    return g, ch


def _bot_announce(g, gid_nyata):
    """Mock bot yang hanya mengenali satu guild (seperti aslinya).

    Tanpa ini, get_guild mengembalikan mock untuk SEMUA id sehingga
    sisa pengumuman guild lain dari file test lain ikut terkirim dan
    membuat assert_called_once gagal tergantung urutan test.
    """
    bot = MagicMock()
    bot.get_guild = MagicMock(side_effect=lambda gid: g if gid == gid_nyata else None)
    return bot


def _tambah_pengumuman():
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO dashboard_announcements"
            " (id, guild_id, channel_id, message, run_at, interval_minutes, enabled, last_sent_at)"
            " VALUES (9901, ?, '31337', 'Halo {server}, member={member_count}', NULL, 60, 1, NULL)",
            (str(GID),),
        )
        conn.commit()


def test_kirim_pengumuman_jalan_dan_substitusi():
    _bersih()
    _tambah_pengumuman()
    g, ch = _guild_announce_mock()
    bot = _bot_announce(g, GID)
    sync = DashboardSync(bot)
    asyncio.run(sync.kirim_pengumuman.coro(sync))
    ch.send.assert_called_once()
    terkirim = ch.send.call_args[0][0]
    assert terkirim == "Halo Server Tes, member=77"


def test_kirim_pengumuman_mati_skip():
    _bersih()
    _set("announcements_enabled", "0")
    _tambah_pengumuman()
    g, ch = _guild_announce_mock()
    bot = _bot_announce(g, GID)
    sync = DashboardSync(bot)
    asyncio.run(sync.kirim_pengumuman.coro(sync))
    ch.send.assert_not_called()


# ---------- responder toggle + variabel ----------

def _pesan_responder():
    ch = MagicMock()
    ch.send = AsyncMock()
    ch.mention = "<#31337>"
    author = MagicMock()
    author.bot = False
    author.mention = "<@4242>"
    guild = MagicMock()
    guild.id = GID
    guild.name = "Server Tes"
    guild.member_count = 55
    msg = MagicMock()
    msg.author = author
    msg.guild = guild
    msg.channel = ch
    msg.content = "halo bot"
    return msg, ch


def test_responder_mati_tidak_kirim():
    _bersih()
    _set("responder_enabled", "0")
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO autoresponder (guild_id, trigger, respons)"
            " VALUES (?, 'halo', 'Hai!')",
            (GID,),
        )
        conn.commit()
    cog = Responder(MagicMock())
    msg, ch = _pesan_responder()
    asyncio.run(cog.on_message(msg))
    ch.send.assert_not_called()


def test_responder_variabel_disubstitusi():
    _bersih()
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO autoresponder (guild_id, trigger, respons)"
            " VALUES (?, 'halo', 'Hai {user} di {server} ({member_count}) via {channel}')",
            (GID,),
        )
        conn.commit()
    cog = Responder(MagicMock())
    msg, ch = _pesan_responder()
    asyncio.run(cog.on_message(msg))
    ch.send.assert_called_once_with(
        "Hai <@4242> di Server Tes (55) via <#31337>",
        allowed_mentions=MENTIONS_PENGUMUMAN,
    )


# ---------- starboard toggle ----------

def _pengaturan(**kw):
    """Stub settings: config.settings frozen, jadi ganti objeknya sementara."""
    stub = MagicMock()
    for k, v in kw.items():
        setattr(stub, k, v)
    return patch("src.config.settings", new=stub)


def test_starboard_mati():
    _bersih()
    _set("starboard_enabled", "0")
    with _pengaturan(starboard_channel_id=31337, starboard_min=3):
        bot = MagicMock()
        cog = Starboard(bot)
        payload = MagicMock()
        payload.emoji = "⭐"
        payload.guild_id = GID
        payload.message_id = 111
        payload.channel_id = 222
        asyncio.run(cog._sync(payload))
        bot.get_guild.assert_not_called()


def test_starboard_default_off_selaras_dashboard():
    """Regresi: starboard default OFF ("0") selaras SETTING_DEFAULTS dashboard.

    modul_aktif() default ON hanya untuk modul lama — guild baru sebelum pull
    pertama tidak boleh dianggap starboard ON.
    """
    _bersih()
    with _pengaturan(starboard_channel_id=31337, starboard_min=3):
        bot = MagicMock()
        cog = Starboard(bot)
        payload = MagicMock()
        payload.emoji = "⭐"
        payload.guild_id = GID
        payload.message_id = 111
        payload.channel_id = 222
        asyncio.run(cog._sync(payload))
        bot.get_guild.assert_not_called()


def test_starboard_nyala_eksplisit():
    _bersih()
    _set("starboard_enabled", "1")
    with _pengaturan(starboard_channel_id=31337, starboard_min=3):
        bot = MagicMock()
        bot.get_guild = MagicMock(return_value=None)
        cog = Starboard(bot)
        payload = MagicMock()
        payload.emoji = "⭐"
        payload.guild_id = GID
        payload.message_id = 111
        payload.channel_id = 222
        asyncio.run(cog._sync(payload))
        bot.get_guild.assert_called_once_with(GID)


# ---------- economy loop menghormati toggle ----------

def test_bunga_harian_lewati_guild_mati():
    _bersih()
    GID2 = GID + 1
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO economy (user_id, guild_id, balance, bank)"
            " VALUES (1, ?, 0, 1000)",
            (GID,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO economy (user_id, guild_id, balance, bank)"
            " VALUES (1, ?, 0, 1000)",
            (GID2,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO dashboard_settings (guild_id, key, value)"
            " VALUES (?, 'economy_enabled', '0')",
            (GID2,),
        )
        conn.commit()
    from src.cogs.economy import Economy

    cog = Economy.__new__(Economy)
    cog.bot = MagicMock()
    with _pengaturan(bank_bunga_harian=10):
        asyncio.run(cog.bunga_harian.coro(cog))
    with get_connection() as conn:
        bank_nyala = conn.execute(
            "SELECT bank FROM economy WHERE user_id = 1 AND guild_id = ?", (GID,)
        ).fetchone()[0]
        bank_mati = conn.execute(
            "SELECT bank FROM economy WHERE user_id = 1 AND guild_id = ?", (GID2,)
        ).fetchone()[0]
    assert bank_nyala == 1100, bank_nyala
    assert bank_mati == 1000, bank_mati
    with get_connection() as conn:
        conn.execute("DELETE FROM economy WHERE guild_id = ?", (GID2,))
        conn.execute(
            "DELETE FROM dashboard_settings WHERE guild_id = ? AND key = 'economy_enabled'",
            (GID2,),
        )
        conn.commit()


# ---------- welcome auto-role ----------

def _member_join():
    sysch = MagicMock()
    sysch.send = AsyncMock()
    sysch.mention = "<#sys>"
    role_a = MagicMock()
    role_b = MagicMock()
    g = MagicMock()
    g.id = GID
    g.name = "Server Tes"
    g.member_count = 100
    g.system_channel = sysch
    g.get_role = MagicMock(side_effect=lambda rid: {111: role_a, 222: role_b}.get(rid))
    m = MagicMock()
    m.id = 123
    m.guild = g
    m.mention = "<@123>"
    m.display_name = "Budi"
    m.display_avatar.read = AsyncMock(return_value=b"avatar")
    m.display_avatar.url = "https://cdn.test/avatar.png"
    m.add_roles = AsyncMock()
    m.send = AsyncMock()
    return m, sysch, role_a, role_b


def test_welcome_autorole_diberikan():
    _bersih()
    _set("welcome_enabled", "1")
    _set("welcome_role_ids", "111, 222, abc, 999")
    bot = FinchBot()
    bot.get_channel = MagicMock(return_value=None)
    member, _sysch, role_a, role_b = _member_join()
    with patch("src.bot.make_welcome_card", return_value=io.BytesIO(b"PNG")):
        asyncio.run(bot.on_member_join(member))
    dipanggil = [c.args[0] for c in member.add_roles.call_args_list]
    assert role_a in dipanggil and role_b in dipanggil
    assert len(dipanggil) == 2  # 999 tidak ada, "abc" dilewati


def test_welcome_autorole_tidak_jalan_bila_welcome_mati():
    _bersih()
    _set("welcome_enabled", "0")
    _set("welcome_role_ids", "111")
    bot = FinchBot()
    bot.get_channel = MagicMock(return_value=None)
    member, _sysch, _a, _b = _member_join()
    asyncio.run(bot.on_member_join(member))
    member.add_roles.assert_not_called()


def test_welcome_message_member_count():
    _bersih()
    _set("welcome_enabled", "1")
    _set("welcome_message", "Selamat datang {user}! Member ke-{member_count} di {server}.")
    bot = FinchBot()
    bot.get_channel = MagicMock(return_value=None)
    member, sysch, _a, _b = _member_join()
    with patch("src.bot.make_welcome_card", return_value=io.BytesIO(b"PNG")):
        asyncio.run(bot.on_member_join(member))
    sysch.send.assert_called_once()
    teks = sysch.send.call_args[0][0]
    assert teks == "Selamat datang <@123>! Member ke-100 di Server Tes."


# ---------- regression: audit 2026-10-09 (3 pelanggaran toggle) ----------

def test_leveling_cog_check_mati():
    from src.cogs.leveling import Leveling

    _bersih()
    _set("leveling_enabled", "0")
    cog = Leveling.__new__(Leveling)  # tanpa start loop
    ctx = _ctx()
    assert asyncio.run(Leveling.cog_check(cog, ctx)) is False
    ctx.send.assert_called_once()


def test_leveling_cog_check_nyala_default():
    from src.cogs.leveling import Leveling

    _bersih()
    cog = Leveling.__new__(Leveling)
    assert asyncio.run(Leveling.cog_check(cog, _ctx())) is True


def test_minigames_susunkata_mati_tanpa_koin():
    import time

    from src.cogs import minigames as mg

    _bersih()
    _set("economy_enabled", "0")
    cog = mg.MiniGames.__new__(mg.MiniGames)
    ch_id = 777001
    jawaban = "finchkeren"
    mg._susunkata_aktif[ch_id] = (jawaban, time.time() + 60)
    try:
        channel = MagicMock()
        channel.id = ch_id
        channel.send = AsyncMock()
        author = MagicMock()
        author.bot = False
        author.id = 4242
        guild = MagicMock()
        guild.id = GID
        message = MagicMock()
        message.author = author
        message.guild = guild
        message.channel = channel
        message.content = jawaban
        with patch("src.utils.economy.tambah_koin") as mock_koin:
            asyncio.run(cog.on_message(message))
        mock_koin.assert_not_called()
        # permainan dihentikan + ada pemberitahuan, bukan diam
        channel.send.assert_called_once()
        assert mg._susunkata_aktif.get(ch_id) is None
    finally:
        mg._susunkata_aktif.pop(ch_id, None)


def test_shop_cek_lelang_mati_ditunda():
    from src.cogs.shop import Shop

    _bersih()
    _set("economy_enabled", "0")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO lelang (guild_id, channel_id, message_id, nama_role,"
            " harga_awal, tawaran_tertinggi, penawar_id, ends_at, ended)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (GID, 31337, 424242, "Role Sultan", 100, 500, 999, "2000-01-01T00:00:00"),
        )
        conn.commit()
    try:
        cog = Shop.__new__(Shop)
        cog.bot = MagicMock()
        with patch.object(Shop, "_selesaikan_lelang", new=AsyncMock()) as mock_selesai:
            asyncio.run(cog.cek_lelang.coro(cog))
        # tidak diselesaikan saat modul mati...
        mock_selesai.assert_not_called()
        with get_connection() as conn:
            row = conn.execute(
                "SELECT ended FROM lelang WHERE guild_id = ? AND nama_role = ?",
                (GID, "Role Sultan"),
            ).fetchone()
        assert row[0] == 0, "lelang harus tetap pending saat economy_enabled=0"
    finally:
        with get_connection() as conn:
            conn.execute("DELETE FROM lelang WHERE guild_id = ?", (GID,))
            conn.commit()
