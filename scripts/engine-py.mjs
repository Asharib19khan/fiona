#!/usr/bin/env node
// Runs an engine Python module from the repo root, e.g. `pnpm db:reset`:
//   node scripts/engine-py.mjs engine.ledger.db reset
// It runs from services/ (so the `engine` package is importable, D-010) with the engine's uv project.
import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SERVICES = path.join(ROOT, "services");
const [moduleName, ...args] = process.argv.slice(2);
if (!moduleName) {
  console.error("usage: node scripts/engine-py.mjs <module> [args…]");
  process.exit(2);
}

const modulePath = path.join(SERVICES, ...moduleName.split(".")) + ".py";
if (!existsSync(modulePath)) {
  console.log(`${moduleName} does not exist yet (owned by its lane). Nothing to run.`);
  process.exit(0);
}

const r = spawnSync("uv", ["run", "--project", "engine", "python", "-m", moduleName, ...args], {
  cwd: SERVICES,
  stdio: "inherit",
  shell: process.platform === "win32",
});
process.exit(r.status ?? 1);
