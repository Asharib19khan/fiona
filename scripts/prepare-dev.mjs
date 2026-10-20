#!/usr/bin/env node
// Runs before `pnpm dev`: fills the live settings into .env.local, then loads the demo
// business into the local database if it is not there yet. Safe to run every time.
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const win = process.platform === "win32";

const env = spawnSync(process.execPath, [path.join(ROOT, "scripts/setup-live.mjs")], { stdio: "inherit" });
if (env.status !== 0) process.exit(env.status ?? 1);

// A fixed command string (no user input), run through the shell so uv resolves on every OS.
const db = spawnSync("uv run --project engine python ../scripts/ensure_demo_db.py", {
  cwd: path.join(ROOT, "services"),
  stdio: "inherit",
  shell: true,
});
if (db.status !== 0) {
  console.error("[setup] Could not prepare the local database. Run `pnpm demo-data` and check the error.");
  process.exit(db.status ?? 1);
}
