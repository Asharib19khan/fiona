#!/usr/bin/env node
// Makes sure the root .env.local runs the real (live) product. Runs automatically before
// `pnpm dev`, so a fresh clone needs no manual setup.
// - Values from scripts/live.env are added when missing or blank (yours are never overwritten).
// - Internal service secrets are generated once on this machine.
// Usage: node scripts/setup-live.mjs
import { randomBytes } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const target = resolve(root, ".env.local");

function parse(text) {
  const out = new Map();
  for (const line of text.split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=(.*)$/);
    if (m) out.set(m[1], m[2].trim());
  }
  return out;
}

const secret = () => randomBytes(32).toString("base64url");
const wanted = parse(readFileSync(resolve(root, "scripts/live.env"), "utf8"));
for (const name of ["INTERNAL_JWT_SECRET", "GUARDIAN_INBOUND_TOKEN", "SETTINGS_ENCRYPTION_KEY"]) {
  wanted.set(name, secret());
}

let text = existsSync(target) ? readFileSync(target, "utf8") : "# Local settings. Never commit this file.\n";
const have = parse(text);
const added = [];

for (const [name, value] of wanted) {
  if (have.get(name)) continue; // already set: keep it
  if (have.has(name)) {
    text = text.replace(new RegExp(`^(\\s*${name}\\s*=).*$`, "m"), `$1${value}`);
  } else {
    if (!text.endsWith("\n")) text += "\n";
    text += `${name}=${value}\n`;
  }
  added.push(name);
}

if (added.length) {
  writeFileSync(target, text);
  console.log(`[setup-live] .env.local: filled ${added.join(", ")}`);
}
if (have.get("NEXT_PUBLIC_API_MODE") === "mock" || have.get("FIONA_MODE") === "mock") {
  console.warn("[setup-live] .env.local sets mock mode; you will see the 'Local developer' stand-in.");
}
