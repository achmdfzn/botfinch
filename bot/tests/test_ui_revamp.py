"""Regression test revamp UI (emoji diet, 2026-10-08)."""
import discord

from src.utils.embeds import BRAND, WARNA, base_embed, finch_embed, sukses_embed, tabel


def test_brand_color_satu_untuk_semua():
    for kunci in ("utama", "ekonomi", "game", "moderasi", "info", "event", "sosial"):
        assert WARNA[kunci] == BRAND
        assert finch_embed("x", warna=kunci).color == BRAND


def test_semantik_sukses_tetap_hijau():
    assert finch_embed("x", warna="sukses").color == discord.Color.green()
    assert finch_embed("x", warna="gagal").color == discord.Color.red()


def test_footer_minimalis():
    assert base_embed("Judul").footer.text == "Finch"


def test_sukses_embed_satu_emoji_di_judul():
    e = sukses_embed("Berhasil")
    assert e.title == "✅ Berhasil"
    assert e.color == discord.Color.green()


def test_tabel_rata_dengan_emoji():
    from src.utils.embeds import _lebar_teks

    t = tabel(["#", "Member", "Koin"], [["1", "Budi", "1.500 🪙"], ["2", "Siti", "200 🪙"]])
    data = [b for b in t.split("\n") if b[:1] in ("1", "2")]
    assert len(data) == 2
    assert _lebar_teks(data[0]) == _lebar_teks(data[1])


def test_tabel_kolom_kurang_dari_header_tidak_crash():
    t = tabel(["A", "B"], [["x"]])
    assert "x" in t


def test_tabel_limit():
    rows = [[str(i), "n", "v"] for i in range(30)]
    t = tabel(["#", "N", "V"], rows)
    assert t.count("\n") < 20  # header + pembatas + 10 baris + code fence
