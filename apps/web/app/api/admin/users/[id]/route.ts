import { AdminError, deleteUser, requireSuperAdmin, updateUser, type WorkspaceRole } from "@/lib/admin";
import { allow, clientKey, tooMany } from "@/lib/rate-limit";
import { crossSite, sameOrigin } from "@/lib/same-origin";

export const dynamic = "force-dynamic";

function fail(err: unknown): Response {
  if (err instanceof AdminError) {
    return Response.json({ api_version: "v1", error: { code: err.code, message: err.message } }, { status: err.status });
  }
  return Response.json({ api_version: "v1", error: { code: "internal_error", message: "Account administration failed." } }, { status: 500 });
}

/** Change an account's name, workspace or role; disable or enable it; or reset its password. */
export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  if (!sameOrigin(request)) return crossSite();
  if (!allow(`admin:${clientKey(request)}`, 60, 60_000)) return tooMany();
  try {
    await requireSuperAdmin();
    const { id } = await params;
    const body = (await request.json().catch(() => null)) as Record<string, unknown> | null;
    if (!body) throw new AdminError(400, "invalid_json", "Send the change as JSON.");
    const change: { name?: string; tenantId?: string; role?: WorkspaceRole; disabled?: boolean; resetPassword?: boolean } = {};
    if (typeof body.name === "string") change.name = body.name;
    if (typeof body.tenantId === "string") change.tenantId = body.tenantId;
    if (body.role !== undefined) change.role = body.role as WorkspaceRole;
    if (typeof body.disabled === "boolean") change.disabled = body.disabled;
    if (body.resetPassword === true) change.resetPassword = true;
    const result = await updateUser(id, change);
    return Response.json({ api_version: "v1", ...result }, { headers: { "cache-control": "no-store" } });
  } catch (err) {
    return fail(err);
  }
}

export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
  if (!sameOrigin(request)) return crossSite();
  if (!allow(`admin:${clientKey(request)}`, 60, 60_000)) return tooMany();
  try {
    await requireSuperAdmin();
    const { id } = await params;
    await deleteUser(id);
    return Response.json({ api_version: "v1", deleted: id }, { headers: { "cache-control": "no-store" } });
  } catch (err) {
    return fail(err);
  }
}
