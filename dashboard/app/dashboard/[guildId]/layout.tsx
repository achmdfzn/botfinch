import type { ReactNode } from "react";
import { getSessionSafe } from "@/lib/access";
import { canManage, iconUrl } from "@/lib/discord";
import { fetchUserGuilds } from "@/lib/access";
import { getDict, getLang } from "@/lib/i18n";
import DashboardShell from "@/components/DashboardShell";
import type { SidebarNavItem } from "@/components/Sidebar";

/**
 * Shell navigasi per-server (Sidebar). Aditif: halaman di dalamnya tetap me-render
 * kontennya sendiri. Bila guild tidak ditemukan
 * atau Discord gagal merespons, children di-render apa adanya tanpa shell
 * agar halaman bisa menampilkan state error-nya sendiri.
 */
export default async function GuildLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ guildId: string }>;
}) {
  const { guildId } = await params;
  const dict = getDict(await getLang());
  const session = await getSessionSafe();

  let guildName: string | null = null;
  let guildIconUrl: string | null = null;
  if (session?.accessToken) {
    try {
      const mine = (await fetchUserGuilds(session.accessToken)).find(
        (g) => g.id === guildId && canManage(g),
      );
      if (mine) {
        guildName = mine.name;
        guildIconUrl = iconUrl(guildId, mine.icon, 128);
      }
    } catch {
      // Gagal ambil daftar guild: render children tanpa shell.
    }
  }
  if (!guildName) return <>{children}</>;

  const sub = dict.guild.subnav;
  // navItems adalah daftar kanonis 13 route per-server; DashboardShell
  // (via buildSidebarGroups di lib/sidebar-nav) mengelompokkannya menjadi
  // grup Ringkasan, Modul & Fitur, Konten & Komunitas, Pengaturan, dan
  // Billing VIP — setiap route tampil tepat satu kali. Urutan di sini
  // tidak menentukan urutan sidebar, kecuali navItems[0] yang HARUS tetap
  // home per-server karena DashboardShell memakainya sebagai basis
  // hrefFor().
  const navItems: SidebarNavItem[] = [
    { href: `/dashboard/${guildId}`, label: sub.plugins },
    { href: `/dashboard/${guildId}/overview`, label: sub.overview },
    { href: `/dashboard/${guildId}/leaderboard`, label: sub.leaderboard },
    { href: `/dashboard/${guildId}/template`, label: dict.templates.navLabel },
    { href: `/dashboard/${guildId}/settings`, label: sub.settings },
    { href: `/dashboard/${guildId}/selfroles`, label: sub.selfroles },
    { href: `/dashboard/${guildId}/responder`, label: sub.responder },
    { href: `/dashboard/${guildId}/giveaway`, label: sub.giveaway },
    { href: `/dashboard/${guildId}/embed`, label: sub.embed },
    { href: `/dashboard/${guildId}/pengumuman`, label: sub.pengumuman },
    { href: `/dashboard/${guildId}/modlog`, label: sub.modlog },
    { href: `/dashboard/${guildId}/modul`, label: sub.modul },
    { href: `/dashboard/${guildId}/billing`, label: dict.billing.title },
  ];

  return (
    <DashboardShell guildName={guildName} guildIconUrl={guildIconUrl} navItems={navItems}>
      {children}
    </DashboardShell>
  );
}
