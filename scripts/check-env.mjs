#!/usr/bin/env node
// Checks the root .env.local against scripts/lib/env-spec.mjs and prints a table.
// It never prints a value. Exit code 1 if a variable required for the mode is missing,
// a set value is malformed, the two Anthropic keys are equal, or a NEXT_PUBLIC_* name
// looks like a secret.
//
//   node scripts/check-env.mjs [--mode mock|live] [--file path]
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { ENV_SPEC, PUBLIC_BY_DESIGN, SECRET_LOOKING, parseDotenv } from "./lib/env-spec.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

export function checkEnv({ file = path.join(ROOT, ".env.local"), mode } = {}) {
  const found = existsSync(file);
  const values = found ? parseDotenv(readFileSync(file, "utf8")) : new Map();
  const effectiveMode = mode ?? (values.get("NEXT_PUBLIC_API_MODE") || "mock");
  const rows = [];
  const problems = [];

  for (const spec of ENV_SPEC) {
    const value = values.get(spec.name);
    const isRequired = spec.required.includes(effectiveMode);
    let status;
    if (value === undefined || value === "") {
      status = spec.default !== undefined ? "default" : "missing";
      if (isRequired) problems.push(`${spec.name} is required in ${effectiveMode} mode (${spec.usedBy}).`);
    } else {
      const err = spec.validate?.(value) ?? null;
      status = err ? "malformed" : "set";
      if (err) problems.push(`${spec.name} ${err}.`);
    }
    rows.push({ name: spec.name, status, required: isRequired ? effectiveMode : "", usedBy: spec.usedBy });
  }

  const agentsKey = values.get("ANTHROPIC_API_KEY");
  if (agentsKey && agentsKey === values.get("GUARDIAN_ANTHROPIC_API_KEY")) {
    problems.push("GUARDIAN_ANTHROPIC_API_KEY must differ from ANTHROPIC_API_KEY (R8, D-001).");
  }

  const publicNames = new Set([...ENV_SPEC.map((s) => s.name), ...values.keys()]);
  for (const name of publicNames) {
    if (name.startsWith("NEXT_PUBLIC_") && SECRET_LOOKING.test(name) && !PUBLIC_BY_DESIGN.has(name)) {
      problems.push(`${name} looks like a secret but NEXT_PUBLIC_* values are shipped to every browser (R16).`);
    }
  }

  const known = new Set(ENV_SPEC.map((s) => s.name));
  const unknown = [...values.keys()].filter((k) => !known.has(k));
  return { file, found, mode: effectiveMode, rows, problems, unknown };
}

export function printReport(report) {
  const rel = path.relative(ROOT, report.file) || report.file;
  console.log(`Env file: ${rel} ${report.found ? "(found)" : "(not found: defaults apply)"} · mode: ${report.mode}`);
  const w = Math.max(...report.rows.map((r) => r.name.length));
  console.log(`  ${"Variable".padEnd(w)}  ${"Status".padEnd(9)}  ${"Required".padEnd(8)}  Used by`);
  for (const r of report.rows) {
    console.log(`  ${r.name.padEnd(w)}  ${r.status.padEnd(9)}  ${r.required.padEnd(8)}  ${r.usedBy}`);
  }
  if (report.unknown.length) console.log(`\nNot in the spec (ignored): ${report.unknown.join(", ")}`);
  if (report.problems.length) {
    console.log("\nProblems:");
    for (const p of report.problems) console.log(`  ✗ ${p}`);
  } else {
    console.log("\nEnv OK for this mode.");
  }
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  const args = process.argv.slice(2);
  const opt = (flag) => {
    const i = args.indexOf(flag);
    return i >= 0 ? args[i + 1] : undefined;
  };
  const mode = opt("--mode");
  if (mode && mode !== "mock" && mode !== "live") {
    console.error('--mode must be "mock" or "live"');
    process.exit(2);
  }
  const file = opt("--file");
  const report = checkEnv({ mode, ...(file ? { file: path.resolve(file) } : {}) });
  printReport(report);
  process.exit(report.problems.length ? 1 : 0);
}
