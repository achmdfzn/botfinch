import { NextResponse } from "next/server";
import { latestSnapshot } from "@/lib/db";

export const instant = false;

export async function GET() {
  const snap = await latestSnapshot();
  if (!snap) {
    return NextResponse.json({ empty: true });
  }
  const memberTotal = snap.guilds.reduce((s, g) => s + (g.member_count || 0), 0);
  return NextResponse.json({
    empty: false,
    bot_name: snap.bot_name,
    guild_count: snap.guilds.length,
    member_total: memberTotal,
    pushed_at: snap.pushed_at,
  });
}
