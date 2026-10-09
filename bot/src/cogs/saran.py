"""Sistem saran.

- `/saran <teks>`: member kirim saran -> embed di SARAN_CHANNEL_ID + vote 👍👎
- `/saran-status <message_id> <status>`: mod ubah status (diterima/ditolak/dipertimbangkan)
"""
import discord
from discord.ext import commands

from src import config
from src.store import get_connection
from src.utils import modlog
from src.utils.embeds import base_embed, error_embed, finch_embed

SARAN_COOLDOWN_DETIK = 60


def _klaim_cooldown_saran(conn, guild_id: int, user_id: int) -> float:
    """Klaim cooldown /saran atomik. Return 0 bila boleh, sisa detik bila tidak.

    Pola UPSERT yang sama seperti sosial._cooldown_klaim (duplikasi lokal yang
    disengaja — import antar-cog dilarang ARCHITECTURE.md).
    """
    sekarang = discord.utils.utcnow().isoformat()
    cur = conn.execute(
        "INSERT INTO cooldown_aksi (user_id, guild_id, aksi, terakhir) VALUES (?, ?, 'saran', ?) "
        "ON CONFLICT(user_id, guild_id, aksi) DO UPDATE SET terakhir = excluded.terakhir "
        "WHERE (strftime('%s', 'now') - strftime('%s', terakhir)) >= ?",
        (user_id, guild_id, sekarang, SARAN_COOLDOWN_DETIK),
    )
    conn.commit()
    if cur.rowcount == 1:
        return 0
    row = conn.execute(
        "SELECT terakhir FROM cooldown_aksi WHERE user_id = ? AND guild_id = ? AND aksi = 'saran'",
        (user_id, guild_id),
    ).fetchone()
    if not row:
        return 0
    try:
        import datetime as _dt

        dt = _dt.datetime.fromisoformat(row[0])
    except ValueError:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    sisa = (dt + _dt.timedelta(seconds=SARAN_COOLDOWN_DETIK) - discord.utils.utcnow()).total_seconds()
    return max(0, sisa)


STATUS_WARNA = {
    "menunggu": discord.Color.gold(),
    "diterima": discord.Color.green(),
    "ditolak": discord.Color.red(),
    "dipertimbangkan": discord.Color.blurple(),
}
STATUS_VALID = {"diterima", "ditolak", "dipertimbangkan"}


