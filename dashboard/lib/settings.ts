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
  /**
   * Untuk kind "channel": tipe channel Discord yang boleh dipilih
   * (0 = teks, 2 = voice, 4 = kategori, 5 = pengumuman).
   * Default [0, 5] bila tidak diisi.
   */
  channelTypes?: number[];
}

export interface ModuleDef {
  key: string;
  title: string;
  description: string;
  fields: FieldDef[];
  /**
   * true = seksi tanpa switch master (murni kumpulan field konfigurasi,
   * mis. channel per-server). Switch master tidak dirender di halaman
   * pengaturan, dan seksi dilewati di halaman modul agar tidak ada
   * switch mati.
   */
  noToggle?: boolean;
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
  welcome_role_ids: "",
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
  // toggle plugin baru (bot menentukan default sendiri; dasbor memakai true)
  selfroles_enabled: true,
  giveaway_enabled: true,
  responder_enabled: true,
  announcements_enabled: true,
  embed_enabled: true,
  // toggle plugin baru: custom commands, slowmode, message log, auto-publish
  customcmd_enabled: true,
  slowmode_enabled: true,
  msglog_enabled: true,
  autopublish_enabled: true,
  // channel/kategori per-server ("" = ikut config global .env di sisi bot)
  verify_channel_id: "",
  ticket_category_id: "",
  saran_channel_id: "",
  counting_channel_id: "",
  tempvc_lobby_id: "",
  tempvc_category_id: "",
  confess_channel_id: "",
  dailyq_channel_id: "",
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
  welcome_role_ids: { kind: "str", max: 500 },
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
  selfroles_enabled: { kind: "bool" },
  giveaway_enabled: { kind: "bool" },
  responder_enabled: { kind: "bool" },
  announcements_enabled: { kind: "bool" },
  embed_enabled: { kind: "bool" },
  customcmd_enabled: { kind: "bool" },
  slowmode_enabled: { kind: "bool" },
  msglog_enabled: { kind: "bool" },
  autopublish_enabled: { kind: "bool" },
  verify_channel_id: { kind: "str", max: 32 },
  ticket_category_id: { kind: "str", max: 32 },
  saran_channel_id: { kind: "str", max: 32 },
  counting_channel_id: { kind: "str", max: 32 },
  tempvc_lobby_id: { kind: "str", max: 32 },
  tempvc_category_id: { kind: "str", max: 32 },
  confess_channel_id: { kind: "str", max: 32 },
  dailyq_channel_id: { kind: "str", max: 32 },
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
      {
        key: "welcome_role_ids",
        label: "Role otomatis (ID, pisah koma)",
        kind: "text",
        placeholder: "123456789, 987654321",
        hint: "Role diberikan otomatis saat member join. Kosongkan bila tidak perlu.",
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
  // --- Seksi tanpa switch master: konfigurasi channel/kategori per-server.
  // Kosongkan = bot memakai nilai global dari .env (perilaku lama).
  {
    key: "verifikasi",
    title: "Verifikasi",
    description: "Channel tempat panel tombol verifikasi dipasang via /verifikasi.",
    noToggle: true,
    fields: [
      {
        key: "verify_channel_id",
        label: "Channel verifikasi",
        kind: "channel",
        hint: "Kosongkan untuk memakai VERIFY_CHANNEL_ID dari .env.",
      },
    ],
  },
  {
    key: "tiket",
    title: "Tiket Support",
    description: "Kategori tempat channel tiket baru dibuat.",
    noToggle: true,
    fields: [
      {
        key: "ticket_category_id",
        label: "Kategori tiket",
        kind: "channel",
        channelTypes: [4],
        hint: "Kosongkan untuk memakai TICKET_CATEGORY_ID dari .env.",
      },
    ],
  },
  {
    key: "komunitas",
    title: "Komunitas",
    description: "Channel untuk fitur komunitas: saran, counting, confess, dan pertanyaan harian.",
    noToggle: true,
    fields: [
      {
        key: "saran_channel_id",
        label: "Channel saran",
        kind: "channel",
        hint: "Tempat saran dari /saran dikirim. Kosongkan = SARAN_CHANNEL_ID (.env).",
      },
      {
        key: "counting_channel_id",
        label: "Channel counting",
        kind: "channel",
        hint: "Permainan berhitung. Kosongkan = COUNTING_CHANNEL_ID (.env).",
      },
      {
        key: "confess_channel_id",
        label: "Channel confess",
        kind: "channel",
        hint: "Tempat pesan anonim /confess dikirim. Kosongkan = CONFESS_CHANNEL_ID (.env).",
      },
      {
        key: "dailyq_channel_id",
        label: "Channel pertanyaan harian",
        kind: "channel",
        hint: "Pertanyaan harian otomatis. Kosongkan = DAILYQ_CHANNEL_ID (.env).",
      },
    ],
  },
  {
    key: "tempvc",
    title: "Temp Voice",
    description: "Voice channel sementara: member join lobby lalu dapat room pribadi.",
    noToggle: true,
    fields: [
      {
        key: "tempvc_lobby_id",
        label: "Voice lobby",
        kind: "channel",
        channelTypes: [2],
        hint: "Voice channel pemicu. Kosongkan = TEMPVC_LOBBY_ID (.env).",
      },
      {
        key: "tempvc_category_id",
        label: "Kategori room",
        kind: "channel",
        channelTypes: [4],
        hint: "Kategori tempat room dibuat. Kosongkan = TEMPVC_CATEGORY_ID (.env).",
      },
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
    // CSV ID role: kosong (tak perlu auto-role) atau daftar ID digit,
    // mis. "123456789, 987654321". Tolak format lain agar bot tidak
    // menerima ID role sampah.
    if (
      key === "welcome_role_ids" &&
      v !== "" &&
      !/^(\d{5,25})(,\s*\d{5,25})*$/.test(v)
    )
      return undefined;
    // ID channel/kategori/lobby: hanya digit (atau kosong = ikut config global bot)
    if (
      (key.endsWith("_channel_id") ||
        key.endsWith("_category_id") ||
        key.endsWith("_lobby_id")) &&
      v !== "" &&
      !/^\d{1,25}$/.test(v)
    )
      return undefined;
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
