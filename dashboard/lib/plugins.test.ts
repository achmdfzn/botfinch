import { describe, expect, it } from "vitest";
import { parsePluginTab, PLUGIN_TABS, PLUGINS, TOGGLEABLE_PLUGINS } from "@/lib/plugins";
import { SETTING_DEFAULTS } from "@/lib/settings";

describe("parsePluginTab", () => {
  it("terima tab valid", () => {
    expect(parsePluginTab("all")).toBe("all");
    expect(parsePluginTab("moderation")).toBe("moderation");
  });
  it("nilai asing/null/undefined jatuh ke 'all'", () => {
    expect(parsePluginTab("hacker")).toBe("all");
    expect(parsePluginTab("")).toBe("all");
    expect(parsePluginTab(null)).toBe("all");
    expect(parsePluginTab(undefined)).toBe("all");
  });
});

describe("PLUGIN_TABS", () => {
  it("'all' selalu pertama", () => {
    expect(PLUGIN_TABS[0]).toBe("all");
  });
});

describe("PLUGINS", () => {
  it("id unik", () => {
    const ids = PLUGINS.map((p) => p.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
  it("setiap toggleKey ada di SETTING_DEFAULTS (sinkron dashboard<->bot)", () => {
    for (const p of TOGGLEABLE_PLUGINS) {
      expect(p.toggleKey! in SETTING_DEFAULTS, `toggleKey asing: ${p.toggleKey}`).toBe(true);
    }
  });
});
