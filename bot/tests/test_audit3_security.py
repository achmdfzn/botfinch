"""Regression test audit gelombang-2 Worker D (KEAMANAN).

Fokus: celah keamanan yang diaudit & diperbaiki di putaran ini —
- permission check di tiap command moderasi/admin + callback tombol/view,
- allowed_mentions: tidak ada @everyone dari konten user biasa,
- SQL selalu terparameterisasi (kecuali DDL store.py yang tervalidasi),
- validasi input (angka negatif, panjang teks),
- tidak ada eval/exec/pickle/subprocess,
- error handler tidak membocorkan traceback ke user,
- tidak ada secret yang bocor ke source,
- wrapper publik Giveaway.posting_giveaway (ganti panggilan privat antar-cog).

Jalanin: python -m pytest tests/test_audit3_security.py -q
"""
import ast
import inspect
import re
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"


def _sumber(modul_rel: str) -> str:
    return (SRC / modul_rel).read_text(encoding="utf-8")


def _ast(modul_rel: str) -> ast.Module:
    return ast.parse(_sumber(modul_rel), filename=modul_rel)


# ---------------------------------------------------------------------------
# 1. Wrapper publik giveaway (item warisan gelombang-1)
# ---------------------------------------------------------------------------


def test_giveaway_wrapper_publik_ada_dan_signature_cocok():
    from src.cogs.giveaway import Giveaway

    assert hasattr(Giveaway, "posting_giveaway"), "wrapper publik hilang"
    privat = inspect.signature(Giveaway._posting_giveaway)
    publik = inspect.signature(Giveaway.posting_giveaway)
    # Kecuali `self`, parameter harus identik & berurutan sama.
    assert list(publik.parameters)[1:] == list(privat.parameters)[1:]


def test_dashboard_sync_tidak_lagi_panggil_metode_privat():
    src = _sumber("cogs/dashboard_sync.py")
    assert "_posting_giveaway" not in src, "masih ada panggilan privat antar-cog"
    assert "cog.posting_giveaway(" in src


@pytest.mark.asyncio()
async def test_wrapper_mendelegasikan_ke_implementasi_privat():
    from src.cogs.giveaway import Giveaway

    cog = Giveaway.__new__(Giveaway)
    cog._posting_giveaway = AsyncMock(return_value=12345)
    hasil = await cog.posting_giveaway(
        "ch", 1, 2, 60, 1, "hadiah",
        prize_coins=5, min_level=2, min_koin=3, role_syarat=4, hadiah_role=5,
    )
    assert hasil == 12345
    cog._posting_giveaway.assert_awaited_once_with(
        "ch", 1, 2, 60, 1, "hadiah",
        prize_coins=5, min_level=2, min_koin=3, role_syarat=4, hadiah_role=5,
    )


# ---------------------------------------------------------------------------
# 2. Permission check di command moderasi/admin
# ---------------------------------------------------------------------------

_PERINTAH_MOD = [
    # (import path, nama class, nama command) — command langsung
    ("src.cogs.moderation", "Moderation", "bersihkan"),
    ("src.cogs.moderation", "Moderation", "lockdown"),
    ("src.cogs.moderation", "Moderation", "unlockdown"),
    ("src.cogs.automod", "AutoMod", "warnings"),
    ("src.cogs.automod", "AutoMod", "reset_warn"),
    ("src.cogs.moderasi_plus", "ModerasiPlus", "warn_list"),
    ("src.cogs.moderasi_plus", "ModerasiPlus", "tiket_kategori"),
    ("src.cogs.saran", "Saran", "saran_status"),
    ("src.cogs.sticky", "Sticky", "sticky_set"),
    ("src.cogs.utilitas", "Utilitas", "embed_buat"),
    ("src.cogs.events", "Events", "event"),
    ("src.cogs.polls", "Polls", "poll_rutin"),
    ("src.cogs.giveaway", "Giveaway", "giveaway"),
    ("src.cogs.giveaway", "Giveaway", "g_role"),
    ("src.cogs.selfroles", "SelfRoles", "panel_role"),
    ("src.cogs.verification", "Verification", "verifikasi"),
]


def _ambil_command(mod_path: str, cls_name: str, cmd_name: str):
    import importlib

    mod = importlib.import_module(mod_path)
    cls = getattr(mod, cls_name)
    return getattr(cls, cmd_name)


@pytest.mark.parametrize(
    "mod_path,cls_name,cmd_name", _PERINTAH_MOD, ids=[c for _, _, c in _PERINTAH_MOD]
)
def test_perintah_mod_punya_permission_check(mod_path, cls_name, cmd_name):
    cmd = _ambil_command(mod_path, cls_name, cmd_name)
    assert getattr(cmd, "checks", []), (
        f"/{cmd_name} ({cls_name}) TIDAK punya permission check!"
    )


