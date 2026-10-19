/** Workspaces (tenants) Fiona knows by name. Add a row here when a new business is onboarded. */
export interface Workspace {
  id: string;
  label: string;
  /** Reporting currency (ISO 4217). */
  currency: string;
  /** IANA time zone the business keeps its books in. */
  timezone: string;
  /** A generated demo company: its ledger is synthetic and every screen says so. */
  synthetic: boolean;
}

export const WORKSPACES: ReadonlyArray<Workspace> = [
  { id: "ten_karachi_apparel", label: "Karachi Apparel", currency: "PKR", timezone: "Asia/Karachi", synthetic: true },
];

export function workspaceInfo(id: string | null): Workspace | null {
  return WORKSPACES.find((workspace) => workspace.id === id) ?? null;
}

/** The workspace's reporting currency (ISO 4217), or null when the workspace isn't registered. */
export function workspaceCurrency(id: string | null): string | null {
  return workspaceInfo(id)?.currency ?? null;
}

/** A readable name for a workspace ID: the registered label, else the ID made readable. */
export function workspaceLabel(id: string | null): string {
  if (!id) return "No workspace";
  const known = WORKSPACES.find((workspace) => workspace.id === id);
  if (known) return known.label;
  return id.replace(/^ten_/, "").split("_").filter(Boolean).map((word) => word[0]!.toUpperCase() + word.slice(1)).join(" ") || id;
}
