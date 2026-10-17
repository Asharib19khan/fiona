import crypto from "node:crypto";

export interface MintTokenOptions {
  userId?: string;
  tenantId?: string;
  role?: "owner" | "finance";
  aud?: string;
  ttlSeconds?: number;
}

/**
 * Mint a short-lived internal HS256 JWT for BFF-to-service communication (R15).
 * Lifetime is capped at 60 seconds.
 */
export function mintInternalJwt(options: MintTokenOptions = {}): string | null {
  const secret = process.env.INTERNAL_JWT_SECRET;
  if (!secret || Buffer.from(secret, "utf-8").length < 32) {
    return null;
  }

  const userId = options.userId ?? process.env.DEMO_USER_ID ?? "usr_owner_demo";
  const tenantId = options.tenantId ?? process.env.DEMO_TENANT_ID ?? "ten_karachi_apparel";
  const role = options.role ?? "owner";
  const aud = options.aud ?? "fiona-engine";
  const ttl = Math.min(options.ttlSeconds ?? 60, 60);

  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "HS256", typ: "JWT" };
  const payload = {
    sub: userId,
    tenant_id: tenantId,
    role,
    aud,
    iat: now,
    exp: now + ttl,
  };

  const headerB64 = Buffer.from(JSON.stringify(header)).toString("base64url");
  const payloadB64 = Buffer.from(JSON.stringify(payload)).toString("base64url");
  const message = `${headerB64}.${payloadB64}`;

  const sig = crypto.createHmac("sha256", secret).update(message).digest("base64url");
  return `${message}.${sig}`;
}

export function hasInternalJwtSecret(): boolean {
  const secret = process.env.INTERNAL_JWT_SECRET;
  return Boolean(secret && Buffer.from(secret, "utf-8").length >= 32);
}
