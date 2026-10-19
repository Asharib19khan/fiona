import Link from "next/link";
import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import {
  DegradedBanner,
  EmptyState,
  MoneyText,
  OutcomeBadge,
  ProvenancePopover,
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
import { ForecastScreen } from "@/components/forecast-screen";
import { Kpi, KpiGrid, PageHeader, Panel, Pill, nice, rise, toneFor } from "@/components/screen-kit";
import { PagedTable } from "@/components/paged";
import { FindingList, MatchTable, type FindingRow, type MatchRow } from "@/components/reconcile-tables";
import {
  AlertIcon,
  ArrowRightIcon,
  CalendarIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  CoinsIcon,
  CompassIcon,
  DocIcon,
  GaugeIcon,
  HashIcon,
  LayersIcon,
  LinkIcon,
  ShieldCheckIcon,
  WalletIcon,
} from "@/components/briefing-icons";

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

const LIVE_CHIP = "Computed from your ledger";

/** UTC timestamps as "22 Oct 2026, 09:00 UTC"; the raw value stays in the title. */
const STAMP = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" });
function Stamp({ value }: { value: unknown }) {
  const text = typeof value === "string" ? value : "";
  const parsed = text ? new Date(text) : null;
  if (!parsed || Number.isNaN(parsed.getTime())) return <>{text || "—"}</>;
  return <time className="sk-nowrap" dateTime={text} title={text}>{STAMP.format(parsed)} UTC</time>;
}

function Heading({ section, badge, live = false, actions }: { section: keyof typeof routes; badge?: string | undefined; live?: boolean | undefined; actions?: ReactNode | undefined }) {
  const page = routes[section];
  const chips = [live ? LIVE_CHIP : null, badge && badge !== LIVE_CHIP ? badge : null];
  return <PageHeader title={page.label} description={page.description} chips={chips} actions={actions} />;
}

/** When the engine answered, the heading carries the "computed from your ledger" chip; otherwise this says why there are no figures. */
function DataSource({ connected, fallback }: { connected: boolean; fallback: string }) {
  if (connected) return null;
  return <DegradedBanner>{fallback || "The engine did not answer, so this page shows no figures."}</DegradedBanner>;
}

function Table({ headers, rows, empty, pageSize = 20, noun, numeric }: { headers: string[]; rows: Array<Array<ReactNode>>; empty: string; pageSize?: number | undefined; noun?: string | undefined; numeric?: number[] | undefined }) {
  if (!rows.length) return <EmptyState title="No records to show">{empty}</EmptyState>;
  return <PagedTable headers={headers} rows={rows} pageSize={pageSize} noun={noun} numeric={numeric} />;
}

function Mono({ children, title }: { children: ReactNode; title?: string }) {
  return <code className="sk-mono" title={title}>{children}</code>;
}

/** An engine figure (money, ratio, basis points or a count) as text, or a plain reason when there is no value. */
function figureText(figure: JsonObject, currency?: string): ReactNode {
  const amount = minor(figure.money);
  if (amount !== null) return <MoneyText amountMinor={amount} currency={currency ?? String(object(figure.money)?.currency ?? "")} animateCount={false} />;
  const value = figure.value;
  if (typeof value === "number" && Number.isFinite(value)) {
    const unit = String(figure.unit ?? "");
    if (unit === "bp") return basisPointsText(value, String(figure.metric_id ?? ""));
    return `${value.toLocaleString("en-GB")}${unit ? ` ${unit}` : ""}`;
  }
  if (figure.status === "insufficient_data") return "Insufficient data";
  if (figure.status === "not_applicable") return "Not applicable";
  return "Not available";
}

async function AnalysisScreen() {
  const [stageData, ratioData, healthData] = await Promise.all([engineData("stage"), engineData("analysis/ratios"), engineData("analysis/health")]);
  const stage = object(stageData?.result);
  const health = object(healthData?.result);
  const ratioFigures = objects(ratioData?.figures);
  const healthDimensions = object(health?.dimensions) ?? {};
  const connected = Boolean(stageData && ratioData && healthData);
  const rows = ratioFigures.map((figure) => {
    const shown = figure.money ? <MoneyText amountMinor={minor(figure.money) ?? 0} animateCount={false} /> : figureText(figure);
    const status = String(figure.status ?? "ok");
    return [
      String(figure.label ?? figure.metric_id ?? "Metric"),
      shown,
      <Pill key="status" tone={toneFor(status)} dot>{status === "ok" ? "OK" : nice(status)}</Pill>,
      <ProvenancePopover key={String(figure.metric_id)} sourceRefs={Array.isArray(figure.source_refs) ? figure.source_refs.slice(0, 12).map(String) : []} total={Array.isArray(figure.source_refs) ? figure.source_refs.length : 0} />,
    ];
  });
  const stageName = typeof stage?.stage === "string" ? nice(stage.stage) : null;
  const overall = health?.overall;
  const flagged = ratioFigures.filter((figure) => figure.status && figure.status !== "ok").length;
  return <div className="section-page sk-page">
    <Heading section="analysis" live={connected} badge={stageData ? undefined : "Unavailable"} />
    <DataSource connected={connected} fallback="The analysis could not be computed right now (the engine did not answer). No figures are shown rather than old ones." />
    <KpiGrid label="Analysis summary">
      <Kpi index={1} label="Lifecycle stage" icon={<CompassIcon />} value={stageName ?? "Not loaded"} note={stageName ? `${nice(stage?.confidence, "Unknown")} confidence` : "Load the ledger to classify the stage."} />
      <Kpi index={2} label="Overall health band" icon={<GaugeIcon />} tone={toneFor(overall)} value={nice(overall, "Not loaded")} emphasis={toneFor(overall) === "danger" ? "negative" : toneFor(overall) === "amber" ? "warning" : undefined} note="Categorical health band; no composite score." />
      <Kpi index={3} label="Figures computed" icon={<LayersIcon />} value={ratioFigures.length ? `${ratioFigures.length} figures` : "None"} note={flagged ? `Every engine figure has source references · ${flagged} without a usable value` : "Every engine figure has source references."} />
    </KpiGrid>
    <Panel index={4} eyebrow="Health bands" title="By financial dimension">
      <div className="band-grid sk-band-grid">{Object.entries(healthDimensions).map(([name, raw], index) => { const dimension = object(raw); const band = dimension?.band; return <div className="band-card sk-band sk-rise" style={rise(index + 5)} key={name}><div className="sk-band-top"><span className="eyebrow">{nice(name)}</span><Pill tone={toneFor(band)} dot>{nice(band, "Not available")}</Pill></div><p>{Array.isArray(dimension?.reasons) && dimension.reasons.length ? dimension.reasons.map(String).join(" ") : "No reasons were given for this band."}</p></div>; })}{!Object.keys(healthDimensions).length && <EmptyState title="Health bands not loaded">Connect the local read-only engine to view the bands calculated from posted journal lines.</EmptyState>}</div>
    </Panel>
    <Panel index={5} eyebrow="Financial indicators" title="Ratios and source trail" tag="No composite health score">
      <Table headers={["Metric", "Value", "Status", "Sources"]} rows={rows} numeric={[1]} noun="figures" pageSize={15} empty="The ratios could not be computed right now (the engine did not answer)." />
    </Panel>
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
    return <div className="section-page sk-page"><Heading section="financing" /><DataSource connected={false} fallback="The cash forecast did not load, so there is no shortfall to finance yet." /></div>;
  }
  const requestedMinor = Math.max(0, buffer - lowest);
  if (requestedMinor === 0) {
    return <div className="section-page sk-page"><Heading section="financing" live /><EmptyState title="Nothing to finance">Your 13-week cash forecast stays above your buffer, so there is no shortfall to fund.</EmptyState></div>;
  }
  const result = await postEngine("financing/match", {
    amount: { minor: requestedMinor, currency },
    purpose: "working_capital_seasonal",
  });
  const data = result.kind === "ok" && result.status === 200 ? objectValue(result.data) : null;
  if (!data) return <div className="section-page sk-page"><Heading section="financing" /><DataSource connected={false} fallback={result.kind === "unavailable" ? result.message : "The financing matcher could not run right now."} /></div>;
  const options = objects(data?.options);
  const figures = objects(data?.business_figures);
  const proxy = figures.find((figure) => String(figure.note ?? "").toLowerCase().includes("proxy"));
  const eligible = options.filter((option) => option.eligible === true).length;
  const detail = (values: unknown) => objects(values).map((figure, index) => {
    const label = String(figure.label ?? figure.metric_id ?? `Metric ${index + 1}`);
    const sources = Array.isArray(figure.source_refs) ? figure.source_refs.map(String).join(" · ") : String(figure.status ?? "");
    return <div className="sk-fig" key={String(figure.metric_id ?? index)}><span>{label}</span><strong>{figureText(figure, currency)}</strong>{sources && <small title={sources}>{sources}</small>}</div>;
  });
  const unavailable = result.kind === "unavailable" ? result.message : "Start the local engine and fixture database to load the matcher response.";
  const renderOption = (option: JsonObject, index: number) => {
    const outcome = String(option.outcome ?? "needs_information");
    const eligibility = option.eligible === true ? "Eligible" : option.eligible === false ? "Ineligible" : "Needs more information";
    const outcomeText = nice(outcome);
    const same = outcomeText.toLowerCase() === eligibility.toLowerCase() || (outcome === "needs_information" && option.eligible !== true && option.eligible !== false);
    return <article className={`sk-option sk-rise ${option.eligible === false ? "is-muted" : ""}`} style={rise(index + 5)} key={String(option.option_id ?? index)}>
      <header className="sk-option-head">
        {typeof option.rank === "number" && <span className="sk-rank" aria-label={`Rank ${option.rank}`}>{option.rank}</span>}
        <div className="sk-option-title">
          <span className="eyebrow">{nice(option.provider_label ?? option.kind, "Catalogue option")} · {option.illustrative === true ? "Illustrative" : "Catalogue"}</span>
          <h3>{String(option.name ?? option.option_id)}</h3>
          {Array.isArray(option.rank_reasons) && option.rank_reasons.length > 0 && <p>{option.rank_reasons.map((reason) => nice(reason)).join(" · ")}</p>}
        </div>
        <div className="sk-option-status">
          <Pill tone={toneFor(outcome)} dot>{same ? eligibility : outcomeText}{typeof option.rank === "number" ? ` · rank ${option.rank}` : ""}</Pill>
          {!same && <Pill tone={toneFor(eligibility)}>{eligibility}</Pill>}
        </div>
      </header>
      {objects(option.figures).length > 0 && <div className="sk-figs">{detail(option.figures)}</div>}
      {Boolean(option.source_ref) && <p className="sk-source"><LinkIcon width="12" height="12" /> {String(option.source_ref)}</p>}
    </article>;
  };
  const primary = options.filter((option) => option.eligible !== false);
  const ineligible = options.filter((option) => option.eligible === false);
  return <div className="section-page sk-page">
    <Heading section="financing" live actions={<Link className="button button-secondary arrow-link" href="/forecast">See the shortfall <ArrowRightIcon /></Link>} />
    {proxy && <DegradedBanner><strong>Proxy used for EBITDA.</strong> {String(proxy.label ?? "EBITDA")} is estimated from operating cash flow, not audited EBITDA ({String(proxy.note ?? "")}). It feeds debt-service cover and therefore the ranking below; treat the ranking as indicative until real EBITDA is available.</DegradedBanner>}
    <KpiGrid label="Financing summary">
      <Kpi index={1} label="Funding request" icon={<CoinsIcon />} tone="amber" value={<MoneyText amountMinor={minor(data?.amount) ?? requestedMinor} />} note="Your forecast's largest shortfall below the buffer" />
      <Kpi index={2} label="Snapshot date" icon={<CalendarIcon />} value={String(data?.as_of ?? "Not loaded")} note="Fixture as-of date" />
      <Kpi index={3} label="Eligible options" icon={<CheckCircleIcon />} tone="green" value={<>{eligible}<span className="sk-of"> of {options.length}</span></>} note="Catalogue and known business facts" />
    </KpiGrid>
    <Panel index={4} eyebrow="Matched options" title="Compare cost, coverage and conditions" tag="Each option carries its source">
      {options.length ? <><div className="sk-options">{primary.map(renderOption)}</div>
        {ineligible.length > 0 && <details className="sk-more-options"><summary><span>{ineligible.length} ineligible {ineligible.length === 1 ? "option" : "options"}, with the figures that ruled them out</span><ChevronDownIcon /></summary><div className="sk-options">{ineligible.map((option, index) => renderOption(option, primary.length + index))}</div></details>}</> : <EmptyState title="No matcher response">{data ? "The matcher returned no options." : unavailable}</EmptyState>}
    </Panel>
    <Panel index={6} eyebrow="Business inputs" title="Figures used in the comparison">
      <div className="sk-figs sk-figs-pad">{detail(figures)}</div>
      <p className="proposal-reasoning">Missing inputs are surfaced by the matcher; an operating-cash-flow proxy is not treated as approved EBITDA.</p>
    </Panel>
  </div>;
}

