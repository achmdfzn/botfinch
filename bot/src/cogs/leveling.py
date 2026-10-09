"""Sistem Level & XP untuk member aktif.

- Setiap member dapat XP saat kirim pesan (dengan cooldown untuk cegah spamming XP).
- Rumus level up: XP yang dibutuhkan = level * 100 * 1.5 (atau rumus sederhana).
- Perintah: `/level` atau `!level` untuk cek level sendiri/member lain.
"""
import asyncio
import datetime
import time
from collections import defaultdict
import discord
from discord.ext import commands, tasks

from src import config
from src.store import get_connection
from src.utils.embeds import base_embed, level_embed
from src.utils.rankcard import make_rank_card
from src.utils.xp import tambah_xp, beri_role_reward


# (guild_id, user_id) -> timestamp pesan terakhir untuk cooldown XP
_xp_cooldown = defaultdict(float)
# (guild_id, user_id) -> timestamp reaksi terakhir untuk cooldown reaction XP
_reaction_cooldown = defaultdict(float)


def hitung_rank(conn, guild_id: int, level: int, xp: int) -> int:
    """Peringkat user di server: 1 + jumlah member yang level/xp-nya lebih tinggi."""
    row = conn.execute(
        "SELECT COUNT(*) FROM users "
        "WHERE guild_id = ? AND (level > ? OR (level = ? AND xp > ?))",
        (guild_id, level, level, xp),
    ).fetchone()
    return (row[0] if row else 0) + 1


