"""Tes untuk src/utils/filters.py. Jalanin:  python -m unittest discover tests"""
import unittest

from src.utils.filters import contains_bad_word, contains_invite_link, find_bad_word


class TestInviteFilter(unittest.TestCase):
    def test_discord_gg_pendek(self):
        self.assertTrue(contains_invite_link("join dong discord.gg/abc123"))

    def test_discord_gg_https(self):
        self.assertTrue(contains_invite_link("https://discord.gg/abc123"))

    def test_discord_com_invite(self):
        self.assertTrue(
            contains_invite_link("https://discord.com/invite/xyz-789")
        )

    def test_www_dan_huruf_besar(self):
        self.assertTrue(
            contains_invite_link("cek WWW.DISCORD.GG/NusaGaming ya")
        )

    def test_teks_biasa_lolos(self):
        self.assertFalse(contains_invite_link("halo guys, main bareng yuk!"))

    def test_kata_discord_tanpa_link_lolos(self):
        # "discord.gg" tanpa kode invite bukan link valid
        self.assertFalse(contains_invite_link("buka discord.gg aja"))

    def test_kosong_lolos(self):
        self.assertFalse(contains_invite_link(""))


class TestBadWordFilter(unittest.TestCase):
    WORDS = ["anjing", "tolol"]

    def test_ketemu(self):
        self.assertTrue(contains_bad_word("dasar anjing!", self.WORDS))

    def test_case_insensitive(self):
        self.assertTrue(contains_bad_word("ANJING banget", self.WORDS))

    def test_whole_word(self):
        # "toll" bukan "tolol" -> lolos; "tolol" di tengah kalimat -> kena
        self.assertFalse(contains_bad_word("bayar toll dulu", self.WORDS))
        self.assertTrue(contains_bad_word("kamu tolol ya", self.WORDS))

    def test_bersih_lolos(self):
        self.assertFalse(contains_bad_word("halo guys, main bareng yuk!", self.WORDS))

    def test_list_kosong_lolos(self):
        self.assertFalse(contains_bad_word("anjing", []))

    def test_find_bad_word(self):
        self.assertEqual(find_bad_word("eh tolol!", self.WORDS), "tolol")
        self.assertIsNone(find_bad_word("aman terkendali", self.WORDS))


if __name__ == "__main__":
    unittest.main()
