const BASE = "https://fiona.invalid";

/**
 * A same-site path to go to after signing in. Anything else becomes "/".
 *
 * Browsers drop tabs and newlines from URLs and treat `\` like `/`, so `/\tevil.com` or
 * `/%09/evil.com` (decoded) would turn into `//evil.com`, another site. Control characters and
 * backslashes are refused outright, and the result must still resolve to this site.
 */
export function safeNext(value: string | null | undefined): string {
  if (!value || value.length > 2048 || !value.startsWith("/")) return "/";
  if (/[\u0000-\u001f\u007f\\]/.test(value) || value.startsWith("//")) return "/";
  try {
    const url = new URL(value, BASE);
    if (url.origin !== BASE) return "/";
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return "/";
  }
}
