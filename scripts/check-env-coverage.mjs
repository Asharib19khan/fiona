#!/usr/bin/env node
// S2 acceptance: every environment variable read anywhere in code appears in .env.example,
// and .env.example lists exactly the variables in scripts/lib/env-spec.mjs.
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ENV_SPEC, PLATFORM_ENV, parseDotenv } from "./lib/env-spec.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SKIP_DIRS = new Set([
  "node_modules", ".git", ".venv", ".next", ".turbo", "__pycache__", ".pytest_cache",
  ".ruff_cache", ".hypothesis", "dist", "coverage", "docs", "generated",
]);
const CODE = /\.(m?[jt]sx?|py)$/;
const PATTERNS = [
  /process\.env\.([A-Z][A-Z0-9_]*)/g,
  /process\.env\[\s*["']([A-Z][A-Z0-9_]*)["']\s*\]/g,
  /os\.environ\[\s*["']([A-Z][A-Z0-9_]*)["']\s*\]/g,
  /os\.environ\.get\(\s*["']([A-Z][A-Z0-9_]*)["']/g,
  /os\.getenv\(\s*["']([A-Z][A-Z0-9_]*)["']/g,
];

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue;
    const full = path.join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) yield* walk(full);
    else if (CODE.test(name)) yield full;
  }
}

const used = new Map(); // name -> first file
for (const file of walk(ROOT)) {
  const text = readFileSync(file, "utf8");
  for (const re of PATTERNS) {
    for (const m of text.matchAll(re)) {
      if (!used.has(m[1])) used.set(m[1], path.relative(ROOT, file));
    }
  }
}

const example = parseDotenv(readFileSync(path.join(ROOT, ".env.example"), "utf8"));
const exampleNames = new Set(example.keys());
const specNames = new Set(ENV_SPEC.map((s) => s.name));
const problems = [];

for (const [name, file] of used) {
  if (!PLATFORM_ENV.has(name) && !exampleNames.has(name)) {
    problems.push(`${name} is read in ${file} but missing from .env.example (add it to scripts/lib/env-spec.mjs too).`);
  }
}
for (const name of specNames) if (!exampleNames.has(name)) problems.push(`${name} is in env-spec.mjs but missing from .env.example.`);
for (const name of exampleNames) if (!specNames.has(name)) problems.push(`${name} is in .env.example but missing from env-spec.mjs.`);
for (const [name, value] of example) if (value !== "") problems.push(`${name} has a value in .env.example; the template must stay empty (R16).`);

if (problems.length) {
  for (const p of problems) console.error(`✗ ${p}`);
  process.exit(1);
}
console.log(`env coverage OK: ${used.size} variable(s) read in code, ${specNames.size} documented in .env.example.`);
