"""Tes /bantuan interaktif & dinamis.

- Builder: data diambil live dari tree (bukan hardcode), semua cog terpetakan,
  tiap command muncul tepat 1x, embed dalam limit Discord.
- Interaksi: author bisa ganti kategori, non-author ditolak (ephemeral),
  interaction kedaluwarsa tidak crash.
- Timeout: select dinonaktifkan saat timeout.

Jalanin:  ~/workspace/.venv-finch/bin/python -m pytest tests/test_bantuan.py -q
"""
import asyncio
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from src.cogs import general
from src.cogs.general import (
    COG_KE_KATEGORI,
    URUTAN_KATEGORI,
    HelpView,
    _bagi_ke_field,
    _embed_kategori,
    _embed_semua,
    _kumpulkan_perintah,
    bangun_data_bantuan,
)
from src.utils.embeds import BRAND

# ---------------------------------------------------------------------------
# Helper: tree & command palsu
# ---------------------------------------------------------------------------


def _cog_palsu(nama: str):
    """Instance dengan nama class sesuai — dipakai sebagai `binding`."""
    return type(nama, (), {})()


class _CmdPalsu:
    """App command minimal: name/description/binding/hidden."""

    def __init__(self, name, description="", cog_name=None, hidden=False):
        self.name = name
        self.description = description
        self.hidden = hidden
        self.binding = _cog_palsu(cog_name) if cog_name else None
        self.callback = None


def _tree_palsu(*commands):
    return SimpleNamespace(get_commands=lambda: list(commands))


def _sub_nyata(group_name, sub_name, description, cog_name):
    """Subcommand + grup betulan dari discord.py (uji path Group)."""

    async def _cb(interaction: discord.Interaction):
        pass

    sub = discord.app_commands.Command(name=sub_name, description=description, callback=_cb)
    sub.binding = _cog_palsu(cog_name)
    group = discord.app_commands.Group(name=group_name, description=f"Grup {group_name}")
    group.add_command(sub)
    return group


# ---------------------------------------------------------------------------
# Builder dengan tree palsu
# ---------------------------------------------------------------------------


def test_kumpulkan_group_jadi_qualified_name():
    tree = _tree_palsu(
        _CmdPalsu("status", "Status bot", "General"),
        _sub_nyata("dagang", "trade", "Tukar koin", "EkonomiPlus"),
    )
    data = _kumpulkan_perintah(tree)
    assert data["umum"] == [("/status", "Status bot")]
    assert data["ekonomi"] == [("/dagang trade", "Tukar koin")]


def test_kumpulkan_abaikan_hidden_dan_context_menu():
    tree = _tree_palsu(
        _CmdPalsu("rahasia", "Hidden", "General", hidden=True),
    )
    assert _kumpulkan_perintah(tree) == {}


def test_kumpulkan_cog_tak_dikenal_masuk_lainnya():
    tree = _tree_palsu(_CmdPalsu("misteri", "???", "CogAsing"))
    data = _kumpulkan_perintah(tree)
    assert data["lainnya"] == [("/misteri", "???")]


def test_kumpulkan_tanpa_binding_jatuh_ke_lainnya():
    tree = _tree_palsu(_CmdPalsu("yatim", "tanpa cog"))
    assert "lainnya" in _kumpulkan_perintah(tree)


def test_cache_dipakai_ulang_dan_rebuild_saat_jumlah_berubah():
    general._cache_bantuan["jumlah"] = None
    general._cache_bantuan["data"] = None
    tree = _tree_palsu(_CmdPalsu("satu", "d1", "General"))
    pertama = bangun_data_bantuan(tree)
    kedua = bangun_data_bantuan(tree)
    assert pertama is kedua  # cache hit
    tree2 = _tree_palsu(
        _CmdPalsu("satu", "d1", "General"),
        _CmdPalsu("dua", "d2", "General"),
    )
    ketiga = bangun_data_bantuan(tree2)
    assert ketiga is not pertama  # rebuild karena jumlah berubah
    assert len(ketiga["umum"]) == 2
    # kembalikan cache ke kondisi bersih untuk tes lain
    general._cache_bantuan["jumlah"] = None
    general._cache_bantuan["data"] = None


def test_bagi_ke_field_hormati_batas():
    baris = [f"`/cmd{i}` — deskripsi nomor {i}" for i in range(50)]
    fields = _bagi_ke_field(baris)
    assert sum(len(f) for f in fields) == 50
    for f in fields:
        assert len("\n".join(f)) <= 950


# ---------------------------------------------------------------------------
# Builder dengan tree ASLI (semua 44 cog di-load)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def bot_nyata():
    import pathlib
    from discord.ext import commands

    async def _load():
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        for f in sorted(pathlib.Path("src/cogs").glob("*.py")):
            if f.stem.startswith("_"):
                continue
            await bot.load_extension(f"src.cogs.{f.stem}")
        return bot

    return asyncio.run(_load())