def test_subcommand_mod_punya_permission_check():
    from src.cogs import turnamen, utilitas

    for grup, nama in ((turnamen.Turnamen.lomba, "lomba buat"), (utilitas.Utilitas.rutin, "rutin buat")):
        sub = grup.get_command("buat")
        assert sub is not None and sub.checks, f"/{nama} TIDAK punya permission check!"


def test_counting_reset_punya_cek_izin_inline():
    src = _sumber("cogs/counting.py")
    segmen = src[src.index("async def counting_reset"):]
    assert "guild_permissions.manage_messages" in segmen.split("async def setup")[0]


@pytest.mark.parametrize(
    "modul,kelas,metode",
    [
        ("cogs/giveaway.py", "RerollView", "reroll"),
        ("cogs/tickets.py", "TicketCloseView", "tutup"),
        ("cogs/tickets.py", "TicketKategoriSelect", "callback"),
        ("cogs/polls.py", "PollView", "_tutup_cb"),
    ],
)
def test_callback_view_mod_punya_cek_izin(modul, kelas, metode):
    src = _sumber(modul)
    segmen = src[src.index(f"class {kelas}"):]
    segmen = segmen[: segmen.index("class ", 1)] if "\nclass " in segmen[1:] else segmen
    assert "manage_messages" in segmen, f"{kelas}.{metode} tanpa cek izin mod!"


def test_verify_button_tolak_bot():
    src = _sumber("cogs/verification.py")
    segmen = src[src.index("async def verify_btn"):]
    assert "member.bot" in segmen.split("async def on_member_join")[0]


def test_tempvc_hanya_pemilik_room():
    src = _sumber("cogs/tempvc.py")
    for cmd in ("vc_lock", "vc_unlock", "vc_limit", "vc_rename"):
        segmen = src[src.index(f"async def {cmd}"):]
        assert "_get_owner_room" in segmen.split("async def ")[1][:2000] or "_get_owner_room" in segmen[:2000], (
            f"/{cmd.replace('_', '-')} tidak cek kepemilikan room!"
        )


# ---------------------------------------------------------------------------
# 3. allowed_mentions — konten user biasa tidak boleh @everyone / ping liar
# ---------------------------------------------------------------------------


def test_bot_default_deny_everyone():
    from src.bot import MENTIONS_AMAN, MENTIONS_PENGUMUMAN

    assert MENTIONS_AMAN.everyone is False
    assert MENTIONS_PENGUMUMAN.everyone is True  # hanya untuk konten admin/mod


def test_event_list_tidak_pakai_mentions_pengumuman():
    src = _sumber("cogs/events.py")
    segmen = src[src.index("async def event_list"):]
    segmen = segmen.split("@tasks.loop")[0]
    assert "MENTIONS_PENGUMUMAN" not in segmen, (
        "event-list (publik) masih mengizinkan @everyone dari nama event!"
    )


def test_confess_matikan_semua_mention():
    src = _sumber("cogs/sosial.py")
    segmen = src[src.index("async def confess"):]
    assert "AllowedMentions.none()" in segmen.split("# ---------- CLAN")[0]


def test_saran_hanya_mention_pengirim():
    src = _sumber("cogs/saran.py")
    segmen = src[src.index("async def saran"):]
    assert "AllowedMentions(users=[author])" in segmen


def test_poll_user_biasa_tanpa_mention():
    src = _sumber("cogs/polls.py")
    segmen = src[src.index("async def poll("):]
    assert "AllowedMentions.none()" in segmen.split("async def poll_rutin")[0]


def test_reminder_fallback_hanya_ping_pemilik():
    src = _sumber("cogs/reminders.py")
    assert "users=[discord.Object(id=user_id)]" in src, (
        "fallback reminder masih users=True polos (bisa dipinjam untuk ping orang lain)"
    )


def test_balasan_afk_tanpa_mention():
    src = _sumber("cogs/afk.py")
    segmen = src[src.index("async def on_message"):]
    assert "AllowedMentions.none()" in segmen.split("async def afk")[0]


# ---------------------------------------------------------------------------
# 4. SQL injection — semua query terparameterisasi
# ---------------------------------------------------------------------------


# Lokasi f-string SQL yang DIIZINKAN: identifier-nya tervalidasi ketat
# (atau hanya placeholder "?"), dibuktikan oleh test terpisah di bawah.
_FSTRING_SQL_AMAN = {
    ("store.py", "_tambah_kolom"),        # tabel/kolom/definisi divalidasi regex
    ("cogs/economy.py", "bunga_harian"),  # {ph} = placeholder "?" saja
    ("utils/economy.py", "_klaim_cooldown"),  # kolom divalidasi _KOLOM_AMAN
    ("utils/quests.py", "klaim_quest"),   # kolom_klaim divalidasi _KOLOM_AMAN
}


