/**
 * Regresi audit P1 — markAnnouncementSent di lib/db:
 * Pembaruan last_sent_at harus MONOTONIK (timestamp lama tidak boleh
 * menimpa yang lebih baru), aman terhadap NULL (COALESCE), dan ter-scope
 * id + guild_id. Boolean hasil memetakan "baris ditemukan" untuk route
 * ack (false -> 404).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const sqlCalls: { text: string; values: unknown[] }[] = [];
let nextRows: { id: number }[] = [{ id: 5 }];

vi.mock("@vercel/postgres", () => ({
  sql: (strings: TemplateStringsArray, ...values: unknown[]) => {
    sqlCalls.push({ text: strings.join(" "), values });
    return Promise.resolve({ rows: nextRows });
  },
}));

import { markAnnouncementSent } from "./db";

const TS = "2026-10-22T05:00:00.000Z";

beforeEach(() => {
  sqlCalls.length = 0;
  nextRows = [{ id: 5 }];
});

describe("markAnnouncementSent", () => {
  it("memakai GREATEST + COALESCE dan scope id + guild_id", async () => {
    const ok = await markAnnouncementSent(5, "111", TS);
    expect(ok).toBe(true);
    expect(sqlCalls).toHaveLength(1);
    const { text, values } = sqlCalls[0];
    expect(text).toContain("GREATEST");
    expect(text).toContain("COALESCE(last_sent_at,");
    expect(text).toContain("guild_id");
    expect(values).toContain(5);
    expect(values).toContain("111");
    expect(values).toContain(TS);
  });

  it("mengembalikan false bila tidak ada baris yang cocok (id/guild salah)", async () => {
    nextRows = [];
    const ok = await markAnnouncementSent(5, "guild-lain", TS);
    expect(ok).toBe(false);
  });
});
