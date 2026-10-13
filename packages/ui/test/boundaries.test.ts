import path from "node:path";
import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";

// Proves each R1 import-boundary pattern in eslint.config.mjs fires on a deliberately bad import.
const uiRoot = path.resolve(import.meta.dirname, "..");
const eslint = new ESLint({ cwd: uiRoot });

async function boundaryErrors(source: string) {
  const [result] = await eslint.lintText(source, {
    filePath: path.join(uiRoot, "src", "boundary-probe.ts"),
  });
  return (result?.messages ?? []).filter((m) => m.ruleId === "no-restricted-imports");
}

describe("R1 import boundaries in packages/ui", () => {
  it.each([
    ["an app by relative path", `import { x } from "../../../apps/web/lib/env";`],
    ["the web app package", `import web from "@fiona/web";`],
    ["a service by relative path", `import { y } from "../../../services/agents/x";`],
    ["a service package", `import guardian from "@fiona/guardian";`],
  ])("rejects %s", async (_label, source) => {
    expect(await boundaryErrors(source)).toHaveLength(1);
  });

  it("allows @fiona/contracts and react", async () => {
    const source = [`import { a } from "@fiona/contracts";`, `import { useState } from "react";`].join("\n");
    expect(await boundaryErrors(source)).toEqual([]);
  });
});