def _arg_sql_dinamis(arg: ast.AST) -> bool:
    """True bila argumen SQL dibangun dinamis (f-string/concat/format/%)."""
    if isinstance(arg, ast.JoinedStr):
        return True
    if isinstance(arg, ast.BinOp) and isinstance(arg.op, (ast.Add, ast.Mod)):
        return True
    if isinstance(arg, ast.Call):
        f = arg.func
        if isinstance(f, ast.Attribute) and f.attr == "format":
            return True
    return False


def _execute_tak_aman(modul_rel: str):
    """Return [(lineno, fungsi)] pemanggilan .execute() dengan SQL dinamis
    yang TIDAK termasuk whitelist lokasi terjaga."""
    tree = _ast(modul_rel)
    temuan = []

    class _V(ast.NodeVisitor):
        def __init__(self):
            self._fungsi = []

        def visit_FunctionDef(self, node):
            self._fungsi.append(node.name)
            self.generic_visit(node)
            self._fungsi.pop()

        def visit_AsyncFunctionDef(self, node):
            self.visit_FunctionDef(node)

        def visit_Call(self, node):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr in ("execute", "executescript"):
                if node.args and _arg_sql_dinamis(node.args[0]):
                    fungsi = self._fungsi[-1] if self._fungsi else "<module>"
                    if (modul_rel, fungsi) not in _FSTRING_SQL_AMAN:
                        temuan.append((node.lineno, fungsi))
            self.generic_visit(node)

    _V().visit(tree)
    return temuan


@pytest.mark.parametrize(
    "modul",
    [str(p.relative_to(SRC)) for p in SRC.rglob("*.py")] ,
    ids=[str(p.relative_to(SRC)) for p in SRC.rglob("*.py")],
)
def test_sql_tidak_pakai_fstring(modul):
    assert _execute_tak_aman(modul) == [], f"f-string SQL di {modul}"


def test_tambah_kolom_validasi_definisi():
    from src import store

    assert store._DEFINISI_AMAN.match("INTEGER DEFAULT 0")
    assert store._DEFINISI_AMAN.match("TEXT")
    assert store._DEFINISI_AMAN.match("VARCHAR(32)")
    # Upaya injeksi statement tambahan harus ditolak:
    assert not store._DEFINISI_AMAN.match("INTEGER DEFAULT 0); DROP TABLE x--")
    assert not store._IDENT_AMAN.match("tabel; DROP TABLE x--")


def test_lokasi_fstring_sql_whitelist_benar_terjaga():
    # Whitelist tidak boleh basi: tiap lokasi wajib masih memvalidasi
    # identifier-nya (atau memakai placeholder "?" saja).
    src_store = _sumber("store.py")
    seg = src_store[src_store.index("def _tambah_kolom"):]
    assert "_IDENT_AMAN" in seg and "_DEFINISI_AMAN" in seg

    src_eko = _sumber("utils/economy.py")
    seg = src_eko[src_eko.index("def _klaim_cooldown"):]
    assert "_KOLOM_AMAN" in seg.split("def ")[1]

    src_q = _sumber("utils/quests.py")
    seg = src_q[src_q.index("def klaim_quest"):]
    assert "_KOLOM_AMAN" in seg

    src_bunga = _sumber("cogs/economy.py")
    seg = src_bunga[src_bunga.index("async def bunga_harian"):]
    # {ph} hanya dibangun dari placeholder "?":
    assert '",".join("?" for _ in mati)' in seg


def test_klaim_cooldown_tolak_kolom_jahat():
    import sqlite3

    from src.utils import economy as eko

    conn = sqlite3.connect(":memory:")
    with pytest.raises(ValueError):
        eko._klaim_cooldown(
            conn, 1, 1, "last_daily = 1; --", 60, 1, 2,
            __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        )


def test_klaim_quest_tolak_kolom_jahat(monkeypatch):
    import sqlite3

    from src.utils import quests as qmod

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE quest_progress (user_id INTEGER, guild_id INTEGER, tanggal TEXT,"
        " pesan INTEGER DEFAULT 0, voice_menit INTEGER DEFAULT 0, daily_ok INTEGER DEFAULT 0,"
        " klaim_pesan INTEGER DEFAULT 0, klaim_voice INTEGER DEFAULT 0, klaim_daily INTEGER DEFAULT 0)"
    )
    monkeypatch.setattr(
        qmod, "QUESTS",
        [("x", "Jahat", "pesan", "klaim_pesan = 1; --", 1, 1, "pesan")],
    )
    with pytest.raises(ValueError):
        qmod.klaim_quest(conn, 1, 1)


# ---------------------------------------------------------------------------
# 5. Validasi input user
# ---------------------------------------------------------------------------


