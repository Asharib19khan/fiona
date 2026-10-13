#!/usr/bin/env node
// Proves the secret scan works (S2): gitleaks must flag a generated fake key in a temp folder,
// using this repo's .gitleaks.toml, and must pass a clean folder. The fake key is generated at
// run time and never written inside the repo.
//
//   node scripts/test-gitleaks.mjs [--require]   (CI passes --require; locally a missing gitleaks skips)
import { spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const GITLEAKS = process.env.GITLEAKS_BIN || "gitleaks";
const config = path.join(ROOT, ".gitleaks.toml");

if (spawnSync(GITLEAKS, ["version"], { encoding: "utf8" }).status !== 0) {
  const msg = "gitleaks is not installed (winget install Gitleaks.Gitleaks | brew install gitleaks).";
  if (process.argv.includes("--require")) {
    console.error(`FAIL ${msg}`);
    process.exit(1);
  }
  console.log(`SKIP ${msg}`);
  process.exit(0);
}

const scan = (dir) =>
  spawnSync(GITLEAKS, ["dir", dir, "--config", config, "--no-banner", "--redact", "--exit-code", "1"], {
    encoding: "utf8",
  }).status;

const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
const fakeBody = [...randomBytes(93)].map((b) => alphabet[b % alphabet.length]).join("");
const tmp = mkdtempSync(path.join(os.tmpdir(), "fiona-gitleaks-"));
const leaky = path.join(tmp, "leaky");
const clean = path.join(tmp, "clean");
try {
  for (const d of [leaky, clean]) spawnSync(process.execPath, ["-e", `require("fs").mkdirSync(${JSON.stringify(d)})`]);
  writeFileSync(path.join(leaky, "settings.env"), `ANTHROPIC_API_KEY=sk-ant-api03-${fakeBody}AA\n`);
  writeFileSync(path.join(clean, "settings.env"), "ANTHROPIC_API_KEY=\nFIONA_MODE=mock\n");
  const leakyStatus = scan(leaky);
  const cleanStatus = scan(clean);
  const ok = leakyStatus === 1 && cleanStatus === 0;
  console.log(`${ok ? "OK  " : "FAIL"} gitleaks flags a fake key (exit ${leakyStatus}, want 1) and passes a clean file (exit ${cleanStatus}, want 0).`);
  process.exit(ok ? 0 : 1);
} finally {
  rmSync(tmp, { recursive: true, force: true });
}
