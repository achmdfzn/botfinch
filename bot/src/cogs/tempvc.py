"""Temp Voice Channel (Room mabar dadakan).

- `TEMPVC_LOBBY_ID`: ID voice channel "➕ Buat Room"
- `TEMPVC_CATEGORY_ID`: Opsional, kategori tempat room dibuat.
- Member join lobby -> buat channel `🔊・<nama>-room`, pindahkan member, beri hak kelola.
- Kosong -> hapus channel.
- Command owner: `/vc-lock`, `/vc-unlock`, `/vc-limit`, `/vc-rename`.
"""
import logging
import time
import discord
from discord.ext import commands

from src import config
from src.store import get_connection

log = logging.getLogger("finch")

_vc_cooldown = {}

class TempVC(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ):
        lobby_id = config.settings.tempvc_lobby_id
        if not lobby_id:
            return

        guild = member.guild

        # 1. Join lobby -> Buat room baru
        if after.channel and after.channel.id == lobby_id:
            # Check cooldown 30 detik + 1 room aktif per owner
            now = time.time()
            key_cd = (member.guild.id, member.id)
            if key_cd in _vc_cooldown and now - _vc_cooldown[key_cd] < 30:
                return  # Cooldown aktif, jangan spam channel
            with get_connection() as conn:
                row_exist = conn.execute("SELECT channel_id FROM tempvc WHERE owner_id = ? AND guild_id = ?", (member.id, guild.id)).fetchone()
                if row_exist:
                    # Sudah punya room, jangan buat baru, pindahkan saja ke sana
                    ch_exist = guild.get_channel(row_exist[0])
                    if isinstance(ch_exist, discord.VoiceChannel):
                        try:
                            await member.move_to(ch_exist, reason="TempVC sudah punya room")
                        except discord.HTTPException:
                            pass
                        return
                    # Baris yatim (room dihapus manual) — bersihkan dulu biar tidak menumpuk
                    conn.execute("DELETE FROM tempvc WHERE owner_id = ? AND guild_id = ?", (member.id, guild.id))
                    conn.commit()
            
            category = None
            cat_id = config.settings.tempvc_category_id
            if cat_id:
                ch = guild.get_channel(cat_id)
                if isinstance(ch, discord.CategoryChannel):
                    category = ch

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=True),
                member: discord.PermissionOverwrite(
                    manage_channels=True,
                    mute_members=True,
                    deafen_members=True,
                    move_members=True,
                ),
                guild.me: discord.PermissionOverwrite(manage_channels=True, connect=True),
            }

            nama = f"🔊・{member.display_name[:15]}-room"
            vc = None
            # Tandai cooldown SEBELUM await — dua event join berurutan tidak
            # bisa sama-sama lolos pengecekan lalu membuat 2 room yatim.
            _vc_cooldown[key_cd] = now
            try:
                vc = await guild.create_voice_channel(
                    nama, overwrites=overwrites, category=category, reason=f"TempVC owner {member}"
                )
                try:
                    await member.move_to(vc, reason="Pindah ke room pribadi")
                except (discord.Forbidden, discord.HTTPException):
                    # move_to gagal -> hapus channel yatim biar tidak sampah permanen
                    try:
                        await vc.delete(reason="TempVC move_to gagal")
                    except discord.HTTPException:
                        pass
                    return
                with get_connection() as conn:
                    conn.execute(
                        "INSERT INTO tempvc (channel_id, owner_id, guild_id) VALUES (?, ?, ?)",
                        (vc.id, member.id, guild.id),
                    )
                    conn.commit()
            except discord.Forbidden:
                log.warning("Bot tidak punya izin kelola voice channel.")
            except discord.HTTPException:
                pass

        # 2. Leave / pindah dari room tempvc -> Cek kosong
        if before.channel and before.channel.id != lobby_id:
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT owner_id FROM tempvc WHERE channel_id = ?", (before.channel.id,)
                ).fetchone()
            if row:
                if len(before.channel.members) == 0:
                    with get_connection() as conn:
                        conn.execute("DELETE FROM tempvc WHERE channel_id = ?", (before.channel.id,))
                        conn.commit()
                    try:
                        await before.channel.delete(reason="TempVC kosong")
                    except discord.HTTPException:
                        pass

    def _get_owner_room(self, member: discord.Member) -> discord.VoiceChannel | None:
        if not member.voice or not member.voice.channel:
            return None
        ch = member.voice.channel
        with get_connection() as conn:
            row = conn.execute(
                "SELECT owner_id FROM tempvc WHERE channel_id = ?", (ch.id,)
            ).fetchone()
        if row and row[0] == member.id:
            return ch
        return None

    @commands.hybrid_command(name="vc-lock", description="Kunci voice channel kamu")
    async def vc_lock(self, ctx: commands.Context):
        """Kunci voice channel pribadi: /vc-lock"""
        if not isinstance(ctx.author, discord.Member):
            return
        ch = self._get_owner_room(ctx.author)
        if not ch:
            await ctx.send("❌ Kamu harus berada di voice channel pribadi (tempvc) milikmu sendiri.", ephemeral=True)
            return
        try:
            await ch.set_permissions(ctx.guild.default_role, connect=False)
            await ctx.send("🔒 Voice channel dikunci.", ephemeral=True)
        except discord.Forbidden:
            await ctx.send("❌ Bot butuh izin kelola channel.", ephemeral=True)

    @commands.hybrid_command(name="vc-unlock", description="Buka kunci voice channel kamu")
    async def vc_unlock(self, ctx: commands.Context):
        """Buka kunci voice channel pribadi: /vc-unlock"""
        if not isinstance(ctx.author, discord.Member):
            return
        ch = self._get_owner_room(ctx.author)
        if not ch:
            await ctx.send("❌ Kamu harus berada di voice channel pribadi (tempvc) milikmu sendiri.", ephemeral=True)
            return
        try:
            await ch.set_permissions(ctx.guild.default_role, connect=True)
            await ctx.send("🔓 Voice channel dibuka.", ephemeral=True)
        except discord.Forbidden:
            await ctx.send("❌ Bot butuh izin kelola channel.", ephemeral=True)

    @commands.hybrid_command(name="vc-limit", description="Atur batas member voice channel")
    @discord.app_commands.describe(limit="Batas member (0 = tak terbatas, max 99)")
    async def vc_limit(self, ctx: commands.Context, limit: int):
        """Atur batas member: /vc-limit <0-99>"""
        if not isinstance(ctx.author, discord.Member):
            return
        ch = self._get_owner_room(ctx.author)
        if not ch:
            await ctx.send("❌ Kamu harus berada di voice channel pribadi (tempvc) milikmu sendiri.", ephemeral=True)
            return
        if not 0 <= limit <= 99:
            await ctx.send("❌ Batas member harus antara 0 sampai 99.", ephemeral=True)
            return
        try:
            await ch.edit(user_limit=limit)
            await ctx.send(f"👥 Batas member diatur ke: {limit if limit > 0 else 'Tidak terbatas'}", ephemeral=True)
        except discord.Forbidden:
            await ctx.send("❌ Bot butuh izin kelola channel.", ephemeral=True)

    @commands.hybrid_command(name="vc-rename", description="Ubah nama voice channel kamu")
    @discord.app_commands.describe(nama="Nama baru (maks 30 karakter)")
    async def vc_rename(self, ctx: commands.Context, nama: str):
        """Ubah nama voice channel: /vc-rename <nama>"""
        if not isinstance(ctx.author, discord.Member):
            return
        ch = self._get_owner_room(ctx.author)
        if not ch:
            await ctx.send("❌ Kamu harus berada di voice channel pribadi (tempvc) milikmu sendiri.", ephemeral=True)
            return
        nama_bersih = nama.strip()[:30]
        if not nama_bersih:
            await ctx.send("❌ Nama tidak boleh kosong.", ephemeral=True)
            return
        try:
            await ch.edit(name=f"・{nama_bersih}")
            await ctx.send(f"✏️ Nama room diubah ke: `🔊・{nama_bersih}`", ephemeral=True)
        except discord.Forbidden:
            await ctx.send("❌ Bot butuh izin kelola channel.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(TempVC(bot))
