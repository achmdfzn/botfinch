"""Custom commands — command buatan admin server.

`/cc-tambah <trigger> <respons>` (Manage Guild) → user mengetik
`!<trigger>` dan bot membalas respons yang tersimpan.

- Trigger: huruf kecil/angka/`-`/`_`, 2–32 karakter, maks 50 per server.
- Respons mendukung variabel: {user} {server} {member_count} {channel}.
- @everyone/@here di respons disanitasi (zero-width space) + mention
  dibatasi eksplisit saat kirim — anti mass-ping.
- Hormat toggle dashboard `customcmd_enabled`.
"""
import re

import discord
from discord.ext import commands

from src import config
from src.store import get_connection
from src.utils.toggle import cek_toggle

POLA_TRIGGER = re.compile(r"^[a-z0-9_-]{2,32}$")
RESPON_MAKS = 1000
JUMLAH_MAKS = 50
ZWSP = "\u200b"  # zero-width space untuk memutus mention @everyone/@here
TEAL = 0x2EC4B6

# Variabel yang didukung di respons: nama -> fungsi(message)
def _variabel_tersedia():
    return {
        "user": lambda m: m.author.mention,
        "server": lambda m: m.guild.name,
        "member_count": lambda m: str(m.guild.member_count),
        "channel": lambda m: m.channel.mention,
    }


def validasi_trigger(trigger: str) -> tuple[bool, str]:
    """Cek format trigger. Return (ok, pesan_error). Pure — gampang dites."""
    if not trigger:
        return False, "❌ Trigger tidak boleh kosong."
    if not POLA_TRIGGER.match(trigger):
        return (
            False,
            "❌ Trigger harus 2–32 karakter: huruf kecil, angka, `-`, atau `_` saja.",
        )
    return True, ""


def tabrakan_command(bot: commands.Bot, trigger: str) -> bool:
    """True bila trigger menabrak command bawaan (prefix maupun slash)."""
    if trigger in bot.all_commands:
        return True
    try:
        for cmd in bot.tree.walk_commands():
            if getattr(cmd, "name", None) == trigger:
                return True
    except Exception:
        pass
    return False


def sanitasi_mention(teks: str) -> str:
    """Putus @everyone/@here dengan zero-width space biar tidak nge-ping.

    Case-insensitive; varian tak dikenal (mis. @EVERYONE aneh) ikut ditangani
    regex yang sama.
    """
    return re.sub(
        r"@(everyone|here)",
        r"@" + ZWSP + r"\1",
        teks,
        flags=re.IGNORECASE,
    )


def substitusi_variabel(respons: str, message: discord.Message) -> str:
    """Ganti variabel yang dikenal; yang tak dikenal dibiarkan apa adanya."""
    for nama, ambil in _variabel_tersedia().items():
        respons = respons.replace("{" + nama + "}", ambil(message))
    return respons


def _mention_aman(message: discord.Message) -> discord.AllowedMentions:
    """Mention hanya ke pengirim; everyone/roles selalu mati."""
    return discord.AllowedMentions(
        users=[message.author], everyone=False, roles=False
    )


