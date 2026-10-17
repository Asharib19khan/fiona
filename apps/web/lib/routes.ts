export const routes = {
  briefing: { href: "/", label: "Briefing", description: "A ranked view of cash, inventory and decisions that may need your attention." },
  approvals: { href: "/approvals", label: "Approvals", description: "Review proposals and see the checks Fiona has completed before any action." },
  forecast: { href: "/forecast", label: "Cash forecast", description: "Explore the 13-week cash forecast, its assumptions and upcoming buffer alerts." },
  financing: { href: "/financing", label: "Financing", description: "Compare eligible financing options with their costs, assumptions and sources." },
  analysis: { href: "/analysis", label: "Financial analysis", description: "Review stage, financial ratios and health bands from posted ledger activity." },
  bills: { href: "/bills", label: "Bills", description: "Review imported bills and the checks that must pass before payment." },
  reconcile: { href: "/reconcile", label: "Reconciliation", description: "Review bank-line matches and unresolved differences." },
  wallet: { href: "/wallet", label: "Sandbox wallet", description: "See the guarded, simulated payment path and its audit requirements." },
  import: { href: "/import", label: "Import data", description: "Bring in ledger exports and review source records before they are used." },
  inventory: { href: "/inventory", label: "Inventory", description: "Find stock movement, coverage and draft reorder suggestions." },
  "launch-lab": { href: "/launch-lab", label: "Launch Lab", description: "Explore an illustrative launch scenario and the assumptions behind it." },
  council: { href: "/council", label: "Council", description: "Compare perspectives on a business decision and keep disagreements visible." },
  audit: { href: "/audit", label: "Audit trail", description: "Follow proposals, Guardian verdicts and simulated wallet events." },
  mandates: { href: "/settings/mandates", label: "Mandates & limits", description: "See the autonomy levels and spending limits that constrain each agent." },
  "payment-timing": { href: "/decisions/payment-timing", label: "Payment timing", description: "Compare payment dates against discounts, financing cost and cash buffer." },
} as const;

export type RouteKey = keyof typeof routes;
export const routeList = Object.values(routes);
