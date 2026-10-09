import { NextResponse } from "next/server";
import { ackEmbedRequest, dbConfigured } from "@/lib/db";
import { botAuthorized } from "@/lib/access";
import { optStr } from "@/lib/validate";

export const instant = false;

/** Bot menandai permintaan embed sudah diproses (done) atau gagal (failed). */
export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string; reqId: string }> },
) {
  const { id, reqId } = await params;
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
  const status = body.status;
  if (status !== "done" && status !== "failed") {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }
  const note = optStr(body.note, 200);
  if (note === undefined) {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }
  await ackEmbedRequest(rid, id, status, note);
  return NextResponse.json({ ok: true });
}
