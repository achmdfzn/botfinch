"""Helper teks — dipakai minigames & turnamen (dulu duplikat di dua file)."""
import random


def acak_huruf(kata: str, rng=None) -> str:
    """Acak huruf sebuah kata; hasil dijamin != kata asli (huruf tetap sama).

    Dipakai game susun-kata di minigames (acak_kata) dan turnamen.
    """
    rng = rng or random
    huruf = list(kata)
    for _ in range(50):
        rng.shuffle(huruf)
        hasil = "".join(huruf)
        if hasil.lower() != kata.lower():
            return hasil
    # fallback: tukar dua huruf pertama yang berbeda
    for i in range(len(huruf)):
        for j in range(i + 1, len(huruf)):
            if huruf[i].lower() != huruf[j].lower():
                huruf[i], huruf[j] = huruf[j], huruf[i]
                return "".join(huruf)
    return kata
