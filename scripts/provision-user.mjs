#!/usr/bin/env node
// Creates (or updates) a Fiona sign-in account in Supabase Auth and assigns its workspace and
// role. Workspace and role go in app_metadata, which only an admin key can write and the
// person cannot edit; Fiona authorises from those two fields only.
//
//   node scripts/provision-user.mjs --email you@company.com --name "Your Name" \
//        [--role owner|finance] [--tenant ten_karachi_apparel] [--password '…']
//
// Reads NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY from the root .env.local.
// Without --password it generates one and prints it once. The key is never printed.
import { randomBytes } from "node:crypto";
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function loadEnv() {
  const file = path.join(ROOT, ".env.local");
  if (!existsSync(file)) return;
  for (const raw of readFileSync(file, "utf8").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const [key, ...rest] = line.split("=");
    const value = rest.join("=").trim();
    if (key && value && process.env[key.trim()] === undefined) process.env[key.trim()] = value;
  }
}

function args() {
  const out = {};
  const argv = process.argv.slice(2);
  for (let i = 0; i < argv.length; i += 2) {
    if (!argv[i]?.startsWith("--")) throw new Error(`Unexpected argument ${argv[i]}`);
    out[argv[i].slice(2)] = argv[i + 1];
  }
  return out;
}

async function admin(base, key, method, route, body) {
  const res = await fetch(`${base}/auth/v1/admin/${route}`, {
    method,
    headers: { apikey: key, Authorization: `Bearer ${key}`, "content-type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(`Supabase ${method} ${route}: ${res.status} ${data.msg ?? data.message ?? data.error_description ?? JSON.stringify(data)}`);
  return data;
}

async function main() {
  loadEnv();
  const a = args();
  const base = process.env.NEXT_PUBLIC_SUPABASE_URL?.replace(/\/$/, "");
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!base || !key) throw new Error("Set NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env.local first.");
  const email = String(a.email ?? "").trim().toLowerCase();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) throw new Error("--email is required.");
  const role = a.role ?? "owner";
  if (!["owner", "finance"].includes(role)) throw new Error("--role must be owner or finance.");
  const tenant = a.tenant ?? process.env.DEMO_TENANT_ID ?? "ten_karachi_apparel";
  if (!/^ten_[a-z0-9_]{1,60}$/.test(tenant)) throw new Error("--tenant must look like ten_<slug>.");
  const name = String(a.name ?? email.split("@")[0]).slice(0, 80);
  const generated = !a.password;
  const password = a.password ?? randomBytes(12).toString("base64url");
  if (password.length < 10) throw new Error("--password must be at least 10 characters.");

  const app_metadata = { tenant_id: tenant, role };
  const user_metadata = { full_name: name };
  const listed = await admin(base, key, "GET", `users?page=1&per_page=1000`);
  const existing = (listed.users ?? []).find((u) => u.email?.toLowerCase() === email);
  if (existing) {
    await admin(base, key, "PUT", `users/${existing.id}`, { app_metadata, user_metadata, ...(a.password ? { password } : {}) });
    console.log(`Updated ${email}: workspace ${tenant}, role ${role}${a.password ? ", password changed" : ""}.`);
  } else {
    await admin(base, key, "POST", "users", { email, password, email_confirm: true, app_metadata, user_metadata });
    console.log(`Created ${email}: workspace ${tenant}, role ${role}.`);
    if (generated) console.log(`Password (shown once, store it safely): ${password}`);
  }
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
