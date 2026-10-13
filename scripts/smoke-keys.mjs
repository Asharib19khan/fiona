#!/usr/bin/env node
// S2 proof that the keys work, without sharing them: reads the root .env.local and prints
// only OK/FAIL with an HTTP status or error class, never a value. Manual only, never in CI.
//
//   node scripts/smoke-keys.mjs              free: Models API lookup per key and model + Supabase health
//   node scripts/smoke-keys.mjs --complete   also one 16-token message per model (costs money; C5 first)
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import Anthropic from "@anthropic-ai/sdk";
import { ENV_SPEC, parseDotenv } from "./lib/env-spec.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const envFile = path.join(ROOT, ".env.local");
if (!existsSync(envFile)) {
  console.error("No .env.local at the repo root. Copy .env.example and fill in the keys first.");
  process.exit(1);
}
const env = parseDotenv(readFileSync(envFile, "utf8"));
const get = (name) => env.get(name) || ENV_SPEC.find((s) => s.name === name)?.default || "";
const complete = process.argv.includes("--complete");

// Which key may call which model (D-001): agents use the agents key, the Guardian its own.
const CHECKS = [
  { label: "agents · extract", keyVar: "ANTHROPIC_API_KEY", modelVar: "FIONA_MODEL_EXTRACT" },
  { label: "agents · reason", keyVar: "ANTHROPIC_API_KEY", modelVar: "FIONA_MODEL_REASON" },
  { label: "agents · guide", keyVar: "ANTHROPIC_API_KEY", modelVar: "FIONA_MODEL_GUIDE" },
  { label: "guardian · review", keyVar: "GUARDIAN_ANTHROPIC_API_KEY", modelVar: "FIONA_MODEL_GUARDIAN" },
];

function describe(error) {
  if (error instanceof Anthropic.APIError) return `${error.status ?? "-"} ${error.constructor.name}`;
  return error instanceof Error ? error.constructor.name : "error";
}

let failed = false;
const report = (label, ok, detail) => {
  if (!ok) failed = true;
  console.log(`  ${ok ? "OK  " : "FAIL"}  ${label.padEnd(22)} ${detail}`);
};

console.log(`Claude keys (${complete ? "model lookup + 16-token message" : "model lookup only, free"})`);
for (const check of CHECKS) {
  const apiKey = get(check.keyVar);
  const model = get(check.modelVar);
  if (!apiKey) {
    report(check.label, false, `${check.keyVar} is not set`);
    continue;
  }
  const client = new Anthropic({ apiKey, maxRetries: 0, timeout: 20_000 });
  try {
    const info = await client.models.retrieve(model);
    if (!complete) {
      report(check.label, true, `${info.id} visible to ${check.keyVar}`);
      continue;
    }
    const msg = await client.messages.create({
      model,
      max_tokens: 16,
      messages: [{ role: "user", content: "Reply with the single word: ok" }],
    });
    report(check.label, true, `${model} answered (stop_reason ${msg.stop_reason}, ${msg.usage.output_tokens} output tokens)`);
  } catch (error) {
    report(check.label, false, `${model}: ${describe(error)}`);
  }
}

console.log("Supabase");
const supabaseUrl = get("NEXT_PUBLIC_SUPABASE_URL");
const anonKey = get("NEXT_PUBLIC_SUPABASE_ANON_KEY");
if (!supabaseUrl || !anonKey) {
  report("auth health", false, "NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY is not set");
} else {
  try {
    const res = await fetch(new URL("/auth/v1/health", supabaseUrl), {
      headers: { apikey: anonKey },
      signal: AbortSignal.timeout(10_000),
    });
    report("auth health", res.ok, `HTTP ${res.status}`);
  } catch (error) {
    report("auth health", false, describe(error));
  }
}

process.exit(failed ? 1 : 0);
