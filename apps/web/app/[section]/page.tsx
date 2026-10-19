import Link from "next/link";
import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import {
  Card,
  DegradedBanner,
  EmptyState,
  MoneyText,
  OutcomeBadge,
  ProvenancePopover,
  StateChip,
} from "@fiona/ui";
import { postEngine, readEngine, objectValue, type EngineRead } from "@/lib/server-read";
import { routes } from "@/lib/routes";
import { ImportPreview } from "@/components/import-preview";
import { BillIntake } from "@/components/bill-intake";
import { ProposalInbox } from "@/components/proposal-inbox";
import { CouncilRoom } from "@/components/council-room";
import { ReconcileRunner } from "@/components/reconcile-runner";
import { InventoryView, type InventoryItemData, type InventorySummaryData } from "@/components/inventory-view";
import { LaunchLabSimulator } from "@/components/launch-lab-simulator";
import { getWorkspaceSession } from "@/lib/session";
import { workspaceCurrency } from "@/lib/workspaces";
import { basisPointsText } from "@/lib/figure-format";

type JsonObject = Record<string, unknown>;

function object(value: unknown): JsonObject | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonObject)
    : null;
}

function objects(value: unknown): JsonObject[] {
  return Array.isArray(value) ? value.map(object).filter((item): item is JsonObject => item !== null) : [];
}

function minor(value: unknown): number | null {
  const money = object(value);
  return money && Number.isSafeInteger(money.minor) ? (money.minor as number) : null;
}

function figureMinor(value: unknown): number | null {
  const figure = object(value);
  return figure ? minor(figure.money) : null;
}

function figureValue(value: unknown): number | null {
  const figure = object(value);
  return figure && Number.isSafeInteger(figure.value) ? (figure.value as number) : null;
}

async function engineData(name: EngineRead): Promise<JsonObject | null> {
  const result = await readEngine(name);
  return result.kind === "ok" && result.status === 200 ? objectValue(result.data) : null;
}

function Heading({ section, badge }: { section: keyof typeof routes; badge?: string }) {
  const page = routes[section];
  return <><div className="page-kicker">{badge && <StateChip>{badge}</StateChip>}</div><header className="page-heading"><div><h1>{page.label}</h1><p>{page.description}</p></div></header></>;
}

function DataSource({ connected, fallback }: { connected: boolean; fallback: string }) {
  return (
    connected ? (
      <div className="data-note">
        <span aria-hidden="true">●</span>
        <span><strong>Computed from your ledger</strong> · Read live from the engine.</span>
      </div>
    ) : (
      <DegradedBanner>{fallback || "The engine did not answer, so this page shows no figures."}</DegradedBanner>
    )
  );
}

function Metric({ label, amount, value, unit, note }: { label: string; amount?: number | null; value?: number | string | null; unit?: string; note?: string }) {
  return <Card className="tier-metric"><span className="eyebrow">{label}</span><strong>{amount !== undefined && amount !== null ? <MoneyText amountMinor={amount} /> : value !== undefined && value !== null ? `${value}${unit ?? ""}` : "Not available"}</strong>{note && <small>{note}</small>}</Card>;
}

function Table({ headers, rows, empty }: { headers: string[]; rows: Array<Array<ReactNode>>; empty: string }) {
  if (!rows.length) return <EmptyState title="No records to show">{empty}</EmptyState>;
  return <div className="data-table-wrap"><table className="data-table"><thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>)}</tbody></table></div>;
}

