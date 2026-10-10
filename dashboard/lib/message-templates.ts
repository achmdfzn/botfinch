/**
 * Galeri "Pesan Keren": template pesan siap pakai untuk welcome, goodbye,
 * dan pengumuman.
 *
 * Aturan placeholder (terverifikasi dari repo bot, baca-saja):
 * - welcome/goodbye: bot mensubstitusi {user}, {server}, {member_count},
 *   dan {channel} via substitusi_variabel (src/utils/variabel.py),
 *   dipanggil dari on_member_join/on_member_remove (src/bot.py).
 * - pengumuman: bot mensubstitusi {server}, {date}, dan {member_count}
 *   via substitusi_pengumuman (src/cogs/dashboard_sync.py) — BUKAN
 *   teks apa adanya.
 *
 * Batas panjang: welcome/goodbye maks 500 karakter (cleanValue di
 * lib/settings.ts), pengumuman maks 2000 karakter (validasi API).
 */

export type TemplateCategory = "welcome" | "goodbye" | "announcement";

export interface MessageTemplate {
  /** ID unik, diawali kategori. */
  id: string;
  category: TemplateCategory;
  name: { id: string; en: string };
  /** Teks pesan dalam dua bahasa. Versi EN = terjemahan natural. */
  text: { id: string; en: string };
  /** Placeholder yang dipakai template ini. Hanya yang terbukti dirender bot. */
  placeholders: string[];
}

