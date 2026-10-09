import Link from "next/link";

const TABS = [
  { href: "", label: "Pengaturan" },
  { href: "/leaderboard", label: "Leaderboard" },
  { href: "/selfroles", label: "Self-roles" },
  { href: "/responder", label: "Auto-responder" },
  { href: "/giveaway", label: "Giveaway" },
  { href: "/embed", label: "Embed" },
  { href: "/pengumuman", label: "Pengumuman" },
  { href: "/modlog", label: "Mod Log" },
  { href: "/modul", label: "Modul" },
];

export default function GuildSubnav({ guildId, active }: { guildId: string; active: string }) {
  return (
    <nav aria-label="Bagian server" className="mt-6 flex gap-1 overflow-x-auto border-b border-edge">
      {TABS.map((t) => {
        const isActive = t.href === active;
        return (
          <Link
            key={t.href}
            href={`/dashboard/${guildId}${t.href}`}
            aria-current={isActive ? "page" : undefined}
            className={`whitespace-nowrap rounded-t-lg px-4 py-2.5 text-sm font-medium focus-visible:outline-2 focus-visible:outline-brand min-h-[44px] inline-flex items-center ${
              isActive ? "bg-panel text-zinc-50 border-b-2 border-brand" : "text-zinc-400 hover:text-zinc-100"
            }`}
          >
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
