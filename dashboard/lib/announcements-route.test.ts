/**
 * Regresi audit P1 — route pengumuman:
 * - POST ack bot: wajib botAuthorized (401), timestamp ketat (400),
 *   id/guild tidak cocok (404), dan hanya field last_sent_at yang diubah.
 * - PUT manager: channel_id dari guild lain / tipe non-teks ditolak (400)
 *   dan update selalu ter-scope guild pada URL, bukan dari body.
 * - POST buat baru: channel lintas-guild, tipe voice, dan snapshot kosong
 *   semuanya ditolak (fail-safe).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/db", () => ({
  dbConfigured: vi.fn(() => true),
  deleteAnnouncement: vi.fn(async () => true),
  getSnapshotChannel: vi.fn(async () => null),
  markAnnouncementSent: vi.fn(async () => true),
  updateAnnouncement: vi.fn(async () => true),
  createAnnouncement: vi.fn(async () => 42),
  createAnnouncementWithQuota: vi.fn(async () => 42),
  getEntitlement: vi.fn(async () => null),
  countActiveAnnouncements: vi.fn(async () => 0),
  listAnnouncements: vi.fn(async () => []),
  withDbError: (fn: unknown) => fn,
}));

vi.mock("@/lib/access", () => ({
  botAuthorized: vi.fn(() => false),
  requireManager: vi.fn(async () => null),
}));

import * as access from "@/lib/access";
import * as db from "@/lib/db";
import { DELETE, POST as ackPost, PUT } from "../app/api/guilds/[id]/announcements/[annId]/route";
import { POST as createPost } from "../app/api/guilds/[id]/announcements/route";

const botAuth = vi.mocked(access.botAuthorized);
const manager = vi.mocked(access.requireManager);
const getSnapshotChannel = vi.mocked(db.getSnapshotChannel);
const markAnnouncementSent = vi.mocked(db.markAnnouncementSent);
const updateAnnouncement = vi.mocked(db.updateAnnouncement);
const deleteAnnouncement = vi.mocked(db.deleteAnnouncement);
const createAnnouncement = vi.mocked(db.createAnnouncement);
const createAnnouncementWithQuota = vi.mocked(db.createAnnouncementWithQuota);
const getEntitlement = vi.mocked(db.getEntitlement);
const countActiveAnnouncements = vi.mocked(db.countActiveAnnouncements);

const GUILD = "111111111111111111";
const CHANNEL_TEKS = "222222222222222222";
const TS = "2026-10-22T05:00:00.000Z";

function reqJson(body: unknown): Request {
  return new Request("http://localhost/api", {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "content-type": "application/json" },
  });
}

const ctxAnn = { params: Promise.resolve({ id: GUILD, annId: "5" }) };
const ctxGuild = { params: Promise.resolve({ id: GUILD }) };

beforeEach(() => {
  vi.clearAllMocks();
  botAuth.mockReturnValue(false);
  manager.mockResolvedValue(null);
  getSnapshotChannel.mockResolvedValue(null);
  markAnnouncementSent.mockResolvedValue(true);
  updateAnnouncement.mockResolvedValue(true);
  deleteAnnouncement.mockResolvedValue(true);
  createAnnouncementWithQuota.mockResolvedValue(42);
  getEntitlement.mockResolvedValue(null);
  countActiveAnnouncements.mockResolvedValue(0);
});

describe("POST ack bot (last_sent_at)", () => {
  it("menolak tanpa autentikasi bot (401) dan tidak menyentuh DB", async () => {
    const res = await ackPost(reqJson({ last_sent_at: TS }), ctxAnn);
    expect(res.status).toBe(401);
    expect(markAnnouncementSent).not.toHaveBeenCalled();
  });

  it("menolak timestamp tidak valid (400)", async () => {
    botAuth.mockReturnValue(true);
    for (const bad of ["bukan-tanggal", 12345, null]) {
      const res = await ackPost(reqJson({ last_sent_at: bad }), ctxAnn);
      expect(res.status).toBe(400);
    }
    expect(markAnnouncementSent).not.toHaveBeenCalled();
  });

  it("404 bila pengumuman tidak ada / guild tidak cocok", async () => {
    botAuth.mockReturnValue(true);
    markAnnouncementSent.mockResolvedValue(false);
    const res = await ackPost(reqJson({ last_sent_at: TS }), ctxAnn);
    expect(res.status).toBe(404);
    expect(markAnnouncementSent).toHaveBeenCalledWith(5, GUILD, TS);
  });

  it("200 dan hanya meneruskan (id, guild, timestamp) ke DB", async () => {
    botAuth.mockReturnValue(true);
    const res = await ackPost(
      reqJson({ last_sent_at: TS, message: "diubah penyerang", channel_id: "999" }),
      ctxAnn,
    );
    expect(res.status).toBe(200);
    expect(markAnnouncementSent).toHaveBeenCalledTimes(1);
    expect(markAnnouncementSent).toHaveBeenCalledWith(5, GUILD, TS);
  });
});

describe("PUT pengumuman (manager)", () => {
  it("menolak channel_id milik guild lain (400, tanpa update)", async () => {
    getSnapshotChannel.mockResolvedValue(null);
    const res = await PUT(reqJson({ channel_id: CHANNEL_TEKS }), ctxAnn);
    expect(res.status).toBe(400);
    expect(getSnapshotChannel).toHaveBeenCalledWith(GUILD, CHANNEL_TEKS);
    expect(updateAnnouncement).not.toHaveBeenCalled();
  });

  it("menolak channel voice di guild sendiri (400, tanpa update)", async () => {
    getSnapshotChannel.mockResolvedValue({
      id: CHANNEL_TEKS, name: "voice", type: 2,
    });
    const res = await PUT(reqJson({ channel_id: CHANNEL_TEKS }), ctxAnn);
    expect(res.status).toBe(400);
    expect(updateAnnouncement).not.toHaveBeenCalled();
  });

  it("update ter-scope guild dari URL, bukan dari body", async () => {
    const res = await PUT(
      reqJson({ message: "revisi", guild_id: "999999999999999999" }),
      ctxAnn,
    );
    expect(res.status).toBe(200);
    expect(updateAnnouncement).toHaveBeenCalledWith(
      5, GUILD, expect.objectContaining({ message: "revisi" }),
    );
  });

  it("404 bila id pengumuman tidak ada di guild itu", async () => {
    updateAnnouncement.mockResolvedValue(false);
    const res = await PUT(reqJson({ message: "revisi" }), ctxAnn);
    expect(res.status).toBe(404);
  });
});

describe("DELETE pengumuman (manager)", () => {
  it("200 dan ter-scope (id, guild) bila baris ada", async () => {
    const res = await DELETE(reqJson({}), ctxAnn);
    expect(res.status).toBe(200);
    expect(deleteAnnouncement).toHaveBeenCalledWith(5, GUILD);
  });

  it("404 bila id pengumuman milik guild lain / tidak ada", async () => {
    deleteAnnouncement.mockResolvedValue(false);
    const res = await DELETE(reqJson({}), ctxAnn);
    expect(res.status).toBe(404);
  });
});

describe("POST buat pengumuman (manager)", () => {
  const bodyValid = {
    channel_id: CHANNEL_TEKS,
    message: "Halo server",
    run_at: "2026-10-23T05:00:00.000Z",
    interval_minutes: null,
  };

  it("menolak bila snapshot tidak punya channel itu (fail-safe)", async () => {
    getSnapshotChannel.mockResolvedValue(null);
    const res = await createPost(reqJson(bodyValid), ctxGuild);
    expect(res.status).toBe(400);
    expect(createAnnouncement).not.toHaveBeenCalled();
    expect(createAnnouncementWithQuota).not.toHaveBeenCalled();
  });

  it("menolak channel tipe voice (400)", async () => {
    getSnapshotChannel.mockResolvedValue({
      id: CHANNEL_TEKS, name: "voice", type: 2,
    });
    const res = await createPost(reqJson(bodyValid), ctxGuild);
    expect(res.status).toBe(400);
    expect(createAnnouncement).not.toHaveBeenCalled();
    expect(createAnnouncementWithQuota).not.toHaveBeenCalled();
  });

  it("menerima channel news (tipe 5) milik guild", async () => {
    getSnapshotChannel.mockResolvedValue({
      id: CHANNEL_TEKS, name: "pengumuman", type: 5,
    });
    const res = await createPost(reqJson(bodyValid), ctxGuild);
    expect(res.status).toBe(200);
    expect(createAnnouncementWithQuota).toHaveBeenCalledTimes(1);
    // Guild tanpa baris entitlement = free -> limit 3 diteruskan.
    expect(createAnnouncementWithQuota.mock.calls[0][1]).toBe(3);
  });

  it("kuota free penuh (createAnnouncementWithQuota -> null) -> 409 tanpa create lama", async () => {
    getSnapshotChannel.mockResolvedValue({
      id: CHANNEL_TEKS, name: "umum", type: 0,
    });
    createAnnouncementWithQuota.mockResolvedValue(null);
    const res = await createPost(reqJson(bodyValid), ctxGuild);
    expect(res.status).toBe(409);
    const json = (await res.json()) as { error: string; limit: number };
    expect(json).toEqual({ error: "announcement_quota_exceeded", limit: 3 });
    expect(createAnnouncement).not.toHaveBeenCalled();
  });

  it("guild VIP -> limit 25 diteruskan ke createAnnouncementWithQuota", async () => {
    getSnapshotChannel.mockResolvedValue({
      id: CHANNEL_TEKS, name: "umum", type: 0,
    });
    getEntitlement.mockResolvedValue({
      guild_id: GUILD,
      tier: "vip",
      status: "active",
      source: "owner_grant",
      starts_at: "2026-10-01T00:00:00.000Z",
      expires_at: null,
      granted_by: "999999999999999999",
      note: null,
      bot_present: true,
      first_seen_at: "2026-10-01T00:00:00.000Z",
      last_seen_at: "2026-10-22T00:00:00.000Z",
      created_at: "2026-10-01T00:00:00.000Z",
      updated_at: "2026-10-22T00:00:00.000Z",
      provider_entitlement_id: null,
      provider_subscription_id: null,
    });
    const res = await createPost(reqJson(bodyValid), ctxGuild);
    expect(res.status).toBe(200);
    expect(createAnnouncementWithQuota).toHaveBeenCalledTimes(1);
    expect(createAnnouncementWithQuota.mock.calls[0][1]).toBe(25);
    expect(createAnnouncementWithQuota.mock.calls[0][0]).toMatchObject({
      guildId: GUILD,
      channelId: CHANNEL_TEKS,
      message: "Halo server",
    });
  });
});

describe("PUT pengumuman — kuota saat mengaktifkan", () => {
  it("enabled=true saat kuota free penuh -> 409 sebelum update", async () => {
    countActiveAnnouncements.mockResolvedValue(3);
    const res = await PUT(reqJson({ enabled: true }), ctxAnn);
    expect(res.status).toBe(409);
    const json = (await res.json()) as { error: string; limit: number };
    expect(json).toEqual({ error: "announcement_quota_exceeded", limit: 3 });
    expect(updateAnnouncement).not.toHaveBeenCalled();
  });

  it("enabled=true di bawah kuota -> update jalan (200)", async () => {
    countActiveAnnouncements.mockResolvedValue(2);
    const res = await PUT(reqJson({ enabled: true }), ctxAnn);
    expect(res.status).toBe(200);
    expect(updateAnnouncement).toHaveBeenCalledTimes(1);
  });

  it("enabled=false tidak dicek kuota", async () => {
    countActiveAnnouncements.mockResolvedValue(99);
    const res = await PUT(reqJson({ enabled: false }), ctxAnn);
    expect(res.status).toBe(200);
    expect(countActiveAnnouncements).not.toHaveBeenCalled();
  });
});
