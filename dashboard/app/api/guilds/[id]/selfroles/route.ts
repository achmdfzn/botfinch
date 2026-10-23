import { NextResponse } from "next/server";
import { addSelfRoleWithQuota, countSelfRolePanels, deleteSelfRole, getEntitlement, getSelfRoles, withDbError } from "@/lib/db";
import { botAuthorized, requireManager } from "@/lib/access";
import { discordId, parseJsonBody, str } from "@/lib/validate";
import { FEATURE_LIMITS, getEffectiveTierFromRow } from "@/lib/premium";


async function getImpl(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  // Bot boleh baca untuk sinkronisasi; selain itu harus manager.
  if (!botAuthorized(req)) {
    const denied = await requireManager(id);
    if (denied) return denied;
  }
  return NextResponse.json({ guild_id: id, selfroles: await getSelfRoles(id) });
}

async function postImpl(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const denied = await requireManager(id);
  if (denied) return denied;
  const body = await parseJsonBody(req);
  if (!body) return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  const messageId = discordId(body.message_id);
  const emoji = str(body.emoji, 64, true);
  const roleId = discordId(body.role_id);
  if (messageId === undefined || roleId === undefined || emoji === undefined) {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }
  // Kuota dihitung per PANEL (message_id berbeda), bukan per baris.
  // addSelfRoleWithQuota membedakan di dalam satu statement atomik:
  // message_id yang sudah punya baris = panel lama (selalu boleh,
  // termasuk emoji baru), message_id baru hanya tertulis bila jumlah
  // panel masih di bawah limit tier efektif (tanpa entitlement = free).
  const tier = getEffectiveTierFromRow(await getEntitlement(id));
  const limit = FEATURE_LIMITS.selfrole_panels[tier];
  const written = await addSelfRoleWithQuota(id, messageId, emoji, roleId, limit);
  if (!written) {
    return NextResponse.json(
      {
        error: "quota_exceeded",
        feature: "selfrole_panels",
        used: await countSelfRolePanels(id),
        limit,
        vip_limit: FEATURE_LIMITS.selfrole_panels.vip,
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
  const denied = await requireManager(id);
  if (denied) return denied;
  const body = await parseJsonBody(req);
  if (!body) return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  const messageId = discordId(body.message_id);
  // Batas panjang sama seperti POST (str(..., 64, true)): cegah emoji
  // raksasa dari client yang menggelembungkan query DELETE.
  const emoji = str(body.emoji, 64, true);
  if (messageId === undefined || emoji === undefined) {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }
  await deleteSelfRole(id, messageId, emoji);
  return NextResponse.json({ ok: true });
}

export const GET = withDbError(getImpl);
export const POST = withDbError(postImpl);
export const DELETE = withDbError(deleteImpl);
