export type ApiMode = "mock" | "live";

/**
 * Which backend the Window talks to. NEXT_PUBLIC_* values are inlined at build time,
 * so preview builds and the demo build differ by design. A fresh clone runs in mock
 * mode with no secrets (R2); an unknown value fails loudly instead of guessing.
 */
export function apiMode(): ApiMode {
  const raw = process.env.NEXT_PUBLIC_API_MODE || "mock";
  if (raw === "mock" || raw === "live") return raw;
  throw new Error(`NEXT_PUBLIC_API_MODE must be "mock" or "live" (got "${raw}").`);
}
