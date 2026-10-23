import { NextResponse } from "next/server";
import { addGiveawayRequest, countGiveawayRequestsPending, getEntitlement, getGiveawayRequests, getSnapshotChannel, latestSnapshot, withDbError } from "@/lib/db";
import { requireManager } from "@/lib/access";
import { discordId, parseJsonBody, str } from "@/lib/validate";
import { FEATURE_LIMITS, getEffectiveTierFromRow } from "@/lib/premium";


async function getImpl(
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
  const prize = str(body.prize, 100, true);
  const winners = body.winners;
  const duration = body.duration_minutes;
  const target = await getSnapshotChannel(id, channelId ?? "");
  if (channelId === undefined || !target || (target.type !== 0 && target.type !== 5)) {
    return NextResponse.json({ error: "channel_not_in_guild_or_not_text" }, { status: 400 });
  }
  if (
    prize === undefined ||
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
  // Pre-check kuota dua lapis: cek dashboard ini lapisan pertama
  // (pending + aktif dari snapshot), bot tetap penegak akhir saat
  // mengeksekusi request. used = request 'pending' guild + giveaway
  // aktif di snapshot terbaru (snapshot null -> aktif dihitung 0).
  const tier = getEffectiveTierFromRow(await getEntitlement(id));
  const limit = FEATURE_LIMITS.giveaways_active[tier];
  const snap = await latestSnapshot();
  const aktif = snap?.guilds.find((g) => g.id === id)?.giveaways.length ?? 0;
  const used = (await countGiveawayRequestsPending(id)) + aktif;
  if (used >= limit) {
    return NextResponse.json(
      {
        error: "quota_exceeded",
        feature: "giveaways_active",
        used,
        limit,
        vip_limit: FEATURE_LIMITS.giveaways_active.vip,
        tier,
      },
      { status: 409 },
    );
  }
  await addGiveawayRequest(id, channelId, prize, winners, duration);
  return NextResponse.json({ ok: true, note: "Bot akan membuat giveaway dalam beberapa menit." });
}

export const GET = withDbError(getImpl);
export const POST = withDbError(postImpl);
