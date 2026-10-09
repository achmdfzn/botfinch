export const MANAGE_GUILD = 0x20;

export interface DiscordGuild {
  id: string;
  name: string;
  icon: string | null;
  permissions: string;
}

export function canManage(guild: DiscordGuild): boolean {
  return (BigInt(guild.permissions) & BigInt(MANAGE_GUILD)) === BigInt(MANAGE_GUILD);
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
  const clientId = process.env.NEXT_PUBLIC_DISCORD_CLIENT_ID ?? "";
  return `https://discord.com/oauth2/authorize?client_id=${clientId}&scope=bot+applications.commands&permissions=8`;
}
