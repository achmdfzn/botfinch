"""Achievement — lencana otomatis dari aktivitas member.

Dipakai: cek_buka(conn, guild_id, user_id, stats) -> [(kode, nama)] yang BARU dibuka.
`stats` berisi sebagian/all dari: level, wealth (total_earned), streak, trivia,
invite, rep. Caller mengumumkan yang baru dibuka.
"""

import datetime

# (kode, nama, deskripsi, kunci_stat, ambang)
ACHIEVEMENTS: list[tuple[str, str, str, str, int]] = [
    ("level10", "🌟 Naik Daun", "Capai level 10", "level", 10),
    ("level25", "💫 Veteran", "Capai level 25", "level", 25),
    ("level50", "🔥 Legenda", "Capai level 50", "level", 50),
    ("kaya1", "💰 Kaya", "Total 1.000 koin diperoleh", "wealth", 1_000),
    ("kaya2", "💎 Sultan", "Total 50.000 koin diperoleh", "wealth", 50_000),
    ("streak7", "🔥 Konsisten", "Daily 7 hari beruntun", "streak", 7),
    ("streak30", "⚡ Tak Terhentikan", "Daily 30 hari beruntun", "streak", 30),
    ("trivia10", "🧠 Cerdas", "Menang trivia 10x", "trivia", 10),
    ("invite5", "📨 Promotor", "Undang 5 member", "invite", 5),
    ("rep10", "⭐ Disukai", "Terima 10 reputasi", "rep", 10),
    # --- hidden (Tahap 12): tidak ditampilkan sebelum dibuka ---
    ("hantu", "👻 Hantu", "Kirim pesan jam 00:00–04:00", "hantu", 1),
    ("sultan_diam", "🤑 Sultan Diam-Diam", "Saldo mencapai 100.000 koin", "sultan_diam", 100_000),
    ("kolektor", "🎒 Kolektor", "Punya 3 consumable berbeda", "kolektor", 3),
    ("sosialita", "💕 Sosialita", "Punya pasangan nikah", "sosialita", 1),
]

# Kode achievement tersembunyi — tampil "???" di /achievement sebelum dibuka.
HIDDEN: set[str] = {"hantu", "sultan_diam", "kolektor", "sosialita"}


def is_hidden(kode: str) -> bool:
    """True jika achievement tersembunyi."""
    return kode in HIDDEN


def hidden_terkunci(conn, guild_id: int, user_id: int) -> list[str]:
    """Kode hidden achievement yang BELUM dibuka user (untuk tampil "???" di /achievement)."""
    sudah = {
        r[0]
        for r in conn.execute(
            "SELECT kode FROM achievement WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        )
    }
    return [kode for kode, _n, _d, _k, _a in ACHIEVEMENTS if kode in HIDDEN and kode not in sudah]


def _sekarang_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def cek_buka(conn, guild_id: int, user_id: int, stats: dict) -> list[tuple[str, str]]:
    """Buka achievement yang syaratnya terpenuhi. Return [(kode, nama)] yang baru."""
    sudah = {
        r[0]
        for r in conn.execute(
            "SELECT kode FROM achievement WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        )
    }
    baru = []
    for kode, nama, _desk, kunci, ambang in ACHIEVEMENTS:
        if kode in sudah:
            continue
        if stats.get(kunci, 0) >= ambang:
            conn.execute(
                "INSERT INTO achievement (user_id, guild_id, kode, tgl) VALUES (?, ?, ?, ?)",
                (user_id, guild_id, kode, _sekarang_iso()),
            )
            baru.append((kode, nama))
    if baru:
        conn.commit()
    return baru


def daftar(conn, guild_id: int, user_id: int) -> list[tuple[str, str, str]]:
    """Semua achievement user: [(kode, nama, tgl)]."""
    kode_nama = {k: n for k, n, _d, _k, _a in ACHIEVEMENTS}
    return [
        (r[0], kode_nama.get(r[0], r[0]), r[1])
        for r in conn.execute(
            "SELECT kode, tgl FROM achievement WHERE user_id = ? AND guild_id = ? ORDER BY tgl",
            (user_id, guild_id),
        )
    ]


def embed_pengumuman(nama_user: str, dibuka: list[tuple[str, str]]) -> str:
    """Teks pengumuman achievement (dipakai caller untuk kirim ke channel)."""
    baris = "\n".join(f"🏅 **{nama}**" for _kode, nama in dibuka)
    return f"🎉 {nama_user} membuka achievement:\n{baris}"
