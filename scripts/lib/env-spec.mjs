// Single source for every environment variable Fiona reads (S2). `.env.example` must list
// exactly these names; scripts/check-env-coverage.mjs enforces that, plus coverage of code.
//
// required: the modes in which the variable must be set ("live" for real services).
// secret:   never printed, logged, committed or exposed through NEXT_PUBLIC_*.

const url = (v) => {
  try {
    const u = new URL(v);
    return u.protocol === "http:" || u.protocol === "https:" ? null : "must be an http(s) URL";
  } catch {
    return "must be a URL";
  }
};
const oneOf = (...allowed) => (v) => (allowed.includes(v) ? null : `must be one of ${allowed.join(", ")}`);
const flag = oneOf("0", "1");
const prefix = (...ps) => (v) => (ps.some((p) => v.startsWith(p)) ? null : `should start with ${ps.join(" or ")}`);
const minLength = (n) => (v) => (v.length >= n ? null : `must be at least ${n} characters`);
const claudeModel = (v) => (/^claude-[a-z0-9-]+$/.test(v) ? null : "must be a Claude model ID (claude-…)");
const nonNegativeInt = (v) => (/^\d+$/.test(v) ? null : "must be a whole number ≥ 0");
const positiveNumber = (v) => (/^\d+(\.\d+)?$/.test(v) && Number(v) > 0 ? null : "must be a number > 0");
const postgresUrl = (v) => (/^postgres(ql)?:\/\//.test(v) ? null : "must be a postgres:// URL");

/** @type {Array<{name: string, group: string, usedBy: string, secret: boolean, required: string[], default?: string, deployedIn: string, validate?: (v: string) => string | null, note?: string}>} */
export const ENV_SPEC = [
  // Modes
  { name: "NEXT_PUBLIC_API_MODE", group: "Modes", usedBy: "web", secret: false, required: [], default: "mock", deployedIn: "Vercel", validate: oneOf("mock", "live"), note: "Inlined at build time. Previews build in mock mode; the demo build is live." },
  { name: "FIONA_MODE", group: "Modes", usedBy: "engine", secret: false, required: [], default: "mock", deployedIn: "Fly (fiona-engine)", validate: oneOf("mock", "live") },
  { name: "GUARDIAN_CHECKS_IMPL", group: "Modes", usedBy: "guardian", secret: false, required: [], default: "stub", deployedIn: "Fly (fiona-guardian)", validate: oneOf("stub", "library"), note: "stub = scenario fixtures until D5 lands." },

  // Database and Supabase
  { name: "DATABASE_URL", group: "Database", usedBy: "engine", secret: true, required: [], deployedIn: "Fly (fiona-engine)", validate: postgresUrl, note: "Unset locally = Daniyal's portable Postgres 17 (engine.ledger.db)." },
  { name: "FIONA_PG_PORT", group: "Database", usedBy: "engine (local Postgres)", secret: false, required: [], default: "54329", deployedIn: "local only", validate: nonNegativeInt },
  { name: "FIONA_CACHE_DIR", group: "Database", usedBy: "engine (local Postgres)", secret: false, required: [], default: "~/.cache/fiona", deployedIn: "local only", note: "Where the portable Postgres binaries are cached." },
  { name: "NEXT_PUBLIC_SUPABASE_URL", group: "Database", usedBy: "web", secret: false, required: ["live"], deployedIn: "Vercel", validate: url, note: "Public by design; protected by RLS." },
  { name: "NEXT_PUBLIC_SUPABASE_ANON_KEY", group: "Database", usedBy: "web", secret: false, required: ["live"], deployedIn: "Vercel", validate: prefix("eyJ", "sb_publishable_"), note: "Public by design (anon/publishable key); protected by RLS." },
  { name: "SUPABASE_URL", group: "Database", usedBy: "engine", secret: false, required: ["live"], deployedIn: "Fly (fiona-engine)", validate: url },
  { name: "SUPABASE_ANON_KEY", group: "Database", usedBy: "engine", secret: false, required: [], deployedIn: "Fly (fiona-engine)", validate: prefix("eyJ", "sb_publishable_") },
  { name: "SUPABASE_SERVICE_ROLE_KEY", group: "Database", usedBy: "engine only", secret: true, required: ["live"], deployedIn: "Fly (fiona-engine)", validate: prefix("eyJ", "sb_secret_"), note: "Engine only. Never in web, agents or Guardian." },

  // Service URLs and internal auth
  { name: "ENGINE_BASE_URL", group: "Services", usedBy: "web BFF, agents", secret: false, required: [], default: "http://localhost:8000", deployedIn: "Vercel, Fly", validate: url },
  { name: "AGENTS_BASE_URL", group: "Services", usedBy: "web BFF", secret: false, required: [], default: "http://localhost:8100", deployedIn: "Vercel", validate: url },
  { name: "GUARDIAN_BASE_URL", group: "Services", usedBy: "engine", secret: false, required: [], default: "http://localhost:8200", deployedIn: "Fly (fiona-engine)", validate: url },
  { name: "INTERNAL_JWT_SECRET", group: "Services", usedBy: "web BFF, engine, agents, guardian", secret: true, required: ["live"], deployedIn: "Vercel, Fly (all three)", validate: minLength(32), note: "Signs the BFF's 60-second internal token." },
  { name: "AGENTS_SERVICE_TOKEN", group: "Services", usedBy: "agents → engine", secret: true, required: ["live"], deployedIn: "Fly (fiona-agents, fiona-engine)", validate: minLength(24) },
  { name: "GUARDIAN_INBOUND_TOKEN", group: "Services", usedBy: "engine → guardian", secret: true, required: ["live"], deployedIn: "Fly (fiona-engine, fiona-guardian)", validate: minLength(24), note: "Only the engine's proposals service may call the Guardian." },

  // Claude (D-001: one capped workspace, two keys)
  { name: "ANTHROPIC_API_KEY", group: "Claude", usedBy: "agents only", secret: true, required: ["live"], deployedIn: "Fly (fiona-agents)", validate: prefix("sk-ant-") },
  { name: "GUARDIAN_ANTHROPIC_API_KEY", group: "Claude", usedBy: "guardian only", secret: true, required: ["live"], deployedIn: "Fly (fiona-guardian)", validate: prefix("sk-ant-"), note: "Must differ from ANTHROPIC_API_KEY (R8)." },
  { name: "FIONA_MODEL_EXTRACT", group: "Claude", usedBy: "agents", secret: false, required: [], default: "claude-haiku-5-5", deployedIn: "Fly (fiona-agents)", validate: claudeModel },
  { name: "FIONA_MODEL_REASON", group: "Claude", usedBy: "agents", secret: false, required: [], default: "claude-sonnet-5-5", deployedIn: "Fly (fiona-agents)", validate: claudeModel },
  { name: "FIONA_MODEL_GUIDE", group: "Claude", usedBy: "agents", secret: false, required: [], default: "claude-haiku-5-5", deployedIn: "Fly (fiona-agents)", validate: claudeModel },
  { name: "FIONA_MODEL_GUARDIAN", group: "Claude", usedBy: "guardian", secret: false, required: [], default: "claude-opus-5-5", deployedIn: "Fly (fiona-guardian)", validate: claudeModel },
  { name: "GUARDIAN_ADVERSARIAL_MIN_AMOUNT_MINOR", group: "Claude", usedBy: "guardian", secret: false, required: [], default: "0", deployedIn: "Fly (fiona-guardian)", validate: nonNegativeInt, note: "0 = review every proposal with Opus." },
  { name: "LLM_RUN_BUDGET_USD", group: "Claude", usedBy: "agents, guardian", secret: false, required: ["live"], deployedIn: "Fly (fiona-agents, fiona-guardian)", validate: positiveNumber, note: "Hard stop per run." },
  { name: "LLM_DAILY_BUDGET_USD", group: "Claude", usedBy: "agents, guardian", secret: false, required: ["live"], deployedIn: "Fly (fiona-agents, fiona-guardian)", validate: positiveNumber, note: "Hard stop per day." },
  { name: "AGENTS_REPLAY_ENABLED", group: "Claude", usedBy: "agents, guardian", secret: false, required: [], default: "1", deployedIn: "Fly", validate: flag, note: "Use the labelled replay cache only when a live call fails." },
  { name: "AGENTS_FORCE_REPLAY", group: "Claude", usedBy: "agents, guardian", secret: false, required: [], default: "0", deployedIn: "Fly", validate: flag, note: "Rehearsals and the from-cache run." },
  { name: "AGENTS_RECORD_REPLAY", group: "Claude", usedBy: "agents, guardian", secret: false, required: [], default: "0", deployedIn: "local only", validate: flag },

  // Feature flags (the cut order becomes a config change)
  { name: "FLAG_COUNCIL", group: "Flags", usedBy: "web, agents", secret: false, required: [], default: "1", deployedIn: "Vercel, Fly", validate: flag },
  { name: "FLAG_GUIDE", group: "Flags", usedBy: "web, agents", secret: false, required: [], default: "1", deployedIn: "Vercel, Fly", validate: flag },
  { name: "FLAG_PHONE_PASSKEY", group: "Flags", usedBy: "web", secret: false, required: [], default: "1", deployedIn: "Vercel", validate: flag },
  { name: "FLAG_PERSONA_SWITCH", group: "Flags", usedBy: "web", secret: false, required: [], default: "1", deployedIn: "Vercel", validate: flag },
  { name: "FLAG_FRAMEWORK_LENS", group: "Flags", usedBy: "web", secret: false, required: [], default: "1", deployedIn: "Vercel", validate: flag },
  { name: "FLAG_LAUNCH_LAB", group: "Flags", usedBy: "web", secret: false, required: [], default: "1", deployedIn: "Vercel", validate: flag },

  // Demo and auth
  { name: "DEMO_TENANT_ID", group: "Demo", usedBy: "web, scripts", secret: false, required: [], default: "ten_karachi_apparel", deployedIn: "Vercel", validate: (v) => (/^ten_[a-z0-9_]+$/.test(v) ? null : "must look like ten_…") },
  { name: "DEMO_PRESENTER_KEY", group: "Demo", usedBy: "web (/demo page)", secret: true, required: [], deployedIn: "Vercel (demo only)", validate: minLength(16) },
  { name: "WEBAUTHN_RP_ID", group: "Demo", usedBy: "web BFF", secret: false, required: [], default: "localhost", deployedIn: "Vercel", note: "Passkeys are bound to this domain." },
  { name: "WEBAUTHN_ORIGIN", group: "Demo", usedBy: "web BFF", secret: false, required: [], default: "http://localhost:3000", deployedIn: "Vercel", validate: url },
];

// Variables any code may read without listing them in .env.example (platform-provided).
export const PLATFORM_ENV = new Set([
  "NODE_ENV", "CI", "PATH", "HOME", "PORT", "TEMP", "TMP", "TMPDIR", "APPDATA", "LOCALAPPDATA",
  "USERPROFILE", "SYSTEMROOT", "NEXT_RUNTIME", "NEXT_PHASE", "VERCEL", "VERCEL_ENV", "VERCEL_URL",
  "VERCEL_GIT_COMMIT_SHA", "FLY_APP_NAME", "FLY_REGION", "FLY_MACHINE_ID", "GITHUB_ACTIONS",
  "PYTEST_CURRENT_TEST", "UV_CACHE_DIR",
  // Developer tooling overrides, not app configuration.
  "GITLEAKS_BIN",
]);

// NEXT_PUBLIC_* names that contain KEY/SECRET/TOKEN but are public by design.
export const PUBLIC_BY_DESIGN = new Set(["NEXT_PUBLIC_SUPABASE_ANON_KEY"]);
export const SECRET_LOOKING = /KEY|SECRET|TOKEN|PASSWORD|PRIVATE/;

/** Parse a dotenv file into a Map. Values are never printed by any caller. */
export function parseDotenv(text) {
  const out = new Map();
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const m = /^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/.exec(line);
    if (!m) continue;
    let value = m[2].trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    } else {
      value = value.replace(/\s+#.*$/, "");
    }
    out.set(m[1], value);
  }
  return out;
}
