/** Engine detail text can carry raw keys ("supplier_bills, supplier_bills"); show them as words and count repeats. */
export function readable(text: string): string {
  const words = text.replace(/\b([a-z]+(?:_[a-z]+)+)\b/g, (key) => key.replace(/_/g, " "));
  return words.replace(/:\s*([^.:]+(?:,\s*[^.:,]+)+)/g, (_, items: string) => {
    const counts = new Map<string, number>();
    for (const item of items.split(",").map((s) => s.trim()).filter(Boolean)) counts.set(item, (counts.get(item) ?? 0) + 1);
    return ": " + [...counts].map(([item, n]) => (n > 1 ? `${item} ×${n}` : item)).join(", ");
  });
}

/** Where a finding came from, in words. */
export function sourceLabel(source: string): string {
  if (source === "forecast") return "Cash forecast";
  if (source === "reconciliation") return "Reconciliation";
  if (source === "inventory") return "Inventory";
  return source.charAt(0).toUpperCase() + source.slice(1).replace(/_/g, " ");
}
