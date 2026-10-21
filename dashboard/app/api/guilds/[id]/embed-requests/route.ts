import { NextResponse } from "next/server";
import { createEmbedRequest, getSnapshotChannel, listEmbedRequests, withDbError } from "@/lib/db";
import { requireManager } from "@/lib/access";
import { discordId, embedFields, hexColor, httpUrl, optStr, parseJsonBody } from "@/lib/validate";


/** Daftar permintaan embed terbaru (manager). */
async function getImpl(
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
async function postImpl(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const denied = await requireManager(id);
  if (denied) return denied;
  const body = await parseJsonBody(req);
  if (!body) return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  const channelId = discordId(body.channel_id);
  const title = optStr(body.title, 256);
  const description = optStr(body.description, 4000);
  const color = hexColor(body.color, "2EC4B6");
  const target = await getSnapshotChannel(id, channelId ?? "");
  if (channelId === undefined || !target || (target.type !== 0 && target.type !== 5)) {
    return NextResponse.json({ error: "channel_not_in_guild_or_not_text" }, { status: 400 });
  }
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
  // Embed tanpa konten apa pun (title+description+fields kosong) pasti
  // ditolak Discord di sisi bot — tolak di sini dengan pesan yang jelas.
  if (!title && !description && fields.length === 0) {
    return NextResponse.json({ error: "empty_embed" }, { status: 400 });
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

export const GET = withDbError(getImpl);
export const POST = withDbError(postImpl);
