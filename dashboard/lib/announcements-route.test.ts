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
  });

  it("menolak channel tipe voice (400)", async () => {
    getSnapshotChannel.mockResolvedValue({
      id: CHANNEL_TEKS, name: "voice", type: 2,
    });
    const res = await createPost(reqJson(bodyValid), ctxGuild);
    expect(res.status).toBe(400);
    expect(createAnnouncement).not.toHaveBeenCalled();
  });

  it("menerima channel news (tipe 5) milik guild", async () => {
    getSnapshotChannel.mockResolvedValue({
      id: CHANNEL_TEKS, name: "pengumuman", type: 5,
    });
    const res = await createPost(reqJson(bodyValid), ctxGuild);
    expect(res.status).toBe(200);
    expect(createAnnouncement).toHaveBeenCalledTimes(1);
  });
});
