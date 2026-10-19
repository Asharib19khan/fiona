import { objectValue, readEngine } from "@/lib/server-read";
import { parseFinding, type BriefingFinding } from "@/lib/briefing";

type Json = Record<string, unknown>;

export interface ForecastLine {
  category: string;
  direction: "in" | "out";
  minor: number;
  /** scheduled: a known bill, invoice or commitment; forecast: a statistical estimate. */
  basis: "scheduled" | "forecast";
  refs: string[];
}

export interface ForecastWeek {
  week: number;
  start: string;
  end: string;
  openingMinor: number;
  inflowsMinor: number;
  outflowsMinor: number;
  netMinor: number;
  closingMinor: number;
  lowMinor: number;
  highMinor: number;
  below: boolean;
  lines: ForecastLine[];
}

export interface ForecastNote {
  label: string;
  /** Money in minor units, or a plain value with its unit. */
  minor: number | null;
  value: number | null;
  unit: string;
  verified: boolean;
}

/** How the forecast scored against what actually happened (money, or a value such as basis points). */
export interface BacktestFigure {
  metricId: string;
  label: string;
  minor: number | null;
  value: number | null;
  unit: string;
}

export interface Forecast {
  asOf: string | null;
  currency: string;
  method: { name: string; description: string; band: string; history: { start: string; end: string } | null; backtest: BacktestFigure[] };
  openingMinor: number | null;
  bufferMinor: number;
  lowestMinor: number;
  lowestWeek: number | null;
  firstWeekBelow: number | null;
  shortfallMinor: number;
  receivablesMinor: number | null;
  payablesMinor: number | null;
  weeks: ForecastWeek[];
  assumptions: ForecastNote[];
  gaps: Array<{ need: string; why: string; blocking: boolean }>;
}

export type ForecastResult =
  | { kind: "ok"; forecast: Forecast; findings: BriefingFinding[]; findingsLoaded: boolean }
  | { kind: "unavailable" };

const obj = (v: unknown): Json | null => (v !== null && typeof v === "object" && !Array.isArray(v) ? (v as Json) : null);
const list = (v: unknown): Json[] => (Array.isArray(v) ? v.map(obj).filter((x): x is Json => x !== null) : []);
const str = (v: unknown): string => (typeof v === "string" ? v : "");
const minor = (v: unknown): number | null => {
  const m = obj(v);
  return m && Number.isSafeInteger(m.minor) ? (m.minor as number) : null;
};
const figureMinor = (v: unknown): number | null => minor(obj(v)?.money);

async function read(name: "forecast/cash" | "forecast/findings"): Promise<Json | null> {
  const result = await readEngine(name);
  return result.kind === "ok" && result.status === 200 ? objectValue(result.data) : null;
}

/** The 13-week cash forecast and its alert findings, as computed by the engine. Nothing is filled in locally. */
export async function getForecast(): Promise<ForecastResult> {
  const [cash, feed] = await Promise.all([read("forecast/cash"), read("forecast/findings")]);
  const buffer = figureMinor(cash?.buffer);
  const lowest = figureMinor(cash?.lowest_closing);
  if (!cash || buffer === null || lowest === null) return { kind: "unavailable" };

  const weeks: ForecastWeek[] = list(cash.weeks).map((w) => {
    const closing = minor(w.closing) ?? 0;
    return {
      week: Number(w.week),
      start: str(w.start),
      end: str(w.end),
      openingMinor: minor(w.opening) ?? 0,
      inflowsMinor: minor(w.inflows) ?? 0,
      outflowsMinor: minor(w.outflows) ?? 0,
      netMinor: minor(w.net) ?? 0,
      closingMinor: closing,
      lowMinor: minor(w.closing_low) ?? closing,
      highMinor: minor(w.closing_high) ?? closing,
      below: w.below_buffer === true,
      lines: list(w.lines).map((l) => ({
        category: str(l.category) || "other",
        direction: l.direction === "in" ? "in" : "out",
        minor: minor(l.money) ?? 0,
        basis: l.basis === "scheduled" ? "scheduled" : "forecast",
        refs: Array.isArray(l.refs) ? l.refs.filter((r): r is string => typeof r === "string") : [],
      })),
    };
  });

  const method = obj(cash.method);
  const history = obj(method?.history);
  const lowestWeek = weeks.length ? weeks.reduce((a, b) => (b.closingMinor < a.closingMinor ? b : a)).week : null;
  const now = new Date().toISOString();

  return {
    kind: "ok",
    forecast: {
      asOf: str(cash.as_of) || null,
      currency: str(cash.currency) || "PKR",
      method: {
        name: str(method?.name),
        description: str(method?.description),
        band: str(method?.band),
        history: history ? { start: str(history.start), end: str(history.end) } : null,
        backtest: list(method?.backtest).map((b) => ({
          metricId: str(b.metric_id),
          label: str(b.label) || str(b.metric_id),
          minor: minor(b.money),
          value: typeof b.value === "number" ? b.value : null,
          unit: str(b.unit),
        })),
      },
      openingMinor: figureMinor(cash.opening_balance),
      bufferMinor: buffer,
      lowestMinor: lowest,
      lowestWeek,
      firstWeekBelow: typeof cash.first_week_below_buffer === "number" ? cash.first_week_below_buffer : null,
      shortfallMinor: figureMinor(cash.shortfall) ?? Math.max(0, buffer - lowest),
      receivablesMinor: figureMinor(cash.open_receivables),
      payablesMinor: figureMinor(cash.open_payables),
      weeks,
      assumptions: list(cash.assumptions).map((a) => ({
        label: str(a.name).replace(/_/g, " "),
        minor: minor(a.money),
        value: typeof a.value === "number" ? a.value : null,
        unit: str(a.unit),
        verified: !str(a.origin).includes("unverified"),
      })),
      gaps: list(cash.insufficient_data).map((g) => ({ need: str(g.need), why: str(g.why), blocking: g.blocking === true })),
    },
    findings: list(feed?.findings).map((raw) => parseFinding(raw, now)).filter((f): f is BriefingFinding => f !== null).sort((a, b) => b.moneyMinor - a.moneyMinor),
    findingsLoaded: feed !== null,
  };
}
