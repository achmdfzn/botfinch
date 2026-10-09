"""Season — reset XP/level berkala + hadiah koin untuk top 3.

- Tiap `SEASON_HARI` (default 90), top 3 XP dapat 1000/500/250 koin,
  lalu XP & level semua member di-reset ke awal season berikutnya.
- `/season` — info season berjalan + top 3 saat ini.
"""
import datetime
import logging

import discord
from discord.ext import commands, tasks

from src import config
from src.store import get_connection
from src.utils.embeds import base_embed

log = logging.getLogger("finch")

HADIAH_SEASON = (1000, 500, 250)


def _pastikan_state(conn, guild_id: int) -> tuple[int, str]:
    """Pastikan row season_state ada. Return (season, berakhir_iso)."""
    row = conn.execute(
        "SELECT season, berakhir FROM season_state WHERE guild_id = ?",
        (guild_id,),
    ).fetchone()
    if row:
        return row[0], row[1]
    berakhir = (
        discord.utils.utcnow() + datetime.timedelta(days=config.settings.season_hari)
    ).isoformat()
    conn.execute(
        "INSERT INTO season_state (guild_id, season, berakhir) VALUES (?, ?, ?)",
        (guild_id, 1, berakhir),
    )
    conn.commit()
    return 1, berakhir


class Season(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cek_season.start()

    def cog_unload(self):
        self.cek_season.cancel()

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Season mereset XP + bagi hadiah koin — ikut toggle `economy_enabled`."""
        if ctx.guild is None:
            return True
        from src.cogs.dashboard_sync import modul_aktif

        if modul_aktif(ctx.guild.id, "economy_enabled"):
            return True
        pesan = "Modul ekonomi dimatikan oleh admin server ini."
        try:
            if ctx.interaction is None:
                await ctx.send(pesan)
            elif ctx.interaction.response.is_done():
                await ctx.interaction.followup.send(pesan, ephemeral=True)
            else:
                await ctx.interaction.response.send_message(pesan, ephemeral=True)
        except discord.HTTPException:
            pass
        return False

    @tasks.loop(hours=1)
    async def cek_season(self):
        from src.cogs.dashboard_sync import modul_aktif

        now = discord.utils.utcnow()
        for guild in self.bot.guilds:
            if not modul_aktif(guild.id, "economy_enabled"):
                continue  # modul ekonomi dimatikan di server ini
            try:
                with get_connection() as conn:
                    season, berakhir_iso = _pastikan_state(conn, guild.id)
                try:
                    berakhir = datetime.datetime.fromisoformat(berakhir_iso)
                except ValueError:
                    continue
                if berakhir.tzinfo is None:
                    berakhir = berakhir.replace(tzinfo=datetime.timezone.utc)
                if now < berakhir:
                    continue
                await self._tutup_season(guild, season)
            except Exception:
                log.exception("Gagal proses season guild %s", guild.id)

    @cek_season.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    async def _tutup_season(self, guild: discord.Guild, season: int) -> None:
        # Satu transaksi atomik: kalau gagal di tengah, rollback → tidak ada double payout.
        # (bug lama: tambah_koin commit per panggilan sebelum season dimajukan)
        with get_connection() as conn:
            # S3: users.xp = sisa XP level berjalan, bukan total → urutkan level dulu
            top = conn.execute(
                "SELECT user_id FROM users WHERE guild_id = ?"
                " ORDER BY level DESC, xp DESC LIMIT 3",
                (guild.id,),
            ).fetchall()
            for i, (uid,) in enumerate(top):
                hadiah = HADIAH_SEASON[i]
                conn.execute(
                    "INSERT INTO economy (user_id, guild_id, balance, total_earned)"
                    " VALUES (?, ?, ?, ?)"
                    " ON CONFLICT(user_id, guild_id) DO UPDATE SET"
                    " balance = balance + ?, total_earned = total_earned + ?",
                    (uid, guild.id, hadiah, hadiah, hadiah, hadiah),
                )
            conn.execute(
                "UPDATE users SET xp = 0, level = 1 WHERE guild_id = ?", (guild.id,)
            )
            berakhir_baru = (
                discord.utils.utcnow()
                + datetime.timedelta(days=config.settings.season_hari)
            ).isoformat()
            conn.execute(
                "UPDATE season_state SET season = ?, berakhir = ? WHERE guild_id = ?",
                (season + 1, berakhir_baru, guild.id),
            )
            conn.commit()
        ch = guild.system_channel
        if ch is not None:
            medals = ["🥇", "🥈", "🥉"]
            baris = [
                f"{medals[i]} <@{uid}> — **{HADIAH_SEASON[i]}** 🪙"
                for i, (uid,) in enumerate(top)
            ]
            teks = "\n".join(baris) if baris else "Tidak ada peserta."
            try:
                await ch.send(
                    f"🏁 **Season {season} berakhir!**\n{teks}\n\n"
                    f"Season {season + 1} dimulai — XP di-reset, semangat lagi! 🚀"
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
            except Exception:
                pass
        log.info("Season %s guild %s ditutup.", season, guild.id)

    @commands.hybrid_command(name="season", description="Info season berjalan + top 3")
    async def season(self, ctx: commands.Context):
        """Info season: /season"""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        with get_connection() as conn:
            season, berakhir_iso = _pastikan_state(conn, ctx.guild.id)
            top = conn.execute(
                "SELECT user_id, level, xp FROM users WHERE guild_id = ?"
                " ORDER BY level DESC, xp DESC LIMIT 3",
                (ctx.guild.id,),
            ).fetchall()
        try:
            ts = int(datetime.datetime.fromisoformat(berakhir_iso).timestamp())
            berakhir_txt = f"<t:{ts}:F>"
        except ValueError:
            berakhir_txt = berakhir_iso
        embed = base_embed(f"🏁 Season {season}", f"Berakhir: {berakhir_txt}")
        # UI horizontal: top 3 kesamping
        medals = ["🥇", "🥈", "🥉"]
        if top:
            for i, (uid, lvl, xp) in enumerate(top):
                embed.add_field(
                    name=f"{medals[i]} Peringkat {i + 1}",
                    value=f"<@{uid}>\nLevel **{lvl}** ({xp} XP)\nHadiah: {HADIAH_SEASON[i]} 🪙",
                    inline=True,
                )
        else:
            embed.add_field(name="Top 3", value="Belum ada XP tercatat.", inline=True)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Season(bot))
