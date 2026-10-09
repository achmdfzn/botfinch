export type FieldKind = "toggle" | "number" | "text" | "textarea" | "channel" | "levelroles" | "select";

export interface FieldDef {
  key: string;
  label: string;
  kind: FieldKind;
  min?: number;
  max?: number;
  placeholder?: string;
  hint?: string;
  /** Nilai yang diizinkan untuk kind "select". Label tiap nilai diambil dari kamus. */
  options?: string[];
}

export interface ModuleDef {
  key: string;
  title: string;
  description: string;
  fields: FieldDef[];
}

type Rule =
  | { kind: "bool" }
  | { kind: "str"; max: number }
  | { kind: "num"; min: number; max: number }
  | { kind: "enum"; values: string[] };

export const SETTING_DEFAULTS: Record<string, boolean | string | number> = {
  // modul utama
  welcome_enabled: true,
  welcome_channel_id: "",
  leveling_enabled: true,
  economy_enabled: true,
  automod_enabled: true,
  starboard_enabled: false,
  starboard_channel_id: "",
  starboard_threshold: 3,
  // welcome detail
  welcome_message: "",
  welcome_theme: "default",
  // goodbye detail
  goodbye_enabled: true,
  goodbye_channel_id: "",
  goodbye_message: "",
  // leveling detail
  leveling_xp_rate: 100,
  leveling_announce_channel_id: "",
  leveling_roles: "[]",
  levelup_style: "classic",
  // automod detail
  automod_spam: true,
  automod_invites: true,
  automod_caps: true,
  automod_badwords: true,
  automod_mute_minutes: 10,
  automod_log_channel_id: "",
  // ekonomi detail
  economy_daily: 100,
  economy_work_min: 50,
  economy_work_max: 150,
};

export const SETTING_RULES: Record<string, Rule> = {
  welcome_enabled: { kind: "bool" },
  welcome_channel_id: { kind: "str", max: 32 },
  leveling_enabled: { kind: "bool" },
  economy_enabled: { kind: "bool" },
  automod_enabled: { kind: "bool" },
  starboard_enabled: { kind: "bool" },
  starboard_channel_id: { kind: "str", max: 32 },
  starboard_threshold: { kind: "num", min: 1, max: 25 },
  welcome_message: { kind: "str", max: 500 },
  welcome_theme: { kind: "enum", values: ["default", "midnight", "sunset", "ocean"] },
  goodbye_enabled: { kind: "bool" },
  goodbye_channel_id: { kind: "str", max: 32 },
  goodbye_message: { kind: "str", max: 500 },
  leveling_xp_rate: { kind: "num", min: 25, max: 400 },
  leveling_announce_channel_id: { kind: "str", max: 32 },
  leveling_roles: { kind: "str", max: 4000 },
  levelup_style: { kind: "enum", values: ["classic", "minimal", "party", "mention"] },
  automod_spam: { kind: "bool" },
  automod_invites: { kind: "bool" },
  automod_caps: { kind: "bool" },
  automod_badwords: { kind: "bool" },
  automod_mute_minutes: { kind: "num", min: 1, max: 10080 },
  automod_log_channel_id: { kind: "str", max: 32 },
  economy_daily: { kind: "num", min: 0, max: 100000 },
  economy_work_min: { kind: "num", min: 0, max: 100000 },
  economy_work_max: { kind: "num", min: 0, max: 100000 },
};

