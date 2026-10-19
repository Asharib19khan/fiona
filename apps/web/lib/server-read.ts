import { apiMode } from "@/lib/env";
import { hasInternalJwtSecret, mintInternalJwt } from "@/lib/server-auth";
import { getWorkspaceSession } from "@/lib/session";

const engineReads = {
  "forecast/cash": { path: "/v1/forecast/cash", query: ["weeks"] },
  "forecast/findings": { path: "/v1/forecast/findings", query: [] },
  "inventory/analysis": { path: "/v1/inventory/analysis", query: [] },
  stage: { path: "/v1/stage", query: [] },
  "analysis/ratios": { path: "/v1/analysis/ratios", query: [] },
  "analysis/health": { path: "/v1/analysis/health", query: [] },
  "reconcile/matches": { path: "/v1/reconcile/matches", query: [] },
  "reconcile/findings": { path: "/v1/reconcile/findings", query: ["limit"] },
  audit: { path: "/v1/audit", query: ["proposal_id"] },
  "ledger/events": { path: "/v1/ledger/events", query: ["type", "date_from", "date_to", "limit", "offset"] },
  proposals: { path: "/v1/proposals", query: ["needs_owner"] },
  mandates: { path: "/v1/mandates", query: [] },
} as const;

const enginePosts = {
  "financing/match": { path: "/v1/financing/match" },
  "bills/check": { path: "/v1/bills/check" },
  "reconcile/run": { path: "/v1/reconcile/run" },
  "decisions/debt-equity": { path: "/v1/decisions/debt-equity" },
  "decisions/payment-timing": { path: "/v1/decisions/payment-timing" },
  "participation/run": { path: "/v1/participation/run" },
  "proposals": { path: "/v1/proposals" },
  "launch-lab/simulate": { path: "/v1/launch-lab/simulate" },
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

export type Audience = "fiona-engine" | "fiona-agents";

/**
 * Headers that carry the signed-in person to a service. Live mode signs a 60-second internal
 * token with their user ID, workspace and role (R15); local mock mode names the workspace in a
 * header. No session, no workspace or no signing secret: no headers, and the caller refuses.
 */
export async function sessionHeaders(aud: Audience = "fiona-engine"): Promise<Record<string, string> | null> {
  const session = await getWorkspaceSession();
  if (!session) return null;
  const headers: Record<string, string> = { "X-Fiona-Tenant": session.tenantId };
  const mode = apiMode();
  const fionaMode = process.env.FIONA_MODE ?? "mock";
  if (mode === "mock" && fionaMode === "mock") return headers;
  if (!hasInternalJwtSecret()) return null;
  const token = mintInternalJwt({ userId: session.userId, tenantId: session.tenantId, role: session.role, aud });
  if (!token) return null;
  headers.Authorization = `Bearer ${token}`;
  return headers;
}

const READ_TIMEOUT_MS = 20_000; // live analysis reads the whole ledger: several seconds is normal

/**
 * Server-only engine read access. In mock mode, uses X-Fiona-Tenant; in live mode,
 * signs and forwards a short-lived internal HS256 JWT (R15).
 */
export async function readEngine(
  name: EngineRead,
  incoming = new URLSearchParams(),
): Promise<ReadResult> {
  const headers = await sessionHeaders();
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
      signal: AbortSignal.timeout(READ_TIMEOUT_MS),
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
  const headers = await sessionHeaders();
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
  const headers = await sessionHeaders();
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
  const headers = await sessionHeaders();
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

/**
 * Server-only call to the agents service as the signed-in person (aud fiona-agents). Starting
 * runs can take a moment; reading them is quick.
 */
export async function agentsRequest(method: "GET" | "POST", path: string, body?: unknown, timeoutMs?: number): Promise<ReadResult> {
  if (!/^\/v1\/agents\/[A-Za-z0-9_/-]{1,120}$/.test(path)) {
    return { kind: "unavailable", status: 400, message: "Unknown agents route." };
  }
  const headers = await sessionHeaders("fiona-agents");
  if (!headers) return { kind: "disabled" };
  const base = process.env.AGENTS_BASE_URL ?? "http://127.0.0.1:8100";
  let target: URL;
  try { target = new URL(path, base); }
  catch { return { kind: "unavailable", status: 503, message: "The agents service URL is invalid." }; }
  try {
    const response = await fetch(target, {
      method,
      headers: { accept: "application/json", ...(body === undefined ? {} : { "content-type": "application/json" }), ...headers },
      body: body === undefined ? null : JSON.stringify(body),
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(timeoutMs ?? (method === "GET" ? 10_000 : 30_000)),
    });
    return { kind: "ok", status: response.status, data: await response.json() };
  } catch {
    return { kind: "unavailable", status: 503, message: "The agents service is not responding." };
  }
}

/** Server-only engine GET of one vetted path (for example a single proposal). */
export async function readEnginePath(path: string): Promise<ReadResult> {
  if (!/^\/v1\/(proposals\/prop_[A-Za-z0-9_]+(\/trace)?|bills\/bill_[A-Za-z0-9_]+|parties\?q=[^&#]{2,160})$/.test(path)) {
    return { kind: "unavailable", status: 400, message: "Unknown engine route." };
  }
  const headers = await sessionHeaders();
  if (!headers) return { kind: "disabled" };
  const base = process.env.ENGINE_BASE_URL ?? "http://127.0.0.1:8000";
  try {
    const response = await fetch(new URL(path, base), {
      headers: { accept: "application/json", ...headers },
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(READ_TIMEOUT_MS),
    });
    return { kind: "ok", status: response.status, data: await response.json() };
  } catch {
    return { kind: "unavailable", status: 503, message: "The engine is not responding." };
  }
}