export const MESSAGE_TEMPLATES: MessageTemplate[] = [
  // ---------------------------------------------------------------- welcome
  {
    id: "w-formal",
    category: "welcome",
    name: { id: "Formal hangat", en: "Warm formal" },
    text: {
      id: "Selamat datang, {user}, di {server}. Kami senang kamu bergabung. Silakan baca peraturan di kanal informasi, perkenalkan dirimu, dan jangan ragu bertanya kepada moderator bila butuh bantuan.",
      en: "Welcome, {user}, to {server}. We are glad you joined. Please read the rules in the info channel, introduce yourself, and do not hesitate to ask a moderator if you need help.",
    },
    placeholders: ["{user}", "{server}"],
  },
  {
    id: "w-playful",
    category: "welcome",
    name: { id: "Playful", en: "Playful" },
    text: {
      id: "Wih, ada pendatang baru! Halo {user}, selamat mendarat di {server}. Ambil cemilan, pilih peranmu, dan langsung gas kenalan sama yang lain!",
      en: "Fresh face alert! Hey {user}, welcome aboard {server}. Grab a snack, pick your roles, and jump right in to meet everyone!",
    },
    placeholders: ["{user}", "{server}"],
  },
  {
    id: "w-minimalis",
    category: "welcome",
    name: { id: "Minimalis", en: "Minimalist" },
    text: {
      id: "Halo {user}, selamat datang di {server}.",
      en: "Hey {user}, welcome to {server}.",
    },
    placeholders: ["{user}", "{server}"],
  },
  {
    id: "w-epik",
    category: "welcome",
    name: { id: "Epik", en: "Epic" },
    text: {
      id: "Petualangan baru dimulai. {server} menyambut {user} dengan tangan terbuka. Semoga perjalananmu di sini penuh cerita seru dan teman yang asyik.",
      en: "A new adventure begins. {server} welcomes {user} with open arms. May your journey here be full of great stories and good company.",
    },
    placeholders: ["{user}", "{server}"],
  },
  {
    id: "w-santai",
    category: "welcome",
    name: { id: "Santai", en: "Casual" },
    text: {
      id: "Halo halo {user}! Selamat datang di {server}, tempat nongkrong paling asyik. Kenalin dirimu di channel perkenalan biar cepat akrab ya.",
      en: "Hey hey {user}! Welcome to {server}, the coziest hangout around. Drop an intro in the introductions channel so everyone gets to know you quickly.",
    },
    placeholders: ["{user}", "{server}"],
  },
  {
    id: "w-ramah-mod",
    category: "welcome",
    name: { id: "Ramah moderator", en: "Mod-friendly" },
    text: {
      id: "Selamat bergabung, {user}. Ini {server}, komunitas yang dijaga tetap nyaman untuk semua. Mulai dengan membaca panduan, lalu sapa anggota lain. Tim moderator siap membantu kapan pun.",
      en: "Welcome aboard, {user}. This is {server}, a community kept comfortable for everyone. Start by reading the guidelines, then say hi to the other members. The mod team is here to help anytime.",
    },
    placeholders: ["{user}", "{server}"],
  },
  // ---------------------------------------------------------------- goodbye
  {
    id: "g-hangat",
    category: "goodbye",
    name: { id: "Hangat", en: "Warm" },
    text: {
      id: "{user} baru saja pergi dari {server}. Terima kasih sudah mampir dan berbagi cerita. Pintu kami selalu terbuka kalau kamu ingin kembali.",
      en: "{user} just left {server}. Thanks for stopping by and sharing stories. Our door is always open if you ever want to come back.",
    },
    placeholders: ["{user}", "{server}"],
  },
  {
    id: "g-minimalis",
    category: "goodbye",
    name: { id: "Minimalis", en: "Minimalist" },
    text: {
      id: "{user} meninggalkan {server}. Sampai jumpa lagi.",
      en: "{user} left {server}. See you again sometime.",
    },
    placeholders: ["{user}", "{server}"],
  },
  {
    id: "g-playful",
    category: "goodbye",
    name: { id: "Playful", en: "Playful" },
    text: {
      id: "Waduh, {user} kabur dari {server}! Semoga betah di tempat barunya. Kalau kangen, kamu tahu jalannya pulang.",
      en: "Oh no, {user} slipped away from {server}! Hope the new place treats you well. If you miss us, you know the way back.",
    },
    placeholders: ["{user}", "{server}"],
  },
  {
    id: "g-formal",
    category: "goodbye",
    name: { id: "Formal", en: "Formal" },
    text: {
      id: "Kami mencatat {user} telah keluar dari {server}. Terima kasih atas partisipasinya selama ini. Semoga sukses di mana pun kamu berada.",
      en: "We note that {user} has left {server}. Thank you for your participation all this time. Wishing you success wherever you go.",
    },
    placeholders: ["{user}", "{server}"],
  },
  {
    id: "g-epik",
    category: "goodbye",
    name: { id: "Epik", en: "Epic" },
    text: {
      id: "Satu bab berakhir. {user} menutup petualangannya di {server} hari ini. Terima kasih untuk setiap momennya, dan semoga jalanmu selalu terang.",
      en: "One chapter ends. {user} closes their adventure in {server} today. Thanks for every moment, and may your road always be bright.",
    },
    placeholders: ["{user}", "{server}"],
  },
  {
    id: "g-santai",
    category: "goodbye",
    name: { id: "Santai", en: "Casual" },
    text: {
      id: "Dadah {user}! Makasih udah jadi bagian dari {server}. Jangan jadi orang asing ya, mampir-mampir kalau sempat.",
      en: "Bye {user}! Thanks for being part of {server}. Do not be a stranger, drop by whenever you can.",
    },
    placeholders: ["{user}", "{server}"],
  },
  // ------------------------------------------------------------ announcement
  {
    id: "a-rapat",
    category: "announcement",
    name: { id: "Rapat komunitas", en: "Community meeting" },
    text: {
      id: "Pengumuman untuk seluruh anggota: akan diadakan rapat komunitas pada hari Sabtu pukul 19.00 WIB di voice channel utama. Agenda: evaluasi kegiatan bulan ini dan rencana bulan depan. Kehadiran sangat diharapkan.",
      en: "Announcement for all members: a community meeting will be held Saturday at 7 PM (WIB) in the main voice channel. Agenda: this month's activity review and next month's plans. Your attendance is highly appreciated.",
    },
    placeholders: [],
  },
  {
    id: "a-event",
    category: "announcement",
    name: { id: "Event game night", en: "Game night event" },
    text: {
      id: "Game night minggu ini hadir lagi! Kumpul hari Jumat jam 20.00 WIB, game pilihan: Among Us dan Jackbox. Daftar ke panitia biar dapat slot. Pemenang dapat hadiah koin server!",
      en: "This week's game night is back! Gather Friday at 8 PM (WIB). Featured games: Among Us and Jackbox. Sign up with the organizers to grab a slot. Winners get server coins!",
    },
    placeholders: [],
  },
  {
    id: "a-aturan",
    category: "announcement",
    name: { id: "Pembaruan aturan", en: "Rules update" },
    text: {
      id: "Perhatian: mulai minggu depan berlaku aturan baru tentang promosi di server. Promosi hanya boleh di channel khusus promosi, maksimal satu pesan per hari. Pelanggaran akan diberi peringatan. Terima kasih atas pengertiannya.",
      en: "Attention: starting next week, new promotion rules take effect. Promotions are only allowed in the dedicated promo channel, one message per day max. Violations get a warning. Thanks for your understanding.",
    },
    placeholders: [],
  },
  {
    id: "a-terima-kasih",
    category: "announcement",
    name: { id: "Ucapan terima kasih", en: "Thank you note" },
    text: {
      id: "Terima kasih untuk semua yang ikut meramaikan event kemarin! Server ini hidup karena kalian. Nantikan event berikutnya, dan jangan lupa ajak teman-temanmu bergabung.",
      en: "Thank you to everyone who joined yesterday's event! This server thrives because of you. Stay tuned for the next event, and do not forget to invite your friends.",
    },
    placeholders: [],
  },
];

export const TEMPLATE_CATEGORIES: TemplateCategory[] = [
  "welcome",
  "goodbye",
  "announcement",
];

/** Nilai contoh untuk pratinjau (bukan data asli; jangan pakai nama pribadi). */
const SAMPLE_USER = "@ContohUser";

/** Substitusi placeholder dengan nilai contoh untuk pratinjau kartu. */
export function renderTemplatePreview(text: string, serverName: string): string {
  return text
    .replaceAll("{user}", SAMPLE_USER)
    .replaceAll("{server}", serverName);
}
