/**
 * Route internal entitlement (bot -> dashboard):
 * - wajib botAuthorized; tanpa auth mutation tidak boleh terpanggil.
 * - payload invalid (guild/actor rusak, action aneh, duration di luar
 *   1..3650, extend tanpa duration) ditolak 400.
 * - field palsu dari body (tier/expires_at/isOwner) TIDAK diteruskan ke
 *   applyEntitlementMutation — state dihitung server.
 * - DB belum terkonfigurasi -> 503.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const SAMPLE_ROW = {
  guild_id: "111111111111111111",
  tier: "vip",
  status: "active",
  source: "owner_grant",
  starts_at: "2026-10-22T00:00:00.000Z",
  expires_at: "2026-11-21T00:00:00.000Z",
  granted_by: "333333333333333333",
  note: null,
  bot_present: true,
  first_seen_at: "2026-10-22T00:00:00.000Z",
  last_seen_at: "2026-10-22T00:00:00.000Z",
  created_at: "2026-10-22T00:00:00.000Z",
  updated_at: "2026-10-22T00:00:00.000Z",
  provider_entitlement_id: null,
  provider_subscription_id: null,
};

vi.mock("@/lib/db", () => ({
  dbConfigured: vi.fn(() => true),
  applyEntitlementMutation: vi.fn(async () => SAMPLE_ROW),
  withDbError: (fn: unknown) => fn,
}));

vi.mock("@/lib/access", () => ({
  botAuthorized: vi.fn(() => true),
}));

import * as access from "@/lib/access";
import * as db from "@/lib/db";
import { POST } from "../app/api/internal/entitlements/route";

const botAuthorized = vi.mocked(access.botAuthorized);
const dbConfigured = vi.mocked(db.dbConfigured);
const apply = vi.mocked(db.applyEntitlementMutation);

const GUILD = "111111111111111111";
const ACTOR = "333333333333333333";

function reqJson(body: unknown): Request {
  return new Request("http://localhost/api/internal/entitlements", {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  botAuthorized.mockReturnValue(true);
  dbConfigured.mockReturnValue(true);
  apply.mockResolvedValue(SAMPLE_ROW);
});

describe("POST /api/internal/entitlements", () => {
  it("tanpa auth bot -> 401 dan mutation tidak terpanggil", async () => {
    botAuthorized.mockReturnValue(false);
    const res = await POST(reqJson({ guild_id: GUILD, actor_id: ACTOR, action: "grant", duration_days: 30 }));
    expect(res.status).toBe(401);
    expect(apply).not.toHaveBeenCalled();
  });

  it("db tidak terkonfigurasi -> 503", async () => {
    dbConfigured.mockReturnValue(false);
    const res = await POST(reqJson({ guild_id: GUILD, actor_id: ACTOR, action: "grant", duration_days: 30 }));
    expect(res.status).toBe(503);
    expect(apply).not.toHaveBeenCalled();
  });

  it("payload invalid -> 400 dan mutation tidak terpanggil", async () => {
    const cases: unknown[] = [
      { guild_id: "bukan-id", actor_id: ACTOR, action: "grant", duration_days: 30 },
      { guild_id: GUILD, actor_id: "x", action: "grant", duration_days: 30 },
      { guild_id: GUILD, actor_id: ACTOR, action: "upgrade", duration_days: 30 },
      { guild_id: GUILD, actor_id: ACTOR, action: "grant", duration_days: 0 },
      { guild_id: GUILD, actor_id: ACTOR, action: "grant", duration_days: 99999 },
      { guild_id: GUILD, actor_id: ACTOR, action: "grant", duration_days: 1.5 },
      { guild_id: GUILD, actor_id: ACTOR, action: "extend", duration_days: null },
      { guild_id: GUILD, actor_id: ACTOR, action: "extend" },
      { guild_id: GUILD, actor_id: ACTOR, action: "grant", reason: "x".repeat(201) },
    ];
    for (const body of cases) {
      const res = await POST(reqJson(body));
      expect(res.status).toBe(400);
    }
    expect(apply).not.toHaveBeenCalled();
  });

  it("grant valid -> 200, argumen mutation dihitung server (field palsu body diabaikan)", async () => {
    const res = await POST(
      reqJson({
        guild_id: GUILD,
        actor_id: ACTOR,
        action: "grant",
        duration_days: 30,
        reason: "promo",
        // Field palsu yang tidak boleh dibaca sama sekali:
        tier: "vip",
        expires_at: "2999-01-01T00:00:00.000Z",
        isOwner: true,
      }),
    );
    expect(res.status).toBe(200);
    const json = (await res.json()) as { ok: boolean; entitlement: Record<string, unknown> };
    expect(json.ok).toBe(true);
    expect(json.entitlement).toEqual({
      guild_id: GUILD,
      tier: "vip",
      status: "active",
      starts_at: SAMPLE_ROW.starts_at,
      expires_at: SAMPLE_ROW.expires_at,
      source: "owner_grant",
      updated_at: SAMPLE_ROW.updated_at,
    });
    expect(apply).toHaveBeenCalledTimes(1);
    const arg = apply.mock.calls[0][0] as unknown as Record<string, unknown>;
    expect(arg).toEqual({
      guildId: GUILD,
      action: "grant",
      durationDays: 30,
      reason: "promo",
      actorId: ACTOR,
      source: "owner_grant",
    });
    expect(arg).not.toHaveProperty("tier");
    expect(arg).not.toHaveProperty("expires_at");
    expect(arg).not.toHaveProperty("isOwner");
  });

  it("revoke tanpa duration valid -> 200", async () => {
    const res = await POST(reqJson({ guild_id: GUILD, actor_id: ACTOR, action: "revoke" }));
    expect(res.status).toBe(200);
    expect(apply).toHaveBeenCalledWith(
      expect.objectContaining({ action: "revoke", durationDays: null }),
    );
  });
});