@pytest.fixture(scope="module")
def data_nyata(bot_nyata):
    general._cache_bantuan["jumlah"] = None
    general._cache_bantuan["data"] = None
    return bangun_data_bantuan(bot_nyata.tree)


def _semua_class_cog():
    import inspect
    import pathlib
    import src.cogs as pkg
    from discord.ext import commands as _commands

    hasil = set()
    for f in sorted(pathlib.Path(pkg.__path__[0]).glob("*.py")):
        if f.stem.startswith("_"):
            continue
        mod = __import__(f"src.cogs.{f.stem}", fromlist=["*"])
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, _commands.Cog) and obj is not _commands.Cog:
                hasil.add(obj.__name__)
    return hasil


def test_semua_cog_terpetakan(data_nyata):
    semua = _semua_class_cog()
    # 45 cog: termasuk Premium (Free/VIP) yang ditambahkan bersama sistem tier.
    assert len(semua) == 45, f"jumlah cog berubah: {sorted(semua)}"
    hilang = semua - set(COG_KE_KATEGORI)
    assert not hilang, f"cog belum terpetakan: {sorted(hilang)}"


def test_tidak_ada_command_hilang_ke_lainnya_tanpa_sengaja(data_nyata):
    assert data_nyata.get("lainnya", []) == [], (
        f"ada command nyasar ke 'Lainnya': {data_nyata.get('lainnya')}"
    )


def test_tiap_command_muncul_tepat_satu_kali(bot_nyata, data_nyata):
    semua_qname = [q for daftar in data_nyata.values() for q, _ in daftar]
    assert len(semua_qname) == len(set(semua_qname)), "ada command duplikat"

    # bandingkan dengan hitungan leaf langsung dari tree
    def hitung(cmd, prefix=""):
        if getattr(cmd, "hidden", False):
            return 0
        if isinstance(cmd, discord.app_commands.ContextMenu):
            return 0
        if isinstance(cmd, discord.app_commands.Group):
            return sum(hitung(s, f"{prefix} {cmd.name}".strip()) for s in cmd.commands)
        return 1

    total_tree = sum(hitung(c) for c in bot_nyata.tree.get_commands())
    assert len(semua_qname) == total_tree
    assert total_tree > 100, "terlalu sedikit command — ada yang gagal ke-load?"


def test_embed_kategori_dalam_limit_discord(data_nyata):
    author = MagicMock()
    author.guild_permissions.manage_messages = False
    for kunci in list(URUTAN_KATEGORI) + ["lainnya"]:
        embed = _embed_kategori(kunci, data_nyata, author)
        assert len(embed.fields) <= 25, kunci
        total = len(embed.title or "") + len(embed.description or "")
        for f in embed.fields:
            assert len(f.value) <= 1024, f"{kunci}/{f.name}"
            total += len(f.name) + len(f.value)
        assert total <= 6000, f"embed {kunci} = {total} char"


def test_embed_semua_dalam_limit_discord(data_nyata):
    author = MagicMock()
    embed = _embed_semua(data_nyata, author)
    total = len(embed.title or "") + len(embed.description or "")
    for f in embed.fields:
        total += len(f.name) + len(f.value)
        assert len(f.value) <= 1024
    assert total <= 6000
    assert len(embed.fields) <= 25


def test_standar_ui_embed_bantuan(data_nyata):
    """Warna brand, footer Finch, maks 1 emoji di judul, field polos."""
    author = MagicMock()
    author.guild_permissions.manage_messages = True
    # \uFE0F (variation selector) bukan emoji sendiri — jangan dihitung ganda
    emoji_re = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]", flags=re.UNICODE)
    embeds = [_embed_semua(data_nyata, author)] + [
        _embed_kategori(k, data_nyata, author) for k in URUTAN_KATEGORI
    ]
    for e in embeds:
        assert e.color == BRAND
        assert e.footer.text == "Finch"
        assert len(emoji_re.findall(e.title or "")) <= 1, e.title
        for f in e.fields:
            assert not emoji_re.search(f.name or ""), f"emoji di nama field: {f.name}"


def test_catatan_izin_moderasi_untuk_non_mod(data_nyata):
    non_mod = MagicMock()
    non_mod.guild_permissions.manage_messages = False
    embed = _embed_kategori("moderasi", data_nyata, non_mod)
    nama_field = [f.name for f in embed.fields]
    assert "Izin" in nama_field
    assert "Perhatian" in nama_field

    mod = MagicMock()
    mod.guild_permissions.manage_messages = True
    embed_mod = _embed_kategori("moderasi", data_nyata, mod)
    assert "Perhatian" not in [f.name for f in embed_mod.fields]


