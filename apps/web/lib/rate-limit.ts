/**
 * A small sliding-window limiter kept in this server's memory. It slows scripted probing of the
 * admin and write APIs; it is per instance, so a multi-instance deployment should add an edge
 * limiter too. Sign-in attempts are limited by Supabase Auth itself.
 */
const windows = new Map<string, number[]>();
const MAX_KEYS = 10_000;

export function allow(key: string, limit: number, windowMs: number, now = Date.now()): boolean {
  const recent = (windows.get(key) ?? []).filter((at) => now - at < windowMs);
  if (recent.length >= limit) {
    windows.set(key, recent);
    return false;
  }
  recent.push(now);
  windows.delete(key);
  windows.set(key, recent);
  // Forget the oldest callers first so memory stays bounded.
  while (windows.size > MAX_KEYS) windows.delete(windows.keys().next().value as string);
  return true;
}

/** The caller's address as the hosting proxy reports it (first X-Forwarded-For entry). */
export function clientKey(request: Request): string {
  const forwarded = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  return forwarded || request.headers.get("x-real-ip") || "unknown";
}

export function tooMany(): Response {
  return Response.json(
    { api_version: "v1", error: { code: "rate_limited", message: "Too many requests. Wait a minute and try again." } },
    { status: 429, headers: { "retry-after": "60", "cache-control": "no-store" } },
  );
}

export function resetRateLimits(): void {
  windows.clear();
}
