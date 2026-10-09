import { redirect } from "next/navigation";

/**
 * Halaman ini digabung ke halaman utama server (/dashboard/[guildId]).
 * Redirect agar bookmark lama tetap jalan, tanpa duplikasi konten.
 * Query ?tab=<grup> diteruskan agar sidebar link plugin tanpa halaman
 * konfigurasi (mis. leveling, economy, starboard, automod) tetap mendarat
 * di tab kategori yang benar di halaman Plugins.
 */
export default async function GuildPluginsRedirect({
  params,
  searchParams,
}: {
  params: Promise<{ guildId: string }>;
  searchParams: Promise<{ tab?: string }>;
}) {
  const { guildId } = await params;
  const { tab } = await searchParams;
  const suffix = tab ? `?tab=${encodeURIComponent(tab)}` : "";
  redirect(`/dashboard/${guildId}${suffix}`);
}
