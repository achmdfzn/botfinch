// Definisi kartu plugin ala MEE6 untuk halaman /dashboard/[guildId]/plugins
// dan ringkasan status di overview. Nama + deskripsi diambil dari kamus i18n
// (dict.guild.plugins.cards[<id>]).
export type PluginGroup = "essentials" | "engagement" | "moderation" | "utilities";

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
   * "" = halaman overview (tab Pengaturan); null = tanpa tombol.
   */
  configure: string | null;
}

export const PLUGINS: PluginDef[] = [
  // Essentials
  { id: "welcome", emoji: "👋", group: "essentials", toggleKey: "welcome_enabled", configure: "" },
  { id: "leveling", emoji: "⭐", group: "essentials", toggleKey: "leveling_enabled", configure: null },
  { id: "selfroles", emoji: "🎭", group: "essentials", toggleKey: "selfroles_enabled", configure: "selfroles" },
  { id: "responder", emoji: "💬", group: "essentials", toggleKey: "responder_enabled", configure: "responder" },
  // Engagement & Fun
  { id: "economy", emoji: "🪙", group: "engagement", toggleKey: "economy_enabled", configure: null },
  { id: "starboard", emoji: "🌟", group: "engagement", toggleKey: "starboard_enabled", configure: null },
  { id: "giveaway", emoji: "🎉", group: "engagement", toggleKey: "giveaway_enabled", configure: "giveaway" },
  { id: "announcements", emoji: "📣", group: "engagement", toggleKey: "announcements_enabled", configure: "pengumuman" },
  // Moderation
  { id: "automod", emoji: "🛡️", group: "moderation", toggleKey: "automod_enabled", configure: null },
  // Utilities
  { id: "embed", emoji: "📝", group: "utilities", toggleKey: "embed_enabled", configure: "embed" },
  { id: "templates", emoji: "📋", group: "utilities", toggleKey: null, configure: "template" },
];

export const TOGGLEABLE_PLUGINS: PluginDef[] = PLUGINS.filter((p) => p.toggleKey !== null);
