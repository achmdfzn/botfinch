import { NextResponse } from "next/server";
import { ackGiveawayRequest, dbConfigured, withDbError } from "@/lib/db";
import { botAuthorized } from "@/lib/access";
import { optStr, parseJsonBody } from "@/lib/validate";


/** Bot menandai permintaan giveaway sudah diproses (done) atau gagal (failed). */
async function postImpl(
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
  const body = (await parseJsonBody(req)) ?? {};
  // Konvensi ketat, sama seperti ack embed-requests: status harus eksplisit
  // "done"/"failed". Nilai lain/typo ditolak 400 (bukan diam-diam "done").
  const status = body.status;
  if (status !== "done" && status !== "failed") {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }
  const note = optStr(body.note, 200);
  if (note === undefined) {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }
  await ackGiveawayRequest(rid, id, status, note);
  return NextResponse.json({ ok: true });
}

export const POST = withDbError(postImpl);
