"""Helper bersama untuk fitur 'rutin' (poll rutin, pengingat rutin, ...).

Item rutin dikirim berulang oleh task loop. Kalau channel-nya dihapus,
setiap percobaan kirim gagal — tanpa batas, loop akan me-retry selamanya.
Helper ini menghitung kegagalan beruntun per item; setelah batas tercapai
item dianggap mati permanen dan boleh dihapus dari DB.
"""


def catat_gagal_rutin(gagal: dict[int, int], rid: int, batas: int = 20) -> bool:
    """Catat satu kegagalan kirim item rutin `rid` ke dict `gagal`.

    Return True bila kegagalan beruntun sudah mencapai `batas`
    (default 20 — dengan loop 30 menit ≈ 10 jam gagal terus, channel
    pasti sudah dihapus permanen). Panggil `gagal.pop(rid, None)`
    setelah kirim sukses agar hitungan di-reset.
    """
    n = gagal.get(rid, 0) + 1
    gagal[rid] = n
    return n >= batas
