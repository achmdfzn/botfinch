"""Premium (Free/VIP) — katalog batas fitur, tier efektif, dan kuota.

Sumber kebenaran tier sebuah server adalah dashboard; bot hanya menyimpan
cache-nya di tabel `guild_entitlement_cache` (lihat store.init_db) lewat
`simpan_entitlement_cache()`. Semua pembacaan bersifat fail-closed: cache
kosong, basi, rusak, atau di luar jendela aktif berarti tier "free".

Pengecualian personal: owner bot (BOT_OWNER_IDS di .env) selalu diperlakukan
VIP di semua konteks — ini bypass per-aktor, BUKAN meng-VIP-kan guild-nya.
"""
import datetime

from src import config
from src.store import get_connection
from src.utils.waktu import parse_iso

# Katalog batas per fitur per tier. Angka-angkanya adalah kontrak produk —
# jangan diubah tanpa menyesuaikan dashboard & tes kontrak di test_premium.py.
FEATURE_LIMITS: dict[str, dict[str, int]] = {
    "custom_commands": {"free": 10, "vip": 100},
    "autoresponders": {"free": 10, "vip": 100},
    "giveaways_active": {"free": 3, "vip": 25},
    "selfrole_panels": {"free": 3, "vip": 25},
    "announcements_active": {"free": 3, "vip": 25},
}

# Label Bahasa Indonesia per feature_code untuk pesan ke user.
NAMA_FITUR: dict[str, str] = {
    "custom_commands": "perintah kustom",
    "autoresponders": "auto-responder",
    "giveaways_active": "giveaway aktif",
    "selfrole_panels": "panel self-role",
    "announcements_active": "pengumuman aktif",
}

# Teks ajakan upgrade umum (tanpa harga/URL — halaman upgrade belum tentu ada).
TEKS_UPGRADE = (
    "Server dengan paket VIP mendapatkan batas yang jauh lebih tinggi, "
    "dan owner bot selalu memakai batas VIP di semua server."
)


def _ke_int_id(nilai) -> int | None:
    """Normalisasi ID (int / str digit) jadi int; None bila tidak valid."""
    if isinstance(nilai, bool):
        return None
    if isinstance(nilai, int):
        return nilai
    if isinstance(nilai, str):
        s = nilai.strip()
        if s.isdigit():
            return int(s)
    return None


def is_bot_owner(user_id) -> bool:
    """True bila user_id termasuk BOT_OWNER_IDS. Input rusak -> False."""
    uid = _ke_int_id(user_id)
    if uid is None:
        return False
    return uid in config.settings.bot_owner_ids()


def simpan_entitlement_cache(guild_id, ent) -> None:
    """Simpan/overwrite cache entitlement satu guild dari payload dashboard.

    `ent` dict dengan kunci tier, status, starts_at, expires_at, source
    (nilai ISO string atau None). Bila `ent` None -> tidak mengubah apa pun.
    """
    if ent is None:
        return
    fetched_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO guild_entitlement_cache "
            "(guild_id, tier, status, starts_at, expires_at, source, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(guild_id),
                ent.get("tier") or "free",
                ent.get("status") or "active",
                ent.get("starts_at"),
                ent.get("expires_at"),
                ent.get("source"),
                fetched_at,
            ),
        )
        conn.commit()


def ambil_entitlement_cache(guild_id) -> dict | None:
    """Ambil baris cache entitlement guild sebagai dict; None bila belum ada."""
    with get_connection() as conn:
        baris = conn.execute(
            "SELECT guild_id, tier, status, starts_at, expires_at, source, fetched_at "
            "FROM guild_entitlement_cache WHERE guild_id = ?",
            (str(guild_id),),
        ).fetchone()
    if baris is None:
        return None
    kolom = ("guild_id", "tier", "status", "starts_at", "expires_at", "source", "fetched_at")
    return dict(zip(kolom, baris))