async function ForecastScreenBase() {
  const data = await engineData("forecast/cash");
  const connectedWeeks = objects(data?.weeks);
  if (!data) return <div className="section-page"><Heading section="forecast" /><DataSource connected={false} fallback="The cash forecast could not be computed right now (the engine did not answer). No figures are shown rather than old ones." /></div>;
  const weeks = connectedWeeks.length ? connectedWeeks.map((week) => ({
    week: typeof week.week === "number" ? week.week : 0,
    start: typeof week.start === "string" ? week.start : "—",
    inflows: minor(week.inflows) ?? 0,
    outflows: minor(week.outflows) ?? 0,
    closing: minor(week.closing) ?? 0,
    below: week.below_buffer === true,
    connected: true,
  })) : [];
  const buffer = figureMinor(data?.buffer) ?? 200_000_000;
  const lowest = figureMinor(data?.lowest_closing) ?? Math.min(...weeks.map((week) => week.closing));
  const firstBelow = typeof data?.first_week_below_buffer === "number" ? data.first_week_below_buffer : weeks.find((week) => week.closing < buffer)?.week ?? null;
  const rows = weeks.map((week, index) => {
    const closing = <span className={week.closing < buffer ? "money-negative" : ""}><MoneyText amountMinor={week.closing} /></span>;
    const bufferStatus = week.closing < buffer ? <span className="status-text status-warning">Below buffer</span> : <span className="status-text status-positive">Within buffer</span>;
    if (week.connected) return [
      `Week ${week.week}`, week.start,
      <MoneyText amountMinor={week.inflows} key="in" />,
      <MoneyText amountMinor={week.outflows} key="out" />,
      closing, bufferStatus,
    ];
    const previousClose = index === 0 ? 953_352_992 : (weeks[index - 1]?.closing ?? 953_352_992);
    return [`Week ${week.week}`, week.start, <MoneyText amountMinor={week.closing - previousClose} key="net" />, closing, bufferStatus];
  });
  return <div className="section-page"><Heading section="forecast" badge="Computed from your ledger" /><DataSource connected fallback="" />
    <div className="tier-metric-grid"><Metric label="Lowest forecast close" amount={lowest} note="13-week view" /><Metric label="Owner cash buffer" amount={buffer} note="Tenant policy" /><Metric label="First buffer breach" value={firstBelow ? `Week ${firstBelow}` : "None"} note="Forecast alert" /></div>
    <Card className="tier-panel"><div className="panel-heading"><div><span className="eyebrow">WEEKLY CASH PATH</span><h2>Closing balance and buffer check</h2></div><span className="placeholder-tag">PKR · minor units</span></div><Table headers={data ? ["Period", "Starting", "Inflows", "Outflows", "Closing", "Buffer check"] : ["Period", "Net movement", "Closing", "Buffer check"]} rows={rows} empty="The engine returned no forecast weeks." /></Card>
    <p className="footnote">Forecasts are decision support, computed from your posted ledger: last year&rsquo;s seasonal pattern scaled to recent trading, plus the bills, invoices and loan payments already due. The page does not schedule a payment.</p>
  </div>;
}

async function ForecastScreen() {
  const [base, findingData] = await Promise.all([ForecastScreenBase(), engineData("forecast/findings")]);
  const findings = objects(findingData?.findings);
  return <>{base}<Card className="tier-panel"><div className="panel-heading"><div><span className="eyebrow">RANKED ALERTS</span><h2>Findings by money at stake</h2></div><span className="placeholder-tag">{findingData ? "Engine feed" : "No feed"}</span></div>{findings.length ? <div className="option-list">{findings.map((finding, index) => <article className="option-row" key={String(finding.id ?? index)}><div><span className="eyebrow">{String(finding.source ?? "forecast")} · {String(finding.severity ?? "")}</span><h3>{String(finding.title ?? "Cash-flow finding")}</h3><p>{String(finding.detail ?? "")}</p></div><div className="option-facts"><strong><MoneyText amountMinor={minor(finding.money_at_stake) ?? 0} /></strong>{objects(finding.actions).map((action, actionIndex) => <Link className="text-link" href={String(action.route ?? "/forecast")} key={actionIndex}>{String(action.label ?? "Review finding")}</Link>)}</div></article>)}</div> : <EmptyState title="No engine findings loaded">The ranked findings feed appears when the local engine and fixture data are available.</EmptyState>}</Card></>;
}

