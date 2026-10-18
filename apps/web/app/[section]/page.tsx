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
  VerdictPanel,
} from "@fiona/ui";
import { getMockProposals } from "@/lib/mock-api";
import { demoCashWeeks, demoFinanceSnapshot } from "@/lib/tier-one-data";
import { postEngine, readEngine, objectValue, type EngineRead } from "@/lib/server-read";
import { routes } from "@/lib/routes";
import { ImportPreview } from "@/components/import-preview";
import { BillIntake } from "@/components/bill-intake";
import { ProposalInbox } from "@/components/proposal-inbox";
import { CouncilRoom } from "@/components/council-room";
import { ReconcileRunner } from "@/components/reconcile-runner";
import { InventoryView, type InventoryItemData, type InventorySummaryData } from "@/components/inventory-view";
import { LaunchLabSimulator } from "@/components/launch-lab-simulator";
import { WalletStation } from "@/components/wallet-station";
import { getWorkspaceSession } from "@/lib/session";

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
  return <><div className="page-kicker"><span className="eyebrow">KARACHI APPAREL</span>{badge && <StateChip>{badge}</StateChip>}</div><header className="page-heading"><div><h1>{page.label}</h1><p>{page.description}</p></div></header></>;
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
  const weeks = connectedWeeks.length ? connectedWeeks.map((week) => ({
    week: typeof week.week === "number" ? week.week : 0,
    start: typeof week.start === "string" ? week.start : "—",
    inflows: minor(week.inflows) ?? 0,
    outflows: minor(week.outflows) ?? 0,
    closing: minor(week.closing) ?? 0,
    below: week.below_buffer === true,
    connected: true,
  })) : demoCashWeeks.map((week) => ({ ...week, below: week.closing < 200_000_000, connected: false, inflows: 0, outflows: 0 }));
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
  return <div className="section-page"><Heading section="forecast" badge={data ? "Engine · read only" : "Generator v1 snapshot"} /><DataSource connected={Boolean(data)} fallback="Showing the reproducible synthetic 13-week holdout snapshot." />
    <div className="tier-metric-grid"><Metric label="Lowest forecast close" amount={lowest} note="13-week view" /><Metric label="Owner cash buffer" amount={buffer} note="Tenant policy" /><Metric label="First buffer breach" value={firstBelow ? `Week ${firstBelow}` : "None"} note="Forecast alert" /></div>
    <Card className="tier-panel"><div className="panel-heading"><div><span className="eyebrow">WEEKLY CASH PATH</span><h2>Closing balance and buffer check</h2></div><span className="placeholder-tag">PKR · minor units</span></div><Table headers={data ? ["Period", "Starting", "Inflows", "Outflows", "Closing", "Buffer check"] : ["Period", "Net movement", "Closing", "Buffer check"]} rows={rows} empty="The engine returned no forecast weeks." /></Card>
    <p className="footnote">Forecasts are decision support. The page does not schedule a payment. The fallback snapshot shows the held-out Generator v1 evaluation path; inflow and outflow detail appears only from the local engine response.</p>
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
    const shown = figure.money ? <MoneyText amountMinor={minor(figure.money) ?? 0} /> : figure.value !== undefined ? `${figure.value}${figure.unit === "bp" ? " bp" : ` ${String(figure.unit ?? "")}`}` : figure.status === "insufficient_data" ? "Insufficient data" : "—";
    return [String(figure.label ?? figure.metric_id ?? "Metric"), shown, String(figure.status ?? "ok"), <ProvenancePopover key={String(figure.metric_id)} sourceRefs={Array.isArray(figure.source_refs) ? figure.source_refs.map(String) : []} />];
  });
  const fallbackFigures = [
    ["Annualised sales", <MoneyText amountMinor={demoFinanceSnapshot.annualSalesMinor} key="annual-sales" />],
    ["Operating cash-flow proxy", <MoneyText amountMinor={demoFinanceSnapshot.operatingCashProxyMinor} key="cash-proxy" />],
    ["Existing 12-month debt service", <MoneyText amountMinor={demoFinanceSnapshot.existingDebtServiceMinor} key="debt-service" />],
    ["Forward DSCR", `${(demoFinanceSnapshot.forwardDscrBp / 10_000).toFixed(4)}×`],
  ];
  const stageName = typeof stage?.stage === "string" ? stage.stage.replaceAll("_", " ") : null;
  return <div className="section-page"><Heading section="analysis" badge={stageData ? "Ledger · read only" : "Generator v1 snapshot"} /><DataSource connected={Boolean(stageData && ratioData && healthData)} fallback="The Y2 ledger endpoints are available when the local engine and seeded database are running. Showing calibrated decision inputs here." />
    <div className="tier-metric-grid"><Metric label="Lifecycle stage" value={stageName ?? "Not loaded"} note={stageName ? `${String(stage?.confidence ?? "")} confidence` : "Load the ledger to classify the stage."} /><Metric label="Overall health band" value={String(health?.overall ?? "Not loaded")} note="Categorical health band; no composite score." /><Metric label="Decision coverage" value={ratioFigures.length || fallbackFigures.length} unit=" figures" note="Every engine figure has source references." /></div>
    <Card className="tier-panel"><div className="panel-heading"><div><span className="eyebrow">FINANCIAL INDICATORS</span><h2>Ratios and source trail</h2></div><span className="placeholder-tag">No composite health score</span></div>
      {ratioFigures.length ? <Table headers={["Metric", "Value", "Status", "Sources"]} rows={rows} empty="No ratios were returned." /> : <Table headers={["Generator v1 input", "Calibrated value"]} rows={fallbackFigures} empty="No synthetic calibration figures." />}
    </Card>
    <Card className="tier-panel"><div className="panel-heading"><div><span className="eyebrow">HEALTH BANDS</span><h2>By financial dimension</h2></div></div><div className="band-grid">{Object.entries(healthDimensions).map(([name, raw]) => { const dimension = object(raw); return <div className="band-card" key={name}><span className="eyebrow">{name.replaceAll("_", " ")}</span><strong>{String(dimension?.band ?? "not available")}</strong><p>{Array.isArray(dimension?.reasons) ? dimension.reasons.join(" ") : ""}</p></div>; })}{!Object.keys(healthDimensions).length && <EmptyState title="Health bands not loaded">Connect the local read-only engine to view the bands calculated from posted journal lines.</EmptyState>}</div></Card>
    <p className="footnote">The fallback operating cash-flow proxy is not approved EBITDA and is labelled accordingly in the financing and decision memos.</p>
  </div>;
}

