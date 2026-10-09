"""Tes ringan untuk src/config.py. Jalanin:  python -m unittest discover tests"""
import os
import unittest


class TestSettings(unittest.TestCase):
    def test_validate_menolak_token_kosong(self):
        os.environ["DISCORD_TOKEN"] = ""
        from src.config import Settings

        self.assertTrue(Settings().validate())

    def test_validate_menolak_token_contoh(self):
        os.environ["DISCORD_TOKEN"] = "isi_token_bot_kamu_di_sini"
        from src.config import Settings

        self.assertTrue(Settings().validate())

    def test_validate_lolos_kalau_token_terisi(self):
        os.environ["DISCORD_TOKEN"] = "token-palsu-buat-tes"
        from src.config import Settings

        self.assertEqual(Settings().validate(), [])

    def test_default_anti_spam(self):
        from src.config import Settings

        s = Settings()
        self.assertEqual(s.spam_max_messages, 5)
        self.assertEqual(s.spam_window_seconds, 5)
        self.assertEqual(s.prefix, "!")

    def test_default_verifikasi_dan_modlog(self):
        from src.config import Settings

        s = Settings()
        self.assertEqual(s.verify_channel_id, 0)
        self.assertEqual(s.verified_role_name, "Member")
        self.assertEqual(s.unverified_role_name, "Belum Verifikasi")
        self.assertEqual(s.mod_log_channel_id, 0)
        self.assertTrue(s.anti_invite)

    def test_anti_invite_bisa_dimatikan(self):
        os.environ["ANTI_INVITE"] = "false"
        try:
            from src.config import Settings

            self.assertFalse(Settings().anti_invite)
        finally:
            del os.environ["ANTI_INVITE"]

    def test_default_tiket_dan_self_roles(self):
        from src.config import Settings

        s = Settings()
        self.assertEqual(s.ticket_category_id, 0)
        self.assertEqual(s.self_roles_list(), [])

    def test_self_roles_list_parsing(self):
        os.environ["SELF_ROLES"] = "Pioneer, Notifikasi Event,,Mabar "
        try:
            from src.config import Settings

            self.assertEqual(
                Settings().self_roles_list(),
                ["Pioneer", "Notifikasi Event", "Mabar"],
            )
        finally:
            del os.environ["SELF_ROLES"]

    def test_default_starboard_dan_warn(self):
        from src.config import Settings

        s = Settings()
        self.assertEqual(s.starboard_channel_id, 0)
        self.assertEqual(s.starboard_min, 3)
        self.assertEqual(s.warn_max, 3)
        self.assertIn("tolol", s.bad_words_list())

    def test_bad_words_bisa_dioverride(self):
        os.environ["BAD_WORDS"] = " Kasar1 ,,kasar2 "
        try:
            from src.config import Settings

            self.assertEqual(Settings().bad_words_list(), ["kasar1", "kasar2"])
        finally:
            del os.environ["BAD_WORDS"]


if __name__ == "__main__":
    unittest.main()
