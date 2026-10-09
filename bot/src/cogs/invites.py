"""Invite tracker — lacak siapa undang siapa."""
import logging
import discord
from discord.ext import commands
from src import config
from src.store import get_connection
from src.utils import achievement as ach
from src.utils import economy as eko
from src.utils.embeds import base_embed

log = logging.getLogger("finch")

# guild_id -> {code: uses}
_cache: dict[int, dict[str, int]] = {}


class Invites(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        for g in self.bot.guilds:
            try:
                invs = await g.invites()
                _cache[g.id] = {inv.code: inv.uses for inv in invs}
            except Exception:
                # Tanpa izin / API error: cache kosong, tracking best-effort.
                _cache[g.id] = {}

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        if invite.guild:
            _cache.setdefault(invite.guild.id, {})[invite.code] = invite.uses

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        if invite.guild:
            _cache.get(invite.guild.id, {}).pop(invite.code, None)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not member.guild.me.guild_permissions.manage_guild:
            log.warning("Bot tidak punya Manage Server, tidak bisa tracking invite di %s", member.guild.name)
            return
        
        guild = member.guild
        before = _cache.get(guild.id, {}).copy()
        try:
            invs = await guild.invites()
            after = {inv.code: inv.uses for inv in invs}
        except discord.Forbidden:
            return
        # cari code yang uses bertambah
        candidates = []
        for code, uses in after.items():
            if uses > before.get(code, 0):
                candidates.append(code)
        
        used_code = None
        inviter_id = None
        
        # Hanya catat jika tepat satu code yang naik. 
        # Jika > 1 (wave join saat bot offline), kita tidak tahu mana yang benar.
        if len(candidates) == 1:
            used_code = candidates[0]
            # cari invite object untuk inviter
            for inv in invs:
                if inv.code == used_code:
                    if inv.inviter:
                        inviter_id = inv.inviter.id
                    break
        
        # update cache
        _cache[guild.id] = after
        # simpan log — deteksi rejoin (anti farm koin keluar-masuk)
        rejoin = False
        try:
            with get_connection() as conn:
                rejoin = conn.execute(
                    "SELECT 1 FROM invites_log WHERE user_id = ? AND guild_id = ?",
                    (member.id, guild.id),
                ).fetchone() is not None
                conn.execute(
                    "INSERT OR REPLACE INTO invites_log (user_id, guild_id, inviter_id, code) VALUES (?, ?, ?, ?)",
                    (member.id, guild.id, inviter_id, used_code),
                )
                conn.commit()
        except Exception:
            log.exception("Gagal simpan invites_log")

        # reward inviter: koin + cek achievement invite — hanya join PERTAMA
        if inviter_id and not rejoin:
            dibuka = []
            try:
                from src.cogs.dashboard_sync import modul_aktif

                with get_connection() as conn:
                    koin = config.settings.invite_koin
                    # Hormat toggle ekonomi: achievement tetap dicek, koin tidak dibayar.
                    if koin > 0 and modul_aktif(guild.id, "economy_enabled"):
                        eko.tambah_koin(conn, guild.id, inviter_id, koin)
                    jumlah = conn.execute(
                        "SELECT COUNT(*) FROM invites_log WHERE inviter_id = ? AND guild_id = ?",
                        (inviter_id, guild.id),
                    ).fetchone()[0]
                    dibuka = ach.cek_buka(conn, guild.id, inviter_id, {"invite": jumlah})
            except Exception:
                log.exception("Gagal kasih reward invite ke %s", inviter_id)
            if dibuka:
                channel = guild.system_channel
                if channel is not None:
                    try:
                        await channel.send(
                            ach.embed_pengumuman(f"<@{inviter_id}>", dibuka)
                        )
                    except discord.HTTPException:
                        pass

    @commands.hybrid_command(name="invites", description="Cek jumlah invite kamu")
    async def invites(self, ctx: commands.Context, member: discord.Member = None):
        target = member or ctx.author
        gid = ctx.guild.id if ctx.guild else 0
        with get_connection() as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM invites_log WHERE guild_id = ? AND inviter_id = ?", (gid, target.id)).fetchone()
            row = conn.execute("SELECT inviter_id, joined_at FROM invites_log WHERE user_id = ? AND guild_id = ?", (target.id, gid)).fetchone()
        jumlah = cnt[0] if cnt else 0
        desc = f"{target.mention} punya **{jumlah}** invite valid."
        if row and row[0]:
            desc += f"\nDiundang oleh <@{row[0]}> pada {row[1]}."
        elif row:
            desc += "\nPengundang tidak diketahui (vanity / invite terhapus)."
        embed = base_embed(f"📨 Invites — {target.display_name}", desc)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="invite-lb", description="Top 10 pengundang terbanyak")
    async def invite_lb(self, ctx: commands.Context):
        gid = ctx.guild.id if ctx.guild else 0
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT inviter_id, COUNT(*) as c FROM invites_log WHERE guild_id = ? AND inviter_id IS NOT NULL GROUP BY inviter_id ORDER BY c DESC LIMIT 10",
                (gid,),
            ).fetchall()
        if not rows:
            await ctx.send("Belum ada data invite.", ephemeral=True)
            return
        medals = ["🥇", "🥈", "🥉"]
        desc = ""
        for i, (uid, c) in enumerate(rows):
            medal = medals[i] if i < 3 else f"`{i+1}.`"
            desc += f"{medal} <@{uid}> — **{c}** invite\n"
        embed = base_embed("🏆 Invite Leaderboard", desc)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Invites(bot))
