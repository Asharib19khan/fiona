#!/usr/bin/env node
// `pnpm doctor`: tool versions with install hints, then the env check (values never printed).
// Exit code 1 if a required tool is missing or the env check fails for the current mode.
import { spawnSync } from "node:child_process";
import { checkEnv, printReport } from "./check-env.mjs";

const win = process.platform === "win32";
const TOOLS = [
  { name: "node", cmd: "node --version", need: "required", want: /^v2[4-9]\./, hint: "Install Node 24 LTS: https://nodejs.org (or `winget install OpenJS.NodeJS.LTS`)." },
  { name: "pnpm", cmd: "pnpm --version", need: "required", want: /^10\.34\.6/, hint: "Run `corepack enable` (pnpm 10.34.6 is pinned in package.json)." },
  { name: "uv", cmd: "uv --version", need: "required", hint: win ? "`winget install astral-sh.uv`" : "`curl -LsSf https://astral.sh/uv/install.sh | sh`" },
  { name: "python 3.12", cmd: "uv python find 3.12", need: "required", hint: "`uv python install 3.12`" },
  { name: "git", cmd: "git --version", need: "required", hint: "https://git-scm.com/downloads" },
  { name: "gitleaks", cmd: "gitleaks version", need: "recommended", hint: win ? "`winget install Gitleaks.Gitleaks` (pre-commit secret scan)" : "`brew install gitleaks`" },
  { name: "flyctl", cmd: "flyctl version", need: "for deploys", hint: win ? "`pwsh -c \"iwr https://fly.io/install.ps1 -useb | iex\"`" : "`curl -L https://fly.io/install.sh | sh`" },
  { name: "vercel", cmd: "vercel --version", need: "optional", hint: "`pnpm add -g vercel` (the Git integration deploys without it)" },
  { name: "supabase", cmd: "supabase --version", need: "optional", hint: "Not needed locally: we use portable Postgres (engine.ledger.db)." },
  { name: "docker", cmd: "docker --version", need: "optional", hint: "Only to build service images locally; CI builds them." },
  { name: "gh", cmd: "gh --version", need: "optional", hint: win ? "`winget install GitHub.cli`" : "`brew install gh`" },
];

let failed = false;
console.log("Tools");
for (const t of TOOLS) {
  const r = spawnSync(t.cmd, { shell: true, encoding: "utf8" });
  const out = `${r.stdout ?? ""}${r.stderr ?? ""}`.trim().split(/\r?\n/)[0] ?? "";
  const ok = r.status === 0 && (!t.want || t.want.test(out));
  const label = ok ? "ok" : r.status === 0 ? "wrong version" : "missing";
  if (!ok && t.need === "required") failed = true;
  console.log(`  ${ok ? "✓" : t.need === "required" ? "✗" : "·"} ${t.name.padEnd(12)} ${label === "ok" ? out.slice(0, 60) : `${label} (${t.need}): ${t.hint}`}`);
}

console.log("");
const report = checkEnv();
printReport(report);
if (report.problems.length) failed = true;
process.exit(failed ? 1 : 0);
