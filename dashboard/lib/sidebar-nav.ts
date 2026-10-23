// Logika murni pengelompokan navigasi sidebar per-server.
//
// Dipisah dari komponen (DashboardShell/Sidebar) agar bisa diuji tanpa
// render: DashboardShell hanya menerjemahkan kamus i18n + navItems layout
// menjadi input di sini, lalu me-render grup yang dikembalikan.
//
// Peta grup final (label dari dict.guild.subnav.groups):
// - overview  "Ringkasan"          : Plugins (home), Overview, Leaderboard
// - features  "Modul & Fitur"      : halaman Modul + seksi plugin per grup
//                                    PLUGINS (Esensial/Engagement/Moderasi/
//                                    Utilitas), DISARING: plugin yang
//                                    configure-nya menuju route yang sudah
//                                    ada di grup Konten tidak tampil lagi
//                                    (selfroles, responder, giveaway,
//                                    pengumuman, embed, template).
// - content   "Konten & Komunitas" : Template, Embed, Self-roles,
//                                    Auto-responder, Giveaway, Pengumuman
// - settings  "Pengaturan"         : Pengaturan, Mod Log
// - billing   "Billing VIP"        : Billing
//
// Dengan penyaringan itu setiap route per-guild muncul tepat satu kali
// sebagai item route. Plugin tanpa halaman konfigurasi tetap menunjuk
// halaman Plugins dengan ?tab=<grup> (beberapa plugin segrup berbagi href
// tab yang sama — itu memang satu route yang sama, bukan duplikasi grup).

import { PLUGINS, type PluginGroup } from "@/lib/plugins";

export type SidebarIconId =
  | "plugins"
  | "overview"
  | "leaderboard"
  | "welcome"
  | "leveling"
  | "reactionRoles"
  | "customCommands"
  | "economy"
  | "starboard"
  | "giveaway"
  | "announcements"
  | "automod"
  | "embedBuilder"
  | "templates"
  | "modlog"
  | "modules"
  | "settings";

export interface SidebarEntry {
  href: string;
  label: string;
  icon: SidebarIconId;
  /**
   * true = hanya aktif pada kecocokan path persis (dipakai item Plugins /
   * home per-server: semua subroute berawalan href home, jadi pencocokan
   * awalan akan membuatnya selalu aktif).
   */
  exact?: boolean;
}

export interface SidebarSection {
  id: string;
  title: string;
  items: SidebarEntry[];
}

export interface SidebarGroup {
  id: "overview" | "features" | "content" | "settings" | "billing";
  title: string;
  items: SidebarEntry[];
  /** Hanya grup features: subseksi plugin per grup PLUGINS. */
  sections?: SidebarSection[];
}

export const PLUGIN_ICONS: Record<string, SidebarIconId> = {
  welcome: "welcome",
  leveling: "leveling",
  selfroles: "reactionRoles",
  responder: "customCommands",
  economy: "economy",
  starboard: "starboard",
  giveaway: "giveaway",
  announcements: "announcements",
  customcmd: "customCommands",
  automod: "automod",
  slowmode: "automod",
  msglog: "modlog",
  embed: "embedBuilder",
  autopublish: "announcements",
  templates: "templates",
};

export interface SidebarNavLabels {
  groupTitles: {
    overview: string;
    features: string;
    content: string;
    settings: string;
    billing: string;
  };
  pluginGroupTitles: Record<PluginGroup, string>;
  plugins: string;
  overview: string;
  leaderboard: string;
  template: string;
  embed: string;
  selfroles: string;
  responder: string;
  giveaway: string;
  pengumuman: string;
  settings: string;
  modlog: string;
  modul: string;
  billing: string;
  /** Nama plugin per id dari dict.guild.plugins.cards. */
  pluginNames: Record<string, string>;
}

export interface BuildSidebarGroupsInput {
  /** href home per-server, mis. "/dashboard/123". */
  homeHref: string;
  /** Resolusi href relatif terhadap home (dari navItems layout). */
  hrefFor: (rel: string) => string;
  labels: SidebarNavLabels;
}

/** Path murni dari href: buang hash dan query. */
export function hrefPath(href: string): string {
  return href.split("#")[0].split("?")[0];
}

/**
 * Tujuan link per plugin:
 * - welcome -> seksi welcome di /settings (hrefFor("/settings") + "#welcome");
 * - punya configure -> halaman konfigurasinya;
 * - tanpa configure -> halaman Plugins dengan ?tab=<grup>.
 */
export function pluginHref(
  homeHref: string,
  hrefFor: (rel: string) => string,
  plugin: { id: string; configure: string | null; group: PluginGroup },
): string {
  if (plugin.id === "welcome") return `${hrefFor("/settings")}#welcome`;
  if (plugin.configure) return hrefFor(`/${plugin.configure}`);
  return `${homeHref}?tab=${plugin.group}`;
}