function CouncilScreen() {
  return (
    <div className="section-page sk-page">
      <Heading section="council" badge="Advice only" />
      <div className="sk-rise" style={rise(1)}><CouncilRoom /></div>
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
  if (!data) return <div className="section-page sk-page"><Heading section="bills" /><DataSource connected={false} fallback="The engine did not answer, so no bills are shown. Try again in a moment." /></div>;
  const bills = objects(data?.events).filter((event) => event.event === "purchase_bill").reverse();
  const sampleBillId = typeof bills[0]?.bill_id === "string" ? bills[0].bill_id : null;
  const checkResult = sampleBillId ? await postEngine("bills/check", { bill_id: sampleBillId }) : null;
  const checkData = checkResult?.kind === "ok" && checkResult.status === 200 ? objectValue(checkResult.data) : null;
  const check = object(checkData?.check);
  const checkOutcome = typeof check?.outcome === "string" ? check.outcome : null;
  const totalShown = bills.slice(0, 50).reduce((sum, bill) => sum + (typeof bill.total_minor === "number" ? bill.total_minor : 0), 0);
  const rows = bills.slice(0, 50).map((bill) => [
    <Mono key="id">{String(bill.bill_id ?? "—")}</Mono>,
    String(bill.number ?? "—"),
    <span key="date" className="sk-nowrap">{String(bill.date ?? "—")}</span>,
    String(bill.party ?? bill.party_id ?? "—"),
    <MoneyText key="amount" amountMinor={typeof bill.total_minor === "number" ? bill.total_minor : 0} animateCount={false} />,
  ]);
  const detail = checkResult?.kind === "unavailable" ? checkResult.message : "Import synthetic bills to the local ledger to run the duplicate check.";
  return <div className="section-page sk-page">
    <Heading section="bills" live badge="Ledger" />
    <div className="sk-rise" style={rise(1)}><BillIntake /></div>
    <KpiGrid label="Bills summary">
      <Kpi index={2} label="Bills in the last 60 days" icon={<DocIcon />} value={data.next_offset ? `${bills.length}+` : bills.length} note={`Posted since ${since}`} />
      <Kpi index={3} label="Duplicate check" icon={<ShieldCheckIcon />} tone={checkOutcome ? toneFor(checkOutcome) : "neutral"} value={checkOutcome ? nice(checkOutcome) : "Not run"} note="G-05 on the newest bill · read only" />
      <Kpi index={4} label="New bills" icon={<CheckCircleIcon />} value="Read, then confirmed" note="Claude transcribes with quotes; code checks them; you confirm before anything is posted." />
    </KpiGrid>
    {check && <Panel index={5} eyebrow="Guardian duplicate check" title={<>G-05 · {nice(checkOutcome, "Check")}</>} actions={checkOutcome ? <OutcomeBadge outcome={checkOutcome === "approve_with_conditions" ? "conditions" : (checkOutcome as "approve" | "escalate" | "block" | "conditions")} /> : undefined}><p className="proposal-reasoning">{String(check.detail ?? "")}</p></Panel>}
    {!check && <DegradedBanner>{detail}</DegradedBanner>}
    <Panel index={6} eyebrow="Imported bill register" title="Newest bills in the ledger" tag={bills.length > 50 ? "Latest 50 shown" : "Read only"}>
      {rows.length > 0 && <div className="sk-strip"><span><b>{rows.length}</b> bills listed</span><span>Total <b><MoneyText amountMinor={totalShown} animateCount={false} /></b></span><span>Newest <b>{String(bills[0]?.date ?? "—")}</b></span></div>}
      <Table headers={["Bill ID", "Supplier number", "Received", "Supplier", "Total"]} rows={rows} numeric={[4]} noun="bills" pageSize={15} empty="No imported bill events are available." />
    </Panel>
    <p className="footnote">Bill records remain source data. This screen does not approve a bill or issue a payment.</p>
  </div>;
}

async function ReconcileScreen() {
  const [matchesData, findingsData] = await Promise.all([engineData("reconcile/matches"), engineData("reconcile/findings")]);
  const matches = objects(matchesData?.matches);
  const findings = objects(findingsData?.findings);
  const exact = matches.filter((match) => Number(match.confidence ?? 0) >= 1).length;
  const atStake = findings.reduce((sum, finding) => sum + (minor(finding.money_at_stake) ?? 0), 0);
  const matchRows: MatchRow[] = matches.map((match) => ({
    line: String(match.bank_line_id ?? "—"),
    pass: String(match.pass_name ?? "—"),
    confidence: Number(match.confidence ?? 0),
    status: String(match.status ?? "—"),
    events: Array.isArray(match.event_ids) ? match.event_ids.map(String) : [],
  }));
  const findingRows: FindingRow[] = findings.map((finding, index) => ({
    id: String(finding.id ?? index),
    title: String(finding.title ?? finding.metric_id ?? "Reconciliation finding"),
    detail: String(finding.detail ?? finding.note ?? "Review the source bank line and candidate ledger events."),
    minor: minor(finding.money_at_stake),
  }));
  return <div className="section-page sk-page">
    <Heading section="reconcile" live={Boolean(matchesData)} badge={matchesData ? "Ledger · read only" : "Synthetic preview"} />
    <DataSource connected={Boolean(matchesData)} fallback="No seeded ledger response is available; the page does not invent reconciliation counts." />
    <KpiGrid label="Reconciliation summary">
      <Kpi index={1} label="Saved matches" icon={<LinkIcon />} tone="green" value={matches.length.toLocaleString("en-US")} note={matches.length ? `From the ledger endpoint · ${exact.toLocaleString("en-US")} exact` : "From the ledger endpoint"} />
      <Kpi index={2} label="Open findings" icon={<AlertIcon />} tone={findings.length ? "amber" : "green"} value={findings.length.toLocaleString("en-US")} note={atStake ? <>Ranked by money at stake · <MoneyText amountMinor={atStake} animateCount={false} /> in total</> : "Ranked by money at stake"} />
      <Kpi index={3} label="Posting behavior" icon={<ShieldCheckIcon />} value="Proposals only" note="Matches remain proposals until reviewed." />
    </KpiGrid>
    <Panel index={4} eyebrow="Match register" title="Bank lines and linked events" tag="Review before posting" actions={<ReconcileRunner enabled />}>
      <MatchTable matches={matchRows} />
    </Panel>
    <Panel index={5} eyebrow="Needs review" title="Unmatched bank-line findings" tag={findings.length ? `${findings.length.toLocaleString("en-US")} open` : undefined} tagTone="amber">
      {findings.length ? <FindingList findings={findingRows} /> : <EmptyState title="No live findings loaded">A match decision must remain reviewable. This page has no action that posts ledger events.</EmptyState>}
    </Panel>
  </div>;
}

async function AuditScreen() {
  const data = await engineData("audit");
  const records = objects(data?.records);
  const verified = data?.verified === true;
  const rows = records.slice().reverse().map((item) => [
    <span key="seq" className="sk-seq"><i aria-hidden="true" />{String(item.seq ?? "—")}</span>,
    <Stamp key="at" value={item.recorded_at} />,
    item.proposal_id ? <Link key="p" className="text-link sk-mono-link" href={`/proposals/${String(item.proposal_id)}`}>{String(item.proposal_id)}</Link> : "—",
    <Mono key="hash" title={String(item.hash ?? "")}>{String(item.hash ?? "—").slice(0, 16) + "…"}</Mono>,
  ]);
  return <div className="section-page sk-page">
    <Heading section="audit" live={Boolean(data)} badge={data ? "Ledger · read only" : "Replay preview"} actions={data ? <a className="button button-secondary" href="/api/fiona/audit/export" download>Download execution evidence</a> : undefined} />
    <DataSource connected={Boolean(data)} fallback="The sample timeline is not an audit-chain export." />
    <KpiGrid label="Audit summary">
      <Kpi index={1} label="Chain verification" icon={<ShieldCheckIcon />} tone={data ? (verified ? "green" : "danger") : "neutral"} value={data ? (verified ? "Verified" : "Failed") : "Not checked"} emphasis={data && !verified ? "negative" : undefined} note={data?.first_bad_seq ? `First invalid entry: ${String(data.first_bad_seq)}` : "Read-only verification"} />
      <Kpi index={2} label="Entries" icon={<HashIcon />} value={typeof data?.chain_length === "number" ? data.chain_length : "None"} note="Full tenant chain length" />
      <Kpi index={3} label="Payment mode" icon={<WalletIcon />} value="Simulated" note="No bank rails are connected." />
    </KpiGrid>
    <Panel index={4} eyebrow="Hash-chain entries" title="Latest recorded operations" tag={data ? (verified ? "Verified" : "Check failed") : "Not connected"} tagTone={data ? (verified ? "green" : "danger") : "neutral"}>
      <div className="sk-chain"><Table headers={["Sequence", "Recorded at", "Proposal", "Entry hash"]} rows={rows} noun="entries" pageSize={20} empty="Connect the local mock engine with the seeded database to inspect verified audit entries." /></div>
    </Panel>
    <p className="footnote">The wallet API itself is not called from this read-only screen. A replay marker is not evidence that an operation occurred.</p>
  </div>;
}


async function InventoryScreen() {
  const data = await engineData("inventory/analysis");
  if (!data) {
    return <div className="section-page sk-page"><Heading section="inventory" /><DataSource connected={false} fallback="The engine did not answer, so no inventory figures are shown." /></div>;
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
    <div className="section-page sk-page">
      <Heading section="inventory" live badge="Engine · read only" />
      <div className="sk-rise" style={rise(1)}><InventoryView summary={summary} items={items} /></div>
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
    <div className="section-page sk-page">
      <Heading section="launch-lab" badge="Engine · Monte Carlo" />
      {currency ? (
        <>
          <div className="data-note sk-rise" style={rise(1)}>
            <span aria-hidden="true">●</span>
            <span><strong>Run by the engine</strong> · Your costs and price, plus comparable products and lead times from your ledger. The odds come from a simulation of these assumptions.</span>
          </div>
          <div className="sk-rise" style={rise(2)}><LaunchLabSimulator currency={currency} canSaveDefaults={session?.role === "owner"} /></div>
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
  const paidTotal = executed.reduce((sum, record) => sum + (typeof record.amount_minor === "number" ? record.amount_minor : 0), 0);
  const treasurer = objects(mandates?.mandates).find((mandate) => mandate.agent === "treasurer") ?? null;
  const verified = audit?.verified === true;
  const rows = payments.slice(0, 25).map((record) => {
    const paid = record.action === "payment_executed";
    const reason = String(record.reason ?? "Refused");
    const split = reason.match(/^([A-Z][A-Z0-9_]+):\s*(.*)$/);
    return [
      <span key="when" className="sk-nowrap">{String(record.at ?? "—").replace("T", " ").slice(0, 16)}</span>,
      String(record.payee_id ?? "—"),
      typeof record.amount_minor === "number" ? <MoneyText amountMinor={record.amount_minor} currency={String(record.currency ?? "")} animateCount={false} /> : "—",
      <span key="result" className={`outcome-badge ${paid ? "outcome-approve" : "outcome-block"}`}><span aria-hidden="true">{paid ? "✓" : "×"}</span>{paid ? "Paid" : "Refused"}</span>,
      paid
        ? <span key="detail" className="sk-detail">Wallet ref <Mono>{String(record.wallet_ref ?? "—")}</Mono> · verdict <Mono>{String(record.verdict_hash ?? "").slice(0, 10)}…</Mono></span>
        : split ? <span key="detail" className="sk-detail"><Mono>{split[1]}</Mono> {split[2]}</span> : <Mono key="detail">{reason}</Mono>,
      record.proposal_id ? <Link key="proposal" className="text-link sk-truncate" href={`/proposals/${String(record.proposal_id)}`} title={String(record.proposal_id)}>{String(record.proposal_id)}</Link> : "—",
    ];
  });
  return (
    <div className="section-page sk-page">
      <Heading section="wallet" live={Boolean(audit)} badge="Simulated wallet · no real money moves" actions={<Link className="button button-secondary" href="/settings/mandates">Review mandates</Link>} />
      <DataSource connected={Boolean(audit)} fallback="The engine did not answer, so no wallet activity is shown." />
      {audit && (
        <>
          <KpiGrid label="Wallet summary">
            <Kpi index={1} label="Payments made" icon={<CheckCircleIcon />} tone="green" value={executed.length} note={paidTotal ? <>Simulated; each one is a posted ledger event · <MoneyText amountMinor={paidTotal} animateCount={false} /> paid</> : "Simulated; each one is a posted ledger event"} />
            <Kpi index={2} label="Attempts refused" icon={<AlertIcon />} tone={payments.length - executed.length ? "danger" : "green"} value={payments.length - executed.length} note="Every refusal is recorded with its reason" />
            <Kpi index={3} label="Audit chain" icon={<HashIcon />} tone={verified ? "green" : "danger"} value={verified ? "Verified" : "Check failed"} emphasis={verified ? undefined : "negative"} note={`${String(audit.chain_length ?? 0)} hash-chained entries`} />
          </KpiGrid>
          <Panel index={4} eyebrow="From the audit chain" title="Every payment attempt" tag={verified ? "Chain verified" : "Chain check failed"} tagTone={verified ? "green" : "danger"}>
            <Table headers={["When (UTC)", "Payee", "Amount", "Result", "Detail", "Proposal"]} rows={rows} numeric={[2]} noun="attempts" pageSize={10} empty="No payment has been attempted yet. The wallet pays only proposals the Guardian cleared and a person approved." />
          </Panel>
        </>
      )}
      <Panel index={5} eyebrow="Treasurer mandate" title="Limits the wallet enforces">
        <div className="sk-stats">
          <div><span>Per-payment cap</span><strong>{minor(treasurer?.per_payment_cap) !== null ? <MoneyText amountMinor={minor(treasurer?.per_payment_cap) ?? 0} /> : "Not available"}</strong><small>{treasurer ? `Version ${String(treasurer.version ?? "—")}` : "Mandate not loaded"}</small></div>
          <div><span>Daily cap</span><strong>{minor(treasurer?.daily_cap) !== null ? <MoneyText amountMinor={minor(treasurer?.daily_cap) ?? 0} /> : "Not available"}</strong><small>{treasurer ? `Effective ${String(treasurer.effective_from ?? "—")}` : "Mandate not loaded"}</small></div>
          <div><span>Execution</span><strong>Simulated</strong><small>No bank rails are connected.</small></div>
        </div>
      </Panel>
    </div>
  );
}

function ImportScreen({ localImport }: { localImport: boolean }) {
  return (
    <div className="section-page sk-page">
      <Heading section="import" badge={localImport ? "Your workspace" : undefined} />
      {localImport ? <div className="data-note sk-rise" style={rise(1)}><span aria-hidden="true">●</span><span><strong>Imports go to your workspace</strong> · Rows are validated, duplicates are skipped, and new bills reach the agents and the Guardian on the next run.</span></div> : <DegradedBanner>Sign in to a workspace to import data.</DegradedBanner>}
      <ol className="sk-steps sk-rise" style={rise(2)} aria-label="How an import works">
        <li><b>1</b><div><strong>Choose the record type</strong><span>Bank statement or POS sales</span></div></li>
        <li><b>2</b><div><strong>Preview the file</strong><span>Checked in this tab first</span></div></li>
        <li><b>3</b><div><strong>Import</strong><span>Duplicates are skipped</span></div></li>
      </ol>
      <Panel index={3} eyebrow="Bank and POS intake" title="Preview, then import source records" tag="Tenant selected server-side">
        <ImportPreview enabled={localImport} />
      </Panel>
      <p className="footnote">Imports are idempotent: the same file twice adds nothing. Your workspace comes from your account, never from the file.</p>
    </div>
  );
}

export function generateStaticParams() {
  return Object.keys(routes).filter((key) => key !== "briefing" && key !== "mandates" && key !== "ai-connection" && key !== "payment-timing").map((section) => ({ section }));
}

export default async function WorkspaceSection({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  if (!Object.hasOwn(routes, section) || section === "briefing" || section === "mandates" || section === "ai-connection" || section === "payment-timing") notFound();
  if (section === "forecast") return <ForecastScreen />;
  if (section === "financing") return <FinancingLiveScreen />;
  if (section === "analysis") return <AnalysisScreen />;
  if (section === "bills") return <BillsScreen />;
  if (section === "reconcile") return <ReconcileScreen />;
  if (section === "wallet") return <WalletScreen />;
  if (section === "audit") return <AuditScreen />;
  if (section === "import") return <ImportScreen localImport={Boolean(await getWorkspaceSession())} />;
  if (section === "approvals") {
    return (
      <div className="section-page sk-page">
        <Heading section="approvals" badge="You decide" />
        <div className="data-note sk-rise" style={rise(1)}>
          <span aria-hidden="true">●</span>
          <span><strong>Nothing pays without you</strong> · Agents propose, the Guardian checks every proposal against its rules and with an independent review, and your decision is recorded under your name in the audit trail.</span>
        </div>
        <div className="sk-rise" style={rise(2)}><ProposalInbox /></div>
      </div>
    );
  }
  if (section === "council") return <CouncilScreen />;
  if (section === "inventory") return <InventoryScreen />;
  if (section === "launch-lab") return <LaunchLabScreen />;
  return <div className="section-page sk-page"><Heading section={section as keyof typeof routes} /><EmptyState title="No screen is available">This route is registered but is outside the current Tier 1 view.</EmptyState></div>;
}
