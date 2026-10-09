import { NextResponse } from "next/server";
import { createEmbedRequest, listEmbedRequests } from "@/lib/db";
import { requireManager } from "@/lib/access";
import { discordId, embedFields, hexColor, httpUrl, optStr } from "@/lib/validate";

export const instant = false;

/** Daftar permintaan embed terbaru (manager). */
export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const denied = await requireManager(id);
  if (denied) return denied;
  return NextResponse.json({
    ok: true,
    guild_id: id,
    embed_requests: await listEmbedRequests(id, 20),
  });
}

/** Buat permintaan embed baru (status pending, dieksekusi bot). */
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
  const channelId = discordId(body.channel_id);
  const title = optStr(body.title, 256);
  const description = optStr(body.description, 4000);
  const color = hexColor(body.color, "2EC4B6");
  const fields = embedFields(body.fields);
  const footer = optStr(body.footer, 2048);
  const imageUrl = httpUrl(body.image_url);
  const thumbnailUrl = httpUrl(body.thumbnail_url);
  if (
    channelId === undefined ||
    title === undefined ||
    description === undefined ||
    color === undefined ||
    fields === undefined ||
    footer === undefined ||
    imageUrl === undefined ||
    thumbnailUrl === undefined
  ) {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }
  const reqId = await createEmbedRequest({
    guildId: id,
    channelId,
    title,
    description,
    color,
    fields,
    footer,
    imageUrl,
    thumbnailUrl,
  });
  return NextResponse.json({
    ok: true,
    id: reqId,
    note: "Bot akan mengirim embed dalam beberapa menit.",
  });
}
