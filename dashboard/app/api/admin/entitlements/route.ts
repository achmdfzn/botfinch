import { NextResponse } from "next/server";
import {
  applyEntitlementMutation,
  latestSnapshot,
  listEntitlementAudit,
  listEntitlements,
  getEntitlement,
  type EntitlementAction,
  type GuildEntitlement,
  withDbError,
} from "@/lib/db";
import { getSessionDiscordId, requireBotOwner } from "@/lib/access";
import { discordId, parseJsonBody, str } from "@/lib/validate";

const ACTIONS: EntitlementAction[] = ["grant", "extend", "revoke"];

/** Bentuk EntitlementView sesuai kontrak API (nama dari snapshot terbaru). */
export interface EntitlementView {
  guild_id: string;
  name: string | null;
  tier: string;
  status: string;
  source: string;
  starts_at: string | null;
  expires_at: string | null;
  granted_by: string | null;
  note: string | null;
  bot_present: boolean;
  first_seen_at: string | null;
  last_seen_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

function toView(row: GuildEntitlement, name: string | null): EntitlementView {
  return {
    guild_id: row.guild_id,
    name,
    tier: row.tier,
    status: row.status,
    source: row.source,
    starts_at: row.starts_at,
    expires_at: row.expires_at,
    granted_by: row.granted_by,
    note: row.note,
    bot_present: row.bot_present,
    first_seen_at: row.first_seen_at,
    last_seen_at: row.last_seen_at,
    created_at: row.created_at,
    updated_at: row.updated_at,
  };
}

async function snapshotNames(): Promise<Map<string, string>> {
  const snapshot = await latestSnapshot();
  const map = new Map<string, string>();
  for (const g of snapshot?.guilds ?? []) map.set(g.id, g.name);
  return map;
}

/** Daftar entitlement (owner) + detail satu guild beserta audit-nya. */
async function getImpl(req: Request) {
  const denied = await requireBotOwner();
  if (denied) return denied;
  const params = new URL(req.url).searchParams;
  const guildIdParam = params.get("guild_id");
  const names = await snapshotNames();
  if (guildIdParam) {
    const row = await getEntitlement(guildIdParam);
    const audit = await listEntitlementAudit(guildIdParam, 50);
    return NextResponse.json({
      ok: true,
      entitlement: row ? toView(row, names.get(row.guild_id) ?? null) : null,
      audit,
    });
  }
  const q = params.get("q") ?? "";
  const needle = q.trim().toLowerCase();
  const rows = await listEntitlements();
  const views = rows
    .map((row) => toView(row, names.get(row.guild_id) ?? null))
    .filter(
      (v) =>
        !needle ||
        v.guild_id.toLowerCase().includes(needle) ||
        (v.name ?? "").toLowerCase().includes(needle),
    );
  return NextResponse.json({ ok: true, entitlements: views });
}

/**
 * Mutasi entitlement dari panel admin (owner). Actor SELALU Discord ID
 * dari sesi login — actor_id/tier/expires_at/isOwner dari body diabaikan.
 * Validasi durasi/alasan sama seperti route internal bot.
 */
async function postImpl(req: Request) {
  const denied = await requireBotOwner();
  if (denied) return denied;
  const body = await parseJsonBody(req);
  if (!body) return NextResponse.json({ error: "invalid_json" }, { status: 400 });

  const guildId = discordId(body.guild_id);
  if (guildId === undefined) {
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

  const actorId = await getSessionDiscordId();
  if (!actorId) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
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
  const names = await snapshotNames();
  return NextResponse.json({
    ok: true,
    entitlement: toView(row, names.get(row.guild_id) ?? null),
  });
}

export const GET = withDbError(getImpl);
export const POST = withDbError(postImpl);
