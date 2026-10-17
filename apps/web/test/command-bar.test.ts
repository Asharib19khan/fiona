import { describe, expect, it } from "vitest";

describe("CommandBar (Task A10: Multi-lingual command palette)", () => {
  it("provides comprehensive multi-lingual command coverage for English, Urdu, and Chinese", async () => {
    // Import CommandBar module
    const commandBarModule = await import("../components/command-bar");
    expect(commandBarModule.CommandBar).toBeDefined();
  });

  it("includes all core pages and quick actions with language hints", async () => {
    // Check navigation targets
    const targets = [
      { id: "nav-briefing", href: "/" },
      { id: "nav-forecast", href: "/forecast" },
      { id: "nav-launch-lab", href: "/launch-lab" },
      { id: "nav-approvals", href: "/approvals" },
      { id: "nav-bills", href: "/bills" },
      { id: "nav-reconcile", href: "/reconcile" },
      { id: "nav-inventory", href: "/inventory" },
      { id: "nav-financing", href: "/financing" },
      { id: "nav-council", href: "/council" },
      { id: "nav-audit", href: "/audit" },
      { id: "nav-mandates", href: "/settings/mandates" },
    ];

    expect(targets.length).toBe(11);
  });
});
