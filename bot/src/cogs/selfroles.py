"""Self-roles — member pilih role sendiri via select menu.

Daftar role diatur di .env:  SELF_ROLES="Pioneer,Notifikasi Event,Mabar"
Pasang panel sekali via `/panel-role` (mod). Select bersifat persistent.
Klik opsi untuk pasang role, klik lagi untuk lepas.

Tambahan: reaction self-roles dari dashboard web (tabel `dashboard_selfroles`
yang disinkronkan tiap 5 menit) — member tekan reaksi emoji di pesan
tertentu untuk dapat role. Lihat `dashboard_sync.emoji_cocok`.
"""
import discord
from discord.ext import commands

from src import config
from src.store import get_connection
from src.utils.embeds import base_embed

SELFROLES_ID = "finch:selfroles-select"


class SelfRoleSelect(discord.ui.Select):
    def __init__(self, opsi: list[discord.SelectOption]):
        super().__init__(
            placeholder="Pilih role...",
            min_values=1,
            max_values=len(opsi),
            options=opsi,
            custom_id=SELFROLES_ID,
        )

    async def callback(self, interaction: discord.Interaction):
        member = interaction.user
        guild = interaction.guild
        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "❌ Hanya bisa dipakai di server.", ephemeral=True
            )
            return
        ditambah: list[str] = []
        dicabut: list[str] = []
        gagal: list[str] = []
        for nama in self.values:
            role = discord.utils.get(guild.roles, name=nama)
            if role is None:
                gagal.append(nama)
                continue
            try:
                if role in member.roles:
                    await member.remove_roles(role, reason="Self-role dilepas")
                    dicabut.append(nama)
                else:
                    await member.add_roles(role, reason="Self-role dipasang")
                    ditambah.append(nama)
            except discord.Forbidden:
                gagal.append(nama)
        bagian = []
        if ditambah:
            bagian.append("➕ Dapat: " + ", ".join(f"`{r}`" for r in ditambah))
        if dicabut:
            bagian.append("➖ Dilepas: " + ", ".join(f"`{r}`" for r in dicabut))
        if gagal:
            bagian.append(
                "⚠️ Gagal (role tidak ada / izin kurang): "
                + ", ".join(f"`{r}`" for r in gagal)
            )
        await interaction.response.send_message(
            "\n".join(bagian) or "Tidak ada perubahan.", ephemeral=True
        )


class SelfRolesView(discord.ui.View):
    """Persistent — opsi select di-bake saat view dibuat."""

    def __init__(self, roles: list[str]):
        super().__init__(timeout=None)
        opsi = [discord.SelectOption(label=r, value=r) for r in roles[:25]]
        self.add_item(SelfRoleSelect(opsi))


class SelfRoles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _cari_selfrole(self, guild_id: int, message_id: int, emoji: discord.PartialEmoji):
        """Cari baris dashboard_selfroles yang cocok dengan reaksi."""
        from src.cogs.dashboard_sync import emoji_cocok

        with get_connection() as conn:
            rows = conn.execute(
                "SELECT emoji, role_id FROM dashboard_selfroles WHERE guild_id = ? AND message_id = ?",
                (guild_id, message_id),
            ).fetchall()
        for emoji_txt, role_id in rows:
            if emoji_cocok(emoji_txt, emoji):
                return role_id
        return None

    async def _toggle_role(self, guild: discord.Guild, user_id: int, role_id: int, pasang: bool):
        member = guild.get_member(user_id)
        role = guild.get_role(role_id)
        if member is None or role is None or member.bot:
            return
        try:
            if pasang:
                if role not in member.roles:
                    await member.add_roles(role, reason="Self-role dashboard")
            else:
                if role in member.roles:
                    await member.remove_roles(role, reason="Self-role dashboard dilepas")
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None:
            return
        if self.bot.user is not None and payload.user_id == self.bot.user.id:
            return
        role_id = self._cari_selfrole(payload.guild_id, payload.message_id, payload.emoji)
        if not role_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild:
            await self._toggle_role(guild, payload.user_id, role_id, True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None:
            return
        role_id = self._cari_selfrole(payload.guild_id, payload.message_id, payload.emoji)
        if not role_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild:
            await self._toggle_role(guild, payload.user_id, role_id, False)

    @commands.hybrid_command(
        name="panel-role", description="Pasang panel pilih role (khusus mod)"
    )
    @commands.has_permissions(manage_guild=True)
    async def panel_role(self, ctx: commands.Context):
        """Pasang panel self-roles: !panel-role / /panel-role (sekali saja)."""
        if ctx.guild is None:
            await ctx.send("❌ Hanya bisa di server.", ephemeral=True)
            return
        daftar = config.settings.self_roles_list()
        if not daftar:
            await ctx.send(
                '❌ `SELF_ROLES` kosong di .env. Contoh:\n`SELF_ROLES="Pioneer,Notifikasi Event,Mabar"`',
                ephemeral=True,
            )
            return
        ada = [r for r in daftar if discord.utils.get(ctx.guild.roles, name=r)]
        hilang = [r for r in daftar if r not in ada]
        if not ada:
            await ctx.send(
                "❌ Tidak ada satupun role dari `SELF_ROLES` yang cocok di server ini.",
                ephemeral=True,
            )
            return
        embed = base_embed(
            "🎭 Pilih Role Kamu",
            "Pilih dari menu di bawah — klik opsi untuk **pasang**, klik lagi untuk **lepas**.\n\n"
            "Role tersedia:\n" + "\n".join(f"• `{r}`" for r in ada),
        )
        await ctx.send(embed=embed, view=SelfRolesView(ada))
        if hilang:
            await ctx.send(
                f"⚠️ Role tidak ditemukan di server (dilewati): {', '.join(hilang)}",
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(SelfRoles(bot))
    roles = config.settings.self_roles_list()
    if roles:
        bot.add_view(SelfRolesView(roles))
