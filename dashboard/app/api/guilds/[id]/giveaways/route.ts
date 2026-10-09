import { NextResponse } from "next/server";
import { addGiveawayRequest, getGiveawayRequests, latestSnapshot } from "@/lib/db";
import { requireManager } from "@/lib/access";

export const instant = false;

const ID_RE = /^\d{5,25}$/;

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const denied = await requireManager(id);
  if (denied) return denied;
  const snap = await latestSnapshot();
  const guild = snap?.guilds.find((g) => g.id === id);
  return NextResponse.json({
    guild_id: id,
    active: guild?.giveaways ?? [],
    requests: await getGiveawayRequests(id),
    snapshot_at: snap?.pushed_at ?? null,
  });
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
  const channelId = typeof body.channel_id === "string" ? body.channel_id.trim() : "";
  const prize = typeof body.prize === "string" ? body.prize.trim() : "";
  const winners = body.winners;
  const duration = body.duration_minutes;
  if (
    !ID_RE.test(channelId) ||
    prize.length === 0 ||
    prize.length > 100 ||
    typeof winners !== "number" ||
    !Number.isInteger(winners) ||
    winners < 1 ||
    winners > 25 ||
    typeof duration !== "number" ||
    !Number.isInteger(duration) ||
    duration < 1 ||
    duration > 10080
  ) {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }
  await addGiveawayRequest(id, channelId, prize, winners, duration);
  return NextResponse.json({ ok: true, note: "Bot akan membuat giveaway dalam beberapa menit." });
}