async function AnalysisScreen() {
  const [stageData, ratioData, healthData] = await Promise.all([engineData("stage"), engineData("analysis/ratios"), engineData("analysis/health")]);
  const stage = object(stageData?.result);
  const health = object(healthData?.result);
  const ratioFigures = objects(ratioData?.figures);
  const healthDimensions = object(health?.dimensions) ?? {};
  const rows = ratioFigures.map((figure) => {
    const shown = figure.money ? <MoneyText amountMinor={minor(figure.money) ?? 0} /> : figure.value !== undefined ? (figure.unit === "bp" && typeof figure.value === "number" ? basisPointsText(figure.value, String(figure.metric_id ?? "")) : `${String(figure.value)} ${String(figure.unit ?? "")}`) : figure.status === "insufficient_data" ? "Insufficient data" : "—";
    return [String(figure.label ?? figure.metric_id ?? "Metric"), shown, String(figure.status ?? "ok"), <ProvenancePopover key={String(figure.metric_id)} sourceRefs={Array.isArray(figure.source_refs) ? figure.source_refs.slice(0, 12).map(String) : []} total={Array.isArray(figure.source_refs) ? figure.source_refs.length : 0} />];
  });
  const stageName = typeof stage?.stage === "string" ? stage.stage.replaceAll("_", " ") : null;
  return <div className="section-page"><Heading section="analysis" badge={stageData ? "Computed from your ledger" : "Unavailable"} /><DataSource connected={Boolean(stageData && ratioData && healthData)} fallback="The analysis could not be computed right now (the engine did not answer). No figures are shown rather than old ones." />
    <div className="tier-metric-grid"><Metric label="Lifecycle stage" value={stageName ?? "Not loaded"} note={stageName ? `${String(stage?.confidence ?? "")} confidence` : "Load the ledger to classify the stage."} /><Metric label="Overall health band" value={String(health?.overall ?? "Not loaded")} note="Categorical health band; no composite score." /><Metric label="Figures computed" value={ratioFigures.length || "None"} unit={ratioFigures.length ? " figures" : ""} note="Every engine figure has source references." /></div>
    <Card className="tier-panel"><div className="panel-heading"><div><span className="eyebrow">FINANCIAL INDICATORS</span><h2>Ratios and source trail</h2></div><span className="placeholder-tag">No composite health score</span></div>
      <Table headers={["Metric", "Value", "Status", "Sources"]} rows={rows} empty="The ratios could not be computed right now (the engine did not answer)." />
    </Card>
    <Card className="tier-panel"><div className="panel-heading"><div><span className="eyebrow">HEALTH BANDS</span><h2>By financial dimension</h2></div></div><div className="band-grid">{Object.entries(healthDimensions).map(([name, raw]) => { const dimension = object(raw); return <div className="band-card" key={name}><span className="eyebrow">{name.replaceAll("_", " ")}</span><strong>{String(dimension?.band ?? "not available")}</strong><p>{Array.isArray(dimension?.reasons) ? dimension.reasons.join(" ") : ""}</p></div>; })}{!Object.keys(healthDimensions).length && <EmptyState title="Health bands not loaded">Connect the local read-only engine to view the bands calculated from posted journal lines.</EmptyState>}</div></Card>
    <p className="footnote">Prototype accounting: cost of sales at item cost, no depreciation run and no monthly sales-tax offset yet, so ratios are indicative, not audited.</p>
  </div>;
}


