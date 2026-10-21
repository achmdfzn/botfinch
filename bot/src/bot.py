"""Finch — Discord bot serbaguna untuk semua server.

Entry logic bot: class FinchBot, auto-load semua cog di src/cogs/,
event on_ready & on_member_join. Dijalankan lewat main.py.
"""
import asyncio
import logging
import pkgutil
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

import src.cogs as cogs_package
from src import config
from src.utils import modlog
from src.utils.embeds import finch_embed
from src.utils.rankcard import make_welcome_card

log = logging.getLogger("finch")

# Kebijakan mention global (audit keamanan 2026-10-10):
# - MENTIONS_AMAN: bawaan semua pesan bot — @everyone/@here DIMATIKAN agar
#   konten user yang diposting ulang bot (/saran, /confess, /poll,
#   /remind-rutin, transkrip tiket, log automod, dsb.) tidak bisa memicu
#   mass-ping. Mention user & role tetap jalan (pemenang giveaway,
#   role notifikasi YT, ...).
# - MENTIONS_PENGUMUMAN: khusus konten resmi yang ditulis admin/mod
#   (pengumuman dashboard, embed builder, event rutin, ...); pakai eksplisit
#   di titik kirimnya masing-masing.
MENTIONS_AMAN = discord.AllowedMentions(
    everyone=False, users=True, roles=True, replied_user=True
)
MENTIONS_PENGUMUMAN = discord.AllowedMentions(
    everyone=True, users=True, roles=True, replied_user=True
)


class FinchBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.invites = True
        super().__init__(
            command_prefix=config.settings.prefix,
            intents=intents,
            help_command=None,
            allowed_mentions=MENTIONS_AMAN,
        )
        self.start_time = datetime.now(timezone.utc)

    async def setup_hook(self) -> None:
        """Dipanggil sekali saat startup: inisialisasi DB, load cog, & sync slash commands."""
        # 1. Init DB
        from src.store import init_db
        init_db()  # raise langsung biar ketahuan gagal startup!

        # 2. Load cogs
        for mod in pkgutil.iter_modules(cogs_package.__path__):
            name = f"{cogs_package.__name__}.{mod.name}"
            try:
                await self.load_extension(name)
                log.info("Cog dimuat: %s", name)
            except Exception:
                log.exception("Gagal memuat cog: %s", name)

        # Sync slash commands.
        guild_id = config.settings.guild_id
        if guild_id:
            guild = discord.Object(id=guild_id)
            # Salin command ke guild biar muncul instan
            self.tree.copy_global_to(guild=guild)
            try:
                synced = await self.tree.sync(guild=guild)
            except (discord.HTTPException, discord.Forbidden) as e:
                # GUILD_ID salah / bot tidak ada di guild → jangan crash startup
                log.error(
                    "Gagal sync slash commands ke guild %d (%s). Cek GUILD_ID di .env.",
                    guild_id,
                    e,
                )
                return
            log.info("Synced %d slash commands ke guild ID %d (instant)", len(synced), guild_id)
            # Hapus command GLOBAL yang tersisa di sisi Discord — inilah penyebab
            # duplikat di picker (tiap command muncul 2x: versi global + versi guild).
            # Caranya: sync daftar global KOSONG ke Discord, tanpa merusak local tree.
            # Idempoten & aman diulang tiap startup.
            global_cmds = list(self.tree.get_commands())
            try:
                for cmd in global_cmds:
                    self.tree.remove_command(cmd.name)
                await self.tree.sync()
                log.info("Global slash commands dibersihkan (anti-duplikat).")
            except (discord.HTTPException, discord.Forbidden) as e:
                log.warning("Gagal bersihkan global commands: %s", e)
            finally:
                for cmd in global_cmds:
                    try:
                        self.tree.add_command(cmd)
                    except (discord.app_commands.CommandAlreadyRegistered, ValueError):
                        pass
        else:
            synced = await self.tree.sync()
            log.info("Synced %d slash commands (global, propagate ±1 jam)", len(synced))

    async def on_ready(self) -> None:
        assert self.user is not None
        log.info("✅ %s udah online dan siap!", self.user)
        log.info("Terhubung ke %d server.", len(self.guilds))
        # Status "Playing" ala bot populer (MEE6, Dyno): tampil di profil bot
        try:
            await self.change_presence(activity=discord.Game(name="/bantuan"))
        except Exception:
            log.exception("Gagal pasang status presence")

    async def _respon_error_aman(self, ctx: commands.Context, pesan: str) -> None:
        """Kirim pesan error yang TIDAK PERNAH crash.

        Konteks hybrid-slash membawa interaction yang bisa sudah di-ack atau
        mati (10062/40060). Error handler yang ikut meledak = user tidak dapat
        pesan apa-apa + log ketumpuk traceback ganda.
        """
        try:
            if ctx.interaction is None:
                await ctx.send(pesan)  # prefix: ephemeral tidak didukung
            elif ctx.interaction.response.is_done():
                await ctx.interaction.followup.send(pesan, ephemeral=True)
            else:
                await ctx.interaction.response.send_message(pesan, ephemeral=True)
        except discord.HTTPException:
            pass  # interaction mati — tidak ada yang bisa dilakukan

    async def on_app_command_error(self, interaction: discord.Interaction, error: commands.CommandError) -> None:
        """Pesan error ramah untuk slash command, jangan traceback ke user."""
        try:
            if isinstance(error, commands.MissingPermissions) or isinstance(error, app_commands.CheckFailure):
                # Cek is_done: interaction yang sudah di-ack lalu gagal check
                # melempar InteractionResponded (bukan HTTPException) bila
                # response.send_message dipaksa — pakai followup bila perlu.
                if interaction.response.is_done():
                    await interaction.followup.send(
                        "❌ Kamu gak punya izin buat perintah ini.", ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        "❌ Kamu gak punya izin buat perintah ini.", ephemeral=True
                    )
            else:
                log.exception("Error slash command: %s", error)
                if interaction.response.is_done():
                    await interaction.followup.send("❌ Ada yang salah, coba lagi nanti ya.", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ Ada yang salah, coba lagi nanti ya.", ephemeral=True)
        except discord.HTTPException:
            pass  # interaction mati — jangan ikut crash

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """Pesan error ramah untuk prefix & hybrid command (hybrid-slash juga masuk sini)."""
        if isinstance(error, commands.MissingPermissions) or isinstance(error, commands.CheckFailure):
            await self._respon_error_aman(ctx, "❌ Kamu gak punya izin buat perintah ini.")
        elif isinstance(error, commands.BadArgument) or isinstance(error, commands.MissingRequiredArgument):
            await self._respon_error_aman(ctx, "❌ Argumen salah/kurang. Cek `!bantuan`.")
        elif isinstance(error, commands.CommandNotFound):
            pass # Abaikan saja command yang tidak dikenal
        else:
            log.exception("Error prefix command: %s", error)
            await self._respon_error_aman(ctx, "❌ Ada yang salah, coba lagi nanti ya.")

    async def on_member_remove(self, member: discord.Member) -> None:
        """Catat member yang keluar ke mod-log + kirim pesan perpisahan ke channel.

        Pesan perpisahan bisa dikonfigurasi per-server via dashboard:
        `goodbye_enabled` ("1"/"0", default "1" = perilaku lama tetap jalan),
        `goodbye_channel_id` (fallback: system channel), `goodbye_message`
        (variabel: {user} {server} {member_count} {channel}).
        """
        from src.cogs.dashboard_sync import (
            _channel_milik_guild,
            get_guild_setting,
            get_guild_setting_int,
        )

        await modlog.log_event(
            self,
            "👋 Member keluar",
            f"`{member}` ({member.id}) keluar dari server.",
            discord.Color.greyple(),
        )
        if get_guild_setting(member.guild.id, "goodbye_enabled", "1") != "1":
            return
        channel_id = get_guild_setting_int(member.guild.id, "goodbye_channel_id", 0)
        channel = self.get_channel(channel_id) if channel_id else None
        if channel is not None and not _channel_milik_guild(channel, member.guild.id):
            log.warning(
                "Goodbye channel %s tidak valid untuk guild %s (bukan miliknya / bukan channel teks); memakai system channel jika tersedia.",
                channel_id, member.guild.id,
            )
            channel = None
        if channel is None:
            # fallback: pakai system channel server
            channel = member.guild.system_channel
        if channel is None:
            return
        from src.utils.variabel import substitusi_variabel

        template = get_guild_setting(member.guild.id, "goodbye_message", "")
        if template.strip():
            teks = substitusi_variabel(
                template,
                user=member.mention,
                server=member.guild.name,
                member_count=member.guild.member_count or 0,
                channel=channel.mention,
            )
        else:
            teks = (
                f"👋 **{member.display_name}** telah keluar dari **{member.guild.name}**.\n"
                "Terima kasih sudah mampir, semoga sukses di mana pun kamu berada!"
            )
        embed = finch_embed("👋 Sampai jumpa", teks)
        try:
            embed.set_thumbnail(url=member.display_avatar.url)
        except Exception:
            pass
        try:
            # Template goodbye ditulis admin via dashboard -> boleh @everyone.
            await channel.send(embed=embed, allowed_mentions=MENTIONS_PENGUMUMAN)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def on_member_join(self, member: discord.Member) -> None:
        """Kirim kartu selamat datang bergambar (bisa dimatikan per-server via dashboard).

        Termasuk auto-role: `welcome_role_ids` (dashboard, daftar ID dipisah koma)
        diberikan otomatis ke member baru. Ikut toggle `welcome_enabled`.
        """
        from src.cogs.dashboard_sync import (
            _channel_milik_guild,
            get_guild_setting,
            get_guild_setting_int,
            parse_id_list,
        )
        from src.utils.variabel import substitusi_variabel

        gid = member.guild.id
        if get_guild_setting(gid, "welcome_enabled", "1") != "1":
            return
        # Auto-role: role otomatis untuk member baru (ala MEE6)
        for rid in parse_id_list(get_guild_setting(gid, "welcome_role_ids", "")):
            role = member.guild.get_role(rid)
            if role is None:
                continue
            try:
                await member.add_roles(role, reason="Welcome auto-role")
            except (discord.Forbidden, discord.HTTPException):
                log.warning("Gagal kasih auto-role %s ke %s", rid, member.id)
        channel_id = (
            get_guild_setting_int(gid, "welcome_channel_id", 0)
            or config.settings.welcome_channel_id
        )
        channel = self.get_channel(channel_id) if channel_id else None
        if channel is not None and not _channel_milik_guild(channel, gid):
            log.warning(
                "Welcome channel %s tidak valid untuk guild %s (bukan miliknya / bukan channel teks); memakai system channel jika tersedia.",
                channel_id, gid,
            )
            channel = None
        if channel is None:
            # fallback: pakai system channel server
            channel = member.guild.system_channel
        if channel is None:
            return
        try:
            avatar_bytes = await member.display_avatar.read()
        except discord.HTTPException:
            avatar_bytes = None
        loop = asyncio.get_running_loop()
        try:
            theme = get_guild_setting(gid, "welcome_theme", "default")
            buf = await loop.run_in_executor(
                None,
                make_welcome_card,
                avatar_bytes,
                member.display_name,
                member.guild.name,
                member.guild.member_count or 0,
                theme,
            )
            file = discord.File(buf, filename="welcome.png")
        except Exception:
            log.exception("Gagal bikin welcome card")
            file = None
        try:
            # Pesan custom via dashboard (variabel: {user} {server} {member_count} {channel})
            template = get_guild_setting(gid, "welcome_message", "")
            if template.strip():
                teks = substitusi_variabel(
                    template,
                    user=member.mention,
                    server=member.guild.name,
                    member_count=member.guild.member_count or 0,
                    channel=channel.mention,
                )
            else:
                teks = (
                    f"👋 Selamat datang di **{member.guild.name}**, {member.mention}!\n"
                    "Jangan lupa baca rules ya, dan have fun! 🎮"
                )
            # Template welcome ditulis admin via dashboard -> boleh @everyone.
            await channel.send(
                teks, file=file, allowed_mentions=MENTIONS_PENGUMUMAN
            )
        except discord.Forbidden:
            log.warning("Tidak bisa kirim welcome (cek permission).")
