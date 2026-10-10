import { NextResponse } from "next/server";
import { addAutoResponse, deleteAutoResponse, deleteAutoResponseByTrigger, getAutoResponses, withDbError } from "@/lib/db";
import { botAuthorized, requireManager } from "@/lib/access";
import { parseJsonBody, str } from "@/lib/validate";


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
  const denied = await requireManager(id);
  if (denied) return denied;
  const body = await parseJsonBody(req);
  if (!body) return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  const trigger = str(body.trigger, 100, true)?.toLowerCase();
  const response = str(body.response, 500, true);
  if (trigger === undefined || response === undefined) {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }
  await addAutoResponse(id, trigger, response);
  return NextResponse.json({ ok: true });
}

async function deleteImpl(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const denied = await requireManager(id);
  if (denied) return denied;
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