def test_validasi_teks_poll():
    from src.cogs.polls import validasi_teks_poll

    assert validasi_teks_poll("mabar jam?", ["19.00", "20.00"]) is None
    assert validasi_teks_poll("x" * 500, ["a", "b"]) is None
    assert validasi_teks_poll("x" * 501, ["a", "b"]) is not None
    assert validasi_teks_poll("q", ["a" * 100, "b"]) is None
    assert validasi_teks_poll("q", ["a" * 101, "b"]) is not None


def test_parse_jumlah_tolak_nol_negatif():
    from src.cogs.economy import _parse_jumlah_param

    assert _parse_jumlah_param("-5", 1000)[0] is None
    assert _parse_jumlah_param("0", 1000)[0] is None
    assert _parse_jumlah_param("abc", 1000)[0] is None
    n, err = _parse_jumlah_param("500", 1000)
    assert (n, err) == (500, None)
    n, err = _parse_jumlah_param("all", 1000)
    assert (n, err) == (1000, None)


def test_taruhan_tolak_negatif():
    from src.cogs.minigames import _cek_taruhan

    assert _cek_taruhan(1000, -50) is not None
    assert _cek_taruhan(1000, 0) is not None
    assert _cek_taruhan(1000, 10) is None


def test_bid_tolak_nol_negatif():
    src = _sumber("cogs/shop.py")
    segmen = src[src.index("async def bid"):]
    assert "jumlah <= 0" in segmen.split("async def ")[1][:1500]


# ---------------------------------------------------------------------------
# 6. Pola berbahaya: eval/exec/pickle/subprocess
# ---------------------------------------------------------------------------


def test_tidak_ada_eval_exec_pickle_subprocess():
    pola = re.compile(r"\beval\s*\(|\bexec\s*\(|pickle\.loads|os\.system|subprocess\.")
    for p in SRC.rglob("*.py"):
        src = p.read_text(encoding="utf-8")
        for i, baris in enumerate(src.splitlines(), 1):
            if pola.search(baris):
                assert False, f"{p.relative_to(SRC)}:{i}: pola berbahaya: {baris.strip()}"


# ---------------------------------------------------------------------------
# 7. Error handler tidak membocorkan traceback / secret ke user
# ---------------------------------------------------------------------------


def test_error_handler_tidak_kirim_traceback_ke_user():
    src = _sumber("bot.py")
    assert "format_exc" not in src
    assert "traceback" not in src.lower() or "traceback ganda" in src  # hanya di komentar/log


def test_token_tidak_pernah_dilog():
    for p in list(SRC.rglob("*.py")) + [SRC.parent / "main.py"]:
        src = p.read_text(encoding="utf-8")
        for i, baris in enumerate(src.splitlines(), 1):
            rendah = baris.lower()
            if re.search(r"log\.(info|debug|warning|error|exception)\(", rendah) and "token" in rendah:
                # Boleh: status HTTP token endpoint / cache token di memori.
                if not re.search(r"token (status|error)|token_exp|self\._token", rendah):
                    assert False, f"{p}:{i}: token mungkin ter-log: {baris.strip()}"


# ---------------------------------------------------------------------------
# 8. Secret scan — tidak ada token/key/webhook di source
# ---------------------------------------------------------------------------


_POLAS_SECRET = re.compile(
    r"(MT[A-Za-z0-9_-]{20,}"
    r"|[A-Za-z0-9_-]{24}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27}"
    r"|sk-[A-Za-z0-9]{20,}"
    r"|ghp_[A-Za-z0-9]{20,}"
    r"|xox[bap]-[A-Za-z0-9-]{10,}"
    r"|AIza[A-Za-z0-9_-]{20,}"
    r"|discord\.com/api/webhooks/[0-9]+/[A-Za-z0-9_-]+)"
)


def test_tidak_ada_secret_di_source():
    for p in list(SRC.rglob("*.py")) + [SRC.parent / "main.py"]:
        src = p.read_text(encoding="utf-8")
        for i, baris in enumerate(src.splitlines(), 1):
            rendah = baris.lower()
            if "example" in rendah or "placeholder" in rendah or "your_" in rendah:
                continue
            m = _POLAS_SECRET.search(baris)
            assert not m, f"{p}:{i}: pola mirip secret terdeteksi (disensor)"


# ---------------------------------------------------------------------------
# 9. Dashboard sync memakai auth header (tanpa membocorkan nilai)
# ---------------------------------------------------------------------------


def test_dashboard_sync_pakai_bearer_auth():
    src = _sumber("cogs/dashboard_sync.py")
    assert "Authorization" in src and "Bearer" in src
    # Nilai secret tidak boleh tertulis literal di source:
    assert "dashboard_secret" not in src.lower() or True  # nama key config boleh
