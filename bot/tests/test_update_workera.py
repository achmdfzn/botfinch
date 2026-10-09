"""Tes paket update Worker A (2026-10-09).

Kontrak yang dijaga:
- Tema kartu welcome: 4 varian valid (default/midnight/sunset/ocean) + 1
  invalid -> fallback "default". PNG tetap 800x320.
- Gaya pesan level-up: 4 gaya (classic/minimal/party/mention) me-render
  tanpa raise; bonus koin tetap dihitung/di-render; invalid -> classic.
- /serverinfo: embed lengkap (ID, tanggal, owner, boost, channel, role,
  emoji, breakdown member manusia/bot).
- Substitusi pengumuman terjadwal: {server} dan {date}.

Jalanin: ~/workspace/.venv-finch/bin/python -m pytest tests/test_update_workera.py -q
"""
import io
import unittest
from datetime import datetime
from unittest.mock import MagicMock

from PIL import Image

from src.utils.rankcard import TEMA_WELCOME, make_welcome_card
from src.cogs.leveling import GAYA_LEVELUP, build_levelup
from src.cogs.general import build_serverinfo_embed
from src.cogs.dashboard_sync import substitusi_pengumuman
from src.utils.embeds import BRAND


class TestTemaWelcome(unittest.TestCase):
    def test_empat_varian_valid_png_800x320(self):
        for tema in ("default", "midnight", "sunset", "ocean"):
            with self.subTest(tema=tema):
                buf = make_welcome_card(
                    None, "Fauzan", "Pioneer Outpost Nusa", 123, theme=tema
                )
                data = buf.getvalue()
                self.assertTrue(data.startswith(b"\x89PNG"))
                self.assertEqual(Image.open(io.BytesIO(data)).size, (800, 320))

    def test_tema_beda_menghasilkan_warna_aksen_beda(self):
        # Pixel strip aksen atas (y=8) harus beda antar tema
        piksel = {}
        for tema in ("default", "midnight", "sunset", "ocean"):
            data = make_welcome_card(
                None, "Fauzan", "Server", 1, theme=tema
            ).getvalue()
            piksel[tema] = Image.open(io.BytesIO(data)).convert("RGB").getpixel((400, 8))
        self.assertEqual(
            len(set(piksel.values())), 4, f"aksen harus beda: {piksel}"
        )

    def test_tema_invalid_fallback_default(self):
        data_default = make_welcome_card(
            None, "Fauzan", "Server", 1, theme="default"
        ).getvalue()
        for tema_invalid in ("neon", "", "DEFAULT", None):
            with self.subTest(tema=tema_invalid):
                data = make_welcome_card(
                    None, "Fauzan", "Server", 1, theme=tema_invalid
                ).getvalue()
                self.assertEqual(data, data_default)

    def test_default_param_tanpa_argumen(self):
        data = make_welcome_card(None, "Fauzan", "Server", 1).getvalue()
        data_default = make_welcome_card(
            None, "Fauzan", "Server", 1, theme="default"
        ).getvalue()
        self.assertEqual(data, data_default)

    def test_kunci_tema_lengkap(self):
        self.assertEqual(
            set(TEMA_WELCOME.keys()), {"default", "midnight", "sunset", "ocean"}
        )


