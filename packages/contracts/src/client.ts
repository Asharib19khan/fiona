import createClient, { type Middleware } from "openapi-fetch";
import type { paths as EnginePaths } from "../generated/ts/engine-api";
import { API_VERSION } from "./version";

/** A failed call, carrying the contract error envelope's code and request_id (CG-10). */
export class FionaApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly requestId: string | null,
    readonly details?: unknown,
  ) {
    super(message);
    this.name = "FionaApiError";
  }
}

interface EnvelopeLike {
  api_version?: unknown;
  error?: { code?: string; message?: string; request_id?: string; details?: unknown };
}

/** Every JSON response must carry api_version "v1" (R5); error envelopes become FionaApiError. */
export const contractGuard: Middleware = {
  async onResponse({ response }) {
    const type = response.headers.get("content-type") ?? "";
    if (!type.includes("application/json")) return response; // streams (SSE) and files pass through
    const body = (await response.clone().json().catch(() => null)) as EnvelopeLike | null;
    const requestId = response.headers.get("x-request-id");
    if (!response.ok) {
      const e = body?.error;
      throw new FionaApiError(
        response.status,
        e?.code ?? "http_error",
        e?.message ?? `Request failed with HTTP ${response.status}.`,
        e?.request_id ?? requestId,
        e?.details,
      );
    }
    if (body?.api_version !== API_VERSION) {
      throw new FionaApiError(
        response.status,
        "api_version_mismatch",
        `Expected api_version "${API_VERSION}" but got ${JSON.stringify(body?.api_version ?? null)}.`,
        requestId,
      );
    }
    return response;
  },
};

export interface ClientOptions {
  /** e.g. "/api/fiona" in the browser (the BFF), or http://localhost:8000 server-side. */
  baseUrl: string;
  headers?: Record<string, string>;
  fetch?: typeof globalThis.fetch;
}

/** Typed client for the engine API, generated from its OpenAPI (packages/contracts/openapi/engine.v1.json). */
export function createEngineClient(options: ClientOptions) {
  const client = createClient<EnginePaths>({
    baseUrl: options.baseUrl,
    ...(options.headers ? { headers: options.headers } : {}),
    ...(options.fetch ? { fetch: options.fetch } : {}),
  });
  client.use(contractGuard);
  return client;
}

export type EngineClient = ReturnType<typeof createEngineClient>;
export type { EnginePaths };