export const MODULES: ModuleDef[] = [
  {
    key: "welcome_enabled",
    title: "Welcome",
    description: "Kirim kartu selamat datang bergambar tiap ada member baru.",
    fields: [
      { key: "welcome_channel_id", label: "Channel welcome", kind: "channel" },
      {
        key: "welcome_theme",
        label: "Tema kartu welcome",
        kind: "select",
        options: ["default", "midnight", "sunset", "ocean"],
      },
      {
        key: "welcome_message",
        label: "Pesan custom",
        kind: "textarea",
        placeholder: "Selamat datang {user} di {server}!",
        hint: "Bisa pakai {user} dan {server}. Kosongkan untuk kartu default.",
      },
    ],
  },
  {
    key: "goodbye_enabled",
    title: "Goodbye",
    description: "Kirim pesan perpisahan tiap ada member yang keluar dari server.",
    fields: [
      { key: "goodbye_channel_id", label: "Channel goodbye", kind: "channel" },
      {
        key: "goodbye_message",
        label: "Pesan custom",
        kind: "textarea",
        placeholder: "Sampai jumpa {user}, terima kasih sudah mampir di {server}!",
        hint: "Bisa pakai {user} dan {server}. Kosongkan untuk pesan default.",
      },
    ],
  },
  {
    key: "leveling_enabled",
    title: "Leveling",
    description: "XP otomatis tiap chat dan voice, lengkap dengan rank card.",
    fields: [
      {
        key: "leveling_xp_rate",
        label: "Kecepatan XP (%)",
        kind: "number",
        min: 25,
        max: 400,
        hint: "100 = normal, 200 = dua kali lipat.",
      },
      { key: "leveling_announce_channel_id", label: "Channel pengumuman naik level", kind: "channel" },
      {
        key: "leveling_roles",
        label: "Role reward per level",
        kind: "levelroles",
        hint: "Member otomatis dapat role saat mencapai level.",
      },
      {
        key: "levelup_style",
        label: "Gaya pesan level-up",
        kind: "select",
        options: ["classic", "minimal", "party", "mention"],
      },
    ],
  },
  {
    key: "economy_enabled",
    title: "Ekonomi",
    description: "Koin, daily, kerja, bank, dan toko. Mati = semua command ekonomi ditolak.",
    fields: [
      { key: "economy_daily", label: "Hadiah /daily", kind: "number", min: 0, max: 100000 },
      { key: "economy_work_min", label: "/kerja minimal", kind: "number", min: 0, max: 100000 },
      { key: "economy_work_max", label: "/kerja maksimal", kind: "number", min: 0, max: 100000 },
    ],
  },
  {
    key: "automod_enabled",
    title: "AutoMod",
    description: "Moderasi otomatis dengan aturan yang bisa dipilih.",
    fields: [
      { key: "automod_spam", label: "Anti-spam", kind: "toggle" },
      { key: "automod_invites", label: "Anti invite link", kind: "toggle" },
      { key: "automod_caps", label: "Anti caps berlebihan", kind: "toggle" },
      { key: "automod_badwords", label: "Filter kata kasar", kind: "toggle" },
      { key: "automod_mute_minutes", label: "Durasi mute (menit)", kind: "number", min: 1, max: 10080 },
      { key: "automod_log_channel_id", label: "Channel log moderasi", kind: "channel" },
    ],
  },
  {
    key: "starboard_enabled",
    title: "Starboard",
    description: "Pesan berbintang diteruskan ke channel khusus.",
    fields: [
      { key: "starboard_channel_id", label: "Channel starboard", kind: "channel" },
      { key: "starboard_threshold", label: "Minimal bintang", kind: "number", min: 1, max: 25 },
    ],
  },
];

/** Validasi satu nilai sesuai rule. Kembalikan nilai bersih atau undefined (tolak). */
export function cleanValue(key: string, v: unknown): boolean | string | number | undefined {
  const rule = SETTING_RULES[key];
  if (!rule) return undefined;
  if (rule.kind === "bool") return typeof v === "boolean" ? v : undefined;
  if (rule.kind === "enum") return typeof v === "string" && rule.values.includes(v) ? v : undefined;
  if (rule.kind === "str") {
    if (typeof v !== "string") return undefined;
    if (key === "leveling_roles" && !validLevelRoles(v)) return undefined;
    // ID channel: hanya digit (atau kosong = otomatis)
    if (key.endsWith("_channel_id") && v !== "" && !/^\d{1,25}$/.test(v)) return undefined;
    return v.slice(0, rule.max);
  }
  if (typeof v !== "number" || !Number.isFinite(v)) return undefined;
  return Math.max(rule.min, Math.min(rule.max, Math.floor(v)));
}

function validLevelRoles(s: string): boolean {
  try {
    const arr = JSON.parse(s);
    if (!Array.isArray(arr) || arr.length > 40) return false;
    return arr.every(
      (r) =>
        r &&
        typeof r === "object" &&
        Number.isInteger(r.level) &&
        r.level >= 1 &&
        r.level <= 500 &&
        typeof r.role_id === "string" &&
        /^\d{5,25}$/.test(r.role_id),
    );
  } catch {
    return false;
  }
}

export function mergeSettings(stored: Record<string, unknown>): Record<string, boolean | string | number> {
  const out: Record<string, boolean | string | number> = { ...SETTING_DEFAULTS };
  for (const [k, v] of Object.entries(stored)) {
    if (k in SETTING_DEFAULTS) {
      const clean = cleanValue(k, v);
      if (clean !== undefined) out[k] = clean;
    }
  }
  return out;
}
