/**
 * Gerbang kuota jalur mutasi dashboard (putaran final):
 * - POST autoresponses: trigger baru di bawah limit lolos; mencapai
 *   limit -> 409 bentuk seragam dan TIDAK ada baris baru; update
 *   trigger lama saat kuota penuh tetap lolos.
 * - POST selfroles: kuota per panel (message_id berbeda); panel baru
 *   ditolak saat penuh; emoji baru di panel lama saat penuh lolos.
 * - POST giveaways: pre-check pending + aktif snapshot mencapai limit
 *   -> 409; di bawah limit lolos.
 * - Tier VIP memakai limit VIP; guild tanpa entitlement = free.
 *
 * Pola: @vercel/postgres di-mock dengan fake STATEFUL (mengikuti pola
 * mock di billing-db.test.ts / db-announcement-sent.test.ts) yang
 * menerapkan semantik WHERE pada statement kuota (EXISTS panel/trigger
 * lama ATAU COUNT < limit) terhadap tabel di memori. Jadi yang diuji
 * adalah route ASLI + helper db.ts ASLI bersambung, bukan mock route:
 * "tidak ada insert" dibuktikan dari isi tabel yang tidak berubah,
 * dan cabang "sudah ada -> selalu boleh" dibuktikan dari baris yang
 * benar-benar ter-update saat kuota penuh.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

type Row = Record<string, unknown>;

interface AutoRow { id: number; guild_id: string; trigger: string; response: string }
interface SelfRow { id: number; guild_id: string; message_id: string; emoji: string; role_id: string }

const sqlCalls: { text: string; values: unknown[] }[] = [];
let autoRows = new Map<string, AutoRow>();
let selfRows = new Map<string, SelfRow>();
let giveawayReqs: { guild_id: string; status: string }[] = [];
let entitlementRow: Row | null = null;
let snapshotPayload: unknown = null;
let nextId = 1;

function handleSql(text: string, values: unknown[]): Row[] {
  if (text.includes("FROM snapshots")) {
    return snapshotPayload ? [{ payload: snapshotPayload }] : [];
  }
  if (text.includes("FROM guild_entitlements")) {
    return entitlementRow ? [entitlementRow] : [];
  }
  if (text.includes("INSERT INTO autoresponses")) {
    // Nilai template berurutan: guild, trigger, response,
    // guild, trigger (EXISTS), guild, limit (COUNT < limit).
    const guildId = values[0] as string;
    const trigger = values[1] as string;
    const response = values[2] as string;
    const limit = values[6] as number;
    const key = `${guildId}|${trigger}`;
    const exists = autoRows.has(key);
    const count = [...autoRows.values()].filter((r) => r.guild_id === guildId).length;
    if (!exists && count >= limit) return [];
    const prev = autoRows.get(key);
    const row: AutoRow = { id: prev?.id ?? nextId++, guild_id: guildId, trigger, response };
    autoRows.set(key, row);
    return [{ id: row.id }];
  }
  if (text.includes("DELETE FROM autoresponses")) {
    const guildId = values[0] as string;
    if (typeof values[1] === "number") {
      for (const [key, row] of autoRows) {
        if (row.guild_id === guildId && row.id === values[1]) autoRows.delete(key);
      }
    } else {
      autoRows.delete(`${guildId}|${values[1] as string}`);
    }
    return [];
  }
  if (text.includes("FROM autoresponses")) {
    const guildId = values[0] as string;
    return [{ count: [...autoRows.values()].filter((r) => r.guild_id === guildId).length }];
  }
  if (text.includes("INSERT INTO selfroles")) {
    // Nilai template berurutan: guild, message, emoji, role,
    // guild, message (EXISTS), guild, limit (COUNT DISTINCT < limit).
    const guildId = values[0] as string;
    const messageId = values[1] as string;
    const emoji = values[2] as string;
    const roleId = values[3] as string;
    const limit = values[7] as number;
    const mine = [...selfRows.values()].filter((r) => r.guild_id === guildId);
    const panelExists = mine.some((r) => r.message_id === messageId);
    const panels = new Set(mine.map((r) => r.message_id)).size;
    if (!panelExists && panels >= limit) return [];
    const key = `${guildId}|${messageId}|${emoji}`;
    const prev = selfRows.get(key);
    const row: SelfRow = {
      id: prev?.id ?? nextId++, guild_id: guildId, message_id: messageId, emoji, role_id: roleId,
    };
    selfRows.set(key, row);
    return [{ id: row.id }];
  }
  if (text.includes("FROM selfroles")) {
    const guildId = values[0] as string;
    const panels = new Set(
      [...selfRows.values()].filter((r) => r.guild_id === guildId).map((r) => r.message_id),
    ).size;
    return [{ count: panels }];
  }
  if (text.includes("INSERT INTO giveaway_requests")) {
    giveawayReqs.push({ guild_id: values[0] as string, status: "pending" });
    return [];
  }
  if (text.includes("FROM giveaway_requests")) {
    const guildId = values[0] as string;
    return [{
      count: giveawayReqs.filter((r) => r.guild_id === guildId && r.status === "pending").length,
    }];
  }
  return [];
}

vi.mock("@vercel/postgres", () => ({
  sql: (strings: TemplateStringsArray, ...values: unknown[]) => {
    const text = strings.join(" ");
    sqlCalls.push({ text, values });
    return Promise.resolve({ rows: handleSql(text, values) });
  },
}));

vi.mock("@/lib/access", () => ({
  botAuthorized: vi.fn(() => false),
  requireManager: vi.fn(async () => null),
}));

import { DELETE as autoDelete, POST as autoPost } from "../app/api/guilds/[id]/autoresponses/route";
import { POST as selfPost } from "../app/api/guilds/[id]/selfroles/route";
import { POST as giveawayPost } from "../app/api/guilds/[id]/giveaways/route";
import * as access from "@/lib/access";
import type { SnapshotPayload } from "@/lib/db";

const botAuthorized = vi.mocked(access.botAuthorized);
const requireManager = vi.mocked(access.requireManager);

const GUILD = "111111111111111111";
const CHANNEL = "222222222222222222";
const ROLE = "333333333333333333";
const PANEL_BARU = "644444444444444444";

function panelMsg(i: number): string {
  return `62000000000000000${i}`;
}

function reqJson(body: unknown): Request {
  return new Request("http://localhost/api", {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "content-type": "application/json" },
  });
}

const ctx = { params: Promise.resolve({ id: GUILD }) };

function snapshotWith(activeGiveaways: number): SnapshotPayload {
  return {
    bot_name: "Finch",
    pushed_at: "2026-10-23T00:00:00.000Z",
    guilds: [{
      id: GUILD,
      name: "Server Uji",
      icon: null,
      member_count: 10,
      channels: [{ id: CHANNEL, name: "umum", type: 0 }],
      roles: [],
      leaderboards: { levels: [], coins: [] },
      giveaways: Array.from({ length: activeGiveaways }, (_, i) => ({
        id: i + 1,
        channel_id: CHANNEL,
        prize: "Hadiah",
        winners: 1,
        ends_at: "2026-10-24T00:00:00.000Z",
        participants: 0,
      })),
      modlog: [],
    }],
  };
}

function vipEntitlement(): Row {
  return {
    guild_id: GUILD,
    tier: "vip",
    status: "active",
    source: "owner_grant",
    starts_at: "2026-10-01T00:00:00.000Z",
    expires_at: null,
    provider_entitlement_id: null,
    provider_subscription_id: null,
    granted_by: "999999999999999999",
    note: null,
    bot_present: true,
    first_seen_at: "2026-10-01T00:00:00.000Z",
    last_seen_at: "2026-10-23T00:00:00.000Z",
    created_at: "2026-10-01T00:00:00.000Z",
    updated_at: "2026-10-23T00:00:00.000Z",
  };
}

function seedAuto(n: number): void {
  for (let i = 1; i <= n; i++) {
    autoRows.set(`${GUILD}|rule-${i}`, {
      id: i, guild_id: GUILD, trigger: `rule-${i}`, response: "balasan",
    });
  }
}

function seedSelfPanels(n: number): void {
  for (let i = 0; i < n; i++) {
    selfRows.set(`${GUILD}|${panelMsg(i)}|👍`, {
      id: i + 1, guild_id: GUILD, message_id: panelMsg(i), emoji: "👍", role_id: ROLE,
    });
  }
}

function seedPending(n: number): void {
  for (let i = 0; i < n; i++) giveawayReqs.push({ guild_id: GUILD, status: "pending" });
}

/** Nilai limit yang benar-benar diteruskan route ke statement kuota. */
function insertLimit(fragment: string, valueIndex: number): unknown {
  const call = sqlCalls.find((c) => c.text.includes(fragment));
  return call?.values[valueIndex];
}

