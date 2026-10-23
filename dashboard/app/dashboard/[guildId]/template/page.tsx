import Link from "next/link";
import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { connection } from "next/server";
import SiteHeader from "@/components/SiteHeader";
import EmptyState from "@/components/EmptyState";
import GuildErrorState from "@/components/GuildErrorState";
import ReloadButton from "@/components/ReloadButton";
import PageHeader from "@/components/PageHeader";
import { getSessionSafe } from "@/lib/access";
import { canManage } from "@/lib/discord";
import { fetchUserGuilds } from "@/lib/access";
import {
  createAnnouncementWithQuota,
  dbConfigured,
  getEntitlement,
  getSnapshotChannel,
  latestSnapshot,
  mergeStoredSettings,
} from "@/lib/db";
import { FEATURE_LIMITS, getEffectiveTierFromRow } from "@/lib/premium";
import { requireManager } from "@/lib/access";
import { cleanValue } from "@/lib/settings";
import { discordId, str } from "@/lib/validate";
import { getDict, getLang } from "@/lib/i18n";
import {
  MESSAGE_TEMPLATES,
  TEMPLATE_CATEGORIES,
  renderTemplatePreview,
  type TemplateCategory,
} from "@/lib/message-templates";

export const instant = false;

export async function generateMetadata(): Promise<Metadata> {
  const dict = getDict(await getLang());
  return { title: `${dict.templates.metaTitle} | Finch Dashboard` };
}

const SETTING_KEY: Record<Exclude<TemplateCategory, "announcement">, string> = {
  welcome: "welcome_message",
  goodbye: "goodbye_message",
};

function tabUrl(guildId: string, cat: TemplateCategory, status?: "ok" | "error") {
  const base = `/dashboard/${guildId}/template?cat=${cat}`;
  return status ? `${base}&status=${status}` : base;
}

/** Simpan template sebagai welcome_message/goodbye_message (efek sama seperti PUT /api/guilds/[id]/settings). */
async function applyTemplate(formData: FormData) {
  "use server";
  const guildId = String(formData.get("guild_id") ?? "");
  const cat = String(formData.get("cat") ?? "welcome");
  const key = cat === "goodbye" ? SETTING_KEY.goodbye : SETTING_KEY.welcome;
  const back = tabUrl(guildId, cat === "goodbye" ? "goodbye" : "welcome");
  if (await requireManager(guildId)) redirect(`${back}&status=error`);
  const clean = cleanValue(key, formData.get("text"));
  if (clean === undefined) redirect(`${back}&status=error`);
  // Merge atomik (jsonb ||) — bukan read-modify-write: bila user menerapkan
  // template sementara toggle diubah di tab lain, kedua tulisan tetap bertahan.
  await mergeStoredSettings(guildId, { [key]: clean });
  redirect(`${back}&status=ok`);
}

/**
 * Buat pengumuman sekali-kirim dari template (efek sama seperti
 * POST /api/guilds/[id]/announcements, termasuk validasi + kuotanya):
 * channel wajib ada di snapshot guild ini dan bertipe teks/news (0/5),
 * lalu pembuatan lewat createAnnouncementWithQuota (atomik) dengan limit
 * announcements_active per tier efektif. Kuota penuh (null) = error,
 * sama seperti channel tidak valid.
 */
async function createAnnouncementFromTemplate(formData: FormData) {
  "use server";
  const guildId = String(formData.get("guild_id") ?? "");
  const back = tabUrl(guildId, "announcement");
  if (await requireManager(guildId)) redirect(`${back}&status=error`);
  const channelId = discordId(formData.get("channel_id"));
  const message = str(formData.get("text"), 2000, true);
  if (!channelId || !message) redirect(`${back}&status=error`);
  const target = await getSnapshotChannel(guildId, channelId);
  if (!target || (target.type !== 0 && target.type !== 5)) {
    redirect(`${back}&status=error`);
  }
  const tier = getEffectiveTierFromRow(await getEntitlement(guildId));
  const limit = FEATURE_LIMITS.announcements_active[tier];
  const annId = await createAnnouncementWithQuota(
    {
      guildId,
      channelId,
      message,
      runAt: new Date().toISOString(),
      intervalMinutes: null,
    },
    limit,
  );
  if (annId === null) redirect(`${back}&status=error`);
  redirect(`${back}&status=ok`);
}

const inputCls =
  "rounded-lg border border-edge bg-ink px-3 py-2 text-sm text-fg focus-visible:outline-2 focus-visible:outline-brand min-h-[44px]";
const buttonCls =
  "rounded-lg bg-brand px-6 py-2.5 text-sm font-semibold text-ink hover:bg-brand-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand min-h-[44px]";

