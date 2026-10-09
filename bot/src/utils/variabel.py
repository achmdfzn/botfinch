"""Substitusi variabel template di pesan otomatis bot.

Variabel yang didukung:
- {user}         -> mention user (mis. <@123>)
- {server}       -> nama server
- {member_count} -> jumlah member server
- {channel}      -> mention channel

Dipakai auto-responder, pesan welcome/goodbye, dan pengumuman terjadwal.
Pure function — gampang dites.
"""


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
    hasil = hasil.replace("{user}", str(user or ""))
    hasil = hasil.replace("{server}", str(server or ""))
    hasil = hasil.replace("{channel}", str(channel or ""))
    if member_count is not None:
        hasil = hasil.replace("{member_count}", str(member_count))
    return hasil
