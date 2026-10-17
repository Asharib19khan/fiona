export const demoCashWeeks = [
  { week: 1, start: "2026-10-23", closing: 1_042_025_084 },
  { week: 2, start: "2026-10-30", closing: 838_497_683 },
  { week: 3, start: "2026-11-06", closing: 872_937_572 },
  { week: 4, start: "2026-11-13", closing: 849_063_643 },
  { week: 5, start: "2026-11-20", closing: 892_292_434 },
  { week: 6, start: "2026-11-27", closing: 634_124_439 },
  { week: 7, start: "2026-12-04", closing: -702_272_776 },
  { week: 8, start: "2026-12-11", closing: -813_777_144 },
  { week: 9, start: "2026-12-18", closing: -933_405_265 },
  { week: 10, start: "2026-12-25", closing: -988_781_973 },
  { week: 11, start: "2027-01-01", closing: -1_391_805_770 },
  { week: 12, start: "2027-01-08", closing: -1_528_661_262 },
  { week: 13, start: "2027-01-15", closing: -1_709_366_189 },
] as const;

export const demoFinanceSnapshot = {
  currency: "PKR",
  annualSalesMinor: 15_797_406_963,
  operatingCashProxyMinor: 556_095_249,
  existingDebtServiceMinor: 619_578_000,
  forwardDscrBp: 8_975,
  requestedMinor: 200_000_000,
  debtDscrBp: 7_509,
  debtDownsideDscrBp: 6_353,
  equityDilutionBp: 1_000,
  supplierCreditCostBp: 0,
  supplierCreditDays: 7,
} as const;

