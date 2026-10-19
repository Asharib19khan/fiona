/**
 * Engine figures carry rates in basis points. Margins, returns and costs read as percentages;
 * ratios and cover figures (current ratio, debt-service cover) read as multiples.
 */
const MULTIPLE = /(current_ratio|quick_ratio|cash_ratio|coverage|dscr|capex_to_depreciation)/;

export function basisPointsText(value: number, metricId: string): string {
  return MULTIPLE.test(metricId) ? `${(value / 10_000).toFixed(2)}×` : `${(value / 100).toFixed(2)}%`;
}
