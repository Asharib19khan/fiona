#!/usr/bin/env node
/**
 * Synthetic Fiona API for local Window work. It deliberately has no database, credentials or
 * wallet execution path. Restart it to reset an in-memory POST /v1/proposals response.
 */
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const readJson = (file) => JSON.parse(readFileSync(resolve(root, file), "utf8"));
const briefing = readJson("packages/contracts/examples/Briefing.seed-42.json");
const mandate = readJson("packages/contracts/examples/Mandate.treasurer.json");
const plantedBill = readJson("packages/contracts/examples/scenarios/planted-bill-block.json");
const proposals = new Map([[plantedBill.proposal.id, { proposal: plantedBill.proposal, verdict: plantedBill.verdict }]]);
const idempotency = new Map();
const port = Number(process.env.MOCK_API_PORT || 8300);

const json = (response, status, body) => {
  response.writeHead(status, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
  response.end(`${JSON.stringify(body)}\n`);
};
const error = (response, status, code, message) => json(response, status, { api_version: "v1", error: { code, message, request_id: "req_mock_api" } });
const clone = (value) => structuredClone(value);

function briefingFor(scenario) {
  if (scenario === "error") return null;
  const result = clone(briefing);
  if (scenario === "clean" || scenario === "empty") result.cards = [];
  if (scenario === "degraded") result.degraded = [{ source: "inventory", detail: "The labelled inventory fixture is unavailable in this preview." }];
  if (scenario === "replayed") result.meta = { ...result.meta, replayed: true, model: "replay", recorded_at: "2026-10-22T04:00:00Z" };
  if (scenario === "planted-bill" || scenario === "escalate-over-cap") {
    const blocked = clone(plantedBill.proposal);
    result.cards.unshift({
      id: `card_${scenario}`,
      rank: 1,
      kind: "guardian",
      finding_id: null,
      proposal_id: blocked.id,
      severity: "high",
      needs_owner: true,
      title: scenario === "planted-bill" ? "Guardian blocked a bill to a changed bank account" : "A payment above the mandate needs you",
      detail: scenario === "planted-bill" ? "The synthetic bill duplicates a paid invoice and has a recently changed bank account." : "The synthetic payment exceeds the Treasurer's per-payment mandate.",
      source_label: "Guardian · planted security scenario",
      money_at_stake: blocked.amount,
      evidence: blocked.evidence,
      actions: [{ label: "Review proposal", route: `/proposals/${blocked.id}`, kind: "primary" }],
    });
    result.cards.forEach((card, index) => { card.rank = index + 1; });
    result.greeting = { text: "Good morning. One proposal needs your review.", needs_owner_count: 1 };
  }
  return result;
}

async function readBody(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  if (!chunks.length) return {};
  try { return JSON.parse(Buffer.concat(chunks).toString("utf8")); }
  catch { throw new Error("invalid_json"); }
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url || "/", `http://${request.headers.host || "localhost"}`);
  if (request.method === "GET" && url.pathname === "/healthz") return json(response, 200, { api_version: "v1", status: "ok", service: "mock-api" });
  if (request.method === "GET" && url.pathname === "/v1/briefing") {
    const body = briefingFor(url.searchParams.get("scenario") || "default");
    return body ? json(response, 200, body) : error(response, 503, "mock_unavailable", "The selected synthetic source is unavailable.");
  }
  if (request.method === "GET" && url.pathname === "/v1/proposals") {
    const needsOwner = url.searchParams.get("needs_owner") === "true";
    const list = [...proposals.values()].map(({ proposal, verdict }) => ({ ...proposal, verdict }));
    return json(response, 200, { api_version: "v1", proposals: needsOwner ? list.filter((item) => ["needs_owner", "blocked"].includes(item.status)) : list });
  }
  if (request.method === "GET" && url.pathname.startsWith("/v1/proposals/")) {
    const record = proposals.get(url.pathname.split("/").at(-1));
    return record ? json(response, 200, { api_version: "v1", ...record }) : error(response, 404, "not_found", "No synthetic proposal matches this ID.");
  }
  if (request.method === "GET" && url.pathname === "/v1/mandates") return json(response, 200, { api_version: "v1", mandates: [mandate] });
  if (request.method === "POST" && url.pathname === "/v1/proposals") {
    const key = request.headers["idempotency-key"];
    if (typeof key === "string" && idempotency.has(key)) return json(response, 200, idempotency.get(key));
    let draft;
    try { draft = await readBody(request); } catch { return error(response, 422, "validation_error", "The proposal body must be JSON."); }
    if (!draft || typeof draft.summary !== "string" || !draft.type || !draft.agent) return error(response, 422, "validation_error", "A proposal needs agent, type and summary.");
    const proposal = { ...draft, id: `prop_mock_${proposals.size + 1}`, tenant_id: "ten_karachi_apparel", status: "submitted", created_at: "2026-10-22T04:00:00Z", updated_at: "2026-10-22T04:00:00Z", verdict_id: null, supersedes: null };
    const result = { api_version: "v1", proposal, simulated: true };
    proposals.set(proposal.id, { proposal, verdict: null });
    if (typeof key === "string") idempotency.set(key, result);
    return json(response, 201, result);
  }
  return error(response, 404, "not_found", `No mock endpoint at ${url.pathname}.`);
});

server.listen(port, "127.0.0.1", () => console.log(`Fiona mock API: http://127.0.0.1:${port}`));
