import { apiMode } from "@/lib/env";
import { hasInternalJwtSecret, mintInternalJwt } from "@/lib/server-auth";

const engineReads = {
  "forecast/cash": { path: "/v1/forecast/cash", query: ["weeks"] },
  "forecast/findings": { path: "/v1/forecast/findings", query: [] },
  "inventory/analysis": { path: "/v1/inventory/analysis", query: [] },
  stage: { path: "/v1/stage", query: [] },
  "analysis/ratios": { path: "/v1/analysis/ratios", query: [] },
  "analysis/health": { path: "/v1/analysis/health", query: [] },
  "reconcile/matches": { path: "/v1/reconcile/matches", query: [] },
  "reconcile/findings": { path: "/v1/reconcile/findings", query: [] },
  audit: { path: "/v1/audit", query: ["proposal_id"] },
  "ledger/events": { path: "/v1/ledger/events", query: ["type", "date_from", "date_to", "limit", "offset"] },
  proposals: { path: "/v1/proposals", query: ["needs_owner"] },
} as const;

const enginePosts = {
  "financing/match": { path: "/v1/financing/match" },
  "bills/check": { path: "/v1/bills/check" },
  "reconcile/run": { path: "/v1/reconcile/run" },
  "decisions/debt-equity": { path: "/v1/decisions/debt-equity" },
  "decisions/payment-timing": { path: "/v1/decisions/payment-timing" },
  "participation/run": { path: "/v1/participation/run" },
  "proposals": { path: "/v1/proposals" },
} as const;

export type EngineWrite = keyof typeof enginePosts;
export type ImportKind = "bank" | "pos";

export type FileReadResult =
  | { kind: "ok"; status: number; body: ArrayBuffer; contentType: string; contentDisposition: string | null }
  | { kind: "unavailable"; status: number; message: string }
  | { kind: "disabled" };

export type EngineRead = keyof typeof engineReads;

export type ReadResult =
  | { kind: "ok"; status: number; data: unknown }
  | { kind: "unavailable"; status: number; message: string }
  | { kind: "disabled" };

function demoTenant(): string | null {
  const tenant = process.env.DEMO_TENANT_ID ?? "ten_karachi_apparel";
  return /^ten_[a-z0-9_]{1,60}$/.test(tenant) ? tenant : null;
}

function authHeaders(tenant: string): Record<string, string> | null {
  const mode = apiMode();
  const fionaMode = process.env.FIONA_MODE ?? "mock";
  const isMock = mode === "mock" && fionaMode === "mock";

  const headers: Record<string, string> = {
    "X-Fiona-Tenant": tenant,
  };

  if (!isMock) {
    if (!hasInternalJwtSecret()) {
      return null;
    }
    const token = mintInternalJwt({ tenantId: tenant, aud: "fiona-engine" });
    if (!token) return null;
    headers["Authorization"] = `Bearer ${token}`;
  }

  return headers;
}

/**
 * Server-only engine read access. In mock mode, uses X-Fiona-Tenant; in live mode,
 * signs and forwards a short-lived internal HS256 JWT (R15).
 */
export async function readEngine(
  name: EngineRead,
  incoming = new URLSearchParams(),
): Promise<ReadResult> {
  const tenant = demoTenant();
  if (!tenant) return { kind: "unavailable", status: 500, message: "The server demo tenant is invalid." };

  const headers = authHeaders(tenant);
  if (!headers) {
    return { kind: "disabled" };
  }

  const base = process.env.ENGINE_BASE_URL ?? "http://127.0.0.1:8000";
  const route = engineReads[name];
  let target: URL;
  try {
    target = new URL(route.path, base);
  } catch {
    return { kind: "unavailable", status: 503, message: "The local engine URL is invalid." };
  }
  for (const key of route.query) {
    const value = incoming.get(key);
    if (value !== null && /^[A-Za-z0-9_.:-]{1,100}$/.test(value)) target.searchParams.set(key, value);
  }

  try {
    const response = await fetch(target, {
      method: "GET",
      headers: { accept: "application/json", ...headers },
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(3_000),
    });
    const data: unknown = await response.json();
    return { kind: "ok", status: response.status, data };
  } catch {
    return { kind: "unavailable", status: 503, message: "The local engine is not responding." };
  }
}

/** Server-only engine POST with live token authentication support. */
export async function postEngine(
  name: EngineWrite,
  body: Record<string, unknown>,
  customPath?: string,
): Promise<ReadResult> {
  const tenant = demoTenant();
  if (!tenant) return { kind: "unavailable", status: 500, message: "The server demo tenant is invalid." };

  const headers = authHeaders(tenant);
  if (!headers) {
    return { kind: "disabled" };
  }

  const base = process.env.ENGINE_BASE_URL ?? "http://127.0.0.1:8000";
  const path = customPath ?? enginePosts[name].path;
  let target: URL;
  try {
    target = new URL(path, base);
  } catch {
    return { kind: "unavailable", status: 503, message: "The local engine URL is invalid." };
  }

  try {
    const response = await fetch(target, {
      method: "POST",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
        ...headers,
      },
      body: JSON.stringify(body),
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(30_000),
    });
    const data: unknown = await response.json();
    return { kind: "ok", status: response.status, data };
  } catch {
    return { kind: "unavailable", status: 503, message: "The local engine is not responding." };
  }
}

/** Import a local CSV through the server-selected demo tenant. */
export async function importEngine(
  kind: ImportKind,
  csv: string,
  fileName: string,
): Promise<ReadResult> {
  const tenant = demoTenant();
  if (!tenant) return { kind: "unavailable", status: 500, message: "The server demo tenant is invalid." };
  const headers = authHeaders(tenant);
  if (!headers) return { kind: "disabled" };

  const base = process.env.ENGINE_BASE_URL ?? "http://127.0.0.1:8000";
  let target: URL;
  try {
    target = new URL(`/v1/import/${kind}`, base);
    target.searchParams.set("file_name", fileName);
  } catch {
    return { kind: "unavailable", status: 503, message: "The local engine URL is invalid." };
  }
  try {
    const response = await fetch(target, {
      method: "POST",
      headers: { accept: "application/json", "content-type": "text/csv; charset=utf-8", ...headers },
      body: csv,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(10_000),
    });
    return { kind: "ok", status: response.status, data: await response.json() };
  } catch {
    return { kind: "unavailable", status: 503, message: "The local engine is not responding." };
  }
}

/** Download an execution-evidence bundle through the server-selected demo tenant. */
export async function exportAuditEvidence(): Promise<FileReadResult> {
  const tenant = demoTenant();
  if (!tenant) return { kind: "unavailable", status: 500, message: "The server demo tenant is invalid." };
  const headers = authHeaders(tenant);
  if (!headers) return { kind: "disabled" };

  const base = process.env.ENGINE_BASE_URL ?? "http://127.0.0.1:8000";
  let target: URL;
  try { target = new URL("/v1/audit/export", base); }
  catch { return { kind: "unavailable", status: 503, message: "The local engine URL is invalid." }; }
  try {
    const response = await fetch(target, {
      headers: { accept: "application/zip", ...headers },
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(30_000),
    });
    return {
      kind: "ok",
      status: response.status,
      body: await response.arrayBuffer(),
      contentType: response.headers.get("content-type") ?? "application/octet-stream",
      contentDisposition: response.headers.get("content-disposition"),
    };
  } catch {
    return { kind: "unavailable", status: 503, message: "The local engine is not responding." };
  }
}

export function objectValue(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}