class CustomCmd(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        return await cek_toggle(
            ctx,
            "customcmd_enabled",
            "❌ Modul custom command dimatikan via dashboard.",
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        from src.cogs.dashboard_sync import modul_aktif

        if not modul_aktif(message.guild.id, "customcmd_enabled"):
            return

        prefix = config.settings.prefix
        teks = message.content.strip().lower()
        if not teks.startswith(prefix):
            return
        sisa = teks[len(prefix):]
        trigger = sisa.split(" ", 1)[0]
        if not trigger or not POLA_TRIGGER.match(trigger):
            return
        # Cocok tepat: konten == prefix+trigger atau diawali prefix+trigger + spasi.
        with get_connection() as conn:
            row = conn.execute(
                "SELECT response FROM custom_commands WHERE guild_id = ? AND trigger = ?",
                (message.guild.id, trigger),
            ).fetchone()
        if not row:
            return
        try:
            await message.channel.send(
                substitusi_variabel(row[0], message),
                allowed_mentions=_mention_aman(message),
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.hybrid_command(
        name="cc-tambah", description="Tambah custom command (Manage Guild)"
    )
    @discord.app_commands.describe(
        trigger="Nama pemicu (huruf kecil, angka, -, _; 2–32 karakter)",
        respons="Teks balasan (maks 1000 karakter; mendukung {user} {server} {member_count} {channel})",
    )
    @commands.has_permissions(manage_guild=True)
    async def cc_tambah(self, ctx: commands.Context, trigger: str, *, respons: str):
        """Daftarkan custom command baru: !cc-tambah sapaan Halo, {user}!"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        trigger = trigger.strip().lower()
        ok, err = validasi_trigger(trigger)
        if not ok:
            await ctx.send(err, ephemeral=True)
            return
        if not respons or not respons.strip():
            await ctx.send("❌ Respons tidak boleh kosong.", ephemeral=True)
            return
        if len(respons) > RESPON_MAKS:
            await ctx.send(
                f"❌ Respons maksimal {RESPON_MAKS} karakter.", ephemeral=True
            )
            return
        if tabrakan_command(self.bot, trigger):
            await ctx.send(
                f"❌ Trigger `{trigger}` menabrak nama command bawaan bot. "
                "Pilih nama lain.",
                ephemeral=True,
            )
            return
        gid = ctx.guild.id
        with get_connection() as conn:
            # Kunci tulis duluan (IMMEDIATE): cegah dua /cc-tambah paralel
            # sama-sama lolos SELECT COUNT lalu dua-duanya INSERT sehingga
            # batas 50 terlampaui (check-then-act race).
            conn.execute("BEGIN IMMEDIATE")
            sudah_ada = conn.execute(
                "SELECT 1 FROM custom_commands WHERE guild_id = ? AND trigger = ?",
                (gid, trigger),
            ).fetchone()
            if not sudah_ada:
                jumlah = conn.execute(
                    "SELECT COUNT(*) FROM custom_commands WHERE guild_id = ?",
                    (gid,),
                ).fetchone()[0]
                if jumlah >= JUMLAH_MAKS:
                    await ctx.send(
                        f"❌ Batas {JUMLAH_MAKS} custom command per server tercapai. "
                        "Hapus yang lama dulu dengan `/cc-hapus`.",
                        ephemeral=True,
                    )
                    return
            conn.execute(
                "INSERT INTO custom_commands (guild_id, trigger, response, author_id) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(guild_id, trigger) DO UPDATE SET "
                "response=excluded.response, author_id=excluded.author_id, "
                "created_at=CURRENT_TIMESTAMP",
                (gid, trigger, sanitasi_mention(respons.strip()), ctx.author.id),
            )
            conn.commit()
        aksi = "diperbarui" if sudah_ada else "ditambahkan"
        await ctx.send(
            f"✅ Custom command `!{trigger}` {aksi}. "
            f"Ketik `!{trigger}` untuk memakainya.",
            ephemeral=True,
        )

    @commands.hybrid_command(
        name="cc-hapus", description="Hapus custom command (Manage Guild)"
    )
    @discord.app_commands.describe(trigger="Nama pemicu yang mau dihapus")
    @commands.has_permissions(manage_guild=True)
    async def cc_hapus(self, ctx: commands.Context, trigger: str):
        """Hapus custom command: /cc-hapus sapaan"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        trigger = trigger.strip().lower()
        with get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM custom_commands WHERE guild_id = ? AND trigger = ?",
                (ctx.guild.id, trigger),
            )
            conn.commit()
            terhapus = cur.rowcount > 0
        if terhapus:
            await ctx.send(f"🗑️ Custom command `!{trigger}` dihapus.", ephemeral=True)
        else:
            await ctx.send(
                f"❌ Tidak ada custom command `!{trigger}`.", ephemeral=True
            )

    @commands.hybrid_command(
        name="cc-list", description="Lihat daftar custom command server ini"
    )
    async def cc_list(self, ctx: commands.Context):
        """Daftar semua custom command server ini."""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT trigger FROM custom_commands WHERE guild_id = ? "
                "ORDER BY trigger",
                (ctx.guild.id,),
            ).fetchall()
        if not rows:
            await ctx.send(
                "Belum ada custom command di server ini. "
                "Admin bisa menambah via `/cc-tambah`.",
                ephemeral=True,
            )
            return
        daftar = "\n".join(f"• `!{r[0]}`" for r in rows)
        embed = discord.Embed(
            title=f"📝 Custom command ({len(rows)}/{JUMLAH_MAKS})",
            description=daftar,
            color=TEAL,
        )
        await ctx.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CustomCmd(bot))
