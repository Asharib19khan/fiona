/**
 * Canonical JSON (RFC 8785 for the value types contracts use) and the verdict hash (CG-16).
 * Mirrors python/fiona_contracts/hashing.py; both are tested against the same examples.
 * Floats are refused: contracts carry integers only (minor units, basis points).
 */
export function canonicalJson(value: unknown): string {
  if (value === null || typeof value === "boolean" || typeof value === "string") return JSON.stringify(value);
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) throw new TypeError("Canonical JSON refuses non-integer numbers.");
    return String(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([, v]) => v !== undefined)
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)); // UTF-16 code-unit order, as RFC 8785 requires
    return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonicalJson(v)}`).join(",")}}`;
  }
  throw new TypeError(`Canonical JSON cannot encode ${typeof value}.`);
}

/** "sha256:" + hex SHA-256 of the canonical JSON of the verdict without verdict_hash. Web Crypto, so it runs in browsers too. */
export async function verdictHash(verdict: Record<string, unknown>): Promise<string> {
  const { verdict_hash: _ignored, ...body } = verdict;
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonicalJson(body)));
  return `sha256:${[...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("")}`;
}
