"""Auto-responder — trigger teks → respons otomatis.

- `/respon-add <trigger> <respons>` (mod): tambah/ubah
- `/respon-del <trigger>` (mod): hapus
- `/respon-list`: lihat semua
Trigger dicocokkan case-insensitive sebagai substring pesan.
Respons mendukung variabel: {user} (mention pengirim), {server} (nama server),
{member_count} (jumlah member), {channel} (mention channel asal).
Bisa dimatikan per-server via dashboard: toggle `responder_enabled` ("1"/"0").
"""
import logging

import discord
from discord.ext import commands

from src import config
from src.bot import MENTIONS_PENGUMUMAN
from src.store import get_connection
from src.utils import premium
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
        respons="Balasan otomatis bot (bisa pakai {user} {server} {member_count} {channel})",
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
        # Batas panjang: selaras kontrak dashboard (trigger ≤100, respons ≤500
        # setelah sinkron) dan di bawah limit pesan Discord 2000 — respons
        # lebih panjang pasti gagal terkirim (HTTP 400) tapi user sudah
        # diberi tahu "berhasil" tanpa validasi ini.
        if len(trigger) > 100:
            await ctx.send("❌ Trigger kepanjangan (maks 100 karakter).", ephemeral=True)
            return
        if len(respons.strip()) > 1500:
            await ctx.send("❌ Respons kepanjangan (maks 1500 karakter).", ephemeral=True)
            return
        with get_connection() as conn:
            # Pola sama seperti customcmd: kunci tulis duluan, lalu gate
            # kuota premium HANYA untuk trigger baru (update trigger lama
            # tidak digate). Kuota penuh -> batal tanpa insert & tanpa
            # mirror dashboard.
            conn.execute("BEGIN IMMEDIATE")
            sudah_ada = conn.execute(
                "SELECT 1 FROM autoresponder WHERE guild_id = ? AND trigger = ?",
                (ctx.guild.id, trigger),
            ).fetchone()
            if not sudah_ada:
                jumlah = conn.execute(
                    "SELECT COUNT(*) FROM autoresponder WHERE guild_id = ?",
                    (ctx.guild.id,),
                ).fetchone()[0]
                if not premium.check_resource_quota(
                    ctx.guild.id, "autoresponders", jumlah, actor_id=ctx.author.id
                ):
                    limit = premium.get_feature_limit(
                        ctx.guild.id, "autoresponders", actor_id=ctx.author.id
                    )
                    await ctx.send(
                        premium.pesan_kuota_penuh("autoresponders", limit),
                        ephemeral=True,
                    )
                    return
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
        from src.cogs.dashboard_sync import modul_aktif
        from src.utils.variabel import substitusi_variabel

        # Modul auto-responder bisa dimatikan per-server via dashboard web
        if not modul_aktif(message.guild.id, "responder_enabled"):
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
            # Variabel template: {user}, {server}, {member_count}, {channel}
            respons = substitusi_variabel(
                respons,
                user=message.author.mention,
                server=message.guild.name,
                member_count=message.guild.member_count or 0,
                channel=message.channel.mention,
            )
            try:
                # Respons ditulis mod -> boleh @everyone.
                await message.channel.send(respons, allowed_mentions=MENTIONS_PENGUMUMAN)
            except discord.HTTPException:
                log.warning("Gagal kirim auto-respons di %s", message.channel.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(Responder(bot))
