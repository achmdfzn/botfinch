import { describe, expect, it, vi, afterEach } from "vitest";
import { canManage, inviteUrl, INVITE_PERMISSIONS, type DiscordGuild } from "@/lib/discord";

function guild(partial: Partial<DiscordGuild>): DiscordGuild {
  return { id: "12345", name: "Test", icon: null, permissions: "0", ...partial };
}

describe("canManage", () => {
  it("owner selalu boleh walau bit absen", () => {
    expect(canManage(guild({ owner: true, permissions: "0" }))).toBe(true);
  });
  it("bit MANAGE_GUILD (0x20) cukup", () => {
    expect(canManage(guild({ permissions: String(0x20) }))).toBe(true);
    expect(canManage(guild({ permissions: String(0x20 | 0x800) }))).toBe(true);
  });
  it("tanpa bit & bukan owner ditolak", () => {
    expect(canManage(guild({ permissions: "0" }))).toBe(false);
    expect(canManage(guild({ permissions: String(0x800) }))).toBe(false);
    expect(canManage(guild({ owner: false, permissions: "0" }))).toBe(false);
  });
});

describe("inviteUrl", () => {
  afterEach(() => {
    delete process.env.NEXT_PUBLIC_DISCORD_CLIENT_ID;
    delete process.env.DISCORD_CLIENT_ID;
    vi.restoreAllMocks();
  });

  it("pakai NEXT_PUBLIC_DISCORD_CLIENT_ID + bitmask least-privilege", () => {
    process.env.NEXT_PUBLIC_DISCORD_CLIENT_ID = "999";
    const url = inviteUrl();
    expect(url).toContain("client_id=999");
    expect(url).toContain(`permissions=${INVITE_PERMISSIONS}`);
    expect(url).toContain("scope=bot+applications.commands");
  });

  it("fallback ke DISCORD_CLIENT_ID bila NEXT_PUBLIC_ kosong", () => {
    process.env.DISCORD_CLIENT_ID = "888";
    const url = inviteUrl();
    expect(url).toContain("client_id=888");
  });

  it("warn server-side bila client ID kosong (E-S14)", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const url = inviteUrl();
    expect(url).toContain("client_id=&");
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("NEXT_PUBLIC_DISCORD_CLIENT_ID"));
  });
});

describe("INVITE_PERMISSIONS", () => {
  it("bukan Administrator (8): least-privilege", () => {
    expect(INVITE_PERMISSIONS & 8).toBe(0);
    expect(INVITE_PERMISSIONS).toBe(6862400592);
  });
});