async function FinancingLiveScreen() {
  // The amount to finance is the forecast's own largest shortfall against the cash buffer. Facts
  // the engine doesn't hold (valuation, supplier terms) are left out; the matcher names them as
  // missing instead of the page inventing them.
  const forecast = await engineData("forecast/cash");
  const lowest = figureMinor(forecast?.lowest_closing);
  const buffer = figureMinor(forecast?.buffer);
  const currency = typeof forecast?.currency === "string" ? forecast.currency : null;
  if (lowest === null || buffer === null || !currency) {
    return <div className="section-page"><Heading section="financing" /><DataSource connected={false} fallback="The cash forecast did not load, so there is no shortfall to finance yet." /></div>;
  }
  const requestedMinor = Math.max(0, buffer - lowest);
  if (requestedMinor === 0) {
    return <div className="section-page"><Heading section="financing" badge="Computed from your ledger" /><EmptyState title="Nothing to finance">Your 13-week cash forecast stays above your buffer, so there is no shortfall to fund.</EmptyState></div>;
  }
  const result = await postEngine("financing/match", {
    amount: { minor: requestedMinor, currency },
    purpose: "working_capital_seasonal",
  });
  const data = result.kind === "ok" && result.status === 200 ? objectValue(result.data) : null;
  if (!data) return <div className="section-page"><Heading section="financing" /><DataSource connected={false} fallback={result.kind === "unavailable" ? result.message : "The financing matcher could not run right now."} /></div>;
  const options = objects(data?.options);
  const figures = objects(data?.business_figures);
  const proxy = figures.find((figure) => String(figure.note ?? "").toLowerCase().includes("proxy"));
  const detail = (values: unknown) => objects(values).map((figure, index) => {
    const label = String(figure.label ?? figure.metric_id ?? `Metric ${index + 1}`);
    const amount = minor(figure.money);
    const unit = String(figure.unit ?? "");
    const value = figureValue(figure);
    const text = amount !== null
      ? <MoneyText amountMinor={amount} currency={String(object(figure.money)?.currency ?? currency)} />
      : value !== null
        ? unit === "bp"
          ? basisPointsText(value, String(figure.metric_id ?? ""))
          : `${value.toLocaleString("en-GB")}${unit ? ` ${unit}` : ""}`
        : "Insufficient data";
    return <div className="band-card" key={String(figure.metric_id ?? index)}><span className="eyebrow">{label}</span><strong>{text}</strong><p>{Array.isArray(figure.source_refs) ? figure.source_refs.map(String).join(" · ") : String(figure.status ?? "")}</p></div>;
  });
  const unavailable = result.kind === "unavailable" ? result.message : "Start the local engine and fixture database to load the matcher response.";
  return <div className="section-page"><Heading section="financing" badge="Computed from your ledger" /><DataSource connected={Boolean(data)} fallback={unavailable} />
    {proxy && <DegradedBanner><strong>Proxy used for EBITDA.</strong> {String(proxy.label ?? "EBITDA")} is estimated from operating cash flow, not audited EBITDA ({String(proxy.note ?? "")}). It feeds debt-service cover and therefore the ranking below; treat the ranking as indicative until real EBITDA is available.</DegradedBanner>}
    <div className="tier-metric-grid"><Metric label="Funding request" amount={minor(data?.amount) ?? requestedMinor} note="Your forecast's largest shortfall below the buffer" /><Metric label="Snapshot date" value={String(data?.as_of ?? "Not loaded")} note="Fixture as-of date" /><Metric label="Eligible options" value={options.filter((option) => option.eligible === true).length} note="Catalogue and known business facts" /></div>
    <Card className="tier-panel"><div className="panel-heading"><div><span className="eyebrow">MATCHED OPTIONS</span><h2>Compare cost, coverage and conditions</h2></div><span className="placeholder-tag">Each option carries its source</span></div>
      {options.length ? <div className="option-list">{options.map((option, index) => <article className="option-row" key={String(option.option_id ?? index)}><div><span className="eyebrow">{String(option.provider_label ?? option.kind ?? "Catalogue option")} · {option.illustrative === true ? "Illustrative" : "Catalogue"}</span><h3>{String(option.name ?? option.option_id)}</h3><p>{Array.isArray(option.rank_reasons) ? option.rank_reasons.map(String).join(" · ") : ""}</p><p className="footnote">{String(option.source_ref ?? "")}</p></div><div className="option-facts"><strong>{String(option.outcome ?? "needs_information").replaceAll("_", " ")}{typeof option.rank === "number" ? ` · rank ${option.rank}` : ""}</strong><span>{option.eligible === true ? "Eligible" : option.eligible === false ? "Ineligible" : "Needs more information"}</span><div className="band-grid">{detail(option.figures)}</div></div></article>)}</div> : <EmptyState title="No matcher response">{data ? "The matcher returned no options." : unavailable}</EmptyState>}
    </Card><Card className="tier-panel"><div className="panel-heading"><div><span className="eyebrow">BUSINESS INPUTS</span><h2>Figures used in the comparison</h2></div></div><div className="band-grid">{detail(figures)}</div><p className="proposal-reasoning">Missing inputs are surfaced by the matcher; an operating-cash-flow proxy is not treated as approved EBITDA.</p></Card>
  </div>;
}

function CouncilScreen() {
  return (
    <div className="section-page">
      <Heading section="council" badge="Advice only" />
      <CouncilRoom />
    </div>
  );
}


/** The business date `days` ago, as YYYY-MM-DD (the demo dataset pins "today" with FIONA_NOW). */
function daysBeforeToday(days: number): string {
  const today = process.env.FIONA_NOW ? new Date(process.env.FIONA_NOW) : new Date();
  return new Date(today.getTime() - days * 86_400_000).toISOString().slice(0, 10);
}

