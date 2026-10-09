import { NextResponse } from "next/server";
import { addAutoResponse, deleteAutoResponse, deleteAutoResponseByTrigger, getAutoResponses } from "@/lib/db";
import { botAuthorized, requireManager } from "@/lib/access";

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
  const trigger = typeof body.trigger === "string" ? body.trigger.trim().toLowerCase() : "";
  const response = typeof body.response === "string" ? body.response.trim() : "";
  if (trigger.length === 0 || trigger.length > 100 || response.length === 0 || response.length > 500) {
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
  const trigger = (searchParams.get("trigger") ?? "").trim().toLowerCase();
  if (Number.isInteger(rid) && rid > 0) {
    await deleteAutoResponse(id, rid);
    return NextResponse.json({ ok: true });
  }
  if (trigger.length > 0 && trigger.length <= 100) {
    await deleteAutoResponseByTrigger(id, trigger);
    return NextResponse.json({ ok: true });
  }
  return NextResponse.json({ error: "invalid_input" }, { status: 400 });
}
