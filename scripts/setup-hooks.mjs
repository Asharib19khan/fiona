#!/usr/bin/env node
// Runs on `pnpm install` (the `prepare` script): points git at .githooks/ so the gitleaks
// pre-commit hook runs. Does nothing outside a git checkout or in CI.
import { spawnSync } from "node:child_process";

if (process.env.CI) process.exit(0);
const inRepo = spawnSync("git", ["rev-parse", "--is-inside-work-tree"], { encoding: "utf8" });
if (inRepo.status !== 0 || inRepo.stdout.trim() !== "true") process.exit(0);
const current = spawnSync("git", ["config", "--get", "core.hooksPath"], { encoding: "utf8" }).stdout.trim();
if (current !== ".githooks") {
  spawnSync("git", ["config", "core.hooksPath", ".githooks"], { stdio: "inherit" });
  console.log("git hooks: core.hooksPath set to .githooks (gitleaks pre-commit).");
}
