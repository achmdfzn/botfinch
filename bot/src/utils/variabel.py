"""Substitusi variabel template di pesan otomatis bot.

Variabel yang didukung:
- {user}         -> mention user (mis. <@123>)
- {server}       -> nama server
- {member_count} -> jumlah member server
- {channel}      -> mention channel

Dipakai auto-responder, pesan welcome/goodbye, dan pengumuman terjadwal.
Pure function — gampang dites.
"""


def _bersihkan_mass_mention(nilai: str) -> str:
    """Netralkan @everyone/@here di NILAI substitusi (nama server, dsb.).

    Template ditulis admin/mod dan dikirim dengan allowed_mentions yang
    mengizinkan @everyone — itu disengaja. Tapi nilai yang disubstitusi
    (mis. nama server) bisa dikendalikan pihak lain; tanpa ini, server
    bernama "@everyone" akan memicu mass-ping lewat responder/welcome/
    goodbye. Zero-width space memutus parsing mention tapi teks tetap
    terbaca normal.
    """
    return nilai.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")


def substitusi_variabel(
    teks: str | None,
    *,
    user: str = "",
    server: str = "",
    member_count: int | None = None,
    channel: str = "",
) -> str:
    """Ganti placeholder {user}/{server}/{member_count}/{channel} di teks."""
    hasil = teks or ""
    hasil = hasil.replace("{user}", _bersihkan_mass_mention(str(user or "")))
    hasil = hasil.replace("{server}", _bersihkan_mass_mention(str(server or "")))
    hasil = hasil.replace("{channel}", _bersihkan_mass_mention(str(channel or "")))
    if member_count is not None:
        hasil = hasil.replace("{member_count}", str(member_count))
    return hasil
