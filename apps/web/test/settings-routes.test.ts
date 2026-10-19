import { describe, expect, it, vi } from "vitest";
import { readEnginePath } from "@/lib/server-read";

vi.mock("@/lib/session", () => ({
  getWorkspaceSession: async () => ({ userId: "usr_owner", tenantId: "ten_karachi_apparel", role: "owner" }),
}));

describe("workspace settings through the web server", () => {
  it("never relays the endpoint that returns a workspace's Claude secret", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    for (const path of ["/v1/settings/ai/credential", "/v1/settings/ai/../ai/credential", "/v1/settings/anything"]) {
      const result = await readEnginePath(path);
      expect(result).toMatchObject({ kind: "unavailable", status: 400 });
    }
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