beforeEach(() => {
  sqlCalls.length = 0;
  autoRows = new Map();
  selfRows = new Map();
  giveawayReqs = [];
  entitlementRow = null;
  snapshotPayload = snapshotWith(0);
  nextId = 100;
  botAuthorized.mockReturnValue(false);
  requireManager.mockResolvedValue(null);
  process.env.POSTGRES_URL = "postgres://test:test@localhost/test";
});

describe("POST autoresponses — gerbang kuota", () => {
  it("trigger baru di bawah limit lolos (200), tertulis, trigger di-lowercase", async () => {
    seedAuto(2);
    const res = await autoPost(reqJson({ trigger: "Baru", response: "Halo!" }), ctx);
    expect(res.status).toBe(200);
    expect(autoRows.size).toBe(3);
    expect(autoRows.get(`${GUILD}|baru`)?.response).toBe("Halo!");
    // Guild tanpa entitlement -> limit free (10) diteruskan ke SQL.
    expect(insertLimit("INSERT INTO autoresponses", 6)).toBe(10);
  });

  it("mirror bot ber-DASHBOARD_SECRET tidak butuh sesi manager untuk POST dan DELETE", async () => {
    botAuthorized.mockReturnValue(true);
    requireManager.mockResolvedValue(
      new Response(JSON.stringify({ error: "unauthorized" }), { status: 401 }) as never,
    );
    const postRes = await autoPost(reqJson({ trigger: "dari-bot", response: "Halo!" }), ctx);
    expect(postRes.status).toBe(200);
    expect(autoRows.has(`${GUILD}|dari-bot`)).toBe(true);
    expect(requireManager).not.toHaveBeenCalled();

    const deleteReq = new Request(`http://localhost/api?trigger=${encodeURIComponent("dari-bot")}`, {
      method: "DELETE",
    });
    const deleteRes = await autoDelete(deleteReq, ctx);
    expect(deleteRes.status).toBe(200);
    expect(autoRows.has(`${GUILD}|dari-bot`)).toBe(false);
    expect(requireManager).not.toHaveBeenCalled();
  });

  it("trigger baru mencapai limit -> 409 bentuk seragam dan tidak ada insert", async () => {
    seedAuto(10);
    const res = await autoPost(reqJson({ trigger: "kesebelas", response: "Halo!" }), ctx);
    expect(res.status).toBe(409);
    expect(await res.json()).toEqual({
      error: "quota_exceeded",
      feature: "autoresponders",
      used: 10,
      limit: 10,
      vip_limit: 100,
      tier: "free",
    });
    expect(autoRows.size).toBe(10);
    expect(autoRows.has(`${GUILD}|kesebelas`)).toBe(false);
  });

  it("update trigger lama saat kuota penuh tetap lolos (200, response berubah)", async () => {
    seedAuto(9);
    autoRows.set(`${GUILD}|halo`, {
      id: 50, guild_id: GUILD, trigger: "halo", response: "lama",
    });
    const res = await autoPost(reqJson({ trigger: "HALO", response: "diperbarui" }), ctx);
    expect(res.status).toBe(200);
    expect(autoRows.size).toBe(10);
    expect(autoRows.get(`${GUILD}|halo`)?.response).toBe("diperbarui");
  });

  it("tier VIP memakai limit VIP: trigger baru ke-11 lolos, limit 100 diteruskan", async () => {
    entitlementRow = vipEntitlement();
    seedAuto(10);
    const res = await autoPost(reqJson({ trigger: "vip-baru", response: "Halo!" }), ctx);
    expect(res.status).toBe(200);
    expect(autoRows.size).toBe(11);
    expect(insertLimit("INSERT INTO autoresponses", 6)).toBe(100);
  });

  it("guild tanpa entitlement diperlakukan free (limit 10, tier 'free' di respons)", async () => {
    entitlementRow = null;
    seedAuto(10);
    const res = await autoPost(reqJson({ trigger: "baru", response: "Halo!" }), ctx);
    expect(res.status).toBe(409);
    const json = (await res.json()) as { tier: string; limit: number };
    expect(json.tier).toBe("free");
    expect(json.limit).toBe(10);
  });
});

