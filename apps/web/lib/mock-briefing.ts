/**
 * Small view model copied from the engine's labelled seed-42 mock response so the
 * Window can be previewed without starting the services. All values are synthetic.
 */
export const mockBriefing = {
  tenant: "ten_karachi_apparel",
  asOf: "2026-10-22",
  sourceLabel: "Seed-42 synthetic business · mock response",
  cash: {
    lowestClosingMinor: 24_611_900,
    bufferMinor: 200_000_000,
    shortfallMinor: 175_388_100,
  },
  findings: [
    {
      id: "fnd_demo_cash_week_7",
      title: "Cash dips below your buffer in week 7",
      description: "Winter stock bills in weeks 5 to 7 overlap payroll, rent and the loan instalment.",
      amountMinor: 175_388_100,
      severity: "high" as const,
      source: "Cash forecast · 4–10 Dec 2026",
      time: "2026-10-22T04:00:00Z",
      route: "/forecast",
      action: "Open forecast",
    },
    {
      id: "fnd_demo_slow_stock",
      title: "Summer lawn suits cover more than a year of sales",
      description: "Slow-moving stock is tying up working capital. Review the synthetic inventory sample before placing more orders.",
      amountMinor: 53_300_000,
      severity: "medium" as const,
      source: "Inventory · 90-day sample",
      time: "2026-10-22T04:00:00Z",
      route: "/inventory",
      action: "Open inventory",
    },
    {
      id: "fnd_demo_reorder",
      title: "Wool shawls may run out before the next delivery",
      description: "The example reorder estimate is a draft suggestion. It does not create a purchase order.",
      amountMinor: 12_730_000,
      severity: "medium" as const,
      source: "Inventory · reorder estimate",
      time: "2026-10-22T04:00:00Z",
      route: "/inventory",
      action: "Review estimate",
    },
  ],
};

export const scenarioFinding = {
  plantedBill: {
    id: "fnd_scenario_planted_bill",
    title: "Supplier bank details changed before payment",
    description: "The planted bill includes an unconfirmed bank-detail change. The Guardian blocks the payment for owner review.",
    amountMinor: 18_450_000,
    severity: "high" as const,
    outcome: "block" as const,
    source: "Planted-bill security scenario",
    time: "2026-10-22T04:00:00Z",
    route: "/approvals",
    action: "Review blocked proposal",
  },
  overCap: {
    id: "fnd_scenario_over_cap",
    title: "Payment is above the Treasurer’s per-payment limit",
    description: "This demo payment exceeds the PKR 150,000 mandate cap and must be escalated for owner review.",
    amountMinor: 18_450_000,
    severity: "high" as const,
    outcome: "escalate" as const,
    source: "Mandate limit scenario",
    time: "2026-10-22T04:00:00Z",
    route: "/approvals",
    action: "Review escalation",
  },
};
