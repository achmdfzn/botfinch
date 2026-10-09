import { NextResponse } from "next/server";
import { latestSnapshot } from "@/lib/db";
import { requireManager } from "@/lib/access";

export const instant = false;

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const denied = await requireManager(id);
  if (denied) return denied;
  const snap = await latestSnapshot();
  const guild = snap?.guilds.find((g) => g.id === id);
  if (!guild) {
    return NextResponse.json({ error: "no_data", hint: "Bot belum mengirim snapshot untuk server ini." }, { status: 404 });
  }
  return NextResponse.json({
    guild_id: id,
    guild_name: guild.name,
    levels: guild.leaderboards.levels,
    coins: guild.leaderboards.coins,
    updated_at: snap!.pushed_at,
  });
}
