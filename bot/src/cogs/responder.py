"""Auto-responder — trigger teks → respons otomatis.

- `/respon-add <trigger> <respons>` (mod): tambah/ubah
- `/respon-del <trigger>` (mod): hapus
- `/respon-list`: lihat semua
Trigger dicocokkan case-insensitive sebagai substring pesan.
"""
import logging

import discord
from discord.ext import commands

from src import config
from src.store import get_connection
from src.utils.embeds import base_embed

log = logging.getLogger("finch")


async def _mirror_dashboard(guild_id: int, method: str, path: str, payload: dict | None = None) -> None:
    """Best-effort: samakan perubahan responder ke dashboard web bila dikonfigurasi."""
    from src import config as _cfg

    url = _cfg.settings.dashboard_url
    secret = _cfg.settings.dashboard_secret
    if not url or not secret:
        return
    try:
        import aiohttp

        async with aiohttp.ClientSession() as sesi:
            async with sesi.request(
                method,
                f"{url}/api/guilds/{guild_id}{path}",
                json=payload,
                headers={"Authorization": f"Bearer {secret}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status >= 400:
                    log.warning("responder: mirror dashboard gagal (HTTP %d)", resp.status)
    except Exception:
        log.warning("responder: mirror dashboard gagal", exc_info=True)


def cari_respons(
    daftar: list[tuple[str, str]], content: str
) -> str | None:
    """Kembalikan respons pertama yang trigger-nya terkandung di content.

    Case-insensitive, substring. Pure function — gampang dites.
    """
    c = (content or "").lower()
    for trigger, respons in daftar:
        if trigger and trigger.lower() in c:
            return respons
    return None


class Responder(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="respon-add", description="Tambah auto-responder (khusus mod)"
    )
    @commands.has_permissions(manage_messages=True)
    @discord.app_commands.describe(
        trigger="Kata pemicu (case-insensitive)",
        respons="Balasan otomatis bot",
    )
    async def respon_add(self, ctx: commands.Context, trigger: str, *, respons: str):
        """Tambah responder: /respon-add "ip mabar" "IP: 123.45..." """
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        trigger = trigger.strip().lower()
        if not trigger or not respons.strip():
            await ctx.send("❌ Trigger dan respons tidak boleh kosong.", ephemeral=True)
            return
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO autoresponder (guild_id, trigger, respons) VALUES (?, ?, ?) "
                "ON CONFLICT(guild_id, trigger) DO UPDATE SET respons = excluded.respons",
                (ctx.guild.id, trigger, respons.strip()),
            )
            conn.commit()
        await _mirror_dashboard(
            ctx.guild.id, "POST", "/autoresponses",
            {"trigger": trigger, "response": respons.strip()},
        )
        await ctx.send(
            f"✅ Responder ditambahkan: kalau ada yang mengetik **{trigger}** → bot membalas.",
            ephemeral=True,
        )

    @commands.hybrid_command(
        name="respon-del", description="Hapus auto-responder (khusus mod)"
    )
    @commands.has_permissions(manage_messages=True)
    @discord.app_commands.describe(trigger="Trigger yang mau dihapus")
    async def respon_del(self, ctx: commands.Context, trigger: str):
        """Hapus responder: /respon-del "ip mabar" """
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        with get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM autoresponder WHERE guild_id = ? AND trigger = ?",
                (ctx.guild.id, trigger.strip().lower()),
            )
            conn.commit()
            kena = cur.rowcount
        if kena:
            import urllib.parse

            await _mirror_dashboard(
                ctx.guild.id, "DELETE",
                f"/autoresponses?trigger={urllib.parse.quote(trigger.strip().lower())}",
            )
        await ctx.send(
            "✅ Responder dihapus." if kena else "❌ Trigger tidak ketemu.",
            ephemeral=True,
        )

    @commands.hybrid_command(
        name="respon-list", description="Lihat daftar auto-responder"
    )
    async def respon_list(self, ctx: commands.Context):
        """Lihat responder: /respon-list"""
        gid = ctx.guild.id if ctx.guild else 0
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT trigger, respons FROM autoresponder WHERE guild_id = ? ORDER BY trigger",
                (gid,),
            ).fetchall()
        if not rows:
            await ctx.send("📭 Belum ada auto-responder.", ephemeral=True)
            return
        embed = base_embed("💬 Auto-Responder", f"Total: **{len(rows)}**")
        for trigger, respons in rows[:25]:
            potong = respons if len(respons) <= 100 else respons[:97] + "..."
            embed.add_field(name=f"{trigger}", value=potong, inline=False)
        await ctx.send(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        # jangan ganggu command bot
        if message.content.startswith(config.settings.prefix):
            return
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT trigger, respons FROM autoresponder WHERE guild_id = ?",
                (message.guild.id,),
            ).fetchall()
        respons = cari_respons(rows, message.content)
        if respons:
            try:
                await message.channel.send(respons)
            except discord.HTTPException:
                log.warning("Gagal kirim auto-respons di %s", message.channel.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(Responder(bot))
