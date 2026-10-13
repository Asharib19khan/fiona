import path from "node:path";
import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";

// Proves each R1 import-boundary pattern in eslint.config.mjs fires on a deliberately bad import.
const webRoot = path.resolve(import.meta.dirname, "..");
const eslint = new ESLint({ cwd: webRoot });

async function boundaryErrors(source: string) {
  const [result] = await eslint.lintText(source, {
    filePath: path.join(webRoot, "lib", "boundary-probe.ts"),
  });
  return (result?.messages ?? []).filter((m) => m.ruleId === "no-restricted-imports");
}

describe("R1 import boundaries in apps/web", () => {
  it.each([
    ["a service by relative path", `import { app } from "../../../services/engine/app/main";`],
    ["a service package", `import agents from "@fiona/agents";`],
    ["a package by relative path", `import { x } from "../../../packages/ui/src/index";`],
    ["an unlisted workspace package", `import mobile from "@fiona/mobile";`],
  ])("rejects %s", async (_label, source) => {
    expect(await boundaryErrors(source)).toHaveLength(1);
  });

  it("allows @fiona/contracts, @fiona/ui and local aliases", async () => {
    const source = [
      `import { a } from "@fiona/contracts";`,
      `import { b } from "@fiona/contracts/mocks";`,
      `import { c } from "@fiona/ui";`,
      `import { d } from "@/lib/utils";`,
    ].join("\n");
    expect(await boundaryErrors(source)).toEqual([]);
  });
});
