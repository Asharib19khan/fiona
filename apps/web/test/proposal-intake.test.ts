import { describe, expect, it } from "vitest";

import { POST } from "@/app/api/fiona/[...path]/route";

function request(body: unknown): Request {
  return new Request("http://localhost/api/fiona/proposals", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "idempotency-key": "test-proposal-intake-001",
    },
    body: JSON.stringify(body),
  });
}

describe("proposal intake boundary", () => {
  it("rejects partial drafts instead of forwarding them to the mock service", async () => {
    const response = await POST(request({ agent: "treasurer", type: "payment", summary: "Pay this" }), {
      params: Promise.resolve({ path: ["proposals"] }),
    });

    expect(response.status).toBe(422);
    await expect(response.json()).resolves.toMatchObject({
      error: {
        code: "validation_error",
        message: "The proposal draft does not satisfy the ProposalDraft contract.",
        details: { issues: expect.arrayContaining([expect.objectContaining({ message: expect.any(String) })]) },
      },
    });
  });

  it("rejects an unknown proposal type at the contract boundary", async () => {
    const response = await POST(request({
      agent: "treasurer",
      type: "wire_money",
      summary: "Pay this",
    }), { params: Promise.resolve({ path: ["proposals"] }) });

    expect(response.status).toBe(422);
  });
});