describe("POST selfroles — gerbang kuota per panel", () => {
  it("panel baru di bawah limit lolos (200) dan tertulis", async () => {
    seedSelfPanels(2);
    const res = await selfPost(
      reqJson({ message_id: PANEL_BARU, emoji: "👍", role_id: ROLE }), ctx,
    );
    expect(res.status).toBe(200);
    expect(selfRows.size).toBe(3);
    expect(insertLimit("INSERT INTO selfroles", 7)).toBe(3);
  });

  it("panel baru ditolak saat kuota penuh -> 409 bentuk seragam, tidak ada baris baru", async () => {
    seedSelfPanels(3);
    const res = await selfPost(
      reqJson({ message_id: PANEL_BARU, emoji: "👍", role_id: ROLE }), ctx,
    );
    expect(res.status).toBe(409);
    expect(await res.json()).toEqual({
      error: "quota_exceeded",
      feature: "selfrole_panels",
      used: 3,
      limit: 3,
      vip_limit: 25,
      tier: "free",
    });
    expect(selfRows.size).toBe(3);
    expect([...selfRows.values()].some((r) => r.message_id === PANEL_BARU)).toBe(false);
  });

  it("emoji baru di panel lama saat kuota penuh tetap lolos (200)", async () => {
    seedSelfPanels(3);
    const res = await selfPost(
      reqJson({ message_id: panelMsg(0), emoji: "🔥", role_id: ROLE }), ctx,
    );
    expect(res.status).toBe(200);
    expect(selfRows.size).toBe(4);
    expect(selfRows.get(`${GUILD}|${panelMsg(0)}|🔥`)?.role_id).toBe(ROLE);
  });
});

