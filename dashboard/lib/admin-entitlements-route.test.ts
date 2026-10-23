/**
 * Route admin entitlement (panel owner):
 * - gerbangnya requireBotOwner: response penolakan (401/403) diteruskan
 *   apa adanya dan mutation tidak terpanggil — bahkan bila body membawa
 *   isOwner:true (klaim dari body tidak pernah dipercaya).
 * - owner lolos -> GET list 200, GET detail memuat audit.
 * - POST: actor diambil dari sesi (getSessionDiscordId), BUKAN body.
 */
import { NextResponse } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const SAMPLE_ROW = {
  guild_id: "111111111111111111",
  tier: "vip",
  status: "active",
  source: "owner_grant",
  starts_at: "2026-10-22T00:00:00.000Z",
  expires_at: null,
  granted_by: "999999999999999999",
  note: null,
  bot_present: true,
  first_seen_at: "2026-10-20T00:00:00.000Z",
  last_seen_at: "2026-10-22T00:00:00.000Z",
  created_at: "2026-10-20T00:00:00.000Z",
  updated_at: "2026-10-22T00:00:00.000Z",
  provider_entitlement_id: null,
  provider_subscription_id: null,
};

vi.mock("@/lib/db", () => ({
  dbConfigured: vi.fn(() => true),
  applyEntitlementMutation: vi.fn(async () => SAMPLE_ROW),
  latestSnapshot: vi.fn(async () => ({
    bot_name: "Finch",
    pushed_at: "2026-10-22T00:00:00.000Z",
    guilds: [
      {
        id: "111111111111111111",
        name: "Server Uji",
        icon: null,
        member_count: 10,
        channels: [],
        roles: [],
        leaderboards: { levels: [], coins: [] },
        giveaways: [],
        modlog: [],
      },
    ],
  })),
  listEntitlements: vi.fn(async () => [SAMPLE_ROW]),
  listEntitlementAudit: vi.fn(async () => [
    { id: 1, guild_id: "111111111111111111", actor_id: "999999999999999999", action: "grant", tier_before: "free", tier_after: "vip", status_before: "active", status_after: "active", expires_before: null, expires_after: null, reason: null, created_at: "2026-10-22T00:00:00.000Z" },
  ]),
  getEntitlement: vi.fn(async () => SAMPLE_ROW),
  withDbError: (fn: unknown) => fn,
}));

vi.mock("@/lib/access", () => ({
  requireBotOwner: vi.fn(async () => null),
  getSessionDiscordId: vi.fn(async () => "999999999999999999"),
}));

import * as access from "@/lib/access";
import * as db from "@/lib/db";
import { GET, POST } from "../app/api/admin/entitlements/route";

const requireBotOwner = vi.mocked(access.requireBotOwner);
const getSessionDiscordId = vi.mocked(access.getSessionDiscordId);
const apply = vi.mocked(db.applyEntitlementMutation);
const listEntitlements = vi.mocked(db.listEntitlements);

const GUILD = "111111111111111111";
const OWNER = "999999999999999999";

function reqJson(body: unknown, url = "http://localhost/api/admin/entitlements"): Request {
  return new Request(url, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "content-type": "application/json" },
  });
}
function reqGet(url: string): Request {
  return new Request(url, { method: "GET" });
}

beforeEach(() => {
  vi.clearAllMocks();
  requireBotOwner.mockResolvedValue(null);
  getSessionDiscordId.mockResolvedValue(OWNER);
  apply.mockResolvedValue(SAMPLE_ROW);
  listEntitlements.mockResolvedValue([SAMPLE_ROW]);
});

describe("gerbang owner", () => {
  it("anonymous (401 dari requireBotOwner) -> diteruskan, mutation & list tidak terpanggil", async () => {
    requireBotOwner.mockResolvedValue(
      NextResponse.json({ error: "unauthorized" }, { status: 401 }),
    );
    const resPost = await POST(reqJson({ guild_id: GUILD, action: "grant", duration_days: 30 }));
    expect(resPost.status).toBe(401);
    const resGet = await GET(reqGet("http://localhost/api/admin/entitlements"));
    expect(resGet.status).toBe(401);
    expect(apply).not.toHaveBeenCalled();
    expect(listEntitlements).not.toHaveBeenCalled();
  });

  it("non-owner (403) + body isOwner:true -> tetap ditolak", async () => {
    requireBotOwner.mockResolvedValue(
      NextResponse.json({ error: "forbidden" }, { status: 403 }),
    );
    const res = await POST(
      reqJson({ guild_id: GUILD, action: "grant", duration_days: 30, isOwner: true, actor_id: OWNER }),
    );
    expect(res.status).toBe(403);
    expect(apply).not.toHaveBeenCalled();
  });
});

describe("GET /api/admin/entitlements (owner)", () => {
  it("list -> 200 dengan EntitlementView + name dari snapshot", async () => {
    const res = await GET(reqGet("http://localhost/api/admin/entitlements"));
    expect(res.status).toBe(200);
    const json = (await res.json()) as { ok: boolean; entitlements: Record<string, unknown>[] };
    expect(json.ok).toBe(true);
    expect(json.entitlements).toHaveLength(1);
    expect(json.entitlements[0]).toMatchObject({
      guild_id: GUILD,
      name: "Server Uji",
      tier: "vip",
      status: "active",
      bot_present: true,
    });
  });

  it("?q= memfilter substring guild_id / nama", async () => {
    const byName = await GET(reqGet("http://localhost/api/admin/entitlements?q=uji"));
    const jsonName = (await byName.json()) as { entitlements: unknown[] };
    expect(jsonName.entitlements).toHaveLength(1);
    const noMatch = await GET(reqGet("http://localhost/api/admin/entitlements?q=tidakada"));
    const jsonNo = (await noMatch.json()) as { entitlements: unknown[] };
    expect(jsonNo.entitlements).toHaveLength(0);
  });

  it("?guild_id= -> detail + audit", async () => {
    const res = await GET(
      reqGet(`http://localhost/api/admin/entitlements?guild_id=${GUILD}`),
    );
    expect(res.status).toBe(200);
    const json = (await res.json()) as {
      entitlement: Record<string, unknown> | null;
      audit: unknown[];
    };
    expect(json.entitlement).toMatchObject({ guild_id: GUILD, name: "Server Uji" });
    expect(json.audit).toHaveLength(1);
  });
});

describe("POST /api/admin/entitlements (owner)", () => {
  it("grant -> 200, actor dari sesi BUKAN dari body", async () => {
    const res = await POST(
      reqJson({
        guild_id: GUILD,
        action: "grant",
        duration_days: null,
        actor_id: "111222333444555666",
        tier: "free",
        expires_at: "2000-01-01T00:00:00.000Z",
      }),
    );
    expect(res.status).toBe(200);
    expect(apply).toHaveBeenCalledTimes(1);
    const arg = apply.mock.calls[0][0] as unknown as Record<string, unknown>;
    expect(arg.actorId).toBe(OWNER);
    expect(arg).not.toHaveProperty("tier");
    expect(arg).not.toHaveProperty("expires_at");
    const json = (await res.json()) as { entitlement: Record<string, unknown> };
    expect(json.entitlement).toMatchObject({ guild_id: GUILD, name: "Server Uji", tier: "vip" });
  });

  it("payload invalid (extend tanpa duration) -> 400", async () => {
    const res = await POST(reqJson({ guild_id: GUILD, action: "extend" }));
    expect(res.status).toBe(400);
    expect(apply).not.toHaveBeenCalled();
  });
});