async function BillsScreen() {
  const since = daysBeforeToday(60);
  const read = await readEngine("ledger/events", new URLSearchParams({ type: "purchase_bill", date_from: since, limit: "1000" }));
  const data = read.kind === "ok" && read.status === 200 ? objectValue(read.data) : null;
  if (!data) return <div className="section-page"><Heading section="bills" /><DataSource connected={false} fallback="The engine did not answer, so no bills are shown. Try again in a moment." /></div>;
  const bills = objects(data?.events).filter((event) => event.event === "purchase_bill").reverse();
  const sampleBillId = typeof bills[0]?.bill_id === "string" ? bills[0].bill_id : null;
  const checkResult = sampleBillId ? await postEngine("bills/check", { bill_id: sampleBillId }) : null;
  const checkData = checkResult?.kind === "ok" && checkResult.status === 200 ? objectValue(checkResult.data) : null;
  const check = object(checkData?.check);
  const checkOutcome = typeof check?.outcome === "string" ? check.outcome : null;
  const rows = bills.slice(0, 50).map((bill) => [
    String(bill.bill_id ?? "—"),
    String(bill.number ?? "—"),
    String(bill.date ?? "—"),
    String(bill.party ?? bill.party_id ?? "—"),
    <MoneyText key="amount" amountMinor={typeof bill.total_minor === "number" ? bill.total_minor : 0} />,
  ]);
  const detail = checkResult?.kind === "unavailable" ? checkResult.message : "Import synthetic bills to the local ledger to run the duplicate check.";
  return <div className="section-page"><Heading section="bills" badge="Ledger" /><DataSource connected={Boolean(data)} fallback="" /><BillIntake />
    <div className="tier-metric-grid"><Metric label="Bills in the last 60 days" value={data.next_offset ? `${bills.length}+` : bills.length} note={`Posted since ${since}`} /><Metric label="Duplicate check" value={checkOutcome ? checkOutcome.replaceAll("_", " ") : "Not run"} note="G-05 on the newest bill · read only" /><Metric label="New bills" value="Read, then confirmed" note="Claude transcribes with quotes; code checks them; you confirm before anything is posted." /></div>
    {check && <Card className="tier-panel"><div className="panel-heading"><div><span className="eyebrow">GUARDIAN DUPLICATE CHECK</span><h2>G-05 · {String(checkOutcome ?? "check")}</h2></div>{checkOutcome && <OutcomeBadge outcome={checkOutcome === "approve_with_conditions" ? "conditions" : (checkOutcome as "approve" | "escalate" | "block" | "conditions")} />}</div><p className="proposal-reasoning">{String(check.detail ?? "")}</p></Card>}
    {!check && <DegradedBanner>{detail}</DegradedBanner>}
    <Card className="tier-panel"><div className="panel-heading"><div><span className="eyebrow">IMPORTED BILL REGISTER</span><h2>Newest bills in the ledger</h2></div><span className="placeholder-tag">{bills.length > 50 ? "Latest 50 shown" : "Read only"}</span></div><Table headers={["Bill ID", "Supplier number", "Received", "Supplier", "Total"]} rows={rows} empty="No imported bill events are available." /></Card>
    <p className="footnote">Bill records remain source data. This screen does not approve a bill or issue a payment.</p>
  </div>;
}

async function ReconcileScreen() {
  const [matchesData, findingsData] = await Promise.all([engineData("reconcile/matches"), engineData("reconcile/findings")]);
  const matches = objects(matchesData?.matches);
  const findings = objects(findingsData?.findings);
  const rows = matches.map((match) => [String(match.bank_line_id ?? "—"), String(match.pass_name ?? "—"), `${Math.round(Number(match.confidence ?? 0) * 100)}%`, String(match.status ?? "—"), Array.isArray(match.event_ids) ? match.event_ids.join(", ") : "—"]);
  return <div className="section-page"><Heading section="reconcile" badge={matchesData ? "Ledger · read only" : "Synthetic preview"} /><DataSource connected={Boolean(matchesData)} fallback="No seeded ledger response is available; the page does not invent reconciliation counts." />
    <div className="tier-metric-grid"><Metric label="Saved matches" value={matches.length} note="From the ledger endpoint" /><Metric label="Open findings" value={findings.length} note="Ranked by money at stake" /><Metric label="Posting behavior" value="Proposals only" note="Matches remain proposals until reviewed." /></div>
    <Card className="tier-panel"><div className="panel-heading"><div><span className="eyebrow">MATCH REGISTER</span><h2>Bank lines and linked events</h2></div><span className="placeholder-tag">Review before posting</span></div><ReconcileRunner enabled /><Table headers={["Bank line", "Pass", "Confidence", "Review status", "Linked events"]} rows={rows} empty="No match response is available. Run the local engine with the seeded database to load it." /></Card>
    <Card className="tier-panel"><div className="panel-heading"><div><span className="eyebrow">NEEDS REVIEW</span><h2>Unmatched bank-line findings</h2></div></div>{findings.length ? <div className="option-list">{findings.map((finding, index) => <article className="option-row" key={String(finding.id ?? index)}><div><h3>{String(finding.title ?? finding.metric_id ?? "Reconciliation finding")}</h3><p>{String(finding.detail ?? finding.note ?? "Review the source bank line and candidate ledger events.")}</p></div>{minor(finding.money_at_stake) !== null && <strong><MoneyText amountMinor={minor(finding.money_at_stake) ?? 0} /></strong>}</article>)}</div> : <EmptyState title="No live findings loaded">A match decision must remain reviewable. This page has no action that posts ledger events.</EmptyState>}</Card>
  </div>;
}

