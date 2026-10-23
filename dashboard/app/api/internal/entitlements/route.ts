import { NextResponse } from "next/server";
import {
  applyEntitlementMutation,
  dbConfigured,
  type EntitlementAction,
  withDbError,
} from "@/lib/db";
import { botAuthorized } from "@/lib/access";
import { discordId, parseJsonBody, str } from "@/lib/validate";

const ACTIONS: EntitlementAction[] = ["grant", "extend", "revoke"];

/**
 * Mutasi entitlement untuk bot (shared DASHBOARD_SECRET), mis. perintah
 * owner di Discord. HANYA guild_id/action/duration_days/reason/actor_id
 * dari body yang dibaca — field seperti tier/expires_at/isOwner dari body
 * diabaikan sepenuhnya; state baru selalu dihitung server di lib/db.
 */
async function postImpl(req: Request) {
  if (!botAuthorized(req)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  if (!dbConfigured()) {
    return NextResponse.json({ error: "database_not_configured" }, { status: 503 });
  }
  const body = await parseJsonBody(req);
  if (!body) return NextResponse.json({ error: "invalid_json" }, { status: 400 });

  const guildId = discordId(body.guild_id);
  const actorId = discordId(body.actor_id);
  if (guildId === undefined || actorId === undefined) {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }
  if (typeof body.action !== "string" || !ACTIONS.includes(body.action as EntitlementAction)) {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }
  const action = body.action as EntitlementAction;

  let durationDays: number | null = null;
  if (body.duration_days !== undefined && body.duration_days !== null) {
    if (
      typeof body.duration_days !== "number" ||
      !Number.isInteger(body.duration_days) ||
      body.duration_days < 1 ||
      body.duration_days > 3650
    ) {
      return NextResponse.json({ error: "invalid_input" }, { status: 400 });
    }
    durationDays = body.duration_days;
  }
  if (action === "extend" && durationDays === null) {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }

  let reason: string | null = null;
  if (body.reason !== undefined && body.reason !== null) {
    const r = str(body.reason, 200);
    if (r === undefined) {
      return NextResponse.json({ error: "invalid_input" }, { status: 400 });
    }
    reason = r;
  }

  const row = await applyEntitlementMutation({
    guildId,
    action,
    durationDays,
    reason,
    actorId,
    source: "owner_grant",
  });
  if (!row) {
    return NextResponse.json({ error: "entitlement_mutation_failed" }, { status: 500 });
  }
  return NextResponse.json({
    ok: true,
    entitlement: {
      guild_id: row.guild_id,
      tier: row.tier,
      status: row.status,
      starts_at: row.starts_at,
      expires_at: row.expires_at,
      source: row.source,
      updated_at: row.updated_at,
    },
  });
}

export const POST = withDbError(postImpl);