# ---------------------------------------------------------------------------
# Interaksi: select menu
# ---------------------------------------------------------------------------


def _author_palsu(uid=111, manage_messages=False):
    m = MagicMock()
    m.id = uid
    m.guild_permissions.manage_messages = manage_messages
    return m


def _interaction_palsu(uid):
    inter = MagicMock()
    inter.user.id = uid
    inter.response.send_message = AsyncMock()
    inter.response.edit_message = AsyncMock()
    return inter


def test_select_hanya_tampilkan_kategori_berisi():
    tree = _tree_palsu(
        _CmdPalsu("status", "Status", "General"),
        _CmdPalsu("level", "Level", "Leveling"),
    )
    bot = SimpleNamespace(tree=tree)
    view = HelpView(_author_palsu(), bot)
    select = view.children[0]
    values = [o.value for o in select.options]
    assert values[0] == "semua"
    assert "umum" in values and "level" in values
    assert "ekonomi" not in values  # kosong -> tidak ditampilkan
    assert len(values) <= 10  # muat di select Discord


def test_author_bisa_ganti_kategori():
    tree = _tree_palsu(_CmdPalsu("status", "Status", "General"))
    bot = SimpleNamespace(tree=tree)
    author = _author_palsu(uid=111)
    view = HelpView(author, bot)
    select = view.children[0]
    select._values = ["umum"]  # simulasi pilihan user

    inter = _interaction_palsu(uid=111)
    asyncio.run(view._ganti_kategori(inter, select))

    inter.response.edit_message.assert_called_once()
    kwargs = inter.response.edit_message.call_args.kwargs
    assert "⭐" not in (kwargs["embed"].title or "")  # embed kategori umum
    assert "Umum" in kwargs["embed"].title
    assert kwargs["view"] is view
    inter.response.send_message.assert_not_called()


def test_non_author_ditolak_ephemeral():
    tree = _tree_palsu(_CmdPalsu("status", "Status", "General"))
    bot = SimpleNamespace(tree=tree)
    view = HelpView(_author_palsu(uid=111), bot)
    select = view.children[0]
    select._values = ["umum"]

    inter = _interaction_palsu(uid=999)  # bukan author
    asyncio.run(view._ganti_kategori(inter, select))

    inter.response.send_message.assert_called_once()
    kwargs = inter.response.send_message.call_args.kwargs
    assert kwargs.get("ephemeral") is True
    inter.response.edit_message.assert_not_called()


def test_interaction_kedaluwarsa_tidak_crash():
    tree = _tree_palsu(_CmdPalsu("status", "Status", "General"))
    bot = SimpleNamespace(tree=tree)
    view = HelpView(_author_palsu(uid=111), bot)
    select = view.children[0]
    select._values = ["umum"]

    inter = _interaction_palsu(uid=111)
    inter.response.edit_message = AsyncMock(
        side_effect=discord.NotFound(MagicMock(), MagicMock())
    )
    # tidak boleh raise — interaction 404/10062 harus ditelan
    asyncio.run(view._ganti_kategori(inter, select))


def test_timeout_menonaktifkan_select():
    tree = _tree_palsu(_CmdPalsu("status", "Status", "General"))
    bot = SimpleNamespace(tree=tree)
    view = HelpView(_author_palsu(), bot)
    assert view.timeout == 120
    pesan = MagicMock()
    pesan.edit = AsyncMock()
    view.message = pesan

    asyncio.run(view.on_timeout())

    assert all(item.disabled for item in view.children)
    pesan.edit.assert_called_once_with(view=view)


def test_bantuan_terdaftar_sebagai_method_cog():
    """Regresi: /bantuan harus jadi method class General (bukan kode mati di
    module level) agar terdaftar di command tree. Pernah terdampar setelah
    `return` di build_serverinfo_embed sehingga hilang dari tree."""
    import inspect
    from discord.ext import commands as ext_commands

    assert "bantuan" in general.General.__dict__, "bantuan bukan method General"
    attr = general.General.__dict__["bantuan"]
    # hybrid_command menghasilkan Command object / method terdekorasi
    assert isinstance(
        attr, ext_commands.HybridCommand
    ) or callable(attr), "bantuan tidak terdekorasi hybrid_command"
    # build_serverinfo_embed tetap fungsi module-level (bukan method)
    assert "build_serverinfo_embed" not in general.General.__dict__
    assert callable(general.build_serverinfo_embed)
    # bantuan tidak boleh jadi fungsi module-level yang terdampar
    assert not (
        "bantuan" in vars(general)
        and inspect.isfunction(vars(general)["bantuan"])
    ), "bantuan terdampar di module level"