async function AuditScreen() {
  const data = await engineData("audit");
  const records = objects(data?.records);
  const verified = data?.verified === true;
  const rows = records.slice(-20).reverse().map((item) => [String(item.seq ?? "—"), String(item.recorded_at ?? "—"), String(item.proposal_id ?? "—"), String(item.hash ?? "—").slice(0, 16) + "…"]);
  return <div className="section-page"><Heading section="audit" badge={data ? "Ledger · read only" : "Replay preview"} /><DataSource connected={Boolean(data)} fallback="The sample timeline is not an audit-chain export." />
    <div className="tier-metric-grid"><Metric label="Chain verification" value={data ? (verified ? "Verified" : "Failed") : "Not checked"} note={data?.first_bad_seq ? `First invalid entry: ${String(data.first_bad_seq)}` : "Read-only verification"} /><Metric label="Entries" value={typeof data?.chain_length === "number" ? data.chain_length : "None"} note="Full tenant chain length" /><Metric label="Payment mode" value="SIMULATED" note="No bank rails are connected." /></div>
    <Card className="tier-panel"><div className="panel-heading"><div><span className="eyebrow">HASH-CHAIN ENTRIES</span><h2>Latest recorded operations</h2></div><span className={`placeholder-tag ${verified ? "tag-positive" : ""}`}>{data ? (verified ? "VERIFIED" : "CHECK FAILED") : "NOT CONNECTED"}</span></div><Table headers={["Sequence", "Recorded at", "Proposal", "Entry hash"]} rows={rows} empty="Connect the local mock engine with the seeded database to inspect verified audit entries." /></Card>
    {data && <a className="button button-secondary" href="/api/fiona/audit/export" download>Download execution evidence</a>}
    <p className="footnote">The wallet API itself is not called from this read-only screen. A replay marker is not evidence that an operation occurred.</p>
  </div>;
}


