import { NextResponse } from "next/server";
import { ackGiveawayRequest, dbConfigured } from "@/lib/db";
import { botAuthorized } from "@/lib/access";

export const instant = false;

/** Bot menandai permintaan giveaway sudah diproses (done) atau gagal (failed). */
export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string; reqId: string }> },
) {
  const { reqId } = await params;
  if (!botAuthorized(req)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  if (!dbConfigured()) {
    return NextResponse.json({ error: "database_not_configured" }, { status: 503 });
  }
  const rid = Number(reqId);
  if (!Number.isInteger(rid) || rid <= 0) {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }
  let body: Record<string, unknown> = {};
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    /* biarkan default */
  }
  const status = body.status === "failed" ? "failed" : "done";
  const note = typeof body.note === "string" ? body.note.slice(0, 200) : "";
  await ackGiveawayRequest(rid, status, note);
  return NextResponse.json({ ok: true });
}
