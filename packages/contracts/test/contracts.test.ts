import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  API_VERSION,
  canonicalJson,
  check,
  type ContractName,
  createEngineClient,
  FionaApiError,
  type Proposal,
  type Verdict,
  verdictHash,
} from "../src/index";

const root = path.resolve(import.meta.dirname, "..");
const readJson = (p: string) => JSON.parse(readFileSync(p, "utf8"));
const examplesDir = path.join(root, "examples");
const scenariosDir = path.join(examplesDir, "scenarios");

describe("examples validate against their contracts", () => {
  const files = readdirSync(examplesDir).filter((f) => f.endsWith(".json"));
  it.each(files)("%s", (file) => {
    const name = file.split(".")[0] as ContractName;
    expect(check(name, readJson(path.join(examplesDir, file)))).toEqual([]);
  });
});

describe("demo scenarios", () => {
  const files = readdirSync(scenariosDir).filter((f) => f.endsWith(".json"));
  it.each(files)("%s: proposal and verdict are valid and the verdict hash recomputes", async (file) => {
    const { proposal, verdict } = readJson(path.join(scenariosDir, file)) as { proposal: Proposal; verdict: Verdict };
    expect(check("Proposal", proposal)).toEqual([]);
    expect(check("Verdict", verdict)).toEqual([]);
    expect(verdict.proposal_id).toBe(proposal.id);
    expect(await verdictHash(verdict as unknown as Record<string, unknown>)).toBe(verdict.verdict_hash);
  });

  it("the planted bill is blocked, and its strictest check is a block", () => {
    const { verdict } = readJson(path.join(scenariosDir, "planted-bill-block.json")) as { verdict: Verdict };
    expect(verdict.outcome).toBe("block");
    const failing = verdict.checks.filter((c) => c.result === "fail").map((c) => c.rule);
    expect(failing).toEqual(expect.arrayContaining(["G-03", "G-05", "G-12"]));
  });
});

describe("contracts reject what they must", () => {
  const money = { minor: 100, currency: "PKR" };
  it("a float amount", () => expect(check("Money", { minor: 1.5, currency: "PKR" })).not.toEqual([]));
  it("a lower-case currency", () => expect(check("Money", { minor: 1, currency: "pkr" })).not.toEqual([]));
  it("an unknown field (typos fail)", () => expect(check("Money", { ...money, minr: 1 })).not.toEqual([]));
  it("a timestamp that is not UTC", () =>
    expect(check("Timestamp", "2026-10-22T14:15:00+05:00")).not.toEqual([]));
  it("a Figure with both money and value", () =>
    expect(check("Figure", { metric_id: "x", label: "x", money, value: 1, unit: "minor" })).not.toEqual([]));
  it("a Figure whose money is not in minor units", () =>
    expect(check("Figure", { metric_id: "x", label: "x", money, unit: "bp" })).not.toEqual([]));
  it("an ok Figure with no number", () =>
    expect(check("Figure", { metric_id: "x", label: "x", unit: "bp" })).not.toEqual([]));
  it("insufficient_data without saying what is missing", () =>
    expect(check("Figure", { metric_id: "x", label: "x", unit: "bp", status: "insufficient_data" })).not.toEqual([]));
  it("a passing check that claims a non-approve outcome", () =>
    expect(
      check("Check", { name: "policy", rule: "G-01", result: "pass", outcome: "escalate", detail: "x" }),
    ).not.toEqual([]));
  it("approve_with_conditions without a condition", () =>
    expect(
      check("Check", { name: "policy", rule: "G-08", result: "fail", outcome: "approve_with_conditions", detail: "x" }),
    ).not.toEqual([]));
  it("an unknown rule ID", () =>
    expect(check("Check", { name: "policy", rule: "G-99", result: "pass", outcome: "approve", detail: "x" })).not.toEqual([]));
  it("a draft that tries to set the tenant (R15)", () => {
    const draft = readJson(path.join(examplesDir, "ProposalDraft.payment.json"));
    expect(check("ProposalDraft", { ...draft, tenant_id: "ten_other" })).not.toEqual([]);
  });
  it("a payment payload under the wrong type", () => {
    const draft = readJson(path.join(examplesDir, "ProposalDraft.payment.json"));
    expect(check("ProposalDraft", { ...draft, type: "bill_approval" })).not.toEqual([]);
  });
  it("a mandate autonomy key that is not an action type", () => {
    const m = readJson(path.join(examplesDir, "Mandate.treasurer.json"));
    expect(check("Mandate", { ...m, autonomy: { wire_transfer: "act_within_mandate" } })).not.toEqual([]);
  });
});

describe("canonical JSON", () => {
  it("sorts keys, drops whitespace and refuses floats", () => {
    expect(canonicalJson({ b: 1, a: [true, null, "x"] })).toBe('{"a":[true,null,"x"],"b":1}');
    expect(() => canonicalJson({ amount: 1.5 })).toThrow(/non-integer/);
  });
});

describe("engine client", () => {
  const respond = (status: number, body: unknown) =>
    (async () =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json", "x-request-id": "req_test0001" },
      })) as typeof fetch;

  it("passes a v1 response through", async () => {
    const client = createEngineClient({ baseUrl: "http://engine.test", fetch: respond(200, { api_version: API_VERSION, status: "ok", service: "engine" }) });
    const { data } = await client.GET("/healthz");
    expect(data).toMatchObject({ api_version: "v1" });
  });

  it("fails loudly when api_version is missing (R5)", async () => {
    const client = createEngineClient({ baseUrl: "http://engine.test", fetch: respond(200, { status: "ok" }) });
    await expect(client.GET("/healthz")).rejects.toMatchObject({ code: "api_version_mismatch" });
  });

  it("turns the error envelope into FionaApiError with the request_id", async () => {
    const envelope = { api_version: "v1", error: { code: "not_implemented", message: "Not yet.", request_id: "req_abc12345" } };
    const client = createEngineClient({ baseUrl: "http://engine.test", fetch: respond(501, envelope) });
    const err = await client.GET("/healthz").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(FionaApiError);
    expect(err).toMatchObject({ status: 501, code: "not_implemented", requestId: "req_abc12345" });
  });
});
