#!/usr/bin/env node
// A1 done-when test: "A fresh clone runs web and engine locally with one command."
// Clones the committed HEAD to a temp folder, installs with the frozen lockfile, starts
// `pnpm dev` with no .env.local and every secret removed from the environment, waits for all
// four health endpoints, shuts everything down, and prints PASS or FAIL.
//
//   node scripts/verify-a1.mjs [--keep] [--dir <parent folder>] [--timeout <seconds>]
import { spawn, spawnSync } from "node:child_process";
import { createWriteStream, mkdtempSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ENV_SPEC } from "./lib/env-spec.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
const opt = (flag, fallback) => {
  const i = args.indexOf(flag);
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback;
};
const keep = args.includes("--keep");
const timeoutS = Number(opt("--timeout", "420"));
const win = process.platform === "win32";

const ENDPOINTS = [
  { name: "web", url: "http://localhost:3000/api/healthz" },
  { name: "engine", url: "http://localhost:8000/healthz" },
  { name: "agents", url: "http://localhost:8100/healthz" },
  { name: "guardian", url: "http://localhost:8200/healthz" },
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function probe(url) {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
    const body = await res.json();
    return res.ok && body.api_version === "v1" && body.status === "ok" ? body : null;
  } catch {
    return null;
  }
}
function run(cmd, cmdArgs, cwd) {
  const r = spawnSync(cmd, cmdArgs, { cwd, stdio: "inherit", shell: win });
  if (r.status !== 0) throw new Error(`${cmd} ${cmdArgs.join(" ")} exited ${r.status}`);
}
function killTree(child) {
  if (!child?.pid) return;
  if (win) spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  else {
    try {
      process.kill(-child.pid, "SIGTERM");
    } catch {
      /* already gone */
    }
  }
}

// 1. Ports must be free, or we would be testing someone else's running server.
for (const e of ENDPOINTS) {
  if (await probe(e.url)) {
    console.error(`FAIL: something already answers on ${e.url}. Stop your local \`pnpm dev\` first.`);
    process.exit(1);
  }
}

const parent = path.resolve(opt("--dir", os.tmpdir()));
const work = mkdtempSync(path.join(parent, "fiona-verify-"));
const clone = path.join(work, "fiona");
const logPath = path.join(work, "dev.log");
let dev;
let passed = false;
const started = Date.now();
try {
  console.log(`1/4 clone HEAD → ${clone}`);
  run("git", ["clone", "--quiet", "--no-hardlinks", ROOT, clone], ROOT);

  console.log("2/4 pnpm install --frozen-lockfile");
  run("pnpm", ["install", "--frozen-lockfile", "--reporter=silent"], clone);

  console.log(`3/4 pnpm dev with no secrets (log: ${logPath})`);
  const env = { ...process.env, NEXT_PUBLIC_API_MODE: "mock", FIONA_MODE: "mock", CI: "1" };
  for (const s of ENV_SPEC) if (s.secret || s.required.length) delete env[s.name];
  const log = createWriteStream(logPath);
  dev = spawn("pnpm", ["dev"], { cwd: clone, env, shell: win, detached: !win });
  dev.stdout.pipe(log);
  dev.stderr.pipe(log);

  console.log(`4/4 waiting up to ${timeoutS}s for the four health endpoints`);
  const status = new Map();
  while ((Date.now() - started) / 1000 < timeoutS && status.size < ENDPOINTS.length) {
    for (const e of ENDPOINTS) {
      if (status.has(e.name)) continue;
      const body = await probe(e.url);
      if (body) {
        status.set(e.name, body);
        console.log(`    ✓ ${e.name.padEnd(8)} ${e.url}  ${JSON.stringify(body)}`);
      }
    }
    if (dev.exitCode !== null) break;
    await sleep(2000);
  }
  passed = status.size === ENDPOINTS.length;
  for (const e of ENDPOINTS) if (!status.has(e.name)) console.log(`    ✗ ${e.name.padEnd(8)} ${e.url}  no healthy answer`);
} catch (error) {
  console.error(`error: ${error instanceof Error ? error.message : error}`);
} finally {
  killTree(dev);
  await sleep(1500);
  if (!keep) {
    try {
      rmSync(work, { recursive: true, force: true, maxRetries: 5, retryDelay: 500 });
    } catch {
      console.log(`(could not fully remove ${work}; delete it by hand)`);
    }
  }
}

const secs = Math.round((Date.now() - started) / 1000);
console.log(`\nA1 verify: ${passed ? "PASS" : "FAIL"}: fresh clone, frozen install, \`pnpm dev\`, ${passed ? "all four" : "not all"} services healthy in ${secs}s, no secrets.`);
if (!passed) console.log(`See the dev log${keep ? ` at ${logPath}` : " (re-run with --keep to inspect it)"}.`);
process.exit(passed ? 0 : 1);
