import { describe, expect, it } from "vitest";
import { cleanValue, mergeSettings, SETTING_DEFAULTS, SETTING_RULES } from "@/lib/settings";

describe("cleanValue", () => {
  it("bool: hanya boolean", () => {
    expect(cleanValue("welcome_enabled", true)).toBe(true);
    expect(cleanValue("welcome_enabled", false)).toBe(false);
    expect(cleanValue("welcome_enabled", "ya")).toBeUndefined();
    expect(cleanValue("welcome_enabled", 1)).toBeUndefined();
  });
  it("enum: hanya nilai terdaftar", () => {
    expect(cleanValue("welcome_theme", "midnight")).toBe("midnight");
    expect(cleanValue("welcome_theme", "hacker")).toBeUndefined();
  });
  it("num: clamp ke min..max dan floor", () => {
    expect(cleanValue("starboard_threshold", 10)).toBe(10);
    expect(cleanValue("starboard_threshold", 0)).toBe(1);
    expect(cleanValue("starboard_threshold", 99)).toBe(25);
    expect(cleanValue("starboard_threshold", 2.9)).toBe(2);
    expect(cleanValue("starboard_threshold", "5")).toBeUndefined();
    expect(cleanValue("starboard_threshold", NaN)).toBeUndefined();
  });
  it("str: potong ke max", () => {
    expect(cleanValue("welcome_message", "halo")).toBe("halo");
    expect(cleanValue("welcome_message", "x".repeat(600))).toHaveLength(500);
    expect(cleanValue("welcome_message", 42)).toBeUndefined();
  });
  it("key tak dikenal ditolak", () => {
    expect(cleanValue("hack_key", true)).toBeUndefined();
  });
  it("channel_id: hanya digit atau kosong", () => {
    expect(cleanValue("welcome_channel_id", "123456789")).toBe("123456789");
    expect(cleanValue("welcome_channel_id", "")).toBe("");
    expect(cleanValue("welcome_channel_id", "abc")).toBeUndefined();
  });
  it("welcome_role_ids: CSV ID digit valid", () => {
    expect(cleanValue("welcome_role_ids", "12345, 67890")).toBe("12345, 67890");
    expect(cleanValue("welcome_role_ids", "")).toBe("");
    expect(cleanValue("welcome_role_ids", "12345, abc")).toBeUndefined();
  });
});

describe("mergeSettings", () => {
  it("mulai dari default, terapkan nilai valid", () => {
    const out = mergeSettings({ welcome_enabled: false, starboard_threshold: 7 });
    expect(out.welcome_enabled).toBe(false);
    expect(out.starboard_threshold).toBe(7);
    expect(out.leveling_enabled).toBe(true); // default dipertahankan
  });
  it("nilai invalid & key asing diabaikan (default tetap)", () => {
    const out = mergeSettings({
      welcome_enabled: "ya",
      __proto__: true,
      unknown_key: 1,
    });
    expect(out.welcome_enabled).toBe(SETTING_DEFAULTS.welcome_enabled);
    expect("unknown_key" in out).toBe(false);
  });
  it("setiap key SETTING_DEFAULTS punya rule", () => {
    for (const k of Object.keys(SETTING_DEFAULTS)) {
      expect(SETTING_RULES[k], `rule hilang untuk ${k}`).toBeDefined();
    }
  });
});
