import { describe, expect, it } from "vitest";
import {
  discordId,
  embedFields,
  hexColor,
  httpUrl,
  intervalMinutes,
  isoDateTime,
  optStr,
  parseJsonBody,
  str,
} from "@/lib/validate";

describe("str", () => {
  it("trim dan batasi panjang", () => {
    expect(str("  halo  ", 10)).toBe("halo");
    expect(str("terlalu panjang", 5)).toBeUndefined();
    expect(str(123, 10)).toBeUndefined();
  });
  it("required menolak string kosong", () => {
    expect(str("   ", 10, true)).toBeUndefined();
    expect(str("x", 10, true)).toBe("x");
  });
});

describe("optStr", () => {
  it("absen/null = fallback", () => {
    expect(optStr(undefined, 10)).toBe("");
    expect(optStr(null, 10, "fb")).toBe("fb");
    expect(optStr("ok", 10)).toBe("ok");
  });
});

describe("discordId", () => {
  it("terima 5..25 digit", () => {
    expect(discordId("12345")).toBe("12345");
    expect(discordId("1234567890123456789012345")).toBe("1234567890123456789012345");
  });
  it("tolak format salah", () => {
    expect(discordId("1234")).toBeUndefined();
    expect(discordId("12345678901234567890123456")).toBeUndefined();
    expect(discordId("12a45")).toBeUndefined();
    expect(discordId("../12345")).toBeUndefined();
    expect(discordId("")).toBeUndefined();
    expect(discordId(null)).toBeUndefined();
  });
});

describe("httpUrl", () => {
  it("terima https", () => {
    expect(httpUrl("https://cdn.discordapp.com/a.png")).toBe("https://cdn.discordapp.com/a.png");
  });
  it("tolak http (E-S10: hanya https)", () => {
    expect(httpUrl("http://example.com/x.png")).toBeUndefined();
    expect(httpUrl("HTTP://EXAMPLE.COM")).toBeUndefined();
  });
  it("kosong/absen = string kosong", () => {
    expect(httpUrl("")).toBe("");
    expect(httpUrl("   ")).toBe("");
    expect(httpUrl(null)).toBe("");
    expect(httpUrl(undefined)).toBe("");
  });
  it("tolak non-URL dan kepanjangan", () => {
    expect(httpUrl("bukan url")).toBeUndefined();
    expect(httpUrl("ftp://x.com")).toBeUndefined();
    expect(httpUrl(42)).toBeUndefined();
    expect(httpUrl("https://" + "a".repeat(500), 100)).toBeUndefined();
  });
});

describe("hexColor", () => {
  it("normalisasi ke uppercase", () => {
    expect(hexColor("ff0000", "000000")).toBe("FF0000");
    expect(hexColor("AbCdEf", "000000")).toBe("ABCDEF");
  });
  it("fallback untuk absen/kosong, tolak format salah", () => {
    expect(hexColor("", "112233")).toBe("112233");
    expect(hexColor(null, "112233")).toBe("112233");
    expect(hexColor("fff", "112233")).toBeUndefined();
    expect(hexColor("#ff0000", "112233")).toBeUndefined();
  });
});

describe("embedFields", () => {
  it("terima field valid", () => {
    expect(embedFields([{ name: "n", value: "v" }])).toEqual([{ name: "n", value: "v" }]);
    expect(embedFields([{ name: "n", value: "v", inline: true }])).toEqual([
      { name: "n", value: "v", inline: true },
    ]);
  });
  it("absen/null = array kosong", () => {
    expect(embedFields(null)).toEqual([]);
    expect(embedFields(undefined)).toEqual([]);
  });
  it("tolak struktur salah", () => {
    expect(embedFields("x")).toBeUndefined();
    expect(embedFields(new Array(11).fill({ name: "n", value: "v" }))).toBeUndefined();
    expect(embedFields([{ name: "", value: "v" }])).toBeUndefined();
    expect(embedFields([{ name: "n", value: "v", inline: "ya" }])).toBeUndefined();
  });
});

describe("intervalMinutes", () => {
  it("absen = null, int 5..43200 valid", () => {
    expect(intervalMinutes(null)).toBeNull();
    expect(intervalMinutes(undefined)).toBeNull();
    expect(intervalMinutes(5)).toBe(5);
    expect(intervalMinutes(43200)).toBe(43200);
  });
  it("tolak di luar rentang / non-int", () => {
    expect(intervalMinutes(4)).toBeUndefined();
    expect(intervalMinutes(43201)).toBeUndefined();
    expect(intervalMinutes(5.5)).toBeUndefined();
    expect(intervalMinutes("10")).toBeUndefined();
  });
});

describe("isoDateTime", () => {
  it("absen/kosong = null", () => {
    expect(isoDateTime(null)).toBeNull();
    expect(isoDateTime("")).toBeNull();
  });
  it("terima ISO valid, tolak sampah", () => {
    expect(isoDateTime("2026-10-10T17:00:00+07:00")).toBe("2026-10-10T17:00:00+07:00");
    expect(isoDateTime("kemarin")).toBeUndefined();
    expect(isoDateTime(123)).toBeUndefined();
  });
});

describe("parseJsonBody", () => {
  it("parse objek JSON", async () => {
    const req = new Request("http://x", {
      method: "POST",
      body: JSON.stringify({ a: 1 }),
    });
    expect(await parseJsonBody(req)).toEqual({ a: 1 });
  });
  it("null untuk body rusak / array / literal", async () => {
    const bad = new Request("http://x", { method: "POST", body: "{rusak" });
    expect(await parseJsonBody(bad)).toBeNull();
    const arr = new Request("http://x", { method: "POST", body: "[1,2]" });
    expect(await parseJsonBody(arr)).toBeNull();
    const nul = new Request("http://x", { method: "POST", body: "null" });
    expect(await parseJsonBody(nul)).toBeNull();
  });
});
