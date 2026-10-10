"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import type { SnapshotChannel } from "@/lib/db";
import { useI18n } from "@/components/I18nProvider";
import { fmt } from "@/lib/i18n/client";

const inputCls =
  "rounded-lg border border-edge bg-ink px-3 py-2 text-sm text-fg focus-visible:outline-2 focus-visible:outline-brand min-h-[44px]";

// Nama warna mengikuti kamus (colorNames), supaya ikut ganti bahasa.
const PRESETS = [
  { key: "teal", hex: "#2EC4B6" },
  { key: "blue", hex: "#5865F2" },
  { key: "green", hex: "#57F287" },
  { key: "yellow", hex: "#FEE75C" },
  { key: "orange", hex: "#EB459E" },
  { key: "red", hex: "#ED4245" },
] as const;

interface EmbedField {
  name: string;
  value: string;
  inline: boolean;
}

interface EmbedRequest {
  id: number;
  channel_id: string;
  title: string;
  status: string;
  note: string | null;
  created_at: string;
}

const HEX_RE = /^#[0-9a-fA-F]{6}$/;

export default function EmbedBuilder({
  guildId,
  channels,
}: {
  guildId: string;
  channels: SnapshotChannel[];
}) {
  const { lang, dict } = useI18n();
  const g = dict.guild.embed;
  const locale = lang === "en" ? "en-US" : "id-ID";

  const [channelId, setChannelId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [color, setColor] = useState<string>(PRESETS[0].hex);
  const [fields, setFields] = useState<EmbedField[]>([]);
  const [footer, setFooter] = useState("");
  const [imageUrl, setImageUrl] = useState("");
  const [thumbnailUrl, setThumbnailUrl] = useState("");
  const [sending, setSending] = useState(false);
  const [status, setStatus] = useState<"idle" | "ok" | "error">("idle");
  const [requests, setRequests] = useState<EmbedRequest[]>([]);
  const [loadingReq, setLoadingReq] = useState(true);
  const [reqError, setReqError] = useState(false);
  // Error khusus refresh pasca-kirim: list lama tetap tampil + peringatan.
  const [refreshError, setRefreshError] = useState(false);

  // Refresh riwayat TANPA mengganti list dengan teks "loading":
  // list lama tetap tampil (tidak berkedip); bila refresh gagal, list lama
  // dipertahankan dan pesan error ditampilkan.
  async function reload() {
    setRefreshError(false);
    try {
      const res = await fetch(`/api/guilds/${guildId}/embed-requests`);
      if (!res.ok) throw new Error("http");
      const data = await res.json();
      setRequests(data.embed_requests ?? []);
    } catch {
      setRefreshError(true);
    }
  }

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await fetch(`/api/guilds/${guildId}/embed-requests`);
        if (alive) {
          if (res.ok) {
            const data = await res.json();
            setRequests(data.embed_requests ?? []);
          } else {
            setReqError(true);
          }
        }
      } catch {
        if (alive) setReqError(true);
      } finally {
        if (alive) setLoadingReq(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [guildId]);

  // Hanya channel teks yang bisa menerima kiriman (voice/stage tidak).
  const textChannels = channels.filter((c) => c.type === 0 || c.type === 5);
  const channelName = (id: string) => channels.find((c) => c.id === id)?.name ?? id;

  function addField() {
    if (fields.length >= 10) return;
    setFields((f) => [...f, { name: "", value: "", inline: false }]);
  }

  function updateField(i: number, patch: Partial<EmbedField>) {
    setFields((f) => f.map((fld, j) => (j === i ? { ...fld, ...patch } : fld)));
  }

  function removeField(i: number) {
    setFields((f) => f.filter((_, j) => j !== i));
  }

  const canSend = channelId && title.trim().length > 0 && HEX_RE.test(color) && !sending;

  async function send() {
    if (!canSend) return;
    setStatus("idle");
    setSending(true);
    try {
      const res = await fetch(`/api/guilds/${guildId}/embed-requests`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          channel_id: channelId,
          title: title.trim(),
          description: description.trim(),
          color: color.replace(/^#/, "").toUpperCase(), // API menerima 6 char hex tanpa #
          fields: fields
            .filter((f) => f.name.trim() && f.value.trim())
            .map((f) => ({ name: f.name.trim(), value: f.value.trim(), inline: f.inline })),
          footer: footer.trim(),
          image_url: imageUrl.trim(),
          thumbnail_url: thumbnailUrl.trim(),
        }),
      });
      if (res.ok) {
        setStatus("ok");
        // Reset form agar klik "Kirim" lagi tidak mengirim duplikat.
        setChannelId("");
        setTitle("");
        setDescription("");
        setColor(PRESETS[0].hex);
        setFields([]);
        setFooter("");
        setImageUrl("");
        setThumbnailUrl("");
        reload();
      } else {
        setStatus("error");
      }
    } catch {
      setStatus("error");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-2">
      {/* Form */}
      <div className="rounded-xl border border-edge bg-panel p-5">
        <h2 className="text-sm font-semibold text-fg">{g.formTitle}</h2>

        <div className="mt-4">
          <label htmlFor="eb-channel" className="text-xs font-medium text-muted">{g.channelLabel}</label>
          <select
            id="eb-channel"
            value={channelId}
            onChange={(e) => setChannelId(e.target.value)}
            className={`${inputCls} mt-1 w-full`}
          >
            <option value="">{g.selectChannel}</option>
            {textChannels.map((c) => (
              <option key={c.id} value={c.id}>
                #{c.name}
              </option>
            ))}
          </select>
          {textChannels.length === 0 && (
            <p className="mt-1 text-xs text-muted">{g.noChannelsHint}</p>
          )}
        </div>

        <div className="mt-3">
          <label htmlFor="eb-title" className="text-xs font-medium text-muted">{g.titleLabel}</label>
          <input
            id="eb-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={g.titlePlaceholder}
            maxLength={256}
            className={`${inputCls} mt-1 w-full`}
          />
        </div>

        <div className="mt-3">
          <label htmlFor="eb-desc" className="text-xs font-medium text-muted">{g.descLabel}</label>
          <textarea
            id="eb-desc"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder={g.descPlaceholder}
            rows={4}
            maxLength={4000}
            className={`${inputCls} mt-1 w-full resize-y`}
          />
        </div>

        <div className="mt-3">
          <span id="eb-color-label" className="text-xs font-medium text-muted">{g.colorLabel}</span>
          <div className="mt-1 flex flex-wrap items-center gap-2" role="group" aria-labelledby="eb-color-label">
            {PRESETS.map((p) => {
              const name = g.colorNames[p.key];
              const selected = color.toUpperCase() === p.hex.toUpperCase();
              return (
                <button
                  key={p.hex}
                  type="button"
                  title={name}
                  aria-label={fmt(g.colorAria, { name })}
                  aria-pressed={selected}
                  onClick={() => setColor(p.hex)}
                  style={{ backgroundColor: p.hex }}
                  className={`h-11 w-11 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand ${
                    selected ? "ring-2 ring-fg ring-offset-2 ring-offset-panel" : ""
                  }`}
                />
              );
            })}
            <input
              type="color"
              aria-label={g.colorCustom}
              value={HEX_RE.test(color) ? color : "#2EC4B6"}
              onChange={(e) => setColor(e.target.value.toUpperCase())}
              className="h-11 w-14 cursor-pointer rounded-lg border border-edge bg-ink p-1"
            />
            <input
              aria-label={g.colorHex}
              value={color}
              onChange={(e) => setColor(e.target.value.toUpperCase())}
              placeholder="#2EC4B6"
              maxLength={7}
              className={`${inputCls} w-28`}
            />
          </div>
          {!HEX_RE.test(color) && (
            <p className="mt-1 text-xs text-red-400">{g.colorInvalid}</p>
          )}
        </div>

        <div className="mt-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted">{fmt(g.fieldsLabel, { n: fields.length })}</span>
            <button
              type="button"
              onClick={addField}
              disabled={fields.length >= 10}
              className="rounded-lg border border-edge px-3 py-2 text-sm text-fg hover:bg-edge disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-brand min-h-[44px]"
            >
              {g.addField}
            </button>
          </div>
          {fields.map((f, i) => (
            <div key={i} className="mt-2 rounded-lg border border-edge bg-ink p-3">
              <div className="grid gap-2 sm:grid-cols-2">
                <input
                  aria-label={fmt(g.fieldNameAria, { n: i + 1 })}
                  value={f.name}
                  onChange={(e) => updateField(i, { name: e.target.value })}
                  placeholder={g.fieldName}
                  maxLength={256}
                  className={inputCls}
                />
                <div className="flex items-center gap-2">
                  <label className="flex min-h-[44px] cursor-pointer items-center gap-2 text-xs text-muted">
                    <input
                      type="checkbox"
                      checked={f.inline}
                      onChange={(e) => updateField(i, { inline: e.target.checked })}
                      className="h-5 w-5 accent-brand"
                    />
                    {g.inline}
                  </label>
                  <button
                    type="button"
                    onClick={() => removeField(i)}
                    className="ml-auto rounded-lg border border-edge px-3 py-1.5 text-xs text-red-400 hover:bg-edge focus-visible:outline-2 focus-visible:outline-brand min-h-[44px]"
                  >
                    {dict.common.remove}
                  </button>
                </div>
              </div>
              <input
                aria-label={fmt(g.fieldValueAria, { n: i + 1 })}
                value={f.value}
                onChange={(e) => updateField(i, { value: e.target.value })}
                placeholder={g.fieldValue}
                maxLength={1024}
                className={`${inputCls} mt-2 w-full`}
              />
            </div>
          ))}
        </div>

        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor="eb-footer" className="text-xs font-medium text-muted">{g.footerLabel}</label>
            <input
              id="eb-footer"
              value={footer}
              onChange={(e) => setFooter(e.target.value)}
              placeholder={g.footerPlaceholder}
              maxLength={2048}
              className={`${inputCls} mt-1 w-full`}
            />
          </div>
          <div>
            <label htmlFor="eb-thumb" className="text-xs font-medium text-muted">{g.thumbLabel}</label>
            <input
              id="eb-thumb"
              value={thumbnailUrl}
              onChange={(e) => setThumbnailUrl(e.target.value)}
              placeholder={g.urlPlaceholder}
              inputMode="url"
              className={`${inputCls} mt-1 w-full`}
            />
          </div>
        </div>

        <div className="mt-3">
          <label htmlFor="eb-image" className="text-xs font-medium text-muted">{g.imageLabel}</label>
          <input
            id="eb-image"
            value={imageUrl}
            onChange={(e) => setImageUrl(e.target.value)}
            placeholder={g.urlPlaceholder}
            inputMode="url"
            className={`${inputCls} mt-1 w-full`}
          />
        </div>

        <button
          onClick={send}
          disabled={!canSend}
          className="mt-4 w-full rounded-lg bg-brand px-6 py-2.5 text-sm font-semibold text-ink hover:bg-brand-deep disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand min-h-[44px]"
        >
          {sending ? g.sending : g.send}
        </button>
        {status === "ok" && (
          <p role="status" className="mt-2 text-sm text-brand">
            {g.sendOk}
          </p>
        )}
        {status === "error" && (
          <p role="alert" className="mt-2 text-sm text-red-400">
            {g.sendError}
          </p>
        )}
      </div>

      {/* Live preview: tiruan Discord, SENGAJA tetap gelap mengikuti kontrak */}
      <div>
        <h2 className="text-sm font-semibold text-fg">{g.previewTitle}</h2>
        <div className="mt-3 rounded-xl border border-edge bg-[#1e1f22] p-4">
          <div className="flex overflow-hidden rounded-md">
            <div className="w-1 shrink-0" style={{ backgroundColor: HEX_RE.test(color) ? color : "#2EC4B6" }} />
            <div className="min-w-0 flex-1 bg-[#2b2d31] p-4">
              {title.trim() ? (
                <p className="text-base font-semibold text-white">{title}</p>
              ) : (
                <p className="text-base text-zinc-500">{g.previewDefault}</p>
              )}
              {description.trim() && (
                <p className="mt-1 whitespace-pre-wrap text-sm text-zinc-300">{description}</p>
              )}
              {fields.length > 0 && (
                <div className="mt-3 grid grid-cols-3 gap-3">
                  {fields.map((f, i) => (
                    <div key={i} className={f.inline ? "min-w-0" : "col-span-3"}>
                      <p className="break-words text-xs font-semibold text-white">{f.name || `${g.fieldName} ${i + 1}`}</p>
                      <p className="mt-0.5 break-words whitespace-pre-wrap text-xs text-zinc-300">{f.value || "..."}</p>
                    </div>
                  ))}
                </div>
              )}
              {imageUrl.trim() && (
                // unoptimized: URL arbitrer dari user, tanpa lewat Image Optimization
                <Image
                  src={imageUrl}
                  alt=""
                  width={800}
                  height={400}
                  unoptimized
                  className="mt-3 max-h-64 w-auto rounded-md"
                />
              )}
              {footer.trim() && <p className="mt-3 text-xs text-zinc-400">{footer}</p>}
            </div>
          </div>
        </div>

        {/* Riwayat request */}
        <h2 className="mt-6 text-sm font-semibold text-fg">{g.historyTitle}</h2>
        <p className="mt-1 text-xs text-muted">
          {g.historyHint}
        </p>
        {loadingReq ? (
          <p className="mt-3 text-sm text-muted">{dict.common.loading}</p>
        ) : reqError ? (
          <p className="mt-3 text-sm text-muted">{g.historyError}</p>
        ) : requests.length === 0 ? (
          <p className="mt-3 text-sm text-muted">{g.historyEmpty}</p>
        ) : (
          <>
            {refreshError && (
              <p role="alert" className="mt-3 text-sm text-red-400">{dict.common.refreshError}</p>
            )}
            <ul className="mt-3 divide-y divide-edge overflow-hidden rounded-xl border border-edge bg-panel">
              {requests.map((r) => (
              <li key={r.id} className="flex items-center gap-3 px-5 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-fg">{r.title}</p>
                  <p className="truncate font-mono text-xs text-muted">
                    #{channelName(r.channel_id)} · {formatWaktu(r.created_at, locale)}
                  </p>
                  {r.note && <p className="mt-0.5 text-xs text-muted">{r.note}</p>}
                </div>
                <span
                  className={`rounded-lg px-3 py-1 text-xs font-medium ${
                    r.status === "done"
                      ? "bg-green-500/15 text-green-400"
                      : r.status === "failed"
                        ? "bg-red-500/15 text-red-400"
                        : "bg-yellow-500/15 text-yellow-400"
                  }`}
                >
                  {r.status === "done" ? g.statusDone : r.status === "failed" ? g.statusFailed : g.statusPending}
                </span>
              </li>
            ))}
          </ul>
          </>
        )}
      </div>
    </div>
  );
}

function formatWaktu(iso: string, locale: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(locale, { dateStyle: "short", timeStyle: "short" });
}
