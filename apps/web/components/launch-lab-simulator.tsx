"use client";

import { useState } from "react";
import { Card, EmptyState, MoneyText, OutcomeBadge } from "@fiona/ui";

type Json = Record<string, unknown>;

function obj(value: unknown): Json | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? (value as Json) : null;
}

function list(value: unknown): Json[] {
  return Array.isArray(value) ? value.map(obj).filter((item): item is Json => item !== null) : [];
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

const OUTCOME: Record<string, "approve" | "conditions" | "escalate" | "block"> = {
  LAUNCH: "approve",
  PILOT_FIRST: "conditions",
  REVISE: "escalate",
  HOLD: "escalate",
  NOT_RECOMMENDED: "block",
};

const UNITS: Record<string, string> = { units: "units", count: "", months: "months", days: "days" };

/** One engine Figure as text: money with its currency, basis points as a percentage, else value and unit. */
function FigureValue({ figure }: { figure: Json }) {
  const money = obj(figure.money);
  if (money && Number.isSafeInteger(money.minor)) {
    return <MoneyText amountMinor={money.minor as number} currency={String(money.currency ?? "")} animateCount={false} />;
  }
  if (typeof figure.value === "number") {
    if (figure.unit === "bp") return <>{(figure.value / 100).toFixed(1)}%</>;
    const unit = UNITS[String(figure.unit)] ?? String(figure.unit ?? "");
    return <>{figure.value.toLocaleString("en-GB")}{unit ? ` ${unit}` : ""}</>;
  }
  return <>Not available</>;
}

/** An engine code as words: "hard_rule_failed:LL-01" -> "Hard rule failed: LL-01", "20pct" -> "20%". */
function readable(code: string): string {
  const [head = "", ...rest] = code.split(":");
  const words = head.replaceAll("_", " ").replace(/(\d+)pct\b/g, "$1%").toLowerCase().replace(/^./, (c) => c.toUpperCase());
  return rest.length ? `${words}: ${rest.join(":")}` : words;
}

const ORIGIN: Record<string, string> = {
  user_provided: "You",
  ledger_derived: "Your ledger",
  market_observed: "Market data",
  rulebook: "Rulebook",
  engine_estimate: "Engine estimate",
  assumption_unverified: "Unverified default",
  draft_default: "Unverified default",
};

/**
 * Launch Lab: the owner states a product's costs, price and capital, plus a what-if; the engine
 * resolves the rest from the workspace's ledger (comparable products, lead times), runs the
 * Monte Carlo simulation and returns a labelled recommendation. Nothing here is computed in the
 * browser, and no order or commitment is created.
 */
export function LaunchLabSimulator({ currency }: { currency: string }) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [comparables, setComparables] = useState("");
  const [unitCost, setUnitCost] = useState("");
  const [price, setPrice] = useState("");
  const [capital, setCapital] = useState("");
  const [freight, setFreight] = useState("");
  const [packaging, setPackaging] = useState("");
  const [pricePct, setPricePct] = useState(0);
  const [demandPct, setDemandPct] = useState(0);
  const [costPct, setCostPct] = useState(0);
  const [marketing, setMarketing] = useState(1);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [result, setResult] = useState<Json | null>(null);

  const money = (text: string) => {
    const value = Number(text.replaceAll(",", ""));
    return Number.isFinite(value) && value > 0 ? { minor: Math.round(value * 100), currency } : null;
  };

  async function run(event: { preventDefault(): void }) {
    event.preventDefault();
    const cost = money(unitCost);
    const sell = money(price);
    if (!name.trim() || !category.trim()) return setProblem("Name the product and its category.");
    if (!cost || !sell) return setProblem("Enter a unit cost and a selling price above zero.");
    const plan: Json = {
      currency,
      product: {
        name: name.trim(),
        category: category.trim().toLowerCase(),
        comparable_skus: comparables.split(/[\s,]+/).map((sku) => sku.trim()).filter(Boolean).slice(0, 20),
      },
      unit_cost: cost,
      price: sell,
      what_ifs: [
        {
          name: "your_what_if",
          price_change_bp: pricePct * 100,
          demand_change_bp: demandPct * 100,
          unit_cost_change_bp: costPct * 100,
          marketing_multiplier_bp: Math.round(marketing * 10_000),
        },
      ],
    };
    const reserve = money(capital);
    if (reserve) plan.available_capital = reserve;
    // Blank means "let the engine assume"; zero is a real answer ("no freight").
    for (const [field, text] of [["freight_per_unit", freight], ["packaging_per_unit", packaging]] as const) {
      const value = Number(text.replaceAll(",", ""));
      if (text.trim() !== "" && Number.isFinite(value) && value >= 0) plan[field] = { minor: Math.round(value * 100), currency };
    }
    setBusy(true);
    setProblem(null);
    try {
      const res = await fetch("/api/fiona/launch-lab/simulate", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(plan),
      });
      const data = (await res.json().catch(() => ({}))) as Json;
      if (!res.ok) {
        const error = obj(data.error);
        setProblem(String(error?.message ?? "The engine could not run this simulation."));
        return;
      }
      setResult(data);
    } catch {
      setProblem("The engine did not answer. Try again in a moment.");
    } finally {
      setBusy(false);
    }
  }

  const recommendation = obj(result?.recommendation);
  const label = String(recommendation?.label ?? "");
  const simulation = obj(result?.simulation);
  const whatIf = list(result?.what_ifs)[0];
  const explain = obj(result?.explain);
  const gaps = list(result?.data_gaps);
  const inputs = list(result?.inputs);
  const unverified = inputs.filter((input) => input.origin === "assumption_unverified" || input.origin === "draft_default");
  const pct = (value: number) => (value >= 0 ? `+${value}%` : `${value}%`);

  return (
    <div className="launch-lab-interactive">
      <Card className="tier-panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">YOUR LAUNCH PLAN</span>
            <h2>What would you launch?</h2>
          </div>
          <span className="placeholder-tag">Amounts in {currency}</span>
        </div>
        <form onSubmit={run}>
          <div className="admin-form">
            <label><span className="spec-label">Product</span><input required maxLength={120} placeholder="e.g. Wool winter shawl" value={name} onChange={(e) => setName(e.target.value)} /></label>
            <label><span className="spec-label">Category</span><input required maxLength={60} placeholder="e.g. shawl" value={category} onChange={(e) => setCategory(e.target.value)} /></label>
            <label><span className="spec-label">Comparable SKUs (optional)</span><input maxLength={400} placeholder="SKUs from Inventory, comma separated" value={comparables} onChange={(e) => setComparables(e.target.value)} /></label>
            <label><span className="spec-label">Unit cost</span><input required inputMode="decimal" placeholder="0" value={unitCost} onChange={(e) => setUnitCost(e.target.value)} /></label>
            <label><span className="spec-label">Selling price</span><input required inputMode="decimal" placeholder="0" value={price} onChange={(e) => setPrice(e.target.value)} /></label>
            <label><span className="spec-label">Capital you can commit (optional)</span><input inputMode="decimal" placeholder="0" value={capital} onChange={(e) => setCapital(e.target.value)} /></label>
            <label><span className="spec-label">Freight per unit (optional)</span><input inputMode="decimal" placeholder="Engine assumes if blank" value={freight} onChange={(e) => setFreight(e.target.value)} /></label>
            <label><span className="spec-label">Packaging per unit (optional)</span><input inputMode="decimal" placeholder="Engine assumes if blank" value={packaging} onChange={(e) => setPackaging(e.target.value)} /></label>
          </div>

          <div className="simulator-controls-grid">
            <label className="slider-group">
              <div className="slider-label"><span>What if the price changes</span><strong>{pct(pricePct)}</strong></div>
              <input type="range" min="-30" max="50" step="5" value={pricePct} onChange={(e) => setPricePct(Number(e.target.value))} />
              <small className="footnote">Demand responds to price (elasticity applied by the engine).</small>
            </label>
            <label className="slider-group">
              <div className="slider-label"><span>What if demand changes</span><strong>{pct(demandPct)}</strong></div>
              <input type="range" min="-50" max="80" step="5" value={demandPct} onChange={(e) => setDemandPct(Number(e.target.value))} />
            </label>
            <label className="slider-group">
              <div className="slider-label"><span>What if unit cost changes</span><strong>{pct(costPct)}</strong></div>
              <input type="range" min="-20" max="40" step="5" value={costPct} onChange={(e) => setCostPct(Number(e.target.value))} />
            </label>
            <label className="slider-group">
              <div className="slider-label"><span>Marketing spend</span><strong>{marketing.toFixed(2)}×</strong></div>
              <input type="range" min="0.5" max="3" step="0.25" value={marketing} onChange={(e) => setMarketing(Number(e.target.value))} />
            </label>
          </div>

          <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Simulating…" : "Run the simulation"}</button>
          {problem && <p className="mandate-notice" role="alert">{problem}</p>}
        </form>
      </Card>

      {!result && !busy && (
        <EmptyState title="No simulation yet">Describe the product and run it. The engine fills the rest from your ledger and says what it had to assume.</EmptyState>
      )}

      {result && (
        <>
          <Card className="tier-panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">ENGINE RECOMMENDATION · {String(recommendation?.plan ?? "").toUpperCase()} PLAN</span>
                <h2>{readable(label || "No recommendation")}</h2>
              </div>
              {OUTCOME[label] && <OutcomeBadge outcome={OUTCOME[label]} />}
            </div>
            {strings(recommendation?.reason_codes).length > 0 && (
              <p className="proposal-reasoning">Why: {strings(recommendation?.reason_codes).map(readable).join(" · ")}</p>
            )}
            {strings(recommendation?.levers_that_fix).length > 0 && (
              <p className="proposal-reasoning">What would change it: {strings(recommendation?.levers_that_fix).map(readable).join(" · ")}</p>
            )}
          </Card>

          {unverified.length > 0 && (
            <p className="mandate-notice" role="status">
              The engine filled {unverified.length} value{unverified.length === 1 ? "" : "s"} you didn&apos;t give with unverified defaults ({unverified.map((input) => readable(String(input.name ?? ""))).join(", ")}). Check them below; enter your own freight and packaging above to replace the biggest ones.
            </p>
          )}

          <div className="tier-metric-grid">
            {list(result.headline).slice(0, 6).map((figure, index) => (
              <Card className="tier-metric" key={String(figure.metric_id ?? index)}>
                <span className="eyebrow">{String(figure.label ?? figure.metric_id)}</span>
                <strong><FigureValue figure={figure} /></strong>
                {typeof figure.formula === "string" && <small>{figure.formula}</small>}
              </Card>
            ))}
          </div>

          <div className="launch-sub-grid">
            <Card className="tier-panel">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">SIMULATION · {String(simulation?.runs ?? "—")} RUNS</span>
                  <h2>Odds (model-based, not calibrated)</h2>
                </div>
              </div>
              <div className="breakeven-stats-list">
                {list(simulation?.figures).map((figure, index) => (
                  <div className="breakeven-row" key={String(figure.metric_id ?? index)}>
                    <span>{String(figure.label ?? figure.metric_id)}</span>
                    <strong><FigureValue figure={figure} /></strong>
                  </div>
                ))}
                {whatIf && list(whatIf.figures).map((figure, index) => (
                  <div className="breakeven-row" key={`whatif-${String(figure.metric_id ?? index)}`}>
                    <span>Your what-if · {String(figure.label ?? figure.metric_id)}</span>
                    <strong><FigureValue figure={figure} /></strong>
                  </div>
                ))}
              </div>
            </Card>

            <Card className="tier-panel">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">LAUNCH RULES · RULEBOOK</span>
                  <h2>Checks behind the recommendation</h2>
                </div>
              </div>
              <ul className="rule-checklist">
                {list(recommendation?.rule_trace).map((rule, index) => (
                  <li key={String(rule.rule_id ?? index)} className={`rule-item ${rule.passed ? "passed" : "failed"}`}>
                    <span className="rule-icon" aria-hidden="true">{rule.passed ? "✓" : "×"}</span>
                    <div>
                      <strong>{String(rule.rule_id ?? "")} · {String(rule.description ?? "")}</strong>
                      <p>{rule.passed ? "Passed" : "Not met"}{rule.hard ? " · hard rule" : ""}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
          </div>

          <div className="launch-sub-grid">
            <Card className="tier-panel">
              <div className="panel-heading"><div><span className="eyebrow">PER UNIT</span><h2>Where each unit&apos;s cost comes from</h2></div></div>
              <div className="breakeven-stats-list">
                {list(result.cost_lines).map((figure, index) => (
                  <div className="breakeven-row" key={String(figure.metric_id ?? figure.label ?? index)}>
                    <span>{String(figure.label ?? figure.metric_id)}</span>
                    <strong><FigureValue figure={figure} /></strong>
                  </div>
                ))}
              </div>
            </Card>
            <Card className="tier-panel">
              <div className="panel-heading"><div><span className="eyebrow">INPUTS</span><h2>What the engine used, and where from</h2></div></div>
              <div className="breakeven-stats-list">
                {inputs.map((input, index) => {
                  const doubtful = input.origin === "assumption_unverified" || input.origin === "draft_default";
                  return (
                    <div className="breakeven-row" key={String(input.name ?? index)} title={String(input.basis ?? "")}>
                      <span>{readable(String(input.name ?? ""))} · <em className={doubtful ? "money-negative" : ""}>{ORIGIN[String(input.origin)] ?? readable(String(input.origin ?? ""))}</em></span>
                      <strong><FigureValue figure={input} /></strong>
                    </div>
                  );
                })}
              </div>
            </Card>
          </div>

          {explain && (
            <Card className="tier-panel">
              <div className="panel-heading"><div><span className="eyebrow">IN SHORT</span><h2>Risks and the best lever</h2></div></div>
              <div className="breakeven-stats-list">
                <div className="breakeven-row"><span>Biggest risks</span><strong>{strings(explain.main_risks).map(readable).join(", ") || "None ranked"}</strong></div>
                <div className="breakeven-row"><span>Best lever</span><strong>{explain.best_lever ? readable(String(explain.best_lever)) : "None found"}</strong></div>
                <div className="breakeven-row"><span>Safest first step</span><strong>{readable(String(explain.safest_test ?? ""))}</strong></div>
                {obj(explain.max_amount_at_risk) && (
                  <div className="breakeven-row"><span>{String(obj(explain.max_amount_at_risk)?.label ?? "Most at risk")}</span><strong><FigureValue figure={obj(explain.max_amount_at_risk)!} /></strong></div>
                )}
              </div>
            </Card>
          )}

          {gaps.length > 0 && (
            <Card className="tier-panel">
              <div className="panel-heading"><div><span className="eyebrow">DATA GAPS</span><h2>Answer these to sharpen the result</h2></div></div>
              <ul className="rule-checklist">
                {gaps.map((gap, index) => (
                  <li key={String(gap.field ?? index)} className={`rule-item ${gap.blocking ? "failed" : "passed"}`}>
                    <span className="rule-icon" aria-hidden="true">?</span>
                    <div><strong>{String(gap.question ?? gap.field)}</strong><p>{String(gap.impact ?? "")}{gap.blocking ? " · blocks a launch call" : ""}</p></div>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <p className="footnote">
            {strings(result.limitations).join(" ")} Advisory only: no order or commitment is created. Run {String(result.run_id ?? "")} · inputs {String(result.inputs_hash ?? "").slice(0, 12)} · as of {String(result.as_of ?? "")} · {String(result.mode ?? "")} mode.
          </p>
        </>
      )}
    </div>
  );
}
