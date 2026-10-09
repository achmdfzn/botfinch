"""Generator kartu rank (PNG) ala MEE6.

`make_rank_card()` murni image processing (tidak butuh discord.py) sehingga
gampang di-unit-test. Font pakai bawaan Pillow (Aileron, scalable) agar
jalan di Windows maupun Linux tanpa install font tambahan.
"""
import io

from PIL import Image, ImageDraw, ImageFont

W, H = 800, 250
BG = (43, 45, 49)          # abu-abu gelap ala Discord
ACCENT = (88, 101, 242)    # blurple
BAR_BG = (64, 68, 75)
TEXT = (255, 255, 255)
SUBTEXT = (185, 187, 190)
AVATAR_SIZE = 150


def _font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow lama: tidak support argumen size
        return ImageFont.load_default()


def _potong_nama(draw: ImageDraw.ImageDraw, nama: str, font, max_w: int) -> str:
    """Potong nama kepanjangan biar muat di kartu."""
    if draw.textlength(nama, font=font) <= max_w:
        return nama
    while nama and draw.textlength(nama + "…", font=font) > max_w:
        nama = nama[:-1]
    return nama + "…"


def _avatar_bulat(avatar_bytes: bytes | None) -> Image.Image:
    """Avatar 150x150 lingkaran; placeholder abu-abu kalau tidak ada."""
    size = (AVATAR_SIZE, AVATAR_SIZE)
    if avatar_bytes:
        try:
            av = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize(size)
        except Exception:
            av = None
    else:
        av = None
    if av is None:
        av = Image.new("RGBA", size, (90, 95, 105, 255))
        d = ImageDraw.Draw(av)
        f = _font(64)
        t = "?"
        d.text(((size[0] - d.textlength(t, font=f)) / 2, 38), t, font=f, fill=TEXT)
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size[0], size[1]], fill=255)
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.paste(av, (0, 0), mask)
    return out


def make_rank_card(
    avatar_bytes: bytes | None,
    display_name: str,
    level: int,
    xp: int,
    next_xp: int,
    rank: int,
) -> io.BytesIO:
    """Buat kartu rank 800x250 PNG. Return BytesIO siap dikirim sebagai discord.File."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # kartu rounded
    draw.rounded_rectangle([0, 0, W - 1, H - 1], radius=28, fill=BG)
    # garis aksen kiri
    draw.rounded_rectangle([0, 0, 14, H - 1], radius=7, fill=ACCENT)

    # avatar
    img.paste(_avatar_bulat(avatar_bytes), (44, 50), _avatar_bulat(avatar_bytes))

    x0 = 240
    # nama
    f_nama = _font(46)
    nama = _potong_nama(draw, display_name, f_nama, max_w=380)
    draw.text((x0, 42), nama, font=f_nama, fill=TEXT)

    # badge LEVEL
    f_badge = _font(26)
    badge_txt = f"LEVEL {level}"
    bw = int(draw.textlength(badge_txt, font=f_badge)) + 28
    draw.rounded_rectangle([x0, 108, x0 + bw, 142], radius=17, fill=ACCENT)
    draw.text((x0 + 14, 110), badge_txt, font=f_badge, fill=TEXT)

    # RANK kanan atas
    f_rank = _font(30)
    rank_txt = f"RANK #{rank}"
    rw = draw.textlength(rank_txt, font=f_rank)
    draw.text((W - 30 - rw, 48), rank_txt, font=f_rank, fill=SUBTEXT)

    # progress bar
    bar_x, bar_y, bar_w, bar_h = x0, 168, 500, 30
    draw.rounded_rectangle(
        [bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=15, fill=BAR_BG
    )
    progress = min(1.0, max(0.0, xp / max(next_xp, 1)))
    fill_w = int(bar_w * progress)
    if fill_w > 0:
        draw.rounded_rectangle(
            [bar_x, bar_y, bar_x + max(fill_w, bar_h), bar_y + bar_h],
            radius=15,
            fill=ACCENT,
        )

    # teks XP
    f_xp = _font(24)
    draw.text((x0, 208), f"{xp} / {next_xp} XP", font=f_xp, fill=SUBTEXT)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def make_welcome_card(
    avatar_bytes: bytes | None,
    display_name: str,
    guild_name: str,
    member_count: int,
) -> io.BytesIO:
    """Kartu selamat datang 800x320 PNG. Return BytesIO siap dikirim."""
    W2, H2 = 800, 320
    img = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([0, 0, W2 - 1, H2 - 1], radius=28, fill=BG)
    # strip aksen atas
    draw.rounded_rectangle([0, 0, W2 - 1, 16], radius=8, fill=ACCENT)

    # avatar tengah
    av = _avatar_bulat(avatar_bytes).resize((150, 150))
    img.paste(av, ((W2 - 150) // 2, 36), av)

    def tengah(teks: str, y: int, font, fill=TEXT):
        draw.text(((W2 - draw.textlength(teks, font=font)) / 2, y), teks, font=font, fill=fill)

    tengah("SELAMAT DATANG", 200, _font(28), fill=ACCENT)
    nama = _potong_nama(draw, display_name, _font(52), max_w=700)
    tengah(nama, 228, _font(52))
    tengah(
        f"Member ke-{member_count} di {guild_name}",
        288,
        _font(24),
        fill=SUBTEXT,
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
