"""Tes logika tiket (pure function). Jalanin:  python -m pytest tests/ -q"""
import unittest
from unittest.mock import MagicMock

from src.cogs.tickets import _nama_channel, format_transcript


class TestFormatTranscript(unittest.TestCase):
    def test_format_dasar(self):
        entries = [
            ("10:00", "Fauzan", "halo min"),
            ("10:01", "Mod", "ada apa?"),
        ]
        hasil = format_transcript(entries)
        self.assertIn("[10:00] Fauzan: halo min", hasil)
        self.assertIn("[10:01] Mod: ada apa?", hasil)

    def test_kosong(self):
        self.assertEqual(format_transcript([]), "")


class TestNamaChannel(unittest.TestCase):
    def _member(self, name):
        m = MagicMock()
        m.name = name
        return m

    def test_nama_normal(self):
        self.assertEqual(_nama_channel(self._member("Fauzan")), "tiket-fauzan")

    def test_spasi_dan_simbol_dibersihkan(self):
        self.assertEqual(_nama_channel(self._member("Bang Jago!@#")), "tiket-bang-jago")

    def test_nama_aneh_jadi_user(self):
        self.assertEqual(_nama_channel(self._member("!!!")), "tiket-user")


if __name__ == "__main__":
    unittest.main()