def get_effective_tier(guild_id, actor_id=None) -> str:
    """Tier efektif: "vip" hanya bila semua syarat terpenuhi, selain itu "free".

    - actor_id owner bot -> selalu "vip" (bypass personal).
    - Selain itu dari cache: tier 'vip' + status 'active' + sudah mulai
      (starts_at kosong/sudah lewat) + belum kedaluwarsa (expires_at kosong/
      masih di masa depan) + cache masih segar (fetched_at tidak lebih tua
      dari ENTITLEMENT_CACHE_MAX_AGE_SECONDS).
    Timestamp rusak diperlakukan aman (jatuh ke "free"); timestamp naive
    dianggap UTC (semantik parse_iso).
    """
    if actor_id is not None and is_bot_owner(actor_id):
        return "vip"
    try:
        cache = ambil_entitlement_cache(guild_id)
    except Exception:
        return "free"
    if not cache:
        return "free"
    if cache.get("tier") != "vip" or cache.get("status") != "active":
        return "free"
    now = datetime.datetime.now(datetime.timezone.utc)
    fetched_at = parse_iso(cache.get("fetched_at"))
    if fetched_at is None:
        return "free"
    umur = (now - fetched_at).total_seconds()
    if umur < 0 or umur > config.settings.entitlement_cache_max_age_seconds:
        return "free"
    starts_at = cache.get("starts_at")
    if starts_at:
        mulai = parse_iso(starts_at)
        if mulai is None or mulai > now:
            return "free"
    expires_at = cache.get("expires_at")
    if expires_at:
        berakhir = parse_iso(expires_at)
        if berakhir is None or berakhir <= now:
            return "free"
    return "vip"


def get_feature_limit(guild_id, feature_code, actor_id=None) -> int:
    """Batas kuota fitur untuk tier efektif guild/aktor ini.

    feature_code tak dikenal -> KeyError (sengaja dibiarkan, kontrak API).
    """
    tier = get_effective_tier(guild_id, actor_id=actor_id)
    return FEATURE_LIMITS[feature_code][tier]


def can_use_feature(guild_id, feature_code, actor_id=None) -> bool:
    """True bila feature_code dikenal.

    Kedua tier boleh memakai semua fitur di katalog — yang membedakan
    hanya kuotanya (lihat check_resource_quota). Feature tak dikenal -> False.
    """
    return feature_code in FEATURE_LIMITS


def check_resource_quota(guild_id, feature_code, current_count, actor_id=None) -> bool:
    """True bila masih boleh menambah satu resource fitur ini.

    Owner bot selalu True. Selain itu: current_count harus di bawah batas
    tier efektif. feature_code tak dikenal -> KeyError dari get_feature_limit.
    """
    if actor_id is not None and is_bot_owner(actor_id):
        return True
    return current_count < get_feature_limit(guild_id, feature_code, actor_id=actor_id)


def pesan_kuota_penuh(feature_code, limit) -> str:
    """Pesan saat kuota fitur habis (Bahasa Indonesia, tanpa harga/URL)."""
    nama = NAMA_FITUR.get(feature_code, feature_code)
    return (
        f"Batas {nama} untuk paket server ini sudah tercapai "
        f"({limit} {nama}). Hapus sebagian yang sudah tidak dipakai, "
        f"atau naikkan paket server ke VIP untuk batas yang lebih tinggi. "
        f"{TEKS_UPGRADE}"
    )


def _hitung_satu(sql: str, param) -> int:
    """Jalankan satu query COUNT; 0 bila tabel belum ada/query gagal."""
    try:
        with get_connection() as conn:
            baris = conn.execute(sql, (param,)).fetchone()
        return int(baris[0]) if baris and baris[0] is not None else 0
    except Exception:
        return 0


def hitung_pemakaian(guild_id) -> dict[str, int]:
    """Hitung pemakaian resource per fitur untuk satu guild dari SQLite.

    Perhatikan tipe guild_id per tabel: custom_commands/autoresponder/
    giveaways/dashboard_selfroles memakai INTEGER, dashboard_announcements
    memakai TEXT. Tabel yang belum ada dihitung 0.
    """
    gid_int = _ke_int_id(guild_id)
    if gid_int is None:
        gid_int = 0
    gid_str = str(guild_id)
    return {
        "custom_commands": _hitung_satu(
            "SELECT COUNT(*) FROM custom_commands WHERE guild_id = ?", gid_int
        ),
        "autoresponders": _hitung_satu(
            "SELECT COUNT(*) FROM autoresponder WHERE guild_id = ?", gid_int
        ),
        "giveaways_active": _hitung_satu(
            "SELECT COUNT(*) FROM giveaways WHERE guild_id = ? AND ended = 0", gid_int
        ),
        "selfrole_panels": _hitung_satu(
            "SELECT COUNT(DISTINCT message_id) FROM dashboard_selfroles WHERE guild_id = ?",
            gid_int,
        ),
        "announcements_active": _hitung_satu(
            "SELECT COUNT(*) FROM dashboard_announcements WHERE guild_id = ? AND enabled = 1",
            gid_str,
        ),
    }