function FinancingScreen() {
  const snapshot = demoFinanceSnapshot;
  const options = [
    { name: "Supplier credit", provider: "PK supplier terms", cost: "0 bp explicit cost", dscr: "No new scheduled loan service", outcome: "Recommended bridge", note: "Needs supplier agreement; does not repair the forecast cash breach." },
    { name: "PMYB&ALS term loan", provider: "Illustrative scheme", cost: "Catalogue terms; verify with lender", dscr: `${(snapshot.debtDscrBp / 10_000).toFixed(4)}× base · ${(snapshot.debtDownsideDscrBp / 10_000).toFixed(4)}× downside`, outcome: "Fails coverage at requested size", note: "The Generator v1 matcher calculated zero safe additional debt at this snapshot." },
    { name: "Owner equity", provider: "Illustrative offer", cost: `${(snapshot.equityDilutionBp / 100).toFixed(1)}% dilution`, dscr: "No fixed repayment", outcome: "Consider owner-approved terms", note: "Uses the illustrative PKR 18m pre-money offer; diligence and control terms remain open." },
  ];
  return <div className="section-page"><Heading section="financing" badge="Generator v1 calibration" /><DataSource connected={false} fallback="The matcher uses the Generator v1 fixture; direct browser recalculation is not connected in this view." />
    <div className="tier-metric-grid"><Metric label="Funding request" amount={snapshot.requestedMinor} note="Seasonal working capital" /><Metric label="Current forward DSCR" value={`${(snapshot.forwardDscrBp / 10_000).toFixed(4)}×`} note="Based on labelled operating-cash-flow proxy" /><Metric label="Current cash low point" amount={-1_709_366_189} note="13-week Generator v1 forecast" /></div>
    <Card className="tier-panel"><div className="panel-heading"><div><span className="eyebrow">MATCHED OPTIONS</span><h2>Compare cost, coverage and conditions</h2></div><span className="placeholder-tag">Illustrative · verify terms</span></div><div className="option-list">{options.map((option) => <article className="option-row" key={option.name}><div><span className="eyebrow">{option.provider}</span><h3>{option.name}</h3><p>{option.note}</p></div><div className="option-facts"><span>{option.cost}</span><span>{option.dscr}</span><strong>{option.outcome}</strong></div></article>)}</div></Card>
    <Card className="tier-panel"><div className="panel-heading"><div><span className="eyebrow">BUSINESS INPUTS</span><h2>What the comparison used</h2></div></div><div className="tier-metric-grid inner-metrics"><Metric label="Annualised sales" amount={snapshot.annualSalesMinor} /><Metric label="Operating cash-flow proxy" amount={snapshot.operatingCashProxyMinor} note="Not approved EBITDA" /><Metric label="Existing debt service" amount={snapshot.existingDebtServiceMinor} /></div><p className="proposal-reasoning">Source: synthetic Generator v1 ledger, forecast and financing matcher. Supplier credit is a bridge while the owner repairs cash flow; it is not a liquidity cure.</p></Card>
  </div>;
}

