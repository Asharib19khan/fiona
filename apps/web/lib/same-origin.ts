/**
 * True when a state-changing request comes from Fiona's own pages. Browsers send Origin (and
 * Sec-Fetch-Site) on every cross-site POST, so another site can't make a signed-in person's
 * browser approve, pay or change accounts. This backs up the SameSite=Lax session cookie.
 */
export function sameOrigin(request: Request): boolean {
  const site = request.headers.get("sec-fetch-site");
  if (site && site !== "same-origin" && site !== "none") return false;
  const origin = request.headers.get("origin");
  if (!origin) return true; // not a browser request; the session cookie still decides
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host") ?? new URL(request.url).host;
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

export function crossSite(): Response {
  return Response.json(
    { api_version: "v1", error: { code: "cross_site_request", message: "This request did not come from Fiona." } },
    { status: 403, headers: { "cache-control": "no-store" } },
  );
}
