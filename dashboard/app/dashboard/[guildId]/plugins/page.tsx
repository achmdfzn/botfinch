import { redirect } from "next/navigation";

/**
 * Halaman ini digabung ke halaman utama server (/dashboard/[guildId]).
 * Redirect agar bookmark lama tetap jalan, tanpa duplikasi konten.
 */
export default async function GuildPluginsRedirect({
  params,
}: {
  params: Promise<{ guildId: string }>;
}) {
  const { guildId } = await params;
  redirect(`/dashboard/${guildId}`);
}
