import { STATS } from "@/lib/stats";

interface Props {
  guildName: string;
  guildIconUrl: string | null;
  activePlugins: number;
  totalPlugins: number;
  subtitle: string;
  statPlugins: string;
  statCommands: string;
  statCogs: string;
}

/**
 * Banner header lebar di halaman utama dashboard per-server (halaman
 * Plugins), ala banner MEE6 — tapi isinya 100% orisinal dan jujur:
 * identitas server + sapaan singkat + angka nyata (plugin aktif dari
 * settings, jumlah perintah & cog dari lib/stats.ts yang terverifikasi
 * dari kode). Tanpa promo, tanpa klaim palsu.
 *
 * Server component: di-refresh via router.refresh() tiap toggle plugin
 * berubah (lihat PluginCards.toggle) sehingga hitungan plugin aktif
 * selalu sinkron.
 */
export default function GuildHero({
  guildName,
  guildIconUrl,
  activePlugins,
  totalPlugins,
  subtitle,
  statPlugins,
  statCommands,
  statCogs,
}: Props) {
  return (
    <section
      aria-label={guildName}
      className="relative mb-6 overflow-hidden rounded-2xl border border-edge bg-gradient-to-br from-brand/15 via-panel to-panel p-5 sm:p-7"
    >
      {/* Dekorasi orisinal: lingkaran blur brand */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-brand/20 blur-3xl"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -bottom-20 -left-10 h-48 w-48 rounded-full bg-brand/10 blur-3xl"
      />
      <div className="relative flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-4">
          {guildIconUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={guildIconUrl}
              alt=""
              width={64}
              height={64}
              className="h-16 w-16 shrink-0 rounded-2xl"
            />
          ) : (
            <div
              aria-hidden="true"
              className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-brand/20 text-2xl font-bold text-brand"
            >
              {guildName.charAt(0).toUpperCase()}
            </div>
          )}
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-bold text-fg">{guildName}</h1>
            <p className="mt-1 text-sm text-muted">{subtitle}</p>
          </div>
        </div>
        <dl className="flex shrink-0 gap-6 sm:gap-8">
          <div>
            <dt className="text-xs text-muted">{statPlugins}</dt>
            <dd className="text-2xl font-bold text-fg">
              {activePlugins}
              <span className="text-sm font-normal text-muted">/{totalPlugins}</span>
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted">{statCommands}</dt>
            <dd className="text-2xl font-bold text-fg">{STATS.commands}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">{statCogs}</dt>
            <dd className="text-2xl font-bold text-fg">{STATS.cogs}</dd>
          </div>
        </dl>
      </div>
    </section>
  );
}
