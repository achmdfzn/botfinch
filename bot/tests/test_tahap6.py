"""Tes 3 ide kecil Tahap 6. Jalanin:  python -m pytest tests/ -q"""
import io
import os
import unittest

from PIL import Image

from src.cogs.serverstats import nama_stat
from src.utils.rankcard import make_welcome_card


class TestLevelRolesParsing(unittest.TestCase):
    def test_parsing_dasar(self):
        os.environ["LEVEL_ROLES"] = "5:Aktif,10:Veteran,20:Sepuh"
        try:
            from src.config import Settings

            self.assertEqual(
                Settings().level_roles_list(),
                [(5, "Aktif"), (10, "Veteran"), (20, "Sepuh")],
            )
        finally:
            del os.environ["LEVEL_ROLES"]

    def test_urut_dan_invalid_dibuang(self):
        os.environ["LEVEL_ROLES"] = "20:Sepuh, xx:Skip, 5:Aktif, tanpa-kolon"
        try:
            from src.config import Settings

            self.assertEqual(
                Settings().level_roles_list(), [(5, "Aktif"), (20, "Sepuh")]
            )
        finally:
            del os.environ["LEVEL_ROLES"]

    def test_kosong(self):
        from src.config import Settings

        if "LEVEL_ROLES" in os.environ:
            del os.environ["LEVEL_ROLES"]
        self.assertEqual(Settings().level_roles_list(), [])


class TestWelcomeCard(unittest.TestCase):
    def test_valid_png_800x320(self):
        buf = make_welcome_card(None, "Fauzan", "Pioneer Outpost Nusa", 123)
        data = buf.getvalue()
        self.assertTrue(data.startswith(b"\x89PNG"))
        self.assertEqual(Image.open(io.BytesIO(data)).size, (800, 320))

    def test_nama_panjang_tidak_crash(self):
        buf = make_welcome_card(None, "X" * 100, "Server", 1)
        self.assertTrue(buf.getvalue().startswith(b"\x89PNG"))


class TestNamaStat(unittest.TestCase):
    def test_format(self):
        self.assertEqual(nama_stat("👥 Semua", 123), "👥 Semua: 123")
        self.assertEqual(nama_stat("🤖 Bot", 0), "🤖 Bot: 0")


if __name__ == "__main__":
    unittest.main()
