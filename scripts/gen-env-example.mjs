#!/usr/bin/env node
// Regenerates .env.example from scripts/lib/env-spec.mjs. Run after adding a variable to the spec:
//   pnpm gen:env
import { writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ENV_SPEC } from "./lib/env-spec.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const lines = [
  "# Fiona environment template (S2). Copy to .env.local at the repo root and fill in what you need.",
  "# NEVER commit .env.local and never paste a secret into chat, an issue or a PR (R16).",
  "# A fresh clone needs NO values: everything runs in mock mode. `pnpm doctor` checks your",
  "# .env.local without printing values. Live mode needs every variable marked `required: live`.",
  "# Generated from scripts/lib/env-spec.mjs by `pnpm gen:env`; CI checks the two match.",
];
let group = "";
for (const s of ENV_SPEC) {
  if (s.group !== group) {
    group = s.group;
    lines.push("", `# ── ${group} ${"─".repeat(Math.max(4, 72 - group.length))}`);
  }
  const tags = [s.secret ? "SECRET" : "not secret", `used by: ${s.usedBy}`, `deployed in: ${s.deployedIn}`];
  if (s.required.length) tags.push(`required: ${s.required.join(", ")}`);
  if (s.default !== undefined) tags.push(`default: ${s.default}`);
  lines.push(`# ${tags.join(" · ")}`);
  if (s.note) lines.push(`# ${s.note}`);
  lines.push(`${s.name}=`);
}
writeFileSync(path.join(ROOT, ".env.example"), `${lines.join("\n")}\n`);
console.log(`.env.example written: ${ENV_SPEC.length} variables.`);
