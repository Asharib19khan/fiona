/** Workspaces (tenants) Fiona knows by name. Add a row here when a new business is onboarded. */
export const WORKSPACES: ReadonlyArray<{ id: string; label: string }> = [
  { id: "ten_karachi_apparel", label: "Karachi Apparel" },
];

/** A readable name for a workspace ID: the registered label, else the ID made readable. */
export function workspaceLabel(id: string | null): string {
  if (!id) return "No workspace";
  const known = WORKSPACES.find((workspace) => workspace.id === id);
  if (known) return known.label;
  return id.replace(/^ten_/, "").split("_").filter(Boolean).map((word) => word[0]!.toUpperCase() + word.slice(1)).join(" ") || id;
}
