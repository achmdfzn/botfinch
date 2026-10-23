import { describe, expect, it } from "vitest";
import {
  buildSidebarGroups,
  hrefPath,
  isAriaCurrentEligible,
  isSidebarLinkActive,
  type SidebarNavLabels,
} from "@/lib/sidebar-nav";
import { PLUGINS } from "@/lib/plugins";

const HOME = "/dashboard/42";
const hrefFor = (rel: string) => `${HOME}${rel}`;

const labels: SidebarNavLabels = {
  groupTitles: {
    overview: "Ringkasan",
    features: "Modul & Fitur",
    content: "Konten & Komunitas",
    settings: "Pengaturan",
    billing: "Billing VIP",
  },
  pluginGroupTitles: {
    essentials: "Esensial",
    engagement: "Engagement & Fun",
    moderation: "Moderasi",
    utilities: "Utilitas",
  },
  plugins: "Plugins",
  overview: "Ringkasan",
  leaderboard: "Leaderboard",
  template: "Template Pesan",
  embed: "Embed",
  selfroles: "Self-roles",
  responder: "Auto-responder",
  giveaway: "Giveaway",
  pengumuman: "Pengumuman",
  settings: "Pengaturan",
  modlog: "Mod Log",
  modul: "Modul",
  billing: "Billing VIP",
  pluginNames: Object.fromEntries(PLUGINS.map((p) => [p.id, `Plugin:${p.id}`])),
};

const groups = buildSidebarGroups({ homeHref: HOME, hrefFor, labels });
const groupById = (id: string) => groups.find((g) => g.id === id)!;

/** Semua href item route (grup), tanpa subseksi plugin. */
function routeHrefs(): string[] {
  return groups.flatMap((g) => g.items.map((i) => i.href));
}

/** Semua href subseksi plugin di grup features. */
function pluginSectionHrefs(): string[] {
  return (groupById("features").sections ?? []).flatMap((s) => s.items.map((i) => i.href));
}

describe("buildSidebarGroups: peta grup", () => {
  it("urutan dan judul grup sesuai kamus groups.*", () => {
    expect(groups.map((g) => g.id)).toEqual([
      "overview",
      "features",
      "content",
      "settings",
      "billing",
    ]);
    expect(groups.map((g) => g.title)).toEqual([
      "Ringkasan",
      "Modul & Fitur",
      "Konten & Komunitas",
      "Pengaturan",
      "Billing VIP",
    ]);
  });

  it("grup Ringkasan: Plugins (home), Overview, Leaderboard", () => {
    expect(groupById("overview").items.map((i) => i.href)).toEqual([
      HOME,
      `${HOME}/overview`,
      `${HOME}/leaderboard`,
    ]);
    expect(groupById("overview").items[0].exact).toBe(true);
  });

  it("grup Konten & Komunitas: Template, Embed, Self-roles, Auto-responder, Giveaway, Pengumuman", () => {
    expect(groupById("content").items.map((i) => i.href)).toEqual([
      `${HOME}/template`,
      `${HOME}/embed`,
      `${HOME}/selfroles`,
      `${HOME}/responder`,
      `${HOME}/giveaway`,
      `${HOME}/pengumuman`,
    ]);
  });

  it("grup Pengaturan: Pengaturan lalu Mod Log; grup Billing: Billing saja", () => {
    expect(groupById("settings").items.map((i) => i.href)).toEqual([
      `${HOME}/settings`,
      `${HOME}/modlog`,
    ]);
    expect(groupById("billing").items.map((i) => i.href)).toEqual([`${HOME}/billing`]);
  });

  it("grup Modul & Fitur memuat halaman Modul sebagai item", () => {
    expect(groupById("features").items.map((i) => i.href)).toEqual([`${HOME}/modul`]);
  });
});

describe("buildSidebarGroups: tepat satu kali per route", () => {
  const EXPECTED_ROUTES = [
    "",
    "/overview",
    "/leaderboard",
    "/modul",
    "/template",
    "/embed",
    "/selfroles",
    "/responder",
    "/giveaway",
    "/pengumuman",
    "/settings",
    "/modlog",
    "/billing",
  ].map((rel) => `${HOME}${rel}`);

  it("setiap route per-guild muncul tepat satu kali di antara item grup", () => {
    const hrefs = routeHrefs();
    expect(new Set(hrefs).size).toBe(hrefs.length);
    expect([...hrefs].sort()).toEqual([...EXPECTED_ROUTES].sort());
  });

  it("tidak ada path route grup Konten yang muncul lagi di subseksi plugin", () => {
    const contentPaths = new Set(groupById("content").items.map((i) => hrefPath(i.href)));
    for (const href of pluginSectionHrefs()) {
      expect(contentPaths.has(hrefPath(href)), `duplikat route konten: ${href}`).toBe(false);
    }
  });

  it("plugin ber-configure ke route Konten tersaring dari subseksi plugin", () => {
    const sectionLabels = (groupById("features").sections ?? []).flatMap((s) =>
      s.items.map((i) => i.label),
    );
    for (const id of ["selfroles", "responder", "giveaway", "announcements", "embed", "templates"]) {
      expect(sectionLabels).not.toContain(`Plugin:${id}`);
    }
  });

  it("plugin tanpa configure / menuju settings tetap tampil di subseksi plugin", () => {
    const byLabel = new Map(
      (groupById("features").sections ?? []).flatMap((s) =>
        s.items.map((i) => [i.label, i.href] as const),
      ),
    );
    // welcome -> /settings#welcome (bukan route Konten, href ber-hash unik)
    expect(byLabel.get("Plugin:welcome")).toBe(`${HOME}/settings#welcome`);
    // tanpa configure -> halaman Plugins dengan ?tab=<grup>
    expect(byLabel.get("Plugin:leveling")).toBe(`${HOME}?tab=essentials`);
    expect(byLabel.get("Plugin:economy")).toBe(`${HOME}?tab=engagement`);
    expect(byLabel.get("Plugin:automod")).toBe(`${HOME}?tab=moderation`);
    expect(byLabel.get("Plugin:autopublish")).toBe(`${HOME}?tab=utilities`);
    // 15 plugin - 6 tersaring = 9 tersisa
    expect(byLabel.size).toBe(9);
  });

  it("subseksi plugin mempertahankan urutan grup PLUGINS", () => {
    expect((groupById("features").sections ?? []).map((s) => s.id)).toEqual([
      "essentials",
      "engagement",
      "moderation",
      "utilities",
    ]);
  });
});

