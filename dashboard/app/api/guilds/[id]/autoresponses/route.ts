import { NextResponse } from "next/server";
import { addAutoResponseWithQuota, countAutoResponses, deleteAutoResponse, deleteAutoResponseByTrigger, getAutoResponses, getEntitlement, withDbError } from "@/lib/db";
import { botAuthorized, requireManager } from "@/lib/access";
import { parseJsonBody, str } from "@/lib/validate";
import { FEATURE_LIMITS, getEffectiveTierFromRow } from "@/lib/premium";


async function getImpl(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  if (!botAuthorized(req)) {
    const denied = await requireManager(id);
    if (denied) return denied;
  }
  return NextResponse.json({ guild_id: id, autoresponses: await getAutoResponses(id) });
}

async function postImpl(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  // Mirror bot -> dashboard memakai DASHBOARD_SECRET (botAuthorized),
  // sama seperti GET route ini. Tanpa cabang ini POST mirror dari cog
  // responder selalu 401 dan rule yang dibuat lewat Discord hilang saat
  // sinkronisasi dashboard berikutnya menimpa SQLite bot. Pengguna web
  // tetap wajib requireManager, dan gate kuota di bawah berlaku untuk
  // kedua jalur.
  if (!botAuthorized(req)) {
    const denied = await requireManager(id);
    if (denied) return denied;
  }
  const body = await parseJsonBody(req);
  if (!body) return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  const trigger = str(body.trigger, 100, true)?.toLowerCase();
  const response = str(body.response, 500, true);
  if (trigger === undefined || response === undefined) {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }
  // Kuota rule per tier efektif guild (tanpa entitlement = free).
  // addAutoResponseWithQuota membedakan di dalam satu statement atomik:
  // trigger yang sudah ada = pembaruan (selalu boleh), trigger baru
  // hanya tertulis bila jumlah rule masih di bawah limit.
  const tier = getEffectiveTierFromRow(await getEntitlement(id));
  const limit = FEATURE_LIMITS.autoresponders[tier];
  const written = await addAutoResponseWithQuota(id, trigger, response, limit);
  if (!written) {
    return NextResponse.json(
      {
        error: "quota_exceeded",
        feature: "autoresponders",
        used: await countAutoResponses(id),
        limit,
        vip_limit: FEATURE_LIMITS.autoresponders.vip,
        tier,
      },
      { status: 409 },
    );
  }
  return NextResponse.json({ ok: true });
}

async function deleteImpl(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  // Penghapusan mirror bot juga memakai botAuthorized (lihat POST).
  if (!botAuthorized(req)) {
    const denied = await requireManager(id);
    if (denied) return denied;
  }
  const { searchParams } = new URL(req.url);
  const rid = Number(searchParams.get("id"));
  const trigger = str(searchParams.get("trigger"), 100, true)?.toLowerCase();
  if (Number.isInteger(rid) && rid > 0) {
    await deleteAutoResponse(id, rid);
    return NextResponse.json({ ok: true });
  }
  if (trigger !== undefined) {
    await deleteAutoResponseByTrigger(id, trigger);
    return NextResponse.json({ ok: true });
  }
  return NextResponse.json({ error: "invalid_input" }, { status: 400 });
}

export const GET = withDbError(getImpl);
export const POST = withDbError(postImpl);
export const DELETE = withDbError(deleteImpl);