class SaranVoteView(discord.ui.View):
    """Tombol vote 👍/👎 saran — persisten (survive restart, custom_id tetap)."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Setuju", style=discord.ButtonStyle.success, custom_id="finch:saran-up"
    )
    async def vote_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._vote(interaction, 1)

    @discord.ui.button(
        label="Tidak setuju", style=discord.ButtonStyle.danger, custom_id="finch:saran-down"
    )
    async def vote_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._vote(interaction, -1)

    async def _vote(self, interaction: discord.Interaction, nilai: int) -> None:
        msg = interaction.message
        if msg is None:
            await interaction.response.send_message(
                embed=error_embed("Pesan saran tidak ditemukan."), ephemeral=True
            )
            return
        mid = msg.id
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO saran_vote (message_id, user_id, vote) VALUES (?, ?, ?) "
                "ON CONFLICT(message_id, user_id) DO UPDATE SET vote = excluded.vote",
                (mid, interaction.user.id, nilai),
            )
            conn.commit()
            up = conn.execute(
                "SELECT COUNT(*) FROM saran_vote WHERE message_id = ? AND vote = 1",
                (mid,),
            ).fetchone()[0]
            down = conn.execute(
                "SELECT COUNT(*) FROM saran_vote WHERE message_id = ? AND vote = -1",
                (mid,),
            ).fetchone()[0]
        teks_vote = f"Setuju: {up} · Tidak: {down}"
        try:
            embed = msg.embeds[0]
            found = False
            for idx, f in enumerate(embed.fields):
                if "vote" in f.name.lower():
                    embed.set_field_at(idx, name="Vote", value=teks_vote, inline=False)
                    found = True
                    break
            if not found:
                embed.add_field(name="Vote", value=teks_vote, inline=False)
            await interaction.response.edit_message(embed=embed, view=self)
        except (discord.HTTPException, IndexError):
            await interaction.response.send_message(
                "✅ Votemu tercatat!", ephemeral=True
            )


class Saran(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="saran", description="Kirim saran untuk server")
    @discord.app_commands.describe(teks="Isi saran kamu (maks 500 karakter)")
    async def saran(self, ctx: commands.Context, teks: str):
        """Kirim saran: !saran <teks> / /saran"""
        if len(teks) > 500:
            await ctx.send("❌ Saran kepanjangan, maksimal 500 karakter ya.", ephemeral=True)
            return
        if not teks.strip():
            await ctx.send("❌ Saran tidak boleh kosong.", ephemeral=True)
            return

        channel_id = config.settings.saran_channel_id
        if not channel_id:
            await ctx.send("❌ Channel saran belum dikonfigurasi admin.", ephemeral=True)
            return

        channel = ctx.guild.get_channel(channel_id) if ctx.guild else None
        if channel is None or not isinstance(channel, discord.TextChannel):
            await ctx.send("❌ Channel saran tidak ditemukan.", ephemeral=True)
            return

        # Cooldown anti-spam channel saran (atomik, persisten di DB).
        if ctx.guild is not None:
            with get_connection() as conn:
                sisa = _klaim_cooldown_saran(conn, ctx.guild.id, ctx.author.id)
            if sisa > 0:
                await ctx.send(
                    f"❌ Tunggu **{sisa:.0f}** detik sebelum mengirim saran lagi.",
                    ephemeral=True,
                )
                return

        author = ctx.author
        embed = base_embed("💡 Saran Baru", teks)
        embed.color = STATUS_WARNA["menunggu"]
        embed.set_author(name=str(author), icon_url=author.display_avatar.url if author.display_avatar else None)
        embed.add_field(name="Status", value="Menunggu", inline=False)
        embed.add_field(name="Pengirim", value=author.mention, inline=False)
        embed.add_field(name="Vote", value="Setuju: 0 · Tidak: 0", inline=False)

        try:
            # Vote murni via tombol berlabel (components > reaksi emoji)
            # Mention dibatasi hanya ke pengirim saran: teks ditulis user,
            # users=True polos bisa disalahgunakan untuk nge-ping orang lain.
            msg = await channel.send(
                embed=embed,
                view=SaranVoteView(),
                allowed_mentions=discord.AllowedMentions(users=[author]),
            )
        except discord.Forbidden:
            await ctx.send("❌ Bot tidak punya izin kirim ke channel saran.", ephemeral=True)
            return

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO suggestions (message_id, guild_id, author_id, text, status) VALUES (?, ?, ?, ?, ?)",
                (msg.id, ctx.guild.id if ctx.guild else 0, author.id, teks, "Menunggu"),
            )
            conn.commit()

        await ctx.send(f"✅ Saranmu sudah dikirim ke {channel.mention}!", ephemeral=True)

    @commands.hybrid_command(name="saran-status", description="Ubah status saran (khusus mod)")
    @discord.app_commands.describe(
        message_id="ID pesan saran",
        status="Status baru: diterima / ditolak / dipertimbangkan",
    )
    @commands.has_permissions(manage_messages=True)
    async def saran_status(self, ctx: commands.Context, message_id: str, status: str):
        """Ubah status saran: !saran-status <id> <status>"""
        status_norm = status.strip().lower()
        if status_norm not in STATUS_VALID:
            await ctx.send("❌ Status harus salah satu: `diterima`, `ditolak`, `dipertimbangkan`.", ephemeral=True)
            return
        try:
            mid = int(message_id)
        except ValueError:
            await ctx.send("❌ message_id harus angka.", ephemeral=True)
            return

        channel_id = config.settings.saran_channel_id
        if not channel_id:
            await ctx.send("❌ Channel saran belum dikonfigurasi.", ephemeral=True)
            return
        channel = ctx.guild.get_channel(channel_id) if ctx.guild else None
        if channel is None or not isinstance(channel, discord.TextChannel):
            await ctx.send("❌ Channel saran tidak ditemukan.", ephemeral=True)
            return

        with get_connection() as conn:
            row = conn.execute("SELECT author_id, text FROM suggestions WHERE message_id = ?", (mid,)).fetchone()
        if row is None:
            await ctx.send("❌ Saran tidak ditemukan di database.", ephemeral=True)
            return

        # Capitalize untuk tampilan
        status_tampil = status_norm.capitalize() if status_norm != "dipertimbangkan" else "Dipertimbangkan"
        # warna
        warna = STATUS_WARNA[status_norm]

        try:
            msg = await channel.fetch_message(mid)
            embed = msg.embeds[0] if msg.embeds else base_embed("💡 Saran", row[1])
            embed.color = warna
            # update field Status
            found = False
            for idx, f in enumerate(embed.fields):
                if f.name.lower() == "status":
                    embed.set_field_at(idx, name="Status", value=status_tampil, inline=False)
                    found = True
                    break
            if not found:
                embed.add_field(name="Status", value=status_tampil, inline=False)
            await msg.edit(embed=embed)
        except discord.NotFound:
            await ctx.send("❌ Pesan saran tidak ditemukan (mungkin sudah dihapus).", ephemeral=True)
            return
        except discord.Forbidden:
            await ctx.send("❌ Bot tidak punya izin edit pesan saran.", ephemeral=True)
            return

        with get_connection() as conn:
            conn.execute("UPDATE suggestions SET status = ? WHERE message_id = ?", (status_tampil, mid))
            conn.commit()

        await ctx.send(f"✅ Status saran `{mid}` diubah menjadi **{status_tampil}**.", ephemeral=True)
        await modlog.log_event(
            self.bot,
            "💡 Status saran diubah",
            f"Saran `{mid}` oleh <@{row[0]}> diubah menjadi **{status_tampil}** oleh {ctx.author.mention} — [Lihat pesan](https://discord.com/channels/{ctx.guild.id}/{channel_id}/{mid})",
            warna,
        )


    @commands.hybrid_command(name="saran-top", description="5 saran dengan skor vote tertinggi")
    async def saran_top(self, ctx: commands.Context):
        """Top saran: /saran-top"""
        if ctx.guild is None:
            await ctx.send(embed=error_embed("Hanya bisa dipakai di server."), ephemeral=True)
            return
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT s.message_id, s.text, s.status,"
                " COALESCE(SUM(v.vote), 0) AS skor,"
                " COALESCE(SUM(CASE WHEN v.vote = 1 THEN 1 ELSE 0 END), 0) AS up,"
                " COALESCE(SUM(CASE WHEN v.vote = -1 THEN 1 ELSE 0 END), 0) AS down"
                " FROM suggestions s LEFT JOIN saran_vote v ON v.message_id = s.message_id"
                " WHERE s.guild_id = ? GROUP BY s.message_id"
                " ORDER BY skor DESC, up DESC LIMIT 5",
                (ctx.guild.id,),
            ).fetchall()
        if not rows:
            await ctx.send(embed=error_embed("Belum ada saran."), ephemeral=True)
            return
        ch_id = config.settings.saran_channel_id
        embed = finch_embed("Top Saran", "Skor = setuju − tidak setuju", warna="info")
        for mid, teks, status, skor, up, down in rows:
            potong = teks[:90] + ("…" if len(teks) > 90 else "")
            link = (
                f"https://discord.com/channels/{ctx.guild.id}/{ch_id}/{mid}"
                if ch_id
                else ""
            )
            nilai = f"{potong}\nSetuju: {up} · Tidak: {down}" + (f"\n[Lihat saran]({link})" if link else "")
            embed.add_field(
                name=f"Skor {skor:+d} · {status}",
                value=nilai,
                inline=True,
            )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Saran(bot))
    bot.add_view(SaranVoteView())
