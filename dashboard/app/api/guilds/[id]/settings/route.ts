import { NextResponse } from "next/server";
import { dbConfigured, getStoredSettings, mergeStoredSettings, withDbError } from "@/lib/db";
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