async function InventoryScreen() {
  const data = await engineData("inventory/analysis");
  if (!data) {
    return <div className="section-page"><Heading section="inventory" /><DataSource connected={false} fallback="The engine did not answer, so no inventory figures are shown." /></div>;
  }
  const connectedItems = objects(data?.items);
  const items: InventoryItemData[] = connectedItems.length
    ? connectedItems.map((item) => ({
        sku: String(item.sku ?? "—"),
        name: String(item.name ?? "—"),
        category: String(item.category ?? "all"),
        season: String(item.season ?? "all"),
        on_hand: typeof item.on_hand === "number" ? item.on_hand : 0,
        unit_cost_minor: minor(item.unit_cost) ?? 0,
        price_minor: minor(item.price) ?? 0,
        stock_value_minor: minor(item.stock_value) ?? 0,
        units_sold_window: typeof item.units_sold_window === "number" ? item.units_sold_window : 0,
        revenue_minor: minor(item.revenue_window) ?? 0,
        gross_margin_bp: typeof item.gross_margin_bp === "number" ? item.gross_margin_bp : 0,
        abc: (item.abc === "A" || item.abc === "B" || item.abc === "C" ? item.abc : "B") as "A" | "B" | "C",
        xyz: (item.xyz === "X" || item.xyz === "Y" || item.xyz === "Z" ? item.xyz : "Y") as "X" | "Y" | "Z",
        movement: (item.movement === "fast" || item.movement === "normal" || item.movement === "slow" || item.movement === "dead" ? item.movement : "normal") as "fast" | "normal" | "slow" | "dead",
        days_of_cover: typeof item.days_of_cover === "number" ? item.days_of_cover : 0,
        reorder_point: typeof item.reorder_point === "number" ? item.reorder_point : 0,
        suggested_order_qty: typeof item.suggested_order_qty === "number" ? item.suggested_order_qty : 0,
        lead_time_days: typeof item.lead_time_days === "number" ? item.lead_time_days : 7,
        safety_stock: typeof item.safety_stock === "number" ? item.safety_stock : 0,
      }))
    : [];

  const summaryData = objects(data?.summary);
  const stockVal = summaryData.find((s) => s.metric_id === "inventory.stock_value");
  const deadVal = summaryData.find((s) => s.metric_id === "inventory.dead_stock_value");
  const slowVal = summaryData.find((s) => s.metric_id === "inventory.slow_stock_value");
  const gmroiFig = summaryData.find((s) => s.metric_id === "inventory.gmroi");

  const summary: InventorySummaryData = {
    stock_value_minor: minor(stockVal?.money) ?? 0,
    dead_stock_value_minor: minor(deadVal?.money) ?? 0,
    slow_stock_value_minor: minor(slowVal?.money) ?? 0,
    sku_count: items.length,
    gmroi_bp: figureValue(gmroiFig) ?? 0,
  };

  return (
    <div className="section-page">
      <Heading section="inventory" badge="Engine · read only" />
      <DataSource connected fallback="" />
      <InventoryView summary={summary} items={items} />
      <p className="footnote">
        Inventory movement analytics are decision support. Draft reorder suggestions do not automatically dispatch purchase orders or commit cash.
      </p>
    </div>
  );
}

async function LaunchLabScreen() {
  const session = await getWorkspaceSession();
  const currency = workspaceCurrency(session?.tenantId ?? null);
  return (
    <div className="section-page">
      <Heading section="launch-lab" badge="Engine · Monte Carlo" />
      {currency ? (
        <>
          <div className="data-note">
            <span aria-hidden="true">●</span>
            <span><strong>Run by the engine</strong> · Your costs and price, plus comparable products and lead times from your ledger. The odds come from a simulation of these assumptions.</span>
          </div>
          <LaunchLabSimulator currency={currency} />
        </>
      ) : (
        <DegradedBanner>Sign in to a registered workspace to run a launch simulation.</DegradedBanner>
      )}
    </div>
  );
}

