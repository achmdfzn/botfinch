import { NextResponse } from "next/server";
import { addSelfRole, deleteSelfRole, getSelfRoles } from "@/lib/db";
import { botAuthorized, requireManager } from "@/lib/access";
import { discordId, parseJsonBody, str } from "@/lib/validate";


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
  const body = await parseJsonBody(req);
  if (!body) return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  const messageId = discordId(body.message_id);
  const emoji = str(body.emoji, 64, true);
  const roleId = discordId(body.role_id);
  if (messageId === undefined || roleId === undefined || emoji === undefined) {
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
