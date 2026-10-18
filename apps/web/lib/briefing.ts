import { objectValue, readEngine, type EngineRead } from "@/lib/server-read";

type Json = Record<string, unknown>;

export interface BriefingFinding {
  id: string;
  source: string;
  severity: "low" | "medium" | "high" | "critical";
  title: string;
  detail: string | null;
  moneyMinor: number;
  createdAt: string;
  action: { label: string; route: string } | null;
}

export interface Briefing {
  asOf: string | null;
  currency: string;
  cash: {
    lowestMinor: number;
    bufferMinor: number;
    firstWeekBelow: number | null;
    shortfallMinor: number;
    weeks: Array<{ week: number; start: string; closingMinor: number; below: boolean }>;
  } | null;
  approvals: { waiting: number; waitingMinor: number; blocked: number } | null;
  stock: { atCostMinor: number; slowMinor: number | null } | null;
  findings: BriefingFinding[];
  /** Sources that could not be read; the page says so instead of showing stale numbers. */
  unavailable: string[];
}

const SEVERITIES = new Set(["low", "medium", "high", "critical"]);

function obj(value: unknown): Json | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? (value as Json) : null;
}

function list(value: unknown): Json[] {
  return Array.isArray(value) ? value.map(obj).filter((v): v is Json => v !== null) : [];
}

function minor(value: unknown): number | null {
  const money = obj(value);
  return money && Number.isSafeInteger(money.minor) ? (money.minor as number) : null;
}

function figureMinor(value: unknown): number | null {
  return minor(obj(value)?.money);
}

async function read(name: EngineRead, query?: Record<string, string>): Promise<Json | null> {
  const result = await readEngine(name, new URLSearchParams(query));
  return result.kind === "ok" && result.status === 200 ? objectValue(result.data) : null;
}

function finding(raw: Json, fallbackTime: string): BriefingFinding | null {
  const title = typeof raw.title === "string" ? raw.title : null;
  if (!title) return null;
  const action = list(raw.actions)[0];
  return {
    id: String(raw.id ?? title),
    source: String(raw.source ?? "engine"),
    severity: (SEVERITIES.has(String(raw.severity)) ? raw.severity : "medium") as BriefingFinding["severity"],
    title,
    detail: typeof raw.detail === "string" ? raw.detail : null,
    moneyMinor: minor(raw.money_at_stake) ?? 0,
    createdAt: typeof raw.created_at === "string" ? raw.created_at : fallbackTime,
    action: action && typeof action.route === "string" ? { label: String(action.label ?? "Open"), route: action.route } : null,
  };
}

/** Everything the briefing shows, computed by the engine from the posted ledger. */
export async function getBriefing(): Promise<Briefing> {
  // The lifecycle stage is left to the Analysis page: it reads the whole ledger (seconds).
  const [forecast, feed, reconcile, proposals, inventory] = await Promise.all([
    read("forecast/cash"),
    read("forecast/findings"),
    read("reconcile/findings", { limit: "4" }),
    read("proposals"),
    read("inventory/analysis"),
  ]);
  const unavailable: string[] = [];
  const now = new Date().toISOString();

  let cash: Briefing["cash"] = null;
  const lowest = figureMinor(forecast?.lowest_closing);
  const buffer = figureMinor(forecast?.buffer);
  if (forecast && lowest !== null && buffer !== null) {
    cash = {
      lowestMinor: lowest,
      bufferMinor: buffer,
      firstWeekBelow: typeof forecast.first_week_below_buffer === "number" ? forecast.first_week_below_buffer : null,
      shortfallMinor: Math.max(0, buffer - lowest),
      weeks: list(forecast.weeks).map((w) => ({
        week: Number(w.week),
        start: String(w.start),
        closingMinor: minor(w.closing) ?? 0,
        below: w.below_buffer === true,
      })),
    };
  } else unavailable.push("cash forecast");

  let approvals: Briefing["approvals"] = null;
  if (proposals) {
    const all = list(proposals.proposals);
    const waiting = all.filter((p) => p.status === "needs_owner");
    approvals = {
      waiting: waiting.length,
      waitingMinor: waiting.reduce((sum, p) => sum + (minor(p.amount) ?? 0), 0),
      blocked: all.filter((p) => p.status === "blocked").length,
    };
  } else unavailable.push("approvals");

  let stock: Briefing["stock"] = null;
  if (inventory) {
    const summary = list(inventory.summary);
    const pick = (id: string) => figureMinor(summary.find((f) => f.metric_id === id));
    const atCost = pick("inventory.stock_value");
    if (atCost !== null) stock = { atCostMinor: atCost, slowMinor: pick("inventory.slow_stock_value") };
  }
  if (!stock) unavailable.push("inventory");


  // At most two findings per source, so one engine (say, many slow-stock lines) cannot crowd out the rest.
  const perSource = new Map<string, number>();
  const findings = [...list(feed?.findings), ...list(reconcile?.findings)]
    .map((raw) => finding(raw, now))
    .filter((f): f is BriefingFinding => f !== null)
    .sort((a, b) => b.moneyMinor - a.moneyMinor)
    .filter((f) => {
      const seen = perSource.get(f.source) ?? 0;
      perSource.set(f.source, seen + 1);
      return seen < 2;
    })
    .slice(0, 6);
  if (!feed) unavailable.push("findings");

  return {
    asOf: typeof forecast?.as_of === "string" ? forecast.as_of : null,
    currency: typeof forecast?.currency === "string" ? forecast.currency : "PKR",
    cash,
    approvals,
    stock,
    findings,
    unavailable,
  };
}
