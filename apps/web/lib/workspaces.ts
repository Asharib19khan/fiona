/** Workspaces (tenants) Fiona knows by name. Add a row here when a new business is onboarded. */
export const WORKSPACES: ReadonlyArray<{ id: string; label: string; currency: string }> = [
  { id: "ten_karachi_apparel", label: "Karachi Apparel", currency: "PKR" },
];

/** The workspace's reporting currency (ISO 4217), or null when the workspace isn't registered. */
export function workspaceCurrency(id: string | null): string | null {
  return WORKSPACES.find((workspace) => workspace.id === id)?.currency ?? null;
}

/** A readable name for a workspace ID: the registered label, else the ID made readable. */
export function workspaceLabel(id: string | null): string {
  if (!id) return "No workspace";
  const known = WORKSPACES.find((workspace) => workspace.id === id);
  if (known) return known.label;
  return id.replace(/^ten_/, "").split("_").filter(Boolean).map((word) => word[0]!.toUpperCase() + word.slice(1)).join(" ") || id;
}