export function buildSidebarGroups(input: BuildSidebarGroupsInput): SidebarGroup[] {
  const { homeHref, hrefFor, labels } = input;

  const contentItems: SidebarEntry[] = [
    { href: hrefFor("/template"), label: labels.template, icon: "templates" },
    { href: hrefFor("/embed"), label: labels.embed, icon: "embedBuilder" },
    { href: hrefFor("/selfroles"), label: labels.selfroles, icon: "reactionRoles" },
    { href: hrefFor("/responder"), label: labels.responder, icon: "customCommands" },
    { href: hrefFor("/giveaway"), label: labels.giveaway, icon: "giveaway" },
    { href: hrefFor("/pengumuman"), label: labels.pengumuman, icon: "announcements" },
  ];
  const contentPaths = new Set(contentItems.map((i) => hrefPath(i.href)));

  // Saring plugin yang configure-nya (path murninya) sudah menjadi route
  // di grup Konten: selfroles, responder, giveaway, announcements
  // (pengumuman), embed, templates (template). welcome lolos karena
  // tujuannya /settings#welcome (path /settings milik grup Pengaturan,
  // dan href lengkapnya berbeda oleh hash).
  const visiblePlugins = PLUGINS.filter((p) => {
    if (!p.configure) return true;
    const configurePath = hrefPath(hrefFor(`/${p.configure}`));
    return !contentPaths.has(configurePath);
  });

  const sections: SidebarSection[] = (
    ["essentials", "engagement", "moderation", "utilities"] as PluginGroup[]
  )
    .map((group) => ({
      id: group,
      title: labels.pluginGroupTitles[group],
      items: visiblePlugins
        .filter((p) => p.group === group)
        .map((p) => ({
          href: pluginHref(homeHref, hrefFor, p),
          label: labels.pluginNames[p.id] ?? p.id,
          icon: PLUGIN_ICONS[p.id] ?? "plugins",
        })),
    }))
    .filter((s) => s.items.length > 0);

  return [
    {
      id: "overview",
      title: labels.groupTitles.overview,
      items: [
        { href: hrefFor(""), label: labels.plugins, icon: "plugins", exact: true },
        { href: hrefFor("/overview"), label: labels.overview, icon: "overview" },
        { href: hrefFor("/leaderboard"), label: labels.leaderboard, icon: "leaderboard" },
      ],
    },
    {
      id: "features",
      title: labels.groupTitles.features,
      items: [{ href: hrefFor("/modul"), label: labels.modul, icon: "modules" }],
      sections,
    },
    {
      id: "content",
      title: labels.groupTitles.content,
      items: contentItems,
    },
    {
      id: "settings",
      title: labels.groupTitles.settings,
      items: [
        { href: hrefFor("/settings"), label: labels.settings, icon: "settings" },
        { href: hrefFor("/modlog"), label: labels.modlog, icon: "modlog" },
      ],
    },
    {
      id: "billing",
      title: labels.groupTitles.billing,
      items: [{ href: hrefFor("/billing"), label: labels.billing, icon: "economy" }],
    },
  ];
}

/**
 * Apakah entry boleh membawa `aria-current="page"` saat aktif.
 * Hanya route kanonis (href tanpa hash dan tanpa query ?tab=): entry
 * ?tab= berbagi satu route Plugins yang sama antar beberapa plugin dan
 * entry ber-hash menunjuk seksi di dalam halaman lain, jadi keduanya
 * cukup ditandai secara visual. Tanpa aturan ini satu layar bisa
 * memuat sampai empat `aria-current="page"` sekaligus (Plugins/home +
 * tiga plugin ?tab=engagement), melanggar semantik ARIA bahwa hanya
 * satu elemen yang "current" dalam satu set navigasi.
 */
export function isAriaCurrentEligible(entry: Pick<SidebarEntry, "href">): boolean {
  return !entry.href.includes("#") && !entry.href.includes("?");
}

/**
 * Kecocokan aktif untuk satu entry sidebar.
 *
 * - Hash diabaikan untuk path (item "#welcome" aktif di /settings), tetapi
 *   entry ber-hash hanya aktif pada path persisnya.
 * - Entry berquery ?tab= (plugin tanpa halaman konfigurasi) hanya aktif di
 *   path persisnya saat tab itu terbuka; entry tanpa tab di path yang sama
 *   aktif apa pun tab-nya (perilaku lama halaman Plugins).
 * - Entry biasa: path persis ATAU awalan subroute (mis. Billing tetap
 *   aktif di /billing/orders/<ref>), kecuali entry bertanda exact
 *   (Plugins/home).
 */
export function isSidebarLinkActive(
  pathname: string,
  currentTab: string | null,
  entry: Pick<SidebarEntry, "href" | "exact">,
): boolean {
  const href = entry.href;
  const hasHash = href.includes("#");
  const withoutHash = href.split("#")[0];
  const qIdx = withoutHash.indexOf("?");
  const hrefPathOnly = qIdx >= 0 ? withoutHash.slice(0, qIdx) : withoutHash;
  const normalizedPath = pathname === `${hrefPathOnly}/` ? hrefPathOnly : pathname;

  const hrefTab =
    qIdx >= 0 ? new URLSearchParams(withoutHash.slice(qIdx + 1)).get("tab") : null;
  if (hrefTab !== null) {
    return normalizedPath === hrefPathOnly && (currentTab ?? "all") === hrefTab;
  }
  if (hasHash || entry.exact) return normalizedPath === hrefPathOnly;
  return normalizedPath === hrefPathOnly || normalizedPath.startsWith(`${hrefPathOnly}/`);
}