describe("aria-current: tepat satu per layar", () => {
  /** Semua entry sidebar (item grup + subseksi plugin). */
  function allEntries() {
    return groups.flatMap((g) => [
      ...g.items,
      ...(g.sections ?? []).flatMap((s) => s.items),
    ]);
  }

  function ariaCurrentCount(pathname: string, tab: string | null): number {
    return allEntries().filter(
      (e) => isSidebarLinkActive(pathname, tab, e) && isAriaCurrentEligible(e),
    ).length;
  }

  it("entry ?tab= dan ber-hash tidak eligible aria-current", () => {
    expect(isAriaCurrentEligible({ href: `${HOME}?tab=engagement` })).toBe(false);
    expect(isAriaCurrentEligible({ href: `${HOME}/settings#welcome` })).toBe(false);
    expect(isAriaCurrentEligible({ href: `${HOME}/settings` })).toBe(true);
    expect(isAriaCurrentEligible({ href: HOME })).toBe(true);
  });

  it("tab engagement terbuka: hanya Plugins/home yang aria-current (bukan 4)", () => {
    expect(ariaCurrentCount(HOME, "engagement")).toBe(1);
    expect(ariaCurrentCount(HOME, "essentials")).toBe(1);
    expect(ariaCurrentCount(HOME, null)).toBe(1);
  });

  it("/settings: hanya Pengaturan yang aria-current (Welcome hanya visual)", () => {
    expect(ariaCurrentCount(`${HOME}/settings`, null)).toBe(1);
  });

  it("route biasa & subroute: tepat satu aria-current", () => {
    expect(ariaCurrentCount(`${HOME}/overview`, null)).toBe(1);
    expect(ariaCurrentCount(`${HOME}/template`, null)).toBe(1);
    expect(ariaCurrentCount(`${HOME}/billing/orders/REF-1`, null)).toBe(1);
  });
});

describe("isSidebarLinkActive", () => {
  it("path persis aktif; path lain tidak", () => {
    expect(isSidebarLinkActive(`${HOME}/overview`, null, { href: `${HOME}/overview` })).toBe(true);
    expect(isSidebarLinkActive(`${HOME}/leaderboard`, null, { href: `${HOME}/overview` })).toBe(false);
  });

  it("subroute aktif lewat pencocokan awalan (orders di bawah billing)", () => {
    expect(
      isSidebarLinkActive(`${HOME}/billing/orders/REF-1`, null, { href: `${HOME}/billing` }),
    ).toBe(true);
    // awalan string tanpa batas segmen tidak boleh aktif
    expect(isSidebarLinkActive(`${HOME}/billingx`, null, { href: `${HOME}/billing` })).toBe(false);
  });

  it("entry exact (Plugins/home) tidak aktif di subroute", () => {
    const home = { href: HOME, exact: true };
    expect(isSidebarLinkActive(HOME, null, home)).toBe(true);
    expect(isSidebarLinkActive(`${HOME}/overview`, null, home)).toBe(false);
  });

  it("entry ber-hash aktif hanya di path persisnya", () => {
    const welcome = { href: `${HOME}/settings#welcome` };
    expect(isSidebarLinkActive(`${HOME}/settings`, null, welcome)).toBe(true);
    expect(isSidebarLinkActive(`${HOME}/settings/lain`, null, welcome)).toBe(false);
  });

  it("entry ?tab= hanya aktif saat tab itu terbuka", () => {
    const leveling = { href: `${HOME}?tab=essentials` };
    expect(isSidebarLinkActive(HOME, "essentials", leveling)).toBe(true);
    expect(isSidebarLinkActive(HOME, "engagement", leveling)).toBe(false);
    expect(isSidebarLinkActive(HOME, null, leveling)).toBe(false);
    // entry tanpa tab di path yang sama aktif apa pun tab-nya
    expect(isSidebarLinkActive(HOME, "essentials", { href: HOME, exact: true })).toBe(true);
  });
});
