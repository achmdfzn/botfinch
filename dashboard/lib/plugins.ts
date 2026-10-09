// Definisi kartu plugin ala MEE6 untuk halaman utama per-server
// (/dashboard/[guildId]) dan ringkasan status di overview. Nama + deskripsi
// diambil dari kamus i18n (dict.guild.plugins.cards[<id>]).
// Catatan: /dashboard/[guildId]/plugins kini redirect ke halaman utama.
export type PluginGroup = "essentials" | "engagement" | "moderation" | "utilities";

/** Tab kategori katalog plugin: "Semua" + 4 grup. */
export type PluginTab = "all" | PluginGroup;

/** Urutan tab kategori di halaman utama per-server. */
export const PLUGIN_TABS: readonly PluginTab[] = [
  "all",
  "essentials",
  "engagement",
  "moderation",
  "utilities",
];

/**
 * Validasi query ?tab=: nilai asing (atau kosong) jatuh ke "all"
 * agar link share selalu mendarat di tab yang valid.
 */
export function parsePluginTab(value: string | null | undefined): PluginTab {
  return (PLUGIN_TABS as readonly string[]).includes(value ?? "")
    ? (value as PluginTab)
    : "all";
}

export interface PluginDef {
  /** Kunci kamus di dict.guild.plugins.cards. */
  id: string;
  /** Maksimal 1 emoji/ikon sederhana per kartu. */
  emoji: string;
  group: PluginGroup;
  /** Key settings untuk toggle; null = tool tanpa toggle (selalu "aktif"). */
  toggleKey: string | null;
  /**
   * Tujuan tombol Configure, relatif terhadap /dashboard/[guildId].
   * "settings#welcome" = seksi welcome di halaman pengaturan;
   * null = tanpa tombol.
   */
  configure: string | null;
}

export const PLUGINS: PluginDef[] = [
  // Essentials
  { id: "welcome", emoji: "👋", group: "essentials", toggleKey: "welcome_enabled", configure: "settings#welcome" },
  { id: "leveling", emoji: "⭐", group: "essentials", toggleKey: "leveling_enabled", configure: null },
  { id: "selfroles", emoji: "🎭", group: "essentials", toggleKey: "selfroles_enabled", configure: "selfroles" },
  { id: "responder", emoji: "💬", group: "essentials", toggleKey: "responder_enabled", configure: "responder" },
  // Engagement & Fun
  { id: "economy", emoji: "🪙", group: "engagement", toggleKey: "economy_enabled", configure: null },
  { id: "starboard", emoji: "🌟", group: "engagement", toggleKey: "starboard_enabled", configure: null },
  { id: "giveaway", emoji: "🎉", group: "engagement", toggleKey: "giveaway_enabled", configure: "giveaway" },
  { id: "announcements", emoji: "📣", group: "engagement", toggleKey: "announcements_enabled", configure: "pengumuman" },
  { id: "customcmd", emoji: "⌨️", group: "engagement", toggleKey: "customcmd_enabled", configure: null },
  // Moderation
  { id: "automod", emoji: "🛡️", group: "moderation", toggleKey: "automod_enabled", configure: null },
  { id: "slowmode", emoji: "🐌", group: "moderation", toggleKey: "slowmode_enabled", configure: null },
  { id: "msglog", emoji: "📜", group: "moderation", toggleKey: "msglog_enabled", configure: null },
  // Utilities
  { id: "embed", emoji: "📝", group: "utilities", toggleKey: "embed_enabled", configure: "embed" },
  { id: "autopublish", emoji: "📢", group: "utilities", toggleKey: "autopublish_enabled", configure: null },
  { id: "templates", emoji: "📋", group: "utilities", toggleKey: null, configure: "template" },
];

export const TOGGLEABLE_PLUGINS: PluginDef[] = PLUGINS.filter((p) => p.toggleKey !== null);
