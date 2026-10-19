import { AdminError, createUser, listUsers, requireSuperAdmin } from "@/lib/admin";
import { allow, clientKey, tooMany } from "@/lib/rate-limit";

export const dynamic = "force-dynamic";

function fail(err: unknown): Response {
  if (err instanceof AdminError) {
    return Response.json({ api_version: "v1", error: { code: err.code, message: err.message } }, { status: err.status });
  }
  return Response.json({ api_version: "v1", error: { code: "internal_error", message: "Account administration failed." } }, { status: 500 });
}

/** Every account (super admin only). */
export async function GET(request?: Request) {
  if (!allow(`admin:${request ? clientKey(request) : "unknown"}`, 60, 60_000)) return tooMany();
  try {
    await requireSuperAdmin();
    return Response.json({ api_version: "v1", users: await listUsers() }, { headers: { "cache-control": "no-store" } });
  } catch (err) {
    return fail(err);
  }
}

/** Create an account with a workspace and role; the temporary password is returned once. */
export async function POST(request: Request) {
  if (!allow(`admin:${clientKey(request)}`, 60, 60_000)) return tooMany();
  try {
    await requireSuperAdmin();
    const body = (await request.json().catch(() => null)) as Record<string, unknown> | null;
    if (!body) throw new AdminError(400, "invalid_json", "Send the account as JSON.");
    const result = await createUser({
      email: String(body.email ?? ""),
      name: String(body.name ?? ""),
      tenantId: String(body.tenantId ?? ""),
      role: body.role === "finance" ? "finance" : body.role === "owner" ? "owner" : (body.role as never),
    });
    return Response.json({ api_version: "v1", ...result }, { status: 201, headers: { "cache-control": "no-store" } });
  } catch (err) {
    return fail(err);
  }
}