async function FinancingLiveScreen() {
  const snapshot = demoFinanceSnapshot;
  const result = await postEngine("financing/match", {
    amount: { minor: snapshot.requestedMinor, currency: snapshot.currency },
    purpose: "working_capital_seasonal",
    profile: { industry: "retail_apparel" },
    pre_money_valuation: { minor: 1_800_000_000, currency: snapshot.currency },
    supplier_discount: { discount_bp: snapshot.supplierCreditCostBp, within_days: snapshot.supplierCreditDays, net_days: 30 },
  });
  const data = result.kind === "ok" && result.status === 200 ? objectValue(result.data) : null;
  if (!data) return <FinancingScreen />;
  const options = objects(data?.options);
  const figures = objects(data?.business_figures);
  const detail = (values: unknown) => objects(values).map((figure, index) => {
    const label = String(figure.label ?? figure.metric_id ?? `Metric ${index + 1}`);
    const amount = minor(figure.money);
    const unit = String(figure.unit ?? "");
    const value = figureValue(figure);
    const text = amount !== null
      ? <MoneyText amountMinor={amount} currency={String(object(figure.money)?.currency ?? snapshot.currency)} />
      : value !== null ? `${unit === "bp" && String(figure.metric_id ?? "").includes("dscr") ? `${(value / 10_000).toFixed(2)}×` : value}${unit === "bp" ? " bp" : unit ? ` ${unit}` : ""}` : "Insufficient data";
    return <div className="band-card" key={String(figure.metric_id ?? index)}><span className="eyebrow">{label}</span><strong>{text}</strong><p>{Array.isArray(figure.source_refs) ? figure.source_refs.map(String).join(" · ") : String(figure.status ?? "")}</p></div>;
  });
  const unavailable = result.kind === "unavailable" ? result.message : "Start the local engine and fixture database to load the matcher response.";
  return <div className="section-page"><Heading section="financing" badge={data ? "Matcher · fixture backed" : "Matcher unavailable"} /><DataSource connected={Boolean(data)} fallback={unavailable} />
    <div className="tier-metric-grid"><Metric label="Funding request" amount={minor(data?.amount) ?? snapshot.requestedMinor} note="Seasonal working capital" /><Metric label="Snapshot date" value={String(data?.as_of ?? "Not loaded")} note="Fixture as-of date" /><Metric label="Eligible options" value={options.filter((option) => option.eligible === true).length} note="Catalogue and known business facts" /></div>
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


async function BillsScreen() {
  const data = await engineData("ledger/events");
  if (!data) return <div className="section-page"><Heading section="bills" /><DataSource connected={false} fallback="The engine did not answer, so no bills are shown. Try again in a moment." /></div>;
  const bills = objects(data?.events).filter((event) => event.event === "purchase_bill");
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
    <div className="tier-metric-grid"><Metric label="Imported bills" value={bills.length} note="Purchase bill events" /><Metric label="Duplicate check" value={checkOutcome ? checkOutcome.replaceAll("_", " ") : "Not run"} note="G-05 · read only" /><Metric label="Extraction status" value="Imported records" note="Bill extraction must preserve document hashes and citations." /></div>
    {check && <Card className="tier-panel"><div className="panel-heading"><div><span className="eyebrow">GUARDIAN DUPLICATE CHECK</span><h2>G-05 · {String(checkOutcome ?? "check")}</h2></div>{checkOutcome && <OutcomeBadge outcome={checkOutcome === "approve_with_conditions" ? "conditions" : (checkOutcome as "approve" | "escalate" | "block" | "conditions")} />}</div><p className="proposal-reasoning">{String(check.detail ?? "")}</p></Card>}
    {!check && <DegradedBanner>{detail}</DegradedBanner>}
    <Card className="tier-panel"><div className="panel-heading"><div><span className="eyebrow">IMPORTED BILL REGISTER</span><h2>Source records from the ledger</h2></div><span className="placeholder-tag">Read only</span></div><Table headers={["Bill ID", "Supplier number", "Received", "Supplier", "Total"]} rows={rows} empty="No imported bill events are available." /></Card>
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

const defaultInventorySummary: InventorySummaryData = {
  stock_value_minor: 105_530_000,
  dead_stock_value_minor: 8_280_000,
  slow_stock_value_minor: 53_300_000,
  sku_count: 10,
  gmroi_bp: 39864,
};

const defaultInventoryItems: InventoryItemData[] = [
  { sku: "KRT-M-BLU", name: "Cotton kurta - M - Blue", category: "kurta", season: "all", on_hand: 40, unit_cost_minor: 180000, price_minor: 300000, stock_value_minor: 7200000, units_sold_window: 210, revenue_minor: 63000000, gross_margin_bp: 4000, abc: "A", xyz: "X", movement: "fast", days_of_cover: 17, reorder_point: 29, suggested_order_qty: 59, lead_time_days: 7, safety_stock: 13 },
  { sku: "KRT-L-BLU", name: "Cotton kurta - L - Blue", category: "kurta", season: "all", on_hand: 34, unit_cost_minor: 180000, price_minor: 300000, stock_value_minor: 6120000, units_sold_window: 165, revenue_minor: 49500000, gross_margin_bp: 4000, abc: "A", xyz: "X", movement: "fast", days_of_cover: 19, reorder_point: 23, suggested_order_qty: 46, lead_time_days: 7, safety_stock: 10 },
  { sku: "KRT-M-RED", name: "Cotton kurta - M - Crimson", category: "kurta", season: "festive", on_hand: 22, unit_cost_minor: 190000, price_minor: 320000, stock_value_minor: 4180000, units_sold_window: 95, revenue_minor: 30400000, gross_margin_bp: 4062, abc: "B", xyz: "Y", movement: "normal", days_of_cover: 21, reorder_point: 16, suggested_order_qty: 32, lead_time_days: 7, safety_stock: 9 },
  { sku: "TRS-32-BEI", name: "Linen trousers - 32 - Beige", category: "trousers", season: "all", on_hand: 55, unit_cost_minor: 220000, price_minor: 380000, stock_value_minor: 12100000, units_sold_window: 140, revenue_minor: 53200000, gross_margin_bp: 4210, abc: "A", xyz: "X", movement: "normal", days_of_cover: 35, reorder_point: 22, suggested_order_qty: 0, lead_time_days: 7, safety_stock: 11 },
  { sku: "SUIT-3P-EMB", name: "Embroidered lawn 3-pc suit", category: "unstitched", season: "summer", on_hand: 85, unit_cost_minor: 380000, price_minor: 650000, stock_value_minor: 32300000, units_sold_window: 12, revenue_minor: 7800000, gross_margin_bp: 4153, abc: "B", xyz: "Z", movement: "slow", days_of_cover: 638, reorder_point: 4, suggested_order_qty: 0, lead_time_days: 14, safety_stock: 3 },
  { sku: "DUP-SLK-GLD", name: "Silk dupatta - Golden zari", category: "accessories", season: "wedding", on_hand: 30, unit_cost_minor: 140000, price_minor: 280000, stock_value_minor: 4200000, units_sold_window: 8, revenue_minor: 2240000, gross_margin_bp: 5000, abc: "C", xyz: "Z", movement: "slow", days_of_cover: 338, reorder_point: 3, suggested_order_qty: 0, lead_time_days: 14, safety_stock: 2 },
  { sku: "SHL-WOL-GRY", name: "Wool pashmina shawl - Charcoal", category: "shawl", season: "winter", on_hand: 12, unit_cost_minor: 320000, price_minor: 620000, stock_value_minor: 3840000, units_sold_window: 70, revenue_minor: 43400000, gross_margin_bp: 4838, abc: "A", xyz: "Y", movement: "fast", days_of_cover: 15, reorder_point: 18, suggested_order_qty: 45, lead_time_days: 10, safety_stock: 10 },
  { sku: "DEN-34-IND", name: "Stretch denim jeans - 34", category: "denim", season: "all", on_hand: 48, unit_cost_minor: 260000, price_minor: 440000, stock_value_minor: 12480000, units_sold_window: 26, revenue_minor: 11440000, gross_margin_bp: 4090, abc: "B", xyz: "Y", movement: "slow", days_of_cover: 166, reorder_point: 6, suggested_order_qty: 0, lead_time_days: 10, safety_stock: 4 },
  { sku: "SCF-CHF-PRT", name: "Printed chiffon scarf - Multi", category: "accessories", season: "summer", on_hand: 92, unit_cost_minor: 50000, price_minor: 120000, stock_value_minor: 4600000, units_sold_window: 0, revenue_minor: 0, gross_margin_bp: 5833, abc: "C", xyz: "Z", movement: "dead", days_of_cover: 999, reorder_point: 0, suggested_order_qty: 0, lead_time_days: 7, safety_stock: 0 },
  { sku: "BLT-LTH-BRN", name: "Full-grain leather belt - Brown", category: "accessories", season: "all", on_hand: 41, unit_cost_minor: 90000, price_minor: 190000, stock_value_minor: 3690000, units_sold_window: 0, revenue_minor: 0, gross_margin_bp: 5263, abc: "C", xyz: "Z", movement: "dead", days_of_cover: 999, reorder_point: 0, suggested_order_qty: 0, lead_time_days: 14, safety_stock: 0 },
];

async function InventoryScreen() {
  const data = await engineData("inventory/analysis");
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
    : defaultInventoryItems;

  const summaryData = objects(data?.summary);
  const stockVal = summaryData.find((s) => s.metric_id === "inventory.stock_value");
  const deadVal = summaryData.find((s) => s.metric_id === "inventory.dead_stock_value");
  const slowVal = summaryData.find((s) => s.metric_id === "inventory.slow_stock_value");
  const gmroiFig = summaryData.find((s) => s.metric_id === "inventory.gmroi");

  const summary: InventorySummaryData = {
    stock_value_minor: minor(stockVal?.money) ?? defaultInventorySummary.stock_value_minor,
    dead_stock_value_minor: minor(deadVal?.money) ?? defaultInventorySummary.dead_stock_value_minor,
    slow_stock_value_minor: minor(slowVal?.money) ?? defaultInventorySummary.slow_stock_value_minor,
    sku_count: items.length,
    gmroi_bp: figureValue(gmroiFig) ?? defaultInventorySummary.gmroi_bp,
  };

  return (
    <div className="section-page">
      <Heading section="inventory" badge={data ? "Engine · read only" : "Calibrated preview"} />
      <DataSource
        connected={Boolean(data)}
        fallback="Showing the calibrated Karachi Apparel 10-SKU catalogue with movement analysis and interactive EOQ calculator."
      />
      <InventoryView summary={summary} items={items} />
      <p className="footnote">
        Inventory movement analytics are decision support. Draft reorder suggestions do not automatically dispatch purchase orders or commit cash.
      </p>
    </div>
  );
}

function LaunchLabScreen() {
  return (
    <div className="section-page">
      <Heading section="launch-lab" badge="Monte Carlo · resolver" />
      <DataSource
        connected={false}
        fallback="Explore the interactive launch simulator with unit contribution, breakeven horizon, and dynamic what-if sliders."
      />
      <LaunchLabSimulator />
    </div>
  );
}

function WalletScreen() {
  return (
    <div className="section-page">
      <Heading section="wallet" badge="Sandbox · cryptographic" />
      <DataSource
        connected={false}
        fallback="The local wallet endpoint executes in simulated sandbox mode. No live bank rails are connected."
      />
      <WalletStation />
      <Card className="tier-panel" style={{ marginTop: "14px" }}>
        <div className="panel-heading">
          <div>
            <span className="eyebrow">DEMO LIMITS</span>
            <h2>Owner mandate fixture</h2>
          </div>
        </div>
        <div className="tier-metric-grid inner-metrics">
          <Metric label="Per-payment cap" amount={15_000_000} note="PKR 150,000 synthetic limit" />
          <Metric label="Daily cap" amount={45_000_000} note="PKR 450,000 synthetic limit" />
          <Metric label="Execution mode" value="Sandbox only" note="No real money moves." />
        </div>
        <div style={{ padding: "0 15px 15px" }}>
          <Link className="button button-secondary" href="/settings/mandates">
            Review mandate details
          </Link>
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

