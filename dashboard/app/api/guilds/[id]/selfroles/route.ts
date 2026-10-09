import { NextResponse } from "next/server";
import { addSelfRole, deleteSelfRole, getSelfRoles } from "@/lib/db";
import { botAuthorized, requireManager } from "@/lib/access";

export const instant = false;

const ID_RE = /^\d{5,25}$/;

export async function GET(
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
  const messageId = typeof body.message_id === "string" ? body.message_id.trim() : "";
  const emoji = typeof body.emoji === "string" ? body.emoji.trim() : "";
  const roleId = typeof body.role_id === "string" ? body.role_id.trim() : "";
  if (!ID_RE.test(messageId) || !ID_RE.test(roleId) || emoji.length === 0 || emoji.length > 64) {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }
  await addSelfRole(id, messageId, emoji, roleId);
  return NextResponse.json({ ok: true });
}

export async function DELETE(
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
  const messageId = typeof body.message_id === "string" ? body.message_id.trim() : "";
  const emoji = typeof body.emoji === "string" ? body.emoji.trim() : "";
  if (!ID_RE.test(messageId) || emoji.length === 0) {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }
  await deleteSelfRole(id, messageId, emoji);
  return NextResponse.json({ ok: true });
}
