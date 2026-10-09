import { NextResponse } from "next/server";
import { latestSnapshot } from "@/lib/db";
import { requireSession } from "@/lib/access";

export const instant = false;

/**
 * Status ringan untuk auto-refresh daftar server di /dashboard.
 * Mengembalikan guild yang SUDAH ada di snapshot terakhir bot
 * (tanpa memanggil API Discord — jauh lebih ringan dari render halaman).
 */
export async function GET() {
  const denied = await requireSession();
  if (denied) return denied;
  const snap = await latestSnapshot();
  return NextResponse.json({
    pushed_at: snap?.pushed_at ?? null,
    guilds: (snap?.guilds ?? []).map((g) => ({
      id: g.id,
      name: g.name,
      icon: g.icon,
      member_count: g.member_count,
    })),
  });
}
