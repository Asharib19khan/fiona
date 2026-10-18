import { apiMode } from "@/lib/env";
import { check } from "@fiona/contracts";
import { getMockBriefing, getMockMandates, getMockProposal, getMockProposals, type BriefingScenario } from "@/lib/mock-api";
import { hasInternalJwtSecret } from "@/lib/server-auth";
import { agentsRequest, readEnginePath, exportAuditEvidence, importEngine, postEngine, readEngine, type EngineRead, type ReadResult } from "@/lib/server-read";
import { getWorkspaceSession } from "@/lib/session";

export const dynamic = "force-dynamic";

function error(status: number, code: string, message: string) {
  return Response.json({ api_version: "v1", error: { code, message, request_id: "req_window_mock" } }, { status });
}

function mockGet(path: string[], request: Request) {
  const resource = `/${path.join("/")}`;
  const url = new URL(request.url);
  if (resource === "/briefing") {
    const scenario = url.searchParams.get("scenario") as BriefingScenario | null;
    const briefing = getMockBriefing(scenario ?? "default");
    return briefing ? Response.json(briefing) : error(503, "mock_unavailable", "The selected synthetic source is unavailable.");
  }
  if (resource === "/proposals") return Response.json({ api_version: "v1", proposals: getMockProposals() });
  if (path[0] === "proposals" && path[1]) {
    const record = getMockProposal(path[1]);
    return record ? Response.json({ api_version: "v1", ...record }) : error(404, "not_found", "No synthetic proposal matches this ID.");
  }
  if (resource === "/mandates") return Response.json({ api_version: "v1", mandates: getMockMandates() });
  return error(404, "not_found", `No mock BFF route at /v1${resource}.`);
}

function relay(result: ReadResult, what: string): Response {
  if (result.kind === "ok") return Response.json(result.data, { status: result.status, headers: { "cache-control": "no-store" } });
  if (result.kind === "unavailable") return error(result.status, "service_unavailable", result.message);
  return error(401, "not_signed_in", `${what} needs a signed-in person with a workspace.`);
}

const AGENT_READS = [/^agents\/team\/runs$/, /^agents\/team\/runs\/run_[a-z_]+_[0-9a-f]{12}$/, /^agents\/pipelines$/, /^agents\/pipelines\/pl_[a-z]+_[0-9a-f]{12}$/];
const AGENT_WRITES = new Set(["agents/team/run", "agents/council", "agents/pay-approved"]);

function mockApiBase(): string | null {
  const raw = process.env.MOCK_API_PORT ?? "8300";
  const port = Number(raw);
  return Number.isInteger(port) && port > 0 && port <= 65535 ? `http://127.0.0.1:${port}` : null;
}

function localMockMode(): boolean {
  return apiMode() === "mock" && (process.env.FIONA_MODE ?? "mock") === "mock";
}

async function proxyMockRead(path: string[], request: Request): Promise<Response | null> {
  if (!(path.length === 1 && path[0] === "proposals") && !(path.length === 2 && path[0] === "proposals")) return null;
  const base = mockApiBase();
  if (!base) return null;
  const target = new URL(path.length === 1 ? "/v1/proposals" : `/v1/proposals/${encodeURIComponent(path[1] ?? "")}`, base);
  const needsOwner = new URL(request.url).searchParams.get("needs_owner");
  if (needsOwner === "true") target.searchParams.set("needs_owner", "true");
  try {
    const upstream = await fetch(target, { headers: { accept: "application/json" }, cache: "no-store", redirect: "error", signal: AbortSignal.timeout(1_500) });
    return new Response(await upstream.text(), { status: upstream.status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" } });
  } catch {
    return null;
  }
}

async function readLimitedBody(request: Request, maxBytes: number): Promise<Uint8Array | null> {
  const length = Number(request.headers.get("content-length") ?? 0);
  if (Number.isFinite(length) && length > maxBytes) return null;
  if (!request.body) return new Uint8Array();
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > maxBytes) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  const body = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.byteLength; }
  return body;
}