describe("POST giveaways — pre-check kuota pending + aktif", () => {
  const bodyValid = {
    channel_id: CHANNEL, prize: "Nitro", winners: 1, duration_minutes: 60,
  };

  it("pending + aktif mencapai limit -> 409 bentuk seragam, request tidak tertulis", async () => {
    snapshotPayload = snapshotWith(1);
    seedPending(2);
    const res = await giveawayPost(reqJson(bodyValid), ctx);
    expect(res.status).toBe(409);
    expect(await res.json()).toEqual({
      error: "quota_exceeded",
      feature: "giveaways_active",
      used: 3,
      limit: 3,
      vip_limit: 25,
      tier: "free",
    });
    expect(giveawayReqs).toHaveLength(2);
  });

  it("di bawah limit lolos (200) dan request pending tertulis", async () => {
    snapshotPayload = snapshotWith(1);
    seedPending(1);
    const res = await giveawayPost(reqJson(bodyValid), ctx);
    expect(res.status).toBe(200);
    expect(giveawayReqs).toHaveLength(2);
  });

  it("tier VIP memakai limit VIP: used = limit free tetap lolos", async () => {
    entitlementRow = vipEntitlement();
    snapshotPayload = snapshotWith(1);
    seedPending(2);
    const res = await giveawayPost(reqJson(bodyValid), ctx);
    expect(res.status).toBe(200);
    expect(giveawayReqs).toHaveLength(3);
  });
});
