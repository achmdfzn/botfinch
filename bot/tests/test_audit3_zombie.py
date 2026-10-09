"""Regression test audit gelombang-3 (Worker E): zombie code & konsistensi.

- Konstanta KATEGORI_TIKET punya SATU sumber (src.utils.constants).
- buat_tiket tidak lagi memakai private API discord.py.
- Paritas 32 key toggle bot <-> dashboard (dashboard dibaca read-only).
- Warna brand teal dipakai sebagai default embed.
- Embed helper tidak menumpuk emoji di judul (uji via AST source).
"""
import ast
import os
import re
import unittest

import discord

from src.utils.constants import KATEGORI_TIKET
from src.utils import embeds
from src.cogs import tickets as tiket_mod
from src.cogs import moderasi_plus as modplus_mod

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestKategoriTiketSatuSumber(unittest.TestCase):
    def test_isi_kategori(self):
        self.assertEqual(KATEGORI_TIKET, ["Umum", "Bantuan", "Report", "Saran"])

    def test_kedua_cog_pakai_objek_yang_sama(self):
        # Re-export di kedua cog harus menunjuk objek yang sama (bukan duplikat literal).
        self.assertIs(tiket_mod.KATEGORI_TIKET, KATEGORI_TIKET)
        self.assertIs(modplus_mod.KATEGORI_TIKET, KATEGORI_TIKET)

    def test_tidak_ada_literal_duplikat(self):
        # Tidak boleh ada lagi penugasan literal list di kedua file cog.
        for path in (
            "src/cogs/tickets.py",
            "src/cogs/moderasi_plus.py",
        ):
            with open(os.path.join(REPO, path), encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for t in node.targets:
                        if isinstance(t, ast.Name) and t.id == "KATEGORI_TIKET":
                            self.fail(f"literal KATEGORI_TIKET masih ada di {path}")


class TestBuatTiketApiPublik(unittest.TestCase):
    def test_tidak_pakai_private_api(self):
        with open(os.path.join(REPO, "src/cogs/tickets.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("_get_client", src)
        self.assertNotIn("guild._state", src)

    def test_signature_minta_bot(self):
        sig = str(tiket_mod.buat_tiket.__code__.co_varnames)
        self.assertTrue(sig.startswith("('bot', 'guild'"),
                        f"buat_tiket harus menerima bot sebagai argumen pertama: {sig}")


class TestParitasKeyToggle(unittest.TestCase):
    # 32 key yang dipakai bot via modul_aktif/cek_toggle/get_guild_setting.
    # Daftar ini hasil pemindaian AST src/ — bila bertambah, update daftar
    # ini SEKALIGUS pastikan dashboard mengenalnya.
    KEY_BOT = {
        "announcements_enabled", "automod_badwords", "automod_caps",
        "automod_enabled", "automod_invites", "automod_log_channel_id",
        "automod_mute_minutes", "automod_spam", "autopublish_enabled",
        "customcmd_enabled",
        "economy_daily",
        "economy_enabled", "economy_work_max", "economy_work_min",
        "embed_enabled", "giveaway_enabled", "goodbye_channel_id",
        "goodbye_enabled", "goodbye_message", "leveling_announce_channel_id",
        "leveling_enabled", "leveling_roles", "leveling_xp_rate",
        "levelup_style", "msglog_enabled", "responder_enabled", "selfroles_enabled",
        "slowmode_enabled",
        "starboard_channel_id", "starboard_enabled", "starboard_threshold",
        "welcome_channel_id", "welcome_enabled", "welcome_message",
        "welcome_role_ids", "welcome_theme",
    }

    def _key_terpakai_bot(self):
        target = {"modul_aktif", "cek_toggle", "get_guild_setting", "get_guild_setting_int"}
        hasil = set()
        srcdir = os.path.join(REPO, "src")
        for root, _, files in os.walk(srcdir):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                tree = ast.parse(open(os.path.join(root, fn), encoding="utf-8").read())
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        f = node.func
                        nama = f.attr if isinstance(f, ast.Attribute) else (
                            f.id if isinstance(f, ast.Name) else "")
                        if nama in target and len(node.args) >= 2:
                            cand = node.args[1]
                            if isinstance(cand, ast.Constant) and isinstance(cand.value, str):
                                hasil.add(cand.value)
        return hasil

    def test_daftar_key_tidak_berubah_diam_diam(self):
        self.assertEqual(self._key_terpakai_bot(), self.KEY_BOT)

    def test_semua_key_dikenal_dashboard(self):
        dash = os.path.expanduser("~/workspace/finch/dashboard")
        teks = ""
        for rel in ("lib/settings.ts", "lib/plugins.ts"):
            p = os.path.join(dash, rel)
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    teks += f.read()
        hilang = [k for k in self.KEY_BOT if f'"{k}"' not in teks]
        self.assertEqual(hilang, [], f"key tak dikenal dashboard: {hilang}")


class TestWarnaBrand(unittest.TestCase):
    def test_brand_teal(self):
        self.assertEqual(embeds.BRAND, discord.Color(0x2EC4B6))

    def test_base_embed_default_brand(self):
        e = embeds.base_embed("Judul", "isi")
        self.assertEqual(e.color, embeds.BRAND)

    def test_warna_semantik_ada(self):
        self.assertIn("gagal", embeds.WARNA)  # merah semantik bahaya
        self.assertIn("sukses", embeds.WARNA)  # hijau semantik sukses


class TestJudulEmbedEmojiDiet(unittest.TestCase):
    def test_maks_satu_emoji_per_judul(self):
        pola_emoji = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]")
        helper = {"base_embed", "finch_embed", "error_embed", "sukses_embed", "warn_embed"}
        srcdir = os.path.join(REPO, "src")
        pelanggar = []
        for root, _, files in os.walk(srcdir):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                path = os.path.join(root, fn)
                tree = ast.parse(open(path, encoding="utf-8").read())
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        f = node.func
                        nama = f.attr if isinstance(f, ast.Attribute) else (
                            f.id if isinstance(f, ast.Name) else "")
                        if nama in helper and node.args:
                            a = node.args[0]
                            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                                # Abaikan variation selector U+FE0F (bukan emoji kedua).
                                bersih = a.value.replace("\uFE0F", "")
                                if len(pola_emoji.findall(bersih)) > 1:
                                    pelanggar.append((os.path.relpath(path, REPO), a.value))
        self.assertEqual(pelanggar, [], f"judul >1 emoji: {pelanggar}")


if __name__ == "__main__":
    unittest.main()
