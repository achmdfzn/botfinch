"""Sistem UI Finch — embed konsisten ala bot modern.

Aturan emoji diet (2026-10-08):
- SATU warna brand untuk semua embed (teal Finch). Hijau/merah hanya untuk
  semantik sukses/gagal.
- Emoji MAKSIMAL 1 per judul embed. Nama field & isi value = teks polos.
  (Screen reader membacakan tiap emoji; hemat emoji = ramah HP & aksesibilitas.)
- Pengecualian: 🪙 sebagai simbol mata uang koin, ✅/❌ di judul sukses/gagal.
- Field horizontal (inline=True) untuk daftar; vertikal hanya untuk deskripsi panjang.
- Thumbnail = avatar user yang relevan; jangan pakai gambar eksternal.
- Tombol pakai label teks + style warna Discord, bukan emoji.
"""
import discord

BRAND = discord.Color(0x2EC4B6)  # teal Finch — satu-satunya warna brand

WARNA = {
    "utama": BRAND,
    "sukses": discord.Color.green(),
    "gagal": discord.Color.red(),
    # Kunci lama dipertahankan (backward compat) tapi semuanya = brand,
    # kecuali semantik sukses/gagal.
    "ekonomi": BRAND,
    "game": BRAND,
    "moderasi": BRAND,
    "info": BRAND,
    "event": BRAND,
    "sosial": BRAND,
}


def finch_embed(
    judul: str,
    deskripsi: str = "",
    warna: str = "utama",
    thumbnail: str | None = None,
) -> discord.Embed:
    """Embed standar Finch: warna brand + timestamp + footer + thumbnail opsional."""
    embed = discord.Embed(
        title=judul,
        description=deskripsi,
        color=WARNA.get(warna, BRAND),
        timestamp=discord.utils.utcnow(),
    )
    embed.set_footer(text="Finch")
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    return embed


def base_embed(title: str, description: str = "") -> discord.Embed:
    """Embed standar (backward compat) — kini memakai gaya Finch baru."""
    return finch_embed(title, description, warna="utama")


def error_embed(pesan: str) -> discord.Embed:
    """Embed error merah yang konsisten."""
    return finch_embed("❌ Gagal", pesan, warna="gagal")


def sukses_embed(judul: str, pesan: str = "") -> discord.Embed:
    """Embed sukses hijau yang konsisten."""
    return finch_embed(f"✅ {judul}", pesan, warna="sukses")


def get_progress_bar(current: int, total: int, length: int = 10) -> str:
    """Buat visual progress bar."""
    filled = max(0, min(length, int(length * current / max(total, 1))))
    return "█" * filled + "░" * (length - filled)


def level_embed(member: discord.Member, level: int, xp: int, next_xp: int) -> discord.Embed:
    """Embed level dengan progress bar (emoji diet: teks polos)."""
    bar = get_progress_bar(xp, next_xp)
    embed = finch_embed(
        f"Status Level — {member.display_name}",
        warna="info",
        thumbnail=member.avatar.url if member.avatar else None,
    )
    embed.add_field(name="Level", value=f"**{level}**", inline=True)
    embed.add_field(name="Total XP", value=f"**{xp} / {next_xp}**", inline=True)
    embed.add_field(
        name="Progress",
        value=f"`{bar}`",
        inline=False,
    )
    return embed


def koin_text(jumlah: int) -> str:
    """Format koin konsisten: '1.500 🪙' (🪙 = simbol mata uang, dikecualikan dari diet)."""
    return f"**{jumlah:,}** 🪙".replace(",", ".")


def _lebar_teks(s: str) -> int:
    """Lebar tampilan monospace: emoji/CJK dihitung 2 kolom."""
    import unicodedata

    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in s)


def _pad(teks: str, lebar: int) -> str:
    return teks + " " * max(0, lebar - _lebar_teks(teks))


def tabel(headers: list[str], rows: list[list[str]], limit: int = 10) -> str:
    """Tabel monospace untuk leaderboard/ranking — pengganti daftar emoji.

    Return string siap taruh di description/code block:
        ```\n<tabel>\n```
    """
    rows = rows[:limit]
    widths = [_lebar_teks(h) for h in headers]
    for r in rows:
        for i, cell in enumerate(r):
            if i < len(widths):
                widths[i] = max(widths[i], _lebar_teks(cell))
    garis = "  ".join(_pad(h, widths[i]) for i, h in enumerate(headers))
    pembatas = "  ".join("-" * widths[i] for i in range(len(headers)))
    baris = [garis, pembatas]
    for r in rows:
        baris.append("  ".join(_pad(r[i], widths[i]) if i < len(r) else "" for i in range(len(headers))))
    return "```\n" + "\n".join(baris) + "\n```"