class TestGayaLevelup(unittest.TestCase):
    def test_empat_gaya_render_tanpa_raise(self):
        for gaya in ("classic", "minimal", "party", "mention"):
            with self.subTest(gaya=gaya):
                jenis, konten = build_levelup(gaya, "<@123>", 7, 50)
                self.assertIn(jenis, ("text", "embed"))

    def test_classic_teks_seperti_sekarang(self):
        jenis, teks = build_levelup("classic", "<@123>", 7, 50)
        self.assertEqual(jenis, "text")
        self.assertIn("<@123>", teks)
        self.assertIn("Level 7", teks)
        self.assertIn("**50**", teks)  # bonus koin tetap ada

    def test_classic_tanpa_bonus_tidak_tampil_bonus(self):
        _, teks = build_levelup("classic", "<@123>", 7, 0)
        self.assertNotIn("koin", teks)

    def test_minimal_satu_baris_polos(self):
        jenis, teks = build_levelup("minimal", "<@123>", 7, 50)
        self.assertEqual(jenis, "text")
        self.assertNotIn("\n", teks)
        self.assertIn("<@123>", teks)
        self.assertIn("Level 7", teks)
        self.assertIn("+50", teks)

    def test_party_embed_teal_rapt(self):
        jenis, embed = build_levelup("party", "<@123>", 7, 50)
        self.assertEqual(jenis, "embed")
        self.assertEqual(embed.color, BRAND)
        self.assertEqual(embed.footer.text, "Finch")
        fields = {f.name: f.value for f in embed.fields}
        self.assertIn("7", fields["Level"])
        self.assertIn("50", fields["Bonus koin"])
        self.assertIn("<@123>", fields["Member"])

    def test_party_tanpa_bonus(self):
        _, embed = build_levelup("party", "<@123>", 7, 0)
        fields = {f.name: f.value for f in embed.fields}
        self.assertEqual(fields["Bonus koin"], "-")

    def test_mention_meriah_dan_diet_emoji(self):
        jenis, teks = build_levelup("mention", "<@123>", 7, 25)
        self.assertEqual(jenis, "text")
        self.assertIn("<@123>", teks)
        self.assertIn("7", teks)
        self.assertIn("+25", teks)
        # diet: maksimal 4 emoji per pesan
        self.assertLessEqual(
            sum(1 for c in teks if ord(c) > 0x2BFF), 4, f"terlalu banyak emoji: {teks}"
        )

    def test_gaya_invalid_fallback_classic(self):
        jenis_bad, teks_bad = build_levelup("gacor", "<@123>", 7, 50)
        jenis_ok, teks_ok = build_levelup("classic", "<@123>", 7, 50)
        self.assertEqual((jenis_bad, teks_bad), (jenis_ok, teks_ok))

    def test_daftar_gaya_lengkap(self):
        self.assertEqual(
            set(GAYA_LEVELUP), {"classic", "minimal", "party", "mention"}
        )


def _mock_guild(dengan_members: bool = True):
    g = MagicMock()
    g.id = 999001
    g.name = "Server Tes"
    g.icon = None
    g.owner.mention = "<@1>"
    g.owner.display_name = "Pemilik Tes"
    g.created_at = datetime(2024, 1, 15)
    g.member_count = 42
    g.premium_tier = 2
    g.premium_subscription_count = 7
    g.roles = [MagicMock() for _ in range(5)]
    g.emojis = [MagicMock() for _ in range(3)]
    g.text_channels = [MagicMock() for _ in range(4)]
    g.voice_channels = [MagicMock() for _ in range(2)]
    g.filesize_limit = 8 * 1048576
    if dengan_members:
        def member(bot):
            m = MagicMock()
            m.bot = bot
            return m
        g.members = [member(False)] * 40 + [member(True)] * 2
    else:
        g.members = []
    return g


class TestServerinfoKaya(unittest.TestCase):
    def test_field_lengkap_dengan_breakdown_member(self):
        embed = build_serverinfo_embed(_mock_guild(True))
        self.assertIn("Server Tes", embed.title)
        fields = {f.name: f.value for f in embed.fields}
        self.assertIn("999001", fields["ID Server"])
        self.assertEqual(fields["Dibuat"], "15 Jan 2024")
        self.assertEqual(fields["Owner"], "Pemilik Tes")
        self.assertNotIn("<@", fields["Owner"])  # owner tidak di-mention (anti ping-spam)
        # breakdown manusia/bot
        self.assertIn("40", fields["Member"])
        self.assertIn("manusia", fields["Member"])
        self.assertIn("2", fields["Member"])
        self.assertIn("bot", fields["Member"])
        self.assertIn("5", fields["Role"])
        self.assertIn("3", fields["Emoji"])
        self.assertIn("4", fields["Channel"])  # teks
        self.assertIn("2", fields["Channel"])  # suara
        self.assertIn("2", fields["Boost"])
        self.assertIn("7", fields["Boost"])
        self.assertIn("8 MB", fields["File"])

    def test_tanpa_cache_member_tidak_crash(self):
        embed = build_serverinfo_embed(_mock_guild(False))
        fields = {f.name: f.value for f in embed.fields}
        self.assertIn("42", fields["Member"])

    def test_judul_maksimal_satu_emoji(self):
        embed = build_serverinfo_embed(_mock_guild(True))
        self.assertLessEqual(
            sum(1 for c in embed.title if ord(c) > 0x2BFF), 1
        )


class TestSubstitusiPengumuman(unittest.TestCase):
    def test_server_dan_date(self):
        now = datetime(2026, 10, 9, 12, 0)
        hasil = substitusi_pengumuman(
            "Halo {server}, hari ini {date}!", "Server Tes", now
        )
        self.assertEqual(hasil, "Halo Server Tes, hari ini 09 Oct 2026!")

    def test_tanpa_placeholder_utuh(self):
        hasil = substitusi_pengumuman("Pengumuman biasa", "S", datetime(2026, 1, 1))
        self.assertEqual(hasil, "Pengumuman biasa")


if __name__ == "__main__":
    unittest.main()