async function WalletScreen() {
  const [audit, mandates] = await Promise.all([engineData("audit"), engineData("mandates")]);
  const payments = objects(audit?.records)
    .map((entry): JsonObject => ({ ...(object(entry.record) ?? {}), seq: entry.seq }))
    .filter((record) => record.action === "payment_executed" || record.action === "payment_refused")
    .reverse();
  const executed = payments.filter((record) => record.action === "payment_executed");
  const treasurer = objects(mandates?.mandates).find((mandate) => mandate.agent === "treasurer") ?? null;
  const verified = audit?.verified === true;
  const rows = payments.slice(0, 25).map((record) => {
    const paid = record.action === "payment_executed";
    return [
      String(record.at ?? "—").replace("T", " ").slice(0, 16),
      String(record.payee_id ?? "—"),
      typeof record.amount_minor === "number" ? <MoneyText amountMinor={record.amount_minor} currency={String(record.currency ?? "")} animateCount={false} /> : "—",
      <span key="result" className={`outcome-badge ${paid ? "outcome-approve" : "outcome-block"}`}><span aria-hidden="true">{paid ? "✓" : "×"}</span>{paid ? "Paid" : "Refused"}</span>,
      paid ? `Wallet ref ${String(record.wallet_ref ?? "—")} · verdict ${String(record.verdict_hash ?? "").slice(0, 10)}…` : String(record.reason ?? "Refused"),
      record.proposal_id ? <Link className="text-link" href={`/proposals/${String(record.proposal_id)}`}>{String(record.proposal_id)}</Link> : "—",
    ];
  });
  return (
    <div className="section-page">
      <Heading section="wallet" badge="Simulated wallet · no real money moves" />
      <DataSource connected={Boolean(audit)} fallback="The engine did not answer, so no wallet activity is shown." />
      {audit && (
        <>
          <div className="tier-metric-grid">
            <Metric label="Payments made" value={executed.length} note="Simulated; each one is a posted ledger event" />
            <Metric label="Attempts refused" value={payments.length - executed.length} note="Every refusal is recorded with its reason" />
            <Metric label="Audit chain" value={verified ? "Verified" : "Check failed"} note={`${String(audit.chain_length ?? 0)} hash-chained entries`} />
          </div>
          <Card className="tier-panel">
            <div className="panel-heading">
              <div><span className="eyebrow">FROM THE AUDIT CHAIN</span><h2>Every payment attempt</h2></div>
              <span className={`placeholder-tag ${verified ? "tag-positive" : ""}`}>{verified ? "CHAIN VERIFIED" : "CHAIN CHECK FAILED"}</span>
            </div>
            <Table headers={["When (UTC)", "Payee", "Amount", "Result", "Detail", "Proposal"]} rows={rows} empty="No payment has been attempted yet. The wallet pays only proposals the Guardian cleared and a person approved." />
          </Card>
        </>
      )}
      <Card className="tier-panel">
        <div className="panel-heading"><div><span className="eyebrow">TREASURER MANDATE</span><h2>Limits the wallet enforces</h2></div></div>
        <div className="tier-metric-grid inner-metrics">
          <Metric label="Per-payment cap" amount={minor(treasurer?.per_payment_cap)} note={treasurer ? `Version ${String(treasurer.version ?? "—")}` : "Mandate not loaded"} />
          <Metric label="Daily cap" amount={minor(treasurer?.daily_cap)} note={treasurer ? `Effective ${String(treasurer.effective_from ?? "—")}` : "Mandate not loaded"} />
          <Metric label="Execution" value="Simulated" note="No bank rails are connected." />
        </div>
        <div style={{ padding: "0 15px 15px" }}>
          <Link className="button button-secondary" href="/settings/mandates">Review mandates</Link>
        </div>
      </Card>
    </div>
  );
}

export function generateStaticParams() {
  return Object.keys(routes).filter((key) => key !== "briefing" && key !== "mandates" && key !== "payment-timing").map((section) => ({ section }));
}

export default async function WorkspaceSection({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  if (!Object.hasOwn(routes, section) || section === "briefing" || section === "mandates" || section === "payment-timing") notFound();
  if (section === "forecast") return <ForecastScreen />;
  if (section === "financing") return <FinancingLiveScreen />;
  if (section === "analysis") return <AnalysisScreen />;
  if (section === "bills") return <BillsScreen />;
  if (section === "reconcile") return <ReconcileScreen />;
  if (section === "wallet") return <WalletScreen />;
  if (section === "audit") return <AuditScreen />;
  if (section === "import") { const localImport = Boolean(await getWorkspaceSession()); return <div className="section-page"><Heading section="import" />{localImport ? <div className="data-note"><span aria-hidden="true">●</span><span><strong>Imports go to your workspace</strong> · Rows are validated, duplicates are skipped, and new bills reach the agents and the Guardian on the next run.</span></div> : <DegradedBanner>Sign in to a workspace to import data.</DegradedBanner>}<Card className="tier-panel"><div className="panel-heading"><div><span className="eyebrow">BANK AND POS INTAKE</span><h2>Preview, then import source records</h2></div><span className="placeholder-tag">Tenant selected server-side</span></div><ImportPreview enabled={localImport} /></Card><p className="footnote">Imports are idempotent: the same file twice adds nothing. Your workspace comes from your account, never from the file.</p></div>; }
  if (section === "approvals") {
    return (
      <div className="section-page">
        <Heading section="approvals" badge="You decide" />
        <div className="data-note">
          <span aria-hidden="true">●</span>
          <span><strong>Nothing pays without you</strong> · Agents propose, the Guardian checks every proposal against its rules and with an independent review, and your decision is recorded under your name in the audit trail.</span>
        </div>
        <ProposalInbox />
      </div>
    );
  }
  if (section === "council") return <CouncilScreen />;
  if (section === "inventory") return <InventoryScreen />;
  if (section === "launch-lab") return <LaunchLabScreen />;
  return <div className="section-page"><Heading section={section as keyof typeof routes} /><EmptyState title="No screen is available">This route is registered but is outside the current Tier 1 view.</EmptyState></div>;
}

