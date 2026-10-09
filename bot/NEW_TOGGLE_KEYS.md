# Key Toggle Baru — untuk di-wiring ke Dashboard

Key-key ini dipakai via `modul_aktif(guild_id, key)` / helper `cek_toggle()`.
Konvensi: `*_enabled` bernilai `"1"`/`"0"`, default `"1"` (modul jalan bila dashboard
belum pernah mengirim key tersebut).

| Key                  | Default | Fitur (cog)                                      | Deskripsi singkat                                              |
|----------------------|---------|--------------------------------------------------|----------------------------------------------------------------|
| `customcmd_enabled`  | `"1"`   | Custom Commands (`src/cogs/customcmd.py`)        | Perintah teks buatan user (`/cc-tambah`, `/cc-hapus`, `/cc-list`) |
| `slowmode_enabled`   | `"1"`   | Slowmode manual (`src/cogs/slowmode.py`)         | `/slowmode` & `/slowmode-info` per channel                     |
| `msglog_enabled`     | `"1"`   | Message logging (`src/cogs/moderation.py`)       | Log pesan diedit/dihapus/bulk-delete ke mod-log                |
| `autopublish_enabled`| `"1"`   | Auto-publish (`src/cogs/autopublish.py`)         | Auto-publish pesan di announcement channel                     |

Catatan:
- Anti-hoist memakai key lama `automod_enabled` (tidak ada key baru).
- Syarat role giveaway memakai key lama `giveaway_enabled` (fitur sudah ada sebelumnya).
