export const MANAGE_GUILD = 0x20;

export interface DiscordGuild {
  id: string;
  name: string;
  icon: string | null;
  permissions: string;
  /** True bila user login adalah owner server (dari API Discord /users/@me/guilds). */
  owner?: boolean;
}

export function canManage(guild: DiscordGuild): boolean {
  // Owner selalu boleh kelola walau bit MANAGE_GUILD absen di payload
  // /users/@me/guilds (owner bisa saja tak memegang role dengan bit itu).
  return guild.owner === true || (BigInt(guild.permissions) & BigInt(MANAGE_GUILD)) === BigInt(MANAGE_GUILD);
}

export async function fetchUserGuilds(accessToken: string): Promise<DiscordGuild[]> {
  const res = await fetch("https://discord.com/api/users/@me/guilds", {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Discord API ${res.status}`);
  return (await res.json()) as DiscordGuild[];
}

export function iconUrl(guildId: string, icon: string | null, size = 128): string | null {
  if (!icon) return null;
  const ext = icon.startsWith("a_") ? "gif" : "png";
  return `https://cdn.discordapp.com/icons/${guildId}/${icon}.${ext}?size=${size}`;
}

export function inviteUrl(): string {
  // Fallback berantai: operator lama mungkin hanya mengisi DISCORD_CLIENT_ID
  // (dipakai auth.ts), sementara tombol "Undang Bot" baca yang NEXT_PUBLIC_.
  // Di client bundle hanya NEXT_PUBLIC_ yang ter-inline; fallback lainnya
  // aman karena undefined -> "".
  const clientId =
    process.env.NEXT_PUBLIC_DISCORD_CLIENT_ID ?? process.env.DISCORD_CLIENT_ID ?? "";
  // Bitmask least-privilege hasil audit pemakaian izin nyata bot
  // (bot/src/cogs): tanpa Administrator, kick, ban, connect/speak,
  // manage_guild. Lihat INVITE_PERMISSIONS di bawah untuk rinciannya.
  return `https://discord.com/oauth2/authorize?client_id=${clientId}&scope=bot+applications.commands&permissions=${INVITE_PERMISSIONS}`;
}

/**
 * Izin OAuth2 saat invite bot (least-privilege, bukan Administrator=8).
 *
 * Dipakai (diaudit dari kode bot):
 * - manage_channels (16): slowmode otomatis, tempvc buat/hapus room voice,
 *   serverstats rename channel stat, auto-lockdown, tiket buat/hapus channel
 * - add_reactions (64): seed reaksi panel self-role
 * - view_channel (1024) + send_messages (2048): baca & kirim pesan
 * - manage_messages (8192): !bersihkan, anti-spam hapus, auto-publish
 * - embed_links (16384): embed di mana-mana
 * - attach_files (32768): kartu rank PNG, transcript tiket, backup
 * - read_message_history (65536): fetch_message, baca histori
 * - mention_everyone (131072): pengumuman/embed dashboard pakai @everyone
 * - use_external_emojis (262144): seed reaksi emoji custom
 * - move_members (16777216): tempvc pindah member ke room pribadi
 * - manage_nicknames (134217728): anti-hoist ubah nick
 * - manage_roles (268435456): tambah/hapus role + overwrite tiket/tempvc
 * - use_application_commands (2147483648): slash command
 * - moderate_members (4294967296): timeout anti-spam/automod
 *
 * Sengaja TIDAK diminta: kick_members/ban_members (bot tak pernah
 * kick/ban — hanya timeout), connect/speak (bot tak pernah join voice),
 * manage_guild (hanya dipakai sebagai syarat otorisasi *user* admin,
 * bukan panggilan API bot), change_nickname, manage_webhooks/threads.
 */
export const INVITE_PERMISSIONS = 6862400592;
