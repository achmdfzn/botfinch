import { NextResponse } from "next/server";
import { dbConfigured, getStoredSettings, latestSnapshot, mergeStoredSettings, withDbError } from "@/lib/db";
import { botAuthorized, requireManager } from "@/lib/access";
import { SETTING_DEFAULTS, cleanValue, mergeSettings } from "@/lib/settings";
import { parseJsonBody } from "@/lib/validate";

async function getImpl(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  if (!botAuthorized(req)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  if (!dbConfigured()) {
    return NextResponse.json({ error: "database_not_configured" }, { status: 503 });
  }
  const stored = await getStoredSettings(id);
  // Mentah tanpa merge default — bot menentukan default sendiri per key.
  return NextResponse.json({ guild_id: id, settings: stored });
}

async function putImpl(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  // requireManager (bukan auth() mentah): cookie sesi korup diperlakukan
  // sebagai belum login (401), bukan crash 500 via JWTSessionError.
  const denied = await requireManager(id);
  if (denied) return denied;
  const body = await parseJsonBody(req);
  if (!body) return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  const clean: Record<string, boolean | string | number> = {};
  for (const key of Object.keys(SETTING_DEFAULTS)) {
    const v = cleanValue(key, body[key]);
    if (v !== undefined) clean[key] = v;
  }
  // Validasi konfigurasi channel dan role terhadap snapshot guild tujuan.
  // Bot tetap memeriksa kepemilikan guild aktual sebelum menjalankan aksi.
  const snapshot = await latestSnapshot();
  const guildSnapshot = snapshot?.guilds.find((guild) => guild.id === id);
  const channelTypes = new Map(
    (guildSnapshot?.channels ?? []).map((channel) => [channel.id, channel.type] as const),
  );
  const roleIds = new Set((guildSnapshot?.roles ?? []).map((role) => role.id));
  for (const [key, value] of Object.entries(clean)) {
    if (typeof value !== "string" || value === "") continue;
    if (
      key.endsWith("_channel_id") ||
      key.endsWith("_category_id") ||
      key.endsWith("_lobby_id")
    ) {
      const type = channelTypes.get(value);
      const allowed = key.endsWith("_category_id")
        ? type === 4
        : key.endsWith("_lobby_id")
          ? type === 2
          : type === 0 || type === 5;
      if (!allowed) {
        return NextResponse.json(
          { error: "invalid_channel_setting", field: key },
          { status: 400 },
        );
      }
    }
    if (key === "welcome_role_ids") {
      const ids = value.split(",").map((item) => item.trim()).filter(Boolean);
      if (ids.some((roleId) => !roleIds.has(roleId))) {
        return NextResponse.json(
          { error: "invalid_role_setting", field: key },
          { status: 400 },
        );
      }
    }
    if (key === "leveling_roles") {
      let roles: unknown;
      try {
        roles = JSON.parse(value);
      } catch {
        return NextResponse.json(
          { error: "invalid_role_setting", field: key },
          { status: 400 },
        );
      }
      if (
        !Array.isArray(roles) ||
        roles.some((role) => {
          if (!role || typeof role !== "object" || Array.isArray(role)) return true;
          const roleId = (role as Record<string, unknown>).role_id;
          return typeof roleId !== "string" || !roleIds.has(roleId);
        })
      ) {
        return NextResponse.json(
          { error: "invalid_role_setting", field: key },
          { status: 400 },
        );
      }
    }
  }
  // Validasi lintas-key (D-003): /kerja minimal tidak boleh melebihi
  // maksimalnya. Dicek terhadap gabungan nilai tersimpan + request ini,
  // agar konfigurasi "terlihat salah" tidak tersimpan diam-diam.
  const efektif = { ...mergeSettings(await getStoredSettings(id)), ...clean };
  if (efektif.economy_work_min > efektif.economy_work_max) {
    return NextResponse.json({ error: "work_min_gt_max" }, { status: 400 });
  }
  // Merge atomik di Postgres (settings || $1): tanpa read-modify-write
  // di JS, sehingga dua PUT bersamaan tidak saling menimpa.
  await mergeStoredSettings(id, clean);
  return NextResponse.json({ ok: true });
}

export const GET = withDbError(getImpl);
export const PUT = withDbError(putImpl);