export async function GET(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  if (!(await getWorkspaceSession())) return error(401, "not_signed_in", "Sign in to a workspace first.");
  const joined = path.join("/");
  if (AGENT_READS.some((pattern) => pattern.test(joined))) return relay(await agentsRequest("GET", `/v1/${joined}`), "Agent activity");
  if (path.length === 2 && path[0] === "proposals" && /^prop_[A-Za-z0-9_]+$/.test(path[1] ?? "") && !localMockMode()) {
    return relay(await readEnginePath(`/v1/proposals/${path[1]}`), "Proposal detail");
  }
  if (apiMode() !== "mock" && !hasInternalJwtSecret()) {
    return error(501, "live_bff_not_configured", "The live BFF requires an authenticated server configuration.");
  }
  if (path.length === 2 && path[0] === "audit" && path[1] === "export") {
    const result = await exportAuditEvidence();
    if (result.kind === "unavailable") return error(result.status, "engine_unavailable", result.message);
    if (result.kind === "disabled" || result.status !== 200) return error(503, "audit_export_unavailable", "The local execution-evidence export is unavailable.");
    return new Response(result.body, { status: 200, headers: { "content-type": result.contentType, "content-disposition": result.contentDisposition ?? 'attachment; filename="fiona-execution-evidence.zip"', "cache-control": "no-store" } });
  }
  const route = path.join("/");
  const reads: EngineRead[] = ["forecast/cash", "forecast/findings", "inventory/analysis", "stage", "analysis/ratios", "analysis/health", "reconcile/matches", "reconcile/findings", "audit", "ledger/events", "proposals", "mandates"];
  if (reads.includes(route as EngineRead)) {
    const result = await readEngine(route as EngineRead, new URL(request.url).searchParams);
    if (result.kind === "ok") return Response.json(result.data, { status: result.status, headers: { "cache-control": "no-store" } });
    if (result.kind === "unavailable") return error(result.status, "engine_unavailable", result.message);
    return error(501, "live_bff_not_configured", "Live reads require an authenticated server session.");
  }
  const mockRead = await proxyMockRead(path, request);
  if (mockRead) return mockRead;
  return mockGet(path, request);
}