class Leveling(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bersih_cooldown.start()

    def cog_unload(self):
        self.bersih_cooldown.cancel()

    @tasks.loop(minutes=30)
    async def bersih_cooldown(self):
        """Evict entry _xp_cooldown lebih tua dari 1 jam biar dict tidak tumbuh selamanya."""
        batas = time.time() - 3600
        for key in [k for k, v in _xp_cooldown.items() if v < batas]:
            del _xp_cooldown[key]

    @bersih_cooldown.before_loop
    async def _before_bersih(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Cek cooldown XP (per server, biar adil kalau bot di banyak server)
        gid = message.guild.id
        # Quest harian: hitung SEMUA pesan (di luar cooldown XP)
        try:
            from src.utils import quests as quest_utils

            with get_connection() as conn:
                quest_utils.tambah_pesan(conn, gid, message.author.id)
        except Exception:
            pass
        # Modul Leveling bisa dimatikan per-server via dashboard web
        from src.cogs.dashboard_sync import get_guild_setting, get_guild_setting_int

        if get_guild_setting(gid, "leveling_enabled", "1") != "1":
            return
        now = time.time()
        last_time = _xp_cooldown[(gid, message.author.id)]
        cooldown = config.settings.xp_cooldown_seconds
        if now - last_time < cooldown:
            return

        _xp_cooldown[(gid, message.author.id)] = now
        # Kecepatan XP per-server via dashboard (25–400%, default 100)
        rate = max(25, min(400, get_guild_setting_int(gid, "leveling_xp_rate", 100)))
        earned_xp = config.settings.xp_per_message * rate // 100
        # Weekend boost: XP 2x di Sabtu-Minggu WIB (kalau diaktifkan)
        wib = datetime.timezone(datetime.timedelta(hours=7))
        if config.settings.xp_weekend_boost:
            hari_wib = datetime.datetime.now(wib).weekday()
            if hari_wib >= 5:
                earned_xp *= 2
        # Bonus job Petarung: +15% XP chat (Tahap 12)
        try:
            from src.utils import job as jobmod

            with get_connection() as conn:
                bonus = jobmod.bonus_untuk(conn, gid, message.author.id)
            if bonus.get("bonus_xp"):
                earned_xp = int(earned_xp * (1 + bonus["bonus_xp"]))
        except Exception:
            pass
        # Efek consumable xpboost: XP 2x (Tahap 12)
        try:
            from src.utils import consumable as cons

            with get_connection() as conn:
                if cons.punya_aktif(conn, gid, message.author.id, "xpboost"):
                    earned_xp *= 2
        except Exception:
            pass

        # Update database SQLite via helper terpusat
        with get_connection() as conn:
            current_level, naik = tambah_xp(conn, gid, message.author.id, earned_xp)

        if naik:
            # Bonus koin economy tiap naik level
            bonus = max(0, config.settings.economy_level_bonus)
            if bonus:
                from src.utils import economy as eko

                with get_connection() as conn:
                    eko.tambah_koin(conn, gid, message.author.id, bonus)
            try:
                teks = (
                    f"🎉 Selamat {message.author.mention}, kamu naik ke **Level {current_level}**! 🚀"
                )
                if bonus:
                    teks += f" (+**{bonus}** 🪙 koin)"
                # Channel pengumuman khusus via dashboard; fallback ke channel asal
                announce_id = int(get_guild_setting(gid, "leveling_announce_channel_id", "") or 0)
                target = message.guild.get_channel(announce_id) if announce_id else None
                if target is None:
                    await message.channel.send(teks, delete_after=10)
                else:
                    await target.send(teks)
            except discord.Forbidden:
                pass
            # Achievement level (best effort)
            try:
                from src.utils import achievement as ach

                with get_connection() as conn:
                    dibuka = ach.cek_buka(
                        conn, gid, message.author.id, {"level": current_level}
                    )
                if dibuka:
                    await message.channel.send(
                        ach.embed_pengumuman(message.author.mention, dibuka)
                    )
            except (discord.Forbidden, discord.HTTPException):
                pass
            except Exception:
                pass

        # role reward: yang levelnya sudah memenuhi syarat tapi belum punya role → dikasih
        await beri_role_reward(message.author, current_level)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        """Reaction XP (Tahap 12): memberi reaksi dapat XP kecil, cooldown per user."""
        if user.bot or reaction.message.guild is None:
            return
        gid = reaction.message.guild.id
        now = time.time()
        key = (gid, user.id)
        if now - _reaction_cooldown[key] < config.settings.reaction_cooldown:
            return
        _reaction_cooldown[key] = now
        xp = config.settings.reaction_xp
        if xp <= 0:
            return
        try:
            with get_connection() as conn:
                tambah_xp(conn, gid, user.id, xp)
        except Exception:
            pass

    @commands.hybrid_command(name="level", description="Cek level dan XP kamu")
    async def level(self, ctx: commands.Context, member: discord.Member = None):
        """Cek level: !level / /level"""
        target = member or ctx.author
        if target.bot:
            await ctx.send("❌ Bot gak punya level.", ephemeral=True)
            return

        gid = ctx.guild.id if ctx.guild else 0
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT xp, level FROM users WHERE user_id = ? AND guild_id = ?",
                (target.id, gid),
            )
            row = cursor.fetchone()

        xp, lvl = row if row else (0, 1)
        next_xp = lvl * 150

        embed = level_embed(target, lvl, xp, next_xp)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="prestige", description="Reset ke level 1, dapat badge prestige (syarat level 30)")
    async def prestige(self, ctx: commands.Context):
        """Prestige: /prestige — reset level, naikkan prestige."""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        if ctx.author.bot:
            await ctx.send("❌ Bot tidak bisa prestige.", ephemeral=True)
            return
        with get_connection() as conn:
            row = conn.execute(
                "SELECT level, COALESCE(prestige, 0) FROM users WHERE user_id = ? AND guild_id = ?",
                (ctx.author.id, ctx.guild.id),
            ).fetchone()
        level = row[0] if row else 1
        if level < 30:
            await ctx.send(
                f"❌ Butuh level **30** untuk prestige (levelmu **{level}**).",
                ephemeral=True,
            )
            return
        with get_connection() as conn:
            conn.execute(
                "UPDATE users SET xp = 0, level = 1, prestige = prestige + 1"
                " WHERE user_id = ? AND guild_id = ?",
                (ctx.author.id, ctx.guild.id),
            )
            conn.commit()
            baru = conn.execute(
                "SELECT prestige FROM users WHERE user_id = ? AND guild_id = ?",
                (ctx.author.id, ctx.guild.id),
            ).fetchone()[0]
        await ctx.send(
            embed=base_embed(
                "♾️ Prestige!",
                f"Selamat {ctx.author.mention}! Kamu reset ke level 1 "
                f"dengan **Prestige {baru}**. Mulai lagi lebih kuat! 🚀",
            )
        )

    @commands.hybrid_command(name="rank", description="Kartu rank bergambar ala MEE6")
    async def rank(self, ctx: commands.Context, member: discord.Member = None):
        """Kartu rank: !rank / /rank [@user]"""
        target = member or ctx.author
        if target.bot:
            await ctx.send("❌ Bot gak punya rank.", ephemeral=True)
            return

        await ctx.defer()
        gid = ctx.guild.id if ctx.guild else 0
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT xp, level FROM users WHERE user_id = ? AND guild_id = ?",
                (target.id, gid),
            )
            row = cursor.fetchone()
            xp, lvl = row if row else (0, 1)
            rank = hitung_rank(conn, gid, lvl, xp)
        next_xp = lvl * 150

        try:
            avatar_bytes = await target.display_avatar.read()
        except discord.HTTPException:
            avatar_bytes = None

        # generate gambar di thread terpisah biar event loop tidak macet
        loop = asyncio.get_running_loop()
        buf = await loop.run_in_executor(
            None, make_rank_card, avatar_bytes, target.display_name, lvl, xp, next_xp, rank
        )
        await ctx.send(file=discord.File(buf, filename="rank.png"))


async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))
