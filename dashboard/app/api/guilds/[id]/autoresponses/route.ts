import { NextResponse } from "next/server";
import { addAutoResponse, deleteAutoResponse, deleteAutoResponseByTrigger, getAutoResponses } from "@/lib/db";
import { botAuthorized, requireManager } from "@/lib/access";
import { str } from "@/lib/validate";

export const instant = false;

export async function GET(
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

export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const denied = await requireManager(id);
  if (denied) return denied;
  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }
  const trigger = str(body.trigger, 100, true)?.toLowerCase();
  const response = str(body.response, 500, true);
  if (trigger === undefined || response === undefined) {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }
  await addAutoResponse(id, trigger, response);
  return NextResponse.json({ ok: true });
}

export async function DELETE(
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