export async function POST(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  if (!(await getWorkspaceSession())) return error(401, "not_signed_in", "Sign in to a workspace first.");
  const joined = path.join("/");
  if (AGENT_WRITES.has(joined)) {
    const bytes = await readLimitedBody(request, 16 * 1024);
    if (!bytes) return error(413, "request_too_large", "Agent requests are limited to 16 KB.");
    let body: unknown = {};
    if (bytes.byteLength) {
      try { body = JSON.parse(new TextDecoder().decode(bytes)); }
      catch { return error(400, "invalid_json", "The request must be valid JSON."); }
    }
    return relay(await agentsRequest("POST", `/v1/${joined}`, body), "Starting agent work");
  }
  if (path.length === 3 && path[0] === "mandates" && path[2] === "autonomy" && /^[a-z_]{3,40}$/.test(path[1] ?? "")) {
    const bytes = await readLimitedBody(request, 4 * 1024);
    if (!bytes) return error(413, "request_too_large", "Mandate changes are limited to 4 KB.");
    let change: Record<string, unknown>;
    try { change = JSON.parse(new TextDecoder().decode(bytes)); }
    catch { return error(400, "invalid_json", "The change must be valid JSON."); }
    return relay(await postEngine("proposals", change, `/v1/mandates/${path[1]}/autonomy`), "Changing a mandate");
  }
  if (path.length === 3 && path[0] === "proposals" && path[2] === "request-review" && /^prop_[A-Za-z0-9_]+$/.test(path[1] ?? "")) {
    return relay(await postEngine("proposals", {}, `/v1/proposals/${path[1]}/request-review`), "A Guardian re-review");
  }
  const isLive = apiMode() === "live" || (process.env.FIONA_MODE ?? "mock") === "live";

  if (!localMockMode() && !isLive) {
    return error(501, "live_bff_not_configured", "Proposal submission is available only in local mock mode until an authenticated owner session is configured.");
  }
  if (isLive && !hasInternalJwtSecret()) {
    return error(501, "live_bff_not_configured", "Proposal submission requires an authenticated server configuration in live mode.");
  }

  // 1. Decision submission: POST /v1/proposals/{id}/decision
  if (path.length === 3 && path[0] === "proposals" && path[2] === "decision") {
    const bytes = await readLimitedBody(request, 64 * 1024);
    if (!bytes) return error(413, "request_too_large", "Decision payload is limited to 64 KB.");
    let decision: Record<string, unknown>;
    try { decision = JSON.parse(new TextDecoder().decode(bytes)); }
    catch { return error(400, "invalid_json", "The decision must be valid JSON."); }
    const proposalId = path[1] ?? "";
    const result = await postEngine("proposals", decision, `/v1/proposals/${encodeURIComponent(proposalId)}/decision`);
    if (result.kind === "ok") return Response.json(result.data, { status: result.status, headers: { "cache-control": "no-store" } });
    if (result.kind === "unavailable") return error(result.status, "engine_unavailable", result.message);
    return error(501, "live_bff_not_configured", "Decision submission requires an authenticated server session.");
  }

  // 2. Participation loop: POST /v1/participation/run
  if (path.length === 2 && path[0] === "participation" && path[1] === "run") {
    const bytes = await readLimitedBody(request, 128 * 1024);
    if (!bytes) return error(413, "request_too_large", "Participation payload is limited to 128 KB.");
    let runBody: Record<string, unknown>;
    try { runBody = JSON.parse(new TextDecoder().decode(bytes)); }
    catch { return error(400, "invalid_json", "The participation body must be valid JSON."); }
    const result = await postEngine("participation/run", runBody);
    if (result.kind === "ok") return Response.json(result.data, { status: result.status, headers: { "cache-control": "no-store" } });
    if (result.kind === "unavailable") return error(result.status, "engine_unavailable", result.message);
    return error(501, "live_bff_not_configured", "Participation loop requires an authenticated server session.");
  }

  // 3. Bank / POS import
  if (path.length === 2 && path[0] === "import" && (path[1] === "bank" || path[1] === "pos")) {
    if (!request.headers.get("content-type")?.toLowerCase().startsWith("text/csv")) return error(415, "content_type_required", "Send the selected CSV as text/csv.");
    const rawName = request.headers.get("x-file-name") ?? `local_${path[1]}.csv`;
    const fileName = /^[A-Za-z0-9_. -]{1,120}\.csv$/i.test(rawName) ? rawName : `local_${path[1]}.csv`;
    const bytes = await readLimitedBody(request, 2 * 1024 * 1024);
    if (!bytes) return error(413, "request_too_large", "CSV imports are limited to 2 MB.");
    let csv: string;
    try { csv = new TextDecoder("utf-8", { fatal: true }).decode(bytes); }
    catch { return error(400, "invalid_file", "The CSV must be UTF-8."); }
    const result = await importEngine(path[1], csv, fileName);
    if (result.kind === "ok") return Response.json(result.data, { status: result.status, headers: { "cache-control": "no-store" } });
    if (result.kind === "unavailable") return error(result.status, "engine_unavailable", result.message);
    return error(501, "live_bff_not_configured", "CSV import requires an active engine session.");
  }

  // 4. Reconciliation run
  if (path.length === 2 && path[0] === "reconcile" && path[1] === "run") {
    const result = await postEngine("reconcile/run", {});
    if (result.kind === "ok") return Response.json(result.data, { status: result.status, headers: { "cache-control": "no-store" } });
    if (result.kind === "unavailable") return error(result.status, "engine_unavailable", result.message);
    return error(501, "live_bff_not_configured", "Reconciliation runs require an active engine session.");
  }

  if (path.length !== 1 || path[0] !== "proposals") return error(403, "action_not_available", "Only proposal drafts or authorized actions can be submitted.");
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) return error(415, "content_type_required", "Send a JSON proposal draft.");
  const idempotency = request.headers.get("idempotency-key") ?? "";
  if (!/^[A-Za-z0-9_-]{12,128}$/.test(idempotency)) return error(400, "idempotency_key_required", "A stable Idempotency-Key is required for draft submission.");
  const body = await readLimitedBody(request, 64 * 1024);
  if (!body) return error(413, "request_too_large", "Proposal drafts are limited to 64 KB.");
  let draft: unknown;
  try { draft = JSON.parse(new TextDecoder().decode(body)); }
  catch { return error(400, "invalid_json", "The proposal draft must be valid JSON."); }
  const issues = check("ProposalDraft", draft);
  if (issues.length) {
    return Response.json({
      api_version: "v1",
      error: {
        code: "validation_error",
        message: "The proposal draft does not satisfy the ProposalDraft contract.",
        request_id: "req_window_mock",
        details: { issues: issues.slice(0, 20) },
      },
    }, { status: 422 });
  }

  if (isLive) {
    const result = await postEngine("proposals", draft as Record<string, unknown>);
    if (result.kind === "ok") return Response.json(result.data, { status: result.status, headers: { "cache-control": "no-store" } });
    if (result.kind === "unavailable") return error(result.status, "engine_unavailable", result.message);
    return error(501, "live_bff_not_configured", "Live proposal draft submission requires an active engine session.");
  }

  const base = mockApiBase();
  if (!base) return error(503, "mock_api_unavailable", "MOCK_API_PORT must be a valid local port.");
  try {
    const upstream = await fetch(new URL("/v1/proposals", base), {
      method: "POST",
      headers: { "content-type": "application/json", "idempotency-key": idempotency },
      body: new TextDecoder().decode(body),
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(1_500),
    });
    return new Response(await upstream.text(), { status: upstream.status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" } });
  } catch {
    return error(503, "mock_api_unavailable", "Start the synthetic proposal service with pnpm mock:api, then retry.");
  }
}
