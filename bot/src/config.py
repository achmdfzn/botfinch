"""Konfigurasi terpusat Finch.

Semua setting dibaca dari environment variable (file .env).
Tidak ada secret yang di-hardcode di kode.
"""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Baca .env sedini mungkin, sebelum Settings() dibuat di bawah.
# Aman dipanggil tanpa file .env (jadi no-op).
load_dotenv()


def _getenv_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _getenv_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    """Semua konfigurasi bot dalam satu tempat."""

    # --- wajib ---
    token: str = field(default_factory=lambda: os.getenv("DISCORD_TOKEN", ""))

    # --- umum ---
    prefix: str = field(default_factory=lambda: os.getenv("COMMAND_PREFIX", "!"))
    guild_id: int = field(default_factory=lambda: _getenv_int("GUILD_ID", 0))
    welcome_channel_id: int = field(
        default_factory=lambda: _getenv_int("WELCOME_CHANNEL_ID", 0)
    )

    # --- anti-spam (moderation) ---
    spam_max_messages: int = field(
        default_factory=lambda: _getenv_int("SPAM_MAX_MESSAGES", 5)
    )
    spam_window_seconds: int = field(
        default_factory=lambda: _getenv_int("SPAM_WINDOW_SECONDS", 5)
    )

    # --- verifikasi member ---
    verify_channel_id: int = field(
        default_factory=lambda: _getenv_int("VERIFY_CHANNEL_ID", 0)
    )
    verified_role_name: str = field(
        default_factory=lambda: os.getenv("VERIFIED_ROLE_NAME", "Member")
    )
    unverified_role_name: str = field(
        default_factory=lambda: os.getenv("UNVERIFIED_ROLE_NAME", "Belum Verifikasi")
    )

    # --- mod log ---
    mod_log_channel_id: int = field(
        default_factory=lambda: _getenv_int("MOD_LOG_CHANNEL_ID", 0)
    )

    # --- anti invite link ---
    anti_invite: bool = field(
        default_factory=lambda: _getenv_bool("ANTI_INVITE", True)
    )

    # --- mute (moderation) ---
    mute_duration_minutes: int = field(
        default_factory=lambda: _getenv_int("MUTE_DURATION_MINUTES", 10)
    )

    # --- level / xp ---
    xp_per_message: int = field(default_factory=lambda: _getenv_int("XP_PER_MESSAGE", 15))
    xp_cooldown_seconds: int = field(
        default_factory=lambda: _getenv_int("XP_COOLDOWN_SECONDS", 60)
    )

    # --- tiket ---
    ticket_category_id: int = field(
        default_factory=lambda: _getenv_int("TICKET_CATEGORY_ID", 0)
    )

    # --- self roles ---
    self_roles: str = field(default_factory=lambda: os.getenv("SELF_ROLES", ""))

    def self_roles_list(self) -> list[str]:
        """Daftar nama role dari SELF_ROLES (dipisah koma)."""
        return [r.strip() for r in self.self_roles.split(",") if r.strip()]

    # --- level role rewards ---
    level_roles: str = field(default_factory=lambda: os.getenv("LEVEL_ROLES", ""))

    def level_roles_list(self) -> list[tuple[int, str]]:
        """Parse LEVEL_ROLES: '5:Aktif,10:Veteran' -> [(5, 'Aktif'), (10, 'Veteran')]."""
        hasil: list[tuple[int, str]] = []
        for bagian in self.level_roles.split(","):
            if ":" not in bagian:
                continue
            lvl, nama = bagian.split(":", 1)
            nama = nama.strip()
            try:
                hasil.append((int(lvl.strip()), nama))
            except ValueError:
                continue
        return sorted(hasil)

    def level_roles_voice_list(self) -> list[tuple[int, str]]:
        """Parse LEVEL_ROLES_VOICE: '60:Aktif Voice,300:Sepuh Voice' -> [(60, ...)]."""
        hasil: list[tuple[int, str]] = []
        for bagian in (self.level_roles_voice or "").split(","):
            if ":" not in bagian:
                continue
            menit, nama = bagian.split(":", 1)
            nama = nama.strip()
            try:
                hasil.append((int(menit.strip()), nama))
            except ValueError:
                continue
        return sorted(hasil)

    # --- server stats ---
    stats_total_id: int = field(
        default_factory=lambda: _getenv_int("STATS_TOTAL_ID", 0)
    )
    stats_human_id: int = field(
        default_factory=lambda: _getenv_int("STATS_HUMAN_ID", 0)
    )
    stats_bot_id: int = field(
        default_factory=lambda: _getenv_int("STATS_BOT_ID", 0)
    )

    # --- starboard ---
    starboard_channel_id: int = field(
        default_factory=lambda: _getenv_int("STARBOARD_CHANNEL_ID", 0)
    )
    starboard_min: int = field(
        default_factory=lambda: _getenv_int("STARBOARD_MIN", 3)
    )

    # --- auto-mod kata kasar ---
    bad_words: str = field(
        default_factory=lambda: os.getenv(
            "BAD_WORDS",
            "anjing,bangsat,bajingan,brengsek,tolol,goblok,bego,babi,jancuk,jancok,asw",
        )
    )
    warn_max: int = field(default_factory=lambda: _getenv_int("WARN_MAX", 3))

    def bad_words_list(self) -> list[str]:
        """Daftar kata kasar dari BAD_WORDS (dipisah koma, lowercase)."""
        return [w.strip().lower() for w in self.bad_words.split(",") if w.strip()]

    # --- youtube ---
    yt_channel_id: str = field(default_factory=lambda: os.getenv("YT_CHANNEL_ID", ""))
    yt_notify_channel_id: int = field(default_factory=lambda: _getenv_int("YT_NOTIFY_CHANNEL_ID", 0))
    yt_check_minutes: int = field(default_factory=lambda: _getenv_int("YT_CHECK_MINUTES", 15))
    yt_ping_role_id: int = field(default_factory=lambda: _getenv_int("YT_PING_ROLE_ID", 0))

    # --- voice xp ---
    voice_xp_per_min: int = field(default_factory=lambda: _getenv_int("VOICE_XP_PER_MIN", 5))

    # --- temp voice channel ---
    tempvc_lobby_id: int = field(
        default_factory=lambda: _getenv_int("TEMPVC_LOBBY_ID", 0)
    )
    tempvc_category_id: int = field(
        default_factory=lambda: _getenv_int("TEMPVC_CATEGORY_ID", 0)
    )

    # --- sistem saran ---
    saran_channel_id: int = field(
        default_factory=lambda: _getenv_int("SARAN_CHANNEL_ID", 0)
    )

    # --- economy (koin) ---
    economy_start_balance: int = field(default_factory=lambda: _getenv_int("ECONOMY_START_BALANCE", 100))
    economy_daily_min: int = field(default_factory=lambda: _getenv_int("ECONOMY_DAILY_MIN", 100))
    economy_daily_max: int = field(default_factory=lambda: _getenv_int("ECONOMY_DAILY_MAX", 300))
    economy_work_min: int = field(default_factory=lambda: _getenv_int("ECONOMY_WORK_MIN", 50))
    economy_work_max: int = field(default_factory=lambda: _getenv_int("ECONOMY_WORK_MAX", 150))
    economy_work_cooldown: int = field(default_factory=lambda: _getenv_int("ECONOMY_WORK_COOLDOWN", 3600))
    economy_level_bonus: int = field(default_factory=lambda: _getenv_int("ECONOMY_LEVEL_BONUS", 50))

    # --- minigames ---
    economy_min_bet: int = field(default_factory=lambda: _getenv_int("ECONOMY_MIN_BET", 10))
    economy_max_bet: int = field(default_factory=lambda: _getenv_int("ECONOMY_MAX_BET", 5000))
    economy_trivia_reward: int = field(default_factory=lambda: _getenv_int("ECONOMY_TRIVIA_REWARD", 100))
    economy_trivia_cooldown: int = field(default_factory=lambda: _getenv_int("ECONOMY_TRIVIA_COOLDOWN", 300))

    # --- Tahap 12: economy+ ---
    trade_timeout: int = field(default_factory=lambda: _getenv_int("TRADE_TIMEOUT", 120))
    pinjaman_maks: int = field(default_factory=lambda: _getenv_int("PINJAMAN_MAKS", 5000))
    pinjaman_bunga_harian: int = field(default_factory=lambda: _getenv_int("PINJAMAN_BUNGA_HARIAN", 5))
    pinjaman_tenor_hari: int = field(default_factory=lambda: _getenv_int("PINJAMAN_TENOR_HARI", 7))
    deposito_pilihan: str = field(default_factory=lambda: os.getenv("DEPOSITO_PILIHAN", "7:3,30:8"))
    saham_update_menit: int = field(default_factory=lambda: _getenv_int("SAHAM_UPDATE_MENIT", 60))

    def deposito_pilihan_list(self) -> list[tuple[int, int]]:
        """Parse DEPOSITO_PILIHAN jadi [(hari, bunga_pct)]."""
        hasil = []
        for entri in self.deposito_pilihan.split(","):
            entri = entri.strip()
            if ":" not in entri:
                continue
            hari, bunga = entri.split(":", 1)
            try:
                h, b = int(hari.strip()), int(bunga.strip())
            except ValueError:
                continue
            if h > 0 and b >= 0:
                hasil.append((h, b))
        return hasil or [(7, 3), (30, 8)]

    # --- Tahap 12: games ---
    turnamen_hadiah: int = field(default_factory=lambda: _getenv_int("TURNAMEN_HADIAH", 1000))
    kuis_jumlah_soal: int = field(default_factory=lambda: _getenv_int("KUIS_JUMLAH_SOAL", 5))
    kuis_reward: int = field(default_factory=lambda: _getenv_int("KUIS_REWARD", 50))

    # --- Tahap 12: leveling & sosial ---
    reaction_xp: int = field(default_factory=lambda: _getenv_int("REACTION_XP", 2))
    reaction_cooldown: int = field(default_factory=lambda: _getenv_int("REACTION_COOLDOWN", 60))
    level_roles_voice: str = field(default_factory=lambda: os.getenv("LEVEL_ROLES_VOICE", ""))
    confess_channel_id: int = field(default_factory=lambda: _getenv_int("CONFESS_CHANNEL_ID", 0))
    nikah_bonus_harian: int = field(default_factory=lambda: _getenv_int("NIKAH_BONUS_HARIAN", 50))
    clan_biaya: int = field(default_factory=lambda: _getenv_int("CLAN_BIAYA", 1000))
    clan_war_hadiah: int = field(default_factory=lambda: _getenv_int("CLAN_WAR_HADIAH", 2000))

    # --- Tahap 12: engagement ---
    pet_harga: int = field(default_factory=lambda: _getenv_int("PET_HARGA", 500))
    quest_guild_target: int = field(default_factory=lambda: _getenv_int("QUEST_GUILD_TARGET", 2000))
    quest_guild_hadiah: int = field(default_factory=lambda: _getenv_int("QUEST_GUILD_HADIAH", 300))
    bump_koin: int = field(default_factory=lambda: _getenv_int("BUMP_KOIN", 100))
    dailyq_channel_id: int = field(default_factory=lambda: _getenv_int("DAILYQ_CHANNEL_ID", 0))
    dailyq_reward: int = field(default_factory=lambda: _getenv_int("DAILYQ_REWARD", 25))
    dailyq_maks: int = field(default_factory=lambda: _getenv_int("DAILYQ_MAKS", 20))

    # --- Tahap 12: utilitas ---
    backup_channel_id: int = field(default_factory=lambda: _getenv_int("BACKUP_CHANNEL_ID", 0))
    dashboard_port: int = field(default_factory=lambda: _getenv_int("DASHBOARD_PORT", 8080))
    dashboard_host: str = field(default_factory=lambda: os.getenv("DASHBOARD_HOST", "127.0.0.1"))
    # --- dashboard web (Next.js): kosong = sinkronisasi mati ---
    dashboard_url: str = field(
        default_factory=lambda: os.getenv("DASHBOARD_URL", "").rstrip("/")
    )
    dashboard_secret: str = field(
        default_factory=lambda: os.getenv("DASHBOARD_SECRET", "")
    )
    tiket_sla_jam: int = field(default_factory=lambda: _getenv_int("TIKET_SLA_JAM", 24))

    # --- shop (format: "NamaRole:harga,NamaRole:harga") ---
    shop_items: str = field(default_factory=lambda: os.getenv("SHOP_ITEMS", ""))

    def shop_items_list(self) -> list[tuple[str, int]]:
        """Parse SHOP_ITEMS jadi [(nama_role, harga)]. Entri rusak dilewati."""
        hasil = []
        for entri in self.shop_items.split(","):
            entri = entri.strip()
            if ":" not in entri:
                continue
            nama, harga = entri.rsplit(":", 1)
            nama = nama.strip()
            try:
                harga_int = int(harga.strip())
            except ValueError:
                continue
            if nama and harga_int > 0:
                hasil.append((nama, harga_int))
        return hasil

    # --- counting channel ---
    counting_channel_id: int = field(
        default_factory=lambda: _getenv_int("COUNTING_CHANNEL_ID", 0)
    )

    # --- bank, lotre, gaji ---
    bank_bunga_harian: int = field(default_factory=lambda: _getenv_int("BANK_BUNGA_HARIAN", 2))
    lotre_harga_tiket: int = field(default_factory=lambda: _getenv_int("LOTRE_HARGA_TIKET", 100))
    gaji_roles: str = field(default_factory=lambda: os.getenv("GAJI_ROLES", ""))

    def gaji_roles_list(self) -> list[tuple[str, int]]:
        """Parse GAJI_ROLES 'NamaRole:jumlah,...' — pola sama seperti shop."""
        hasil = []
        for entri in self.gaji_roles.split(","):
            entri = entri.strip()
            if ":" not in entri:
                continue
            nama, jumlah = entri.rsplit(":", 1)
            nama = nama.strip()
            try:
                jml = int(jumlah.strip())
            except ValueError:
                continue
            if nama and jml > 0:
                hasil.append((nama, jml))
        return hasil

    # --- reward perilaku ---
    invite_koin: int = field(default_factory=lambda: _getenv_int("INVITE_KOIN", 200))
    starboard_koin: int = field(default_factory=lambda: _getenv_int("STARBOARD_KOIN", 50))
    voice_koin_per_min: int = field(default_factory=lambda: _getenv_int("VOICE_KOIN_PER_MIN", 2))
    ultah_koin: int = field(default_factory=lambda: _getenv_int("ULTAH_KOIN", 200))

    # --- season & leveling ---
    season_hari: int = field(default_factory=lambda: _getenv_int("SEASON_HARI", 90))
    xp_weekend_boost: int = field(default_factory=lambda: _getenv_int("XP_WEEKEND_BOOST", 1))

    # --- minigames+ ---
    maling_cooldown: int = field(default_factory=lambda: _getenv_int("MALING_COOLDOWN", 3600))
    susunkata_reward: int = field(default_factory=lambda: _getenv_int("SUSUNKATA_REWARD", 150))
    susunkata_cooldown: int = field(default_factory=lambda: _getenv_int("SUSUNKATA_COOLDOWN", 600))

    # --- twitch ---
    twitch_client_id: str = field(default_factory=lambda: os.getenv("TWITCH_CLIENT_ID", ""))
    twitch_client_secret: str = field(default_factory=lambda: os.getenv("TWITCH_CLIENT_SECRET", ""))
    twitch_channel: str = field(default_factory=lambda: os.getenv("TWITCH_CHANNEL", ""))
    twitch_notify_channel_id: int = field(default_factory=lambda: _getenv_int("TWITCH_NOTIFY_CHANNEL_ID", 0))
    twitch_check_minutes: int = field(default_factory=lambda: _getenv_int("TWITCH_CHECK_MINUTES", 15))

    def validate(self) -> list[str]:
        """Return daftar masalah konfigurasi (kosong = aman jalan)."""
        masalah = []
        if not self.token or self.token == "isi_token_bot_kamu_di_sini":
            masalah.append(
                "DISCORD_TOKEN belum diisi. Copy .env.example jadi .env lalu isi tokennya."
            )
        if not self.prefix.strip():
            masalah.append("COMMAND_PREFIX tidak boleh kosong atau spasi.")
        if self.spam_max_messages < 1:
            masalah.append("SPAM_MAX_MESSAGES harus >= 1.")
        if self.spam_window_seconds < 1:
            masalah.append("SPAM_WINDOW_SECONDS harus >= 1.")
        if self.mute_duration_minutes < 1:
            masalah.append("MUTE_DURATION_MINUTES harus >= 1.")
        if self.warn_max < 1:
            masalah.append("WARN_MAX harus >= 1.")
        if self.starboard_min < 1:
            masalah.append("STARBOARD_MIN harus >= 1.")
        if self.xp_per_message < 0:
            masalah.append("XP_PER_MESSAGE tidak boleh negatif.")
        if self.xp_cooldown_seconds < 0:
            masalah.append("XP_COOLDOWN_SECONDS tidak boleh negatif.")
        if self.voice_xp_per_min < 0:
            masalah.append("VOICE_XP_PER_MIN tidak boleh negatif.")
        if self.yt_check_minutes < 1:
            masalah.append("YT_CHECK_MINUTES harus >= 1.")
        if self.economy_start_balance < 0:
            masalah.append("ECONOMY_START_BALANCE tidak boleh negatif.")
        if self.economy_daily_min < 0 or self.economy_daily_max < self.economy_daily_min:
            masalah.append("ECONOMY_DAILY_MIN/MAX tidak valid (min >= 0, max >= min).")
        if self.economy_work_min < 0 or self.economy_work_max < self.economy_work_min:
            masalah.append("ECONOMY_WORK_MIN/MAX tidak valid (min >= 0, max >= min).")
        if self.economy_work_cooldown < 0:
            masalah.append("ECONOMY_WORK_COOLDOWN tidak boleh negatif.")
        if self.economy_level_bonus < 0:
            masalah.append("ECONOMY_LEVEL_BONUS tidak boleh negatif.")
        if self.economy_min_bet < 1:
            masalah.append("ECONOMY_MIN_BET harus >= 1.")
        if self.economy_max_bet < self.economy_min_bet:
            masalah.append("ECONOMY_MAX_BET harus >= ECONOMY_MIN_BET.")
        if self.economy_trivia_reward < 0:
            masalah.append("ECONOMY_TRIVIA_REWARD tidak boleh negatif.")
        if self.economy_trivia_cooldown < 0:
            masalah.append("ECONOMY_TRIVIA_COOLDOWN tidak boleh negatif.")
        if not 0 <= self.bank_bunga_harian <= 100:
            masalah.append("BANK_BUNGA_HARIAN harus 0–100.")
        if self.lotre_harga_tiket < 1:
            masalah.append("LOTRE_HARGA_TIKET harus >= 1.")
        for nama, val in [("INVITE_KOIN", self.invite_koin), ("STARBOARD_KOIN", self.starboard_koin),
                          ("VOICE_KOIN_PER_MIN", self.voice_koin_per_min), ("ULTAH_KOIN", self.ultah_koin),
                          ("SUSUNKATA_REWARD", self.susunkata_reward)]:
            if val < 0:
                masalah.append(f"{nama} tidak boleh negatif.")
        if self.season_hari < 1:
            masalah.append("SEASON_HARI harus >= 1.")
        if self.maling_cooldown < 0:
            masalah.append("MALING_COOLDOWN tidak boleh negatif.")
        if self.susunkata_cooldown < 0:
            masalah.append("SUSUNKATA_COOLDOWN tidak boleh negatif.")
        if self.twitch_check_minutes < 1:
            masalah.append("TWITCH_CHECK_MINUTES harus >= 1.")
        # --- Tahap 12 ---
        if self.trade_timeout < 10:
            masalah.append("TRADE_TIMEOUT minimal 10 detik.")
        if self.pinjaman_maks < 0:
            masalah.append("PINJAMAN_MAKS tidak boleh negatif.")
        if not 0 <= self.pinjaman_bunga_harian <= 100:
            masalah.append("PINJAMAN_BUNGA_HARIAN harus 0–100.")
        if self.pinjaman_tenor_hari < 1:
            masalah.append("PINJAMAN_TENOR_HARI harus >= 1.")
        if self.saham_update_menit < 5:
            masalah.append("SAHAM_UPDATE_MENIT minimal 5.")
        if self.turnamen_hadiah < 0:
            masalah.append("TURNAMEN_HADIAH tidak boleh negatif.")
        if self.kuis_jumlah_soal < 1:
            masalah.append("KUIS_JUMLAH_SOAL harus >= 1.")
        if self.reaction_xp < 0 or self.reaction_cooldown < 0:
            masalah.append("REACTION_XP/REACTION_COOLDOWN tidak boleh negatif.")
        if self.nikah_bonus_harian < 0:
            masalah.append("NIKAH_BONUS_HARIAN tidak boleh negatif.")
        if self.clan_biaya < 0:
            masalah.append("CLAN_BIAYA tidak boleh negatif.")
        if self.pet_harga < 0:
            masalah.append("PET_HARGA tidak boleh negatif.")
        if self.quest_guild_target < 1:
            masalah.append("QUEST_GUILD_TARGET harus >= 1.")
        if self.bump_koin < 0:
            masalah.append("BUMP_KOIN tidak boleh negatif.")
        if self.dailyq_reward < 0 or self.dailyq_maks < 1:
            masalah.append("DAILYQ_REWARD/DAILYQ_MAKS tidak valid.")
        if not 1 <= self.dashboard_port <= 65535:
            masalah.append("DASHBOARD_PORT harus 1–65535.")
        # Dashboard web dipakai untuk push snapshot + pull settings; token
        # DASHBOARD_SECRET lewat header Authorization, jadi http:// ke host
        # publik = secret + data server bocor di jaringan.
        if self.dashboard_url:
            rendah = self.dashboard_url.strip().lower()
            if rendah.startswith("http://"):
                # urlparse menangani host bracket IPv6 ([::1]) dengan benar.
                from urllib.parse import urlparse

                host = (urlparse(rendah).hostname or "").lower()
                if host not in ("localhost", "127.0.0.1", "::1"):
                    masalah.append(
                        "DASHBOARD_URL memakai http:// ke host non-lokal — "
                        "tolak demi keamanan. Pakai https:// (kecuali localhost)."
                    )
        if self.tiket_sla_jam < 1:
            masalah.append("TIKET_SLA_JAM harus >= 1.")
        return masalah


settings = Settings()
