import { NextResponse } from "next/server";
import { latestSnapshot, withDbError } from "@/lib/db";
import { requireManager } from "@/lib/access";


async function getImpl(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const denied = await requireManager(id);
  if (denied) return denied;
  const snap = await latestSnapshot();
  const guild = snap?.guilds.find((g) => g.id === id);
  if (!guild) {
    // Kode mesin saja (tanpa teks bahasa): frontend menerjemahkannya
    // sendiri via kamus i18n; API tidak boleh me-hardcode bahasa.
    return NextResponse.json({ error: "no_data" }, { status: 404 });
  }
  return NextResponse.json({
    guild_id: id,
    guild_name: guild.name,
    levels: guild.leaderboards.levels,
    coins: guild.leaderboards.coins,
    updated_at: snap!.pushed_at,
  });
}

export const GET = withDbError(getImpl);
