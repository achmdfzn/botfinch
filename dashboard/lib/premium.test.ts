import { describe, expect, it } from "vitest";
import { FEATURE_LIMITS, getEffectiveTierFromRow, getFeatureLimit } from "./premium";

const NOW = new Date("2026-10-22T00:00:00.000Z");
const PAST = "2026-10-01T00:00:00.000Z";
const FUTURE = "2026-11-01T00:00:00.000Z";

describe("FEATURE_LIMITS", () => {
  it("mematok angka persis kelima fitur x kedua tier", () => {
    expect(FEATURE_LIMITS).toEqual({
      custom_commands: { free: 10, vip: 100 },
      autoresponders: { free: 10, vip: 100 },
      giveaways_active: { free: 3, vip: 25 },
      selfrole_panels: { free: 3, vip: 25 },
      announcements_active: { free: 3, vip: 25 },
    });
    expect(getFeatureLimit("free", "announcements_active")).toBe(3);
    expect(getFeatureLimit("vip", "announcements_active")).toBe(25);
    expect(getFeatureLimit("vip", "custom_commands")).toBe(100);
  });
});

describe("getEffectiveTierFromRow", () => {
  it("null / undefined -> free", () => {
    expect(getEffectiveTierFromRow(null, NOW)).toBe("free");
    expect(getEffectiveTierFromRow(undefined, NOW)).toBe("free");
  });

  it("vip aktif dalam masa berlaku -> vip", () => {
    expect(
      getEffectiveTierFromRow(
        { tier: "vip", status: "active", starts_at: PAST, expires_at: FUTURE },
        NOW,
      ),
    ).toBe("vip");
    // Bentuk Date juga diterima.
    expect(
      getEffectiveTierFromRow(
        { tier: "vip", status: "active", starts_at: new Date(PAST), expires_at: new Date(FUTURE) },
        NOW,
      ),
    ).toBe("vip");
  });

  it("belum mulai (starts_at di masa depan) -> free", () => {
    expect(
      getEffectiveTierFromRow(
        { tier: "vip", status: "active", starts_at: FUTURE, expires_at: null },
        NOW,
      ),
    ).toBe("free");
  });

  it("sudah kedaluwarsa (expires_at <= now) -> free", () => {
    expect(
      getEffectiveTierFromRow(
        { tier: "vip", status: "active", starts_at: PAST, expires_at: PAST },
        NOW,
      ),
    ).toBe("free");
    expect(
      getEffectiveTierFromRow(
        { tier: "vip", status: "active", starts_at: PAST, expires_at: NOW.toISOString() },
        NOW,
      ),
    ).toBe("free");
  });

  it("status revoked / suspended -> free", () => {
    for (const status of ["revoked", "suspended"]) {
      expect(
        getEffectiveTierFromRow(
          { tier: "vip", status, starts_at: PAST, expires_at: FUTURE },
          NOW,
        ),
      ).toBe("free");
    }
  });

  it("expires_at null (permanen) -> vip", () => {
    expect(
      getEffectiveTierFromRow(
        { tier: "vip", status: "active", starts_at: null, expires_at: null },
        NOW,
      ),
    ).toBe("vip");
  });

  it("tier free selalu free", () => {
    expect(
      getEffectiveTierFromRow(
        { tier: "free", status: "active", starts_at: PAST, expires_at: FUTURE },
        NOW,
      ),
    ).toBe("free");
  });
});