export default async function GuildTemplate({
  params,
  searchParams,
}: {
  params: Promise<{ guildId: string }>;
  searchParams: Promise<{ cat?: string; status?: string }>;
}) {
  await connection();
  const lang = await getLang();
  const dict = getDict(lang);
  const t = dict.templates;
  const { guildId } = await params;
  const sp = await searchParams;
  const cat: TemplateCategory = TEMPLATE_CATEGORIES.includes(sp.cat as TemplateCategory)
    ? (sp.cat as TemplateCategory)
    : "welcome";
  const status = sp.status === "ok" || sp.status === "error" ? sp.status : null;

  const session = await getSessionSafe();
  if (!session?.accessToken) {
    return (
      <div>
        <SiteHeader />
        <main className="mx-auto max-w-3xl px-4 py-16">
          <EmptyState title={dict.guild.common.signinTitle} body={t.signinBody} />
        </main>
      </div>
    );
  }

  let guildName = guildId;
  // notFound() dipanggil di luar try/catch: ia melempar error kontrol
  // Next yang tidak boleh tertelan catch — guild tak ditemukan harus 404.
  let guilds: Awaited<ReturnType<typeof fetchUserGuilds>>;
  try {
    guilds = await fetchUserGuilds(session.accessToken);
  } catch {
    return (
      <div>
        <SiteHeader />
        <main className="mx-auto max-w-3xl px-4 py-16">
          <EmptyState title={dict.guild.common.loadTitle} body={dict.guild.common.loadBody} action={<ReloadButton />} />
        </main>
      </div>
    );
  }

  const mine = guilds.find((g) => g.id === guildId && canManage(g));
  if (!mine) notFound();
  guildName = mine.name;

  if (!dbConfigured()) {
    return <GuildErrorState title={dict.guild.common.dbTitle} body={t.dbBody} />;
  }

  const snap = await latestSnapshot();
  const snapGuild = snap?.guilds.find((g) => g.id === guildId);
  const channels = snapGuild?.channels ?? [];
  const shown = MESSAGE_TEMPLATES.filter((m) => m.category === cat);

  const statusOk = status === "ok";
  const statusText = statusOk
    ? cat === "announcement"
      ? t.createOk
      : t.applyOk
    : cat === "announcement"
      ? t.createError
      : t.applyError;

  return (
    // Full-width mengikuti shell: galeri kartu template memakai seluruh
    // lebar konten (grid melebar ke 3 kolom di xl), bukan kolom sempit.
    <div className="w-full">
      <Link
        href="/dashboard"
        className="inline-flex min-h-[44px] items-center text-sm text-muted hover:text-fg focus-visible:outline-2 focus-visible:outline-brand"
      >
        {dict.nav.back}
      </Link>
      <div className="mt-3">
        <PageHeader title={t.metaTitle} description={t.subtitle} />
      </div>

      {status && (
        <div
          role="status"
          className={`mb-5 rounded-xl border px-4 py-3 text-sm ${
            statusOk
              ? "border-green-500/40 bg-green-500/10 text-green-400"
              : "border-red-500/40 bg-red-500/10 text-red-400"
          }`}
        >
          <span className="font-semibold">{statusOk ? t.statusOk : t.statusError}: </span>
          {statusText}
        </div>
      )}

      <nav aria-label={t.metaTitle} className="mb-6 flex flex-wrap gap-1">
        {TEMPLATE_CATEGORIES.map((c) => {
          const active = c === cat;
          return (
            <Link
              key={c}
              href={tabUrl(guildId, c)}
              aria-current={active ? "page" : undefined}
              className={`flex min-h-[44px] items-center rounded-lg px-4 py-2.5 text-sm font-medium focus-visible:outline-2 focus-visible:outline-brand ${
                active ? "bg-edge text-fg" : "text-muted hover:bg-edge hover:text-fg"
              }`}
            >
              {t.tabs[c]}
            </Link>
          );
        })}
      </nav>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {shown.map((tpl) => {
          const text = tpl.text[lang];
          const preview =
            cat === "announcement" ? text : renderTemplatePreview(text, guildName);
          return (
            <article
              key={tpl.id}
              className="flex flex-col rounded-xl border border-edge bg-panel p-5"
            >
              <h2 className="text-base font-semibold text-fg">{tpl.name[lang]}</h2>

              <p className="mt-1 text-xs font-medium text-muted">{t.previewLabel}</p>
              <div className="mt-1 rounded-lg border border-edge bg-ink p-3">
                <p className="whitespace-pre-wrap text-sm text-fg">{preview}</p>
              </div>
              {cat !== "announcement" && (
                <p className="mt-2 text-xs text-muted">{t.previewHint}</p>
              )}

              <div className="mt-3 flex flex-wrap items-center gap-1.5">
                <span className="text-xs font-medium text-muted">{t.placeholdersLabel}:</span>
                {tpl.placeholders.length > 0 ? (
                  tpl.placeholders.map((ph) => (
                    <code
                      key={ph}
                      className="rounded bg-edge px-1.5 py-0.5 font-mono text-xs text-fg"
                    >
                      {ph}
                    </code>
                  ))
                ) : (
                  <span className="text-xs text-muted">{t.noPlaceholders}</span>
                )}
              </div>

              <div className="mt-4 flex-1" />

              {cat === "announcement" ? (
                <form action={createAnnouncementFromTemplate} className="mt-2 space-y-3">
                  <input type="hidden" name="guild_id" value={guildId} />
                  <input type="hidden" name="text" value={text} />
                  <div>
                    <label
                      htmlFor={`tpl-channel-${tpl.id}`}
                      className="text-xs font-medium text-muted"
                    >
                      {t.channelLabel}
                    </label>
                    <select
                      id={`tpl-channel-${tpl.id}`}
                      name="channel_id"
                      required
                      defaultValue=""
                      className={`${inputCls} mt-1 w-full`}
                    >
                      <option value="">{t.selectChannel}</option>
                      {channels
                        .filter((c) => c.type === 0 || c.type === 5)
                        .map((c) => (
                          <option key={c.id} value={c.id}>
                            #{c.name}
                          </option>
                        ))}
                    </select>
                    {channels.length === 0 && (
                      <p className="mt-1 text-xs text-muted">{t.noChannelsHint}</p>
                    )}
                  </div>
                  <p className="text-xs text-muted">{t.sendNowHint}</p>
                  <button type="submit" className={`${buttonCls} w-full`}>
                    {t.create}
                  </button>
                </form>
              ) : (
                <form action={applyTemplate} className="mt-2">
                  <input type="hidden" name="guild_id" value={guildId} />
                  <input type="hidden" name="cat" value={cat} />
                  <input type="hidden" name="text" value={text} />
                  <button type="submit" className={`${buttonCls} w-full`}>
                    {t.apply}
                  </button>
                </form>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}
