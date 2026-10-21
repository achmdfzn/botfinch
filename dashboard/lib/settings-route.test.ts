/**
 * Regresi audit P1 — PUT /api/guilds/[id]/settings:
 * Validasi key channel terhadap snapshot guild harus FAIL-SAFE:
 * snapshot kosong/guild tidak ditemukan TIDAK boleh meloloskan
 * *_channel_id / *_category_id / *_lobby_id. Tipe juga harus sesuai
 * fungsi (teks 0/5, kategori 4, lobby voice 2). Key non-channel tidak
 * terpengaruh ketiadaan snapshot.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/db", () => ({
  dbConfigured: vi.fn(() => true),
  getStoredSettings: vi.fn(async () => ({})),
  latestSnapshot: vi.fn(async () => null),
  mergeStoredSettings: vi.fn(async () => {}),
  withDbError: (fn: unknown) => fn,
}));

vi.mock("@/lib/access", () => ({
  botAuthorized: vi.fn(() => true),
  requireManager: vi.fn(async () => null),
}));

import * as db from "@/lib/db";
import type { SnapshotPayload } from "@/lib/db";
import { PUT } from "../app/api/guilds/[id]/settings/route";

const latestSnapshot = vi.mocked(db.latestSnapshot);
const mergeStoredSettings = vi.mocked(db.mergeStoredSettings);

const GUILD = "111111111111111111";
const CHANNEL = "222222222222222222";

function reqJson(body: unknown): Request {
  return new Request("http://localhost/api", {
    method: "PUT",
    body: JSON.stringify(body),
    headers: { "content-type": "application/json" },
  });
}

const ctx = { params: Promise.resolve({ id: GUILD }) };

function snapshotDengan(channelType: number, guildId: string = GUILD): SnapshotPayload {
  return {
    bot_name: "Finch",
    pushed_at: "2026-10-22T00:00:00.000Z",
    guilds: [{
      id: guildId,
      name: "Server Uji",
      icon: null,
      member_count: 10,
      channels: [{ id: CHANNEL, name: "umum", type: channelType }],
      roles: [],
      leaderboards: { levels: [], coins: [] },
      giveaways: [],
      modlog: [],
    }],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  latestSnapshot.mockResolvedValue(null);
});

describe("PUT settings — validasi channel fail-safe", () => {
  it("snapshot kosong -> welcome_channel_id ditolak (400), tidak ada penulisan", async () => {
    const res = await PUT(reqJson({ welcome_channel_id: CHANNEL }), ctx);
    expect(res.status).toBe(400);
    expect(((await res.json()) as { error: string }).error).toBe("invalid_channel_setting");
    expect(mergeStoredSettings).not.toHaveBeenCalled();
  });

  it("guild tidak ada di snapshot -> channel ditolak (400)", async () => {
    latestSnapshot.mockResolvedValue(snapshotDengan(0, "999999999999999999"));
    const res = await PUT(reqJson({ welcome_channel_id: CHANNEL }), ctx);
    expect(res.status).toBe(400);
    expect(mergeStoredSettings).not.toHaveBeenCalled();
  });

  it("channel ada tapi tipe voice untuk welcome_channel_id -> ditolak (400)", async () => {
    latestSnapshot.mockResolvedValue(snapshotDengan(2));
    const res = await PUT(reqJson({ welcome_channel_id: CHANNEL }), ctx);
    expect(res.status).toBe(400);
    expect(mergeStoredSettings).not.toHaveBeenCalled();
  });

  it("channel teks milik guild -> diterima (200) dan ditulis ter-scope guild", async () => {
    latestSnapshot.mockResolvedValue(snapshotDengan(0));
    const res = await PUT(reqJson({ welcome_channel_id: CHANNEL }), ctx);
    expect(res.status).toBe(200);
    expect(mergeStoredSettings).toHaveBeenCalledWith(
      GUILD, expect.objectContaining({ welcome_channel_id: CHANNEL }),
    );
  });

  it("ticket_category_id mensyaratkan tipe kategori (4)", async () => {
    latestSnapshot.mockResolvedValue(snapshotDengan(0));
    const ditolak = await PUT(reqJson({ ticket_category_id: CHANNEL }), ctx);
    expect(ditolak.status).toBe(400);
    latestSnapshot.mockResolvedValue(snapshotDengan(4));
    const diterima = await PUT(reqJson({ ticket_category_id: CHANNEL }), ctx);
    expect(diterima.status).toBe(200);
  });

  it("snapshot kosong TIDAK menghalangi key non-channel", async () => {
    const res = await PUT(reqJson({ goodbye_message: "Sampai jumpa!" }), ctx);
    expect(res.status).toBe(200);
    expect(mergeStoredSettings).toHaveBeenCalledTimes(1);
  });
});
