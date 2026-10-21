"""Manajemen data persisten (SQLite).

Semua data bot (Level, riwayat moderasi, dsb) disimpan di data/finch.db.
"""
from contextlib import contextmanager
import logging
import re
import sqlite3
from pathlib import Path

log = logging.getLogger("finch")
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "finch.db"

# Validasi nama tabel/kolom untuk query DDL yang memakai f-string
# (SQLite tidak mendukung parameter binding untuk identifier).
_IDENT_AMAN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# Definisi kolom DDL (tipe + DEFAULT) — hanya karakter yang wajar untuk
# "INTEGER DEFAULT 0" / "TEXT" / "VARCHAR(32)" dsb. Tanpa ini, definisi
# yang lolos dari input luar bisa menyuntik statement tambahan.
_DEFINISI_AMAN = re.compile(r"^[A-Za-z0-9_(),\s']+$")  # kutip tunggal diizinkan untuk DEFAULT '...'


@contextmanager
def get_connection():
    conn = sqlite3.connect(str(DB_PATH), timeout=10, check_same_thread=False)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        pass
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    """Setup tabel saat bot startup."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL DEFAULT 0,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, guild_id)
            )
        """)
        # Migrasi DB lama (skema sebelum ada guild_id: user_id saja sebagai PK).
        # Data XP lama dipertahankan, dianggap milik guild 0.
        cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "guild_id" not in cols:
            log.info("Migrasi DB: menambah guild_id ke tabel users...")
            # Idempoten: buang sisa tabel sementara dari migrasi yang terinterupsi
            # (pola sama seperti migrasi invites_log di bawah).
            conn.execute("DROP TABLE IF EXISTS users_old")
            conn.execute("ALTER TABLE users RENAME TO users_old")
            conn.execute("""
                CREATE TABLE users (
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL DEFAULT 0,
                    xp INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 1,
                    PRIMARY KEY (user_id, guild_id)
                )
            """)
            conn.execute(
                "INSERT INTO users (user_id, guild_id, xp, level) "
                "SELECT user_id, 0, xp, level FROM users_old"
            )
            conn.execute("DROP TABLE users_old")
            log.info("Migrasi DB selesai.")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mutes (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL DEFAULT 0,
                ends_at TEXT,
                PRIMARY KEY (user_id, guild_id)
            )
        """)
        # Migrasi mutes lama jika belum ada guild_id di PK
        cols_mutes = [r[1] for r in conn.execute("PRAGMA table_info(mutes)").fetchall()]
        if "guild_id" not in cols_mutes:
            conn.execute("DROP TABLE IF EXISTS mutes_old")
            conn.execute("ALTER TABLE mutes RENAME TO mutes_old")
            conn.execute("""
                CREATE TABLE mutes (
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL DEFAULT 0,
                    ends_at TEXT,
                    PRIMARY KEY (user_id, guild_id)
                )
            """)
            conn.execute("INSERT INTO mutes (user_id, guild_id, ends_at) SELECT user_id, 0, ends_at FROM mutes_old")
            conn.execute("DROP TABLE mutes_old")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                owner_id INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                closed INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS giveaways (
                message_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                ends_at TEXT NOT NULL,
                winners_count INTEGER DEFAULT 1,
                prize TEXT NOT NULL,
                host_id INTEGER NOT NULL,
                ended INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS giveaway_entries (
                message_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                PRIMARY KEY (message_id, user_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS polls (
                message_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                host_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                options TEXT NOT NULL,
                ends_at TEXT,
                ended INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS poll_votes (
                message_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                option_idx INTEGER NOT NULL,
                PRIMARY KEY (message_id, user_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS starboard (
                message_id INTEGER PRIMARY KEY,
                starboard_msg_id INTEGER,
                channel_id INTEGER NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                count INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, guild_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS afk (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                reason TEXT,
                since TEXT NOT NULL,
                PRIMARY KEY (user_id, guild_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                remind_at TEXT NOT NULL,
                done INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tempvc (
                channel_id INTEGER PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS suggestions (
                message_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                status TEXT DEFAULT 'Menunggu'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS yt_posts (
                video_id TEXT PRIMARY KEY,
                posted_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS invites_log (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                inviter_id INTEGER,
                code TEXT,
                joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, guild_id)
            )
        """)
        # Migrasi invites_log lama jika PK-nya masih user_id saja
        cols_inv = [r[1] for r in conn.execute("PRAGMA table_info(invites_log)").fetchall()]
        if cols_inv and cols_inv[0] == "user_id":
            # Idempoten: buang sisa tabel sementara dari migrasi yang terinterupsi.
            conn.execute("DROP TABLE IF EXISTS invites_log_old")
            conn.execute("ALTER TABLE invites_log RENAME TO invites_log_old")
            conn.execute("""
                CREATE TABLE invites_log (
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    inviter_id INTEGER,
                    code TEXT,
                    joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, guild_id)
                )
            """)
            # Ambil data, gabung per guild (best-effort: user paling baru menang tiap guild)
            try:
                conn.execute("INSERT INTO invites_log (user_id, guild_id, inviter_id, code, joined_at) SELECT user_id, guild_id, inviter_id, code, joined_at FROM invites_log_old GROUP BY user_id, guild_id ORDER BY joined_at DESC")
                conn.execute("DROP TABLE invites_log_old")
            except Exception:
                conn.execute("DROP TABLE invites_log_old")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS economy (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                balance INTEGER NOT NULL DEFAULT 0,
                total_earned INTEGER NOT NULL DEFAULT 0,
                last_daily TEXT,
                last_work TEXT,
                PRIMARY KEY (user_id, guild_id)
            )
        """)
        # --- Migrasi Tahap 10: kolom baru di tabel yang sudah ada ---
        def _tambah_kolom(tabel: str, kolom: str, definisi: str) -> None:
            # Identifier tidak bisa di-parameterize -> validasi ketat.
            # Semua pemanggil memakai literal internal, jadi ini tidak
            # mengubah perilaku; hanya mencegah injeksi bila suatu saat
            # ada input luar yang lolos ke sini.
            if not _IDENT_AMAN.match(tabel) or not _IDENT_AMAN.match(kolom):
                raise ValueError(f"Nama tabel/kolom tidak valid: {tabel}.{kolom}")
            if not _DEFINISI_AMAN.match(definisi):
                raise ValueError(f"Definisi kolom tidak valid: {definisi!r}")
            cols = [r[1] for r in conn.execute(
                f"PRAGMA table_info({tabel})").fetchall()]
            if kolom not in cols:
                conn.execute(f"ALTER TABLE {tabel} ADD COLUMN {kolom} {definisi}")

        _tambah_kolom("giveaways", "prize_coins", "INTEGER DEFAULT 0")
        _tambah_kolom("giveaways", "reroll_count", "INTEGER DEFAULT 0")
        # --- Migrasi Tahap 11 ---
        _tambah_kolom("economy", "bank", "INTEGER DEFAULT 0")
        _tambah_kolom("economy", "streak_daily", "INTEGER DEFAULT 0")
        _tambah_kolom("economy", "last_streak_date", "TEXT")
        _tambah_kolom("economy", "trivia_menang", "INTEGER DEFAULT 0")
        _tambah_kolom("users", "prestige", "INTEGER DEFAULT 0")
        _tambah_kolom("giveaways", "min_level", "INTEGER DEFAULT 0")
        _tambah_kolom("giveaways", "min_koin", "INTEGER DEFAULT 0")
        _tambah_kolom("giveaways", "role_syarat", "INTEGER DEFAULT 0")
        _tambah_kolom("giveaways", "hadiah_role", "INTEGER DEFAULT 0")
        # --- Tabel baru Tahap 11 ---
        conn.execute("CREATE TABLE IF NOT EXISTS server_pool (guild_id INTEGER PRIMARY KEY, koin INTEGER NOT NULL DEFAULT 0)")
        conn.execute("CREATE TABLE IF NOT EXISTS lotre_tiket (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, minggu TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS gaji_state (guild_id INTEGER PRIMARY KEY, terakhir TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS lelang (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, message_id INTEGER NOT NULL, nama_role TEXT NOT NULL, harga_awal INTEGER NOT NULL, tawaran_tertinggi INTEGER NOT NULL DEFAULT 0, penawar_id INTEGER, ends_at TEXT NOT NULL, ended INTEGER DEFAULT 0)")
        conn.execute("CREATE TABLE IF NOT EXISTS lelang_bid (id INTEGER PRIMARY KEY AUTOINCREMENT, lelang_id INTEGER NOT NULL, user_id INTEGER NOT NULL, jumlah INTEGER NOT NULL, waktu TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS achievement (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, kode TEXT NOT NULL, tgl TEXT NOT NULL, PRIMARY KEY (user_id, guild_id, kode))")
        conn.execute("CREATE TABLE IF NOT EXISTS autoresponder (guild_id INTEGER NOT NULL, trigger TEXT NOT NULL, respons TEXT NOT NULL, PRIMARY KEY (guild_id, trigger))")
        conn.execute("CREATE TABLE IF NOT EXISTS custom_commands (guild_id INTEGER NOT NULL, trigger TEXT NOT NULL, response TEXT NOT NULL, author_id INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (guild_id, trigger))")
        conn.execute("CREATE TABLE IF NOT EXISTS birthday (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, tgl TEXT NOT NULL, tahun_terakhir TEXT, PRIMARY KEY (user_id, guild_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS sticky (channel_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, teks TEXT NOT NULL, message_id INTEGER)")
        conn.execute("CREATE TABLE IF NOT EXISTS bump (guild_id INTEGER PRIMARY KEY, terakhir TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, message_id INTEGER NOT NULL, nama TEXT NOT NULL, kapan TEXT NOT NULL, deskripsi TEXT NOT NULL DEFAULT '', notif_terkirim INTEGER DEFAULT 0)")
        conn.execute("CREATE TABLE IF NOT EXISTS event_rsvp (event_id INTEGER NOT NULL, user_id INTEGER NOT NULL, status TEXT NOT NULL, PRIMARY KEY (event_id, user_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS season_state (guild_id INTEGER PRIMARY KEY, season INTEGER NOT NULL DEFAULT 1, berakhir TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS giveaway_rutin (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, interval_detik INTEGER NOT NULL, pemenang INTEGER NOT NULL, hadiah TEXT NOT NULL, koin INTEGER NOT NULL DEFAULT 0, host_id INTEGER NOT NULL, terakhir TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS poll_rutin (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, interval_detik INTEGER NOT NULL, pertanyaan TEXT NOT NULL, opsi TEXT NOT NULL, terakhir TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS reminder_rutin (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, user_id INTEGER NOT NULL, interval_detik INTEGER NOT NULL, teks TEXT NOT NULL, terakhir TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS twitch_live (login TEXT PRIMARY KEY, stream_id TEXT, notified_at TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS voice_total (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, menit INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (user_id, guild_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS starboard_rewarded (message_id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE IF NOT EXISTS lockdown_state (channel_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, send_messages INTEGER)")
        conn.execute("CREATE TABLE IF NOT EXISTS tiket_rating_pending (owner_id INTEGER PRIMARY KEY, tiket_id INTEGER NOT NULL, guild_id INTEGER NOT NULL)")
        # ===== Tahap 12 =====
        conn.execute("CREATE TABLE IF NOT EXISTS inventory (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, item_id TEXT NOT NULL, jumlah INTEGER NOT NULL DEFAULT 0, berakhir TEXT, PRIMARY KEY (user_id, guild_id, item_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS pinjaman (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, pokok INTEGER NOT NULL, sisa INTEGER NOT NULL, bunga_harian INTEGER NOT NULL, dibuat TEXT NOT NULL, jatuh_tempo TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS deposito (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, jumlah INTEGER NOT NULL, mulai TEXT NOT NULL, durasi_hari INTEGER NOT NULL, bunga_pct INTEGER NOT NULL, selesai INTEGER NOT NULL DEFAULT 0)")
        conn.execute("CREATE TABLE IF NOT EXISTS saham_harga (simbol TEXT PRIMARY KEY, harga INTEGER NOT NULL, updated_at TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS saham_milik (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, simbol TEXT NOT NULL, jumlah INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (user_id, guild_id, simbol))")
        conn.execute("CREATE TABLE IF NOT EXISTS turnamen (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, jenis TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'buka', dibuat TEXT NOT NULL, berakhir TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS turnamen_peserta (turnamen_id INTEGER NOT NULL, user_id INTEGER NOT NULL, skor INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (turnamen_id, user_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS job (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, job_id TEXT NOT NULL, diambil TEXT NOT NULL, PRIMARY KEY (user_id, guild_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS nikah (user_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, pasangan_id INTEGER NOT NULL, sejak TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS clan (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, nama TEXT NOT NULL, ketua_id INTEGER NOT NULL, dibuat TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS clan_member (clan_id INTEGER NOT NULL, user_id INTEGER PRIMARY KEY, joined TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS gelar_milik (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, gelar_id TEXT NOT NULL, PRIMARY KEY (user_id, guild_id, gelar_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS gelar_aktif (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, gelar_id TEXT NOT NULL, PRIMARY KEY (user_id, guild_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS pet (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, nama TEXT NOT NULL, jenis TEXT NOT NULL, xp INTEGER NOT NULL DEFAULT 0, dibuat TEXT NOT NULL, PRIMARY KEY (user_id, guild_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS quest_guild (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, nama TEXT NOT NULL, target INTEGER NOT NULL, progres INTEGER NOT NULL DEFAULT 0, hadiah INTEGER NOT NULL, berakhir TEXT NOT NULL, selesai INTEGER NOT NULL DEFAULT 0)")
        conn.execute("CREATE TABLE IF NOT EXISTS dailyq (guild_id INTEGER NOT NULL, tanggal TEXT NOT NULL, pertanyaan TEXT NOT NULL, PRIMARY KEY (guild_id, tanggal))")
        conn.execute("CREATE TABLE IF NOT EXISTS dailyq_jawab (guild_id INTEGER NOT NULL, tanggal TEXT NOT NULL, user_id INTEGER NOT NULL, PRIMARY KEY (guild_id, tanggal, user_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS saran_vote (message_id INTEGER NOT NULL, user_id INTEGER NOT NULL, vote INTEGER NOT NULL, PRIMARY KEY (message_id, user_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS event_rutin (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, nama TEXT NOT NULL, deskripsi TEXT NOT NULL DEFAULT '', interval_detik INTEGER NOT NULL, terakhir TEXT)")
        _tambah_kolom("tickets", "kategori", "TEXT DEFAULT 'umum'")
        _tambah_kolom("tickets", "balas_terakhir", "TEXT")
        _tambah_kolom("economy", "peti_terakhir", "TEXT")
        # ===== Tahap 12 hotfix: persist state yang tadinya in-memory =====
        conn.execute("CREATE TABLE IF NOT EXISTS cooldown_aksi (user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, aksi TEXT NOT NULL, terakhir TEXT NOT NULL, PRIMARY KEY (user_id, guild_id, aksi))")
        conn.execute("CREATE TABLE IF NOT EXISTS clan_war_peserta (guild_id INTEGER NOT NULL, clan_id INTEGER NOT NULL, minggu TEXT NOT NULL, PRIMARY KEY (guild_id, clan_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS sla_warned (channel_id INTEGER PRIMARY KEY, warned_at TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS tiket_rating (tiket_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, rating INTEGER NOT NULL)")
        # ===== Dashboard web: wiring pengumuman + mod-log =====
        # (dashboard_sync juga membuatnya defensif di __init__; IF NOT EXISTS aman dua kali)
        conn.execute("CREATE TABLE IF NOT EXISTS dashboard_announcements (id INTEGER PRIMARY KEY, guild_id TEXT NOT NULL, channel_id TEXT NOT NULL, message TEXT NOT NULL, run_at TEXT, interval_minutes INTEGER, enabled INTEGER NOT NULL DEFAULT 1, last_sent_at TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS mod_actions (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id TEXT NOT NULL, user_id TEXT NOT NULL, mod_id TEXT NOT NULL, aksi TEXT NOT NULL, alasan TEXT NOT NULL DEFAULT '', waktu TEXT NOT NULL)")
        conn.commit()
        _tambah_kolom("economy", "rep", "INTEGER DEFAULT 0")
        _tambah_kolom("economy", "last_rep", "TEXT")
        _tambah_kolom("economy", "last_trivia", "TEXT")
        # --- Tabel baru Tahap 10 ---
        conn.execute("""
            CREATE TABLE IF NOT EXISTS counting_state (
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                angka INTEGER NOT NULL DEFAULT 0,
                user_terakhir INTEGER,
                PRIMARY KEY (guild_id, channel_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quest_progress (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                tanggal TEXT NOT NULL,
                pesan INTEGER NOT NULL DEFAULT 0,
                voice_menit INTEGER NOT NULL DEFAULT 0,
                daily_ok INTEGER NOT NULL DEFAULT 0,
                klaim_pesan INTEGER NOT NULL DEFAULT 0,
                klaim_voice INTEGER NOT NULL DEFAULT 0,
                klaim_daily INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, guild_id, tanggal)
            )
        """)
        conn.commit()
    log.info("DB diinisialisasi di %s", DB_PATH)
