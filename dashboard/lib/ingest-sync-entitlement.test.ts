/**
 * Entitlement di jalur bot:
 * - ingest: guild tersanitasi didaftarkan via registerGuildsSeen setelah
 *   snapshot tersimpan (guild baru -> free di DB lewat DEFAULT skema).
 * - sync: response memuat field entitlement dari getEntitlement; guild
 *   tanpa baris -> ensureEntitlement dipanggil (lazy free) dan responsenya
 *   free; baris tetap null -> default free dikirim, sync tidak gagal.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@vercel/postgres", () => ({
  sql: () => Promise.resolve({ rows: [] }),
}));

const FREE_ROW = {
  guild_id: "111111111111111111",
  tier: "free",
  status: "active",
  source: "default",
  starts_at: null,
  expires_at: null,
  granted_by: null,
  note: null,
  bot_present: true,
  first_seen_at: "2026-10-22T00:00:00.000Z",
  last_seen_at: "2026-10-22T00:00:00.000Z",
  created_at: "2026-10-22T00:00:00.000Z",
  updated_at: "2026-10-22T00:00:00.000Z",
  provider_entitlement_id: null,
  provider_subscription_id: null,
};

const VIP_ROW = {
  ...FREE_ROW,
  tier: "vip",
  source: "owner_grant",
  expires_at: "2026-11-21T00:00:00.000Z",
  updated_at: "2026-10-22T01:00:00.000Z",
};

vi.mock("@/lib/db", () => ({
  dbConfigured: vi.fn(() => true),
  saveSnapshot: vi.fn(async () => {}),
  registerGuildsSeen: vi.fn(async () => {}),
  getStoredSettings: vi.fn(async () => ({})),
  getSelfRoles: vi.fn(async () => []),
  getAutoResponses: vi.fn(async () => []),
  listAnnouncements: vi.fn(async () => []),
  getEntitlement: vi.fn(async () => null),
  ensureEntitlement: vi.fn(async () => null),
  withDbError: (fn: unknown) => fn,
}));

vi.mock("@/lib/access", () => ({
  botAuthorized: vi.fn(() => true),
}));

import * as db from "@/lib/db";
import { POST as ingestPost } from "../app/api/ingest/route";
import { GET as syncGet } from "../app/api/guilds/[id]/sync/route";

const saveSnapshot = vi.mocked(db.saveSnapshot);
const registerGuildsSeen = vi.mocked(db.registerGuildsSeen);
const getEntitlement = vi.mocked(db.getEntitlement);
const ensureEntitlement = vi.mocked(db.ensureEntitlement);

const GUILD = "111111111111111111";
const GUILD2 = "444444444444444444";

function reqJson(body: unknown): Request {
  return new Request("http://localhost/api/ingest", {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "content-type": "application/json" },
  });
}

const ctx = { params: Promise.resolve({ id: GUILD }) };

beforeEach(() => {
  vi.clearAllMocks();
  getEntitlement.mockResolvedValue(null);
  ensureEntitlement.mockResolvedValue(null);
});

describe("ingest -> registrasi entitlement", () => {
  it("registerGuildsSeen terpanggil dengan guild tersanitasi", async () => {
    const res = await ingestPost(
      reqJson({
        bot_name: "Finch",
        guilds: [
          { id: GUILD, name: "Server Uji", member_count: 5, channels: [], roles: [] },
          { id: GUILD2, name: "Server Dua", member_count: 3, channels: [], roles: [] },
          { id: "bukan-id", name: "Dibuang", member_count: 1 },
        ],
      }),
    );
    expect(res.status).toBe(200);
    expect(saveSnapshot).toHaveBeenCalledTimes(1);
    expect(registerGuildsSeen).toHaveBeenCalledTimes(1);
    expect(registerGuildsSeen).toHaveBeenCalledWith([
      { id: GUILD, name: "Server Uji" },
      { id: GUILD2, name: "Server Dua" },
    ]);
  });

  it("kegagalan registrasi tidak menggagalkan ingest (best-effort)", async () => {
    registerGuildsSeen.mockRejectedValueOnce(new Error("db hiccup"));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const res = await ingestPost(
      reqJson({ bot_name: "Finch", guilds: [{ id: GUILD, name: "Server Uji" }] }),
    );
    expect(res.status).toBe(200);
    warn.mockRestore();
  });
});

describe("sync -> field entitlement", () => {
  it("guild VIP: entitlement dari getEntitlement, ensure tidak dipanggil", async () => {
    getEntitlement.mockResolvedValue(VIP_ROW);
    const res = await syncGet(new Request("http://localhost/api/sync"), ctx);
    expect(res.status).toBe(200);
    const json = (await res.json()) as { entitlement: Record<string, unknown> };
    expect(json.entitlement).toEqual({
      tier: "vip",
      status: "active",
      starts_at: null,
      expires_at: "2026-11-21T00:00:00.000Z",
      source: "owner_grant",
      updated_at: "2026-10-22T01:00:00.000Z",
    });
    expect(ensureEntitlement).not.toHaveBeenCalled();
  });

  it("guild tanpa baris: ensureEntitlement terpanggil dan response free", async () => {
    getEntitlement.mockResolvedValue(null);
    ensureEntitlement.mockResolvedValue(FREE_ROW);
    const res = await syncGet(new Request("http://localhost/api/sync"), ctx);
    expect(res.status).toBe(200);
    expect(ensureEntitlement).toHaveBeenCalledWith(GUILD);
    const json = (await res.json()) as { entitlement: Record<string, unknown> };
    expect(json.entitlement).toMatchObject({ tier: "free", source: "default" });
  });

  it("baris tetap null setelah ensure: default free dikirim", async () => {
    getEntitlement.mockResolvedValue(null);
    ensureEntitlement.mockResolvedValue(null);
    const res = await syncGet(new Request("http://localhost/api/sync"), ctx);
    expect(res.status).toBe(200);
    const json = (await res.json()) as { entitlement: Record<string, unknown> };
    expect(json.entitlement).toEqual({
      tier: "free",
      status: "active",
      starts_at: null,
      expires_at: null,
      source: "default",
      updated_at: null,
    });
  });
});
