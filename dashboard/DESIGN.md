# DESIGN.md — Dashboard Web Finch

Arah visual (R-37 Anti-Slop). Ditulis dari brief pemilik: "seperti dashboard bot Discord yang lain",
login Discord, tombol invite bot, untuk bot publik multi-server.

## Identitas

Finch: bot Discord yang playful tapi rapi. Maskot burung finch (avatar sudah ada:
`../discord-bot-finch/branding/finch-avatar.png`). Bahasa: Indonesia.

## Palet

- Aksen: teal `#2EC4B6` (satu-satunya warna brand, sama dengan warna embed bot).
- Netral: zinc/slate gelap untuk permukaan, teks zinc-100/zinc-400.
- Semantik: hijau untuk sukses/aktif, merah untuk gagal/nonaktif (sama dengan bot).
- Maksimal 2 warna inti + 1 aksen (R-29). Tanpa gradient (R-01: tanpa tujuan hierarki).

## Tema

Dark-first. Alasan satu baris (R-21, R-31): dashboard admin di ekosistem Discord yang
dark-first, target user (admin server) terbiasa dengan Discord/MEE6 yang gelap.

## Tipografi

Inter (sans). Alasan satu baris (R-06, R-31): keterbacaan tinggi untuk UI admin yang
padat data, nada geometris-humanis yang cocok dengan Discord.

## Layout

Pola panel admin dashboard bot (MEE6/Dyno): sidebar navigasi kiri, konten kanan berupa
kartu modul dengan toggle. Alasan satu baris (R-31): target user sudah familiar dengan
pola ini dari bot lain, jadi tidak perlu belajar ulang.

- Landing: hero satu focal point (satu H1 + dua CTA spesifik), daftar modul nyata bot,
  statistik hanya dari data snapshot bot asli (R-17), tanpa testimoni (R-18), tanpa FAQ generik (R-28).
- Radius: rounded-xl konsisten untuk kartu, rounded-lg untuk tombol (R-11: tidak semua pill).
- Tanpa bento grid, tanpa terminal palsu, tanpa badge kapsul AI (R-05, R-09).

## Motion

Dial: ENERGY 2 / RHYTHM 2 / MOTION 1.
Alasan: admin tool dipakai tiap hari, motion hanya hover state agar tidak mengganggu (R-19).

## Motif identitas (R-20)

Satu aksen teal yang dipakai hemat di momen kunci: CTA utama, toggle aktif, indikator
server terpilih. Maskot finch sebagai logo teks+avatar.

## Design Read

"Dashboard admin web untuk admin server Discord, gaya panel admin bot Discord yang
familiar, identitas Finch (teal, playful tapi rapi), dial ENERGY 2 / RHYTHM 2 / MOTION 1."
