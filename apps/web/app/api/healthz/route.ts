import { apiMode } from "@/lib/env";

export const dynamic = "force-dynamic";

/** Liveness for the Window itself. Same envelope as the services' /healthz, plus the API mode. */
export function GET(): Response {
  return Response.json({ api_version: "v1", status: "ok", service: "web", mode: apiMode() });
}
