import Link from "next/link";
import type { CSSProperties } from "react";
import { Card, DegradedBanner, EmptyState, FindingCard, MoneyText, StateChip } from "@fiona/ui";
import { getBriefing } from "@/lib/briefing";
import { readable } from "@/lib/finding-text";
import { getSession } from "@/lib/session";
import { LiveClock } from "@/components/live-clock";
import { Greeting } from "@/components/greeting";
import { CashSpark } from "@/components/cash-spark";
import { BriefingBackdrop } from "@/components/briefing-backdrop";
import { ArrowRightIcon, BoxIcon, ChatIcon, CompassIcon, InfoIcon, ShieldCheckIcon, TrendDownIcon, TrendUpIcon } from "@/components/briefing-icons";

export const dynamic = "force-dynamic";

/** First name from the account's display name; an email-only account uses the part before the @. */
function firstNameOf(name: string | undefined): string {
  const raw = (name ?? "").trim();
  if (!raw) return "there";
  const base = raw.includes("@") ? (raw.split("@")[0] ?? "").split(/[._-]+/)[0] : raw.split(/\s+/)[0];
  return base ? base.charAt(0).toUpperCase() + base.slice(1) : "there";
}

/** Entrance delay for the staggered page reveal. */
const delay = (ms: number) => ({ "--d": `${ms}ms` }) as CSSProperties;

const LEDGER_DATE = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

export default async function Home() {
  const [briefing, session] = await Promise.all([getBriefing(), getSession()]);
  const { cash, approvals, stock, findings } = briefing;
  const firstName = firstNameOf(session?.name);
  const waiting = approvals?.waiting ?? 0;
  const cashGap = Boolean(cash?.firstWeekBelow);
  const needsYou = waiting + (cashGap ? 1 : 0);
  const reasons = [
    waiting > 0 ? `${waiting} ${waiting === 1 ? "proposal" : "proposals"} to approve` : null,
    cashGap ? `a cash gap from week ${cash?.firstWeekBelow}` : null,
  ].filter(Boolean);

  return (
    <div className="briefing-page">
      <BriefingBackdrop />
      <header className="page-heading reveal" style={delay(0)}>
        <div>
          <div className="page-kicker">
            <LiveClock />
            {briefing.asOf && <StateChip>Ledger as of {LEDGER_DATE.format(new Date(`${briefing.asOf}T00:00:00Z`))}</StateChip>}
          </div>
          <Greeting firstName={firstName} />
          <p>
            {needsYou === 0
              ? "Nothing needs you right now. The team is watching the ledger."
              : <><strong>{needsYou} {needsYou === 1 ? "thing needs" : "things need"} you today</strong>: {reasons.join(" and ")}.</>}
          </p>
        </div>
        <Link className={`button ${waiting > 0 ? "button-primary" : "button-secondary"} heading-action arrow-link`} href="/approvals">
          {waiting > 0 ? `Review ${waiting} ${waiting === 1 ? "approval" : "approvals"}` : "Open approvals"} <ArrowRightIcon />
        </Link>
      </header>

      {briefing.unavailable.length > 0 && (
        <DegradedBanner>Could not load: {briefing.unavailable.join(", ")}. The rest of the briefing is current.</DegradedBanner>
      )}

      <section className="summary-grid" aria-label="Business summary">
        <Card className={`summary-card summary-cash reveal ${cashGap ? "is-alert" : ""}`} style={delay(80)}>
          <div className="summary-label">
            <span>Lowest cash in the next 13 weeks</span>
            <span className={`summary-icon ${cashGap ? "icon-danger" : "icon-green"}`}>{cashGap ? <TrendDownIcon /> : <TrendUpIcon />}</span>
          </div>
          <strong className={`summary-value ${cash && cash.lowestMinor < 0 ? "is-negative" : ""}`}>
            {cash ? <MoneyText amountMinor={cash.lowestMinor} currency={briefing.currency} /> : "Unavailable"}
          </strong>
          <div className="summary-foot">
            {cash ? (
              cash.firstWeekBelow ? (
                <><span className="summary-alert-dot" /> Below your <MoneyText amountMinor={cash.bufferMinor} currency={briefing.currency} animateCount={false} /> buffer from week {cash.firstWeekBelow}</>
              ) : (
                <>Stays above your <MoneyText amountMinor={cash.bufferMinor} currency={briefing.currency} animateCount={false} /> buffer</>
              )
            ) : "The forecast could not be read."}
          </div>
          {cash && cash.weeks.length > 1 ? (
            <CashSpark weeks={cash.weeks} bufferMinor={cash.bufferMinor} currency={briefing.currency} />
          ) : (
            <Link className="summary-link arrow-link" href="/forecast">Open the forecast <ArrowRightIcon /></Link>
          )}
        </Card>

        <Card className="summary-card reveal" style={delay(140)}>
          <div className="summary-label">
            <span>Waiting for your approval</span>
            <span className={`summary-icon ${waiting > 0 ? "icon-amber" : "icon-green"}`}><ShieldCheckIcon /></span>
          </div>
          <strong className="summary-value">
            {approvals ? <>{approvals.waiting} <small>{approvals.waiting === 1 ? "proposal" : "proposals"}</small></> : "Unavailable"}
          </strong>
          <div className="summary-foot">
            {approvals && approvals.waiting > 0 ? (
              <span><MoneyText amountMinor={approvals.waitingMinor} currency={briefing.currency} animateCount={false} /> in payments, checked by the Guardian</span>
            ) : approvals ? "Run the team to plan this week's payments." : "Proposals could not be read."}
            {approvals && approvals.blocked > 0 && <span className="summary-pill">{approvals.blocked} blocked</span>}
          </div>
          <Link className="summary-link arrow-link" href="/approvals">
            Open approvals <ArrowRightIcon />
          </Link>
        </Card>

        <Card className="summary-card reveal" style={delay(200)}>
          <div className="summary-label">
            <span>Stock at cost</span>
            <span className="summary-icon icon-blue"><BoxIcon /></span>
          </div>
          <strong className="summary-value">
            {stock ? <MoneyText amountMinor={stock.atCostMinor} currency={briefing.currency} /> : "Unavailable"}
          </strong>
          <div className="summary-foot">
            {stock?.slowMinor ? <span><MoneyText amountMinor={stock.slowMinor} currency={briefing.currency} animateCount={false} /> in slow stock</span> : "Inventory analysis"}
          </div>
          {stock && stock.slowMinor && stock.atCostMinor > 0 ? (
            <div className="stock-split" aria-label={`${Math.round((stock.slowMinor / stock.atCostMinor) * 100)}% of stock is slow-moving`}>
              <span style={{ "--w": `${Math.min(100, (stock.slowMinor / stock.atCostMinor) * 100)}%` } as CSSProperties} />
            </div>
          ) : null}
          <Link className="summary-link arrow-link" href="/inventory">
            Inspect inventory <ArrowRightIcon />
          </Link>
        </Card>
      </section>

      <div className="briefing-columns">
        <section className="briefing-main-column reveal" style={delay(260)}>
          <div className="section-heading">
            <div>
              <span className="eyebrow">Priority queue</span>
              <h2>Worth a closer look {findings.length > 0 && <span className="count-badge">{findings.length}</span>}</h2>
              <p>Ranked by money at stake, at most two per source.</p>
            </div>
            <details className="ranking-help">
              <summary className="text-link"><InfoIcon /> How ranking works</summary>
              <p>Findings from the cash forecast, inventory analysis and bank reconciliation, ranked by the money each puts at stake. Each source shows at most two, so one issue cannot crowd out the rest.</p>
            </details>
          </div>

          <Card className="findings-panel">
            {findings.length === 0 ? (
              <EmptyState title={briefing.unavailable.includes("findings") ? "Findings could not be loaded" : "Nothing needs a closer look"}>
                {briefing.unavailable.includes("findings") ? "Try again in a moment." : "The engine found no open issues in your ledger."}
              </EmptyState>
            ) : (
              findings.map((f) => {
                const severity = f.severity === "critical" ? "high" : f.severity;
                return (
                  <FindingCard
                    key={f.id}
                    className={`finding-sev-${severity}`}
                    title={f.title}
                    description={f.detail ? readable(f.detail) : `From ${f.source === "forecast" ? "the cash forecast" : f.source === "reconciliation" ? "bank reconciliation" : `the ${f.source} analysis`}.`}
                    amountMinor={f.moneyMinor}
                    severity={severity}
                    source={f.source === "forecast" ? "Cash forecast" : f.source === "reconciliation" ? "Reconciliation" : "Inventory"}
                    time={f.createdAt}
                    action={f.action ? (
                      <Link className="button button-quiet finding-open arrow-link" href={f.action.route}>
                        {f.action.label} <ArrowRightIcon />
                      </Link>
                    ) : undefined}
                  />
                );
              })
            )}
          </Card>
          <p className="footnote">Forecasts and recommendations are decision support from your own data, not financial advice.</p>
        </section>

        <aside className="briefing-side-column">
          <Card className={`cash-callout reveal ${cashGap ? "" : "is-calm"}`} style={delay(320)}>
            <div className="callout-icon"><CompassIcon /></div>
            <span className="eyebrow">Cash forecast</span>
            <h3>{cashGap ? `Week ${cash?.firstWeekBelow} needs a plan` : "Cash stays above your buffer"}</h3>
            <p>
              {cashGap
                ? `The 13-week forecast drops below your cash buffer from week ${cash?.firstWeekBelow}. Ask the council whether to borrow, delay suppliers or sell down stock.`
                : "The 13-week forecast stays above the buffer you set."}
            </p>
            {cash && cash.shortfallMinor > 0 && (
              <div className="callout-stat">
                <span>Largest shortfall against the buffer</span>
                <MoneyText amountMinor={cash.shortfallMinor} currency={briefing.currency} />
              </div>
            )}
            <Link className="button button-primary callout-button arrow-link" href="/forecast">
              Explore the forecast <ArrowRightIcon />
            </Link>
          </Card>

          <Card className="team-card reveal" style={delay(380)}>
            <div className="team-card-heading">
              <span className="eyebrow">Your finance team</span>
              <span className="team-sample-dot" aria-hidden="true" />
            </div>
            <h3>Separation of powers</h3>
            <p>The Controller and Treasurer prepare, the CFO Strategist and Growth Analyst advise, the Guardian checks independently, and you decide.</p>
            <div className="team-avatars" aria-label="Five agent roles">
              {["CT", "TR", "CF", "GA", "G"].map((label, index) => (
                <span className={`team-avatar team-avatar-${index}`} key={label}>{label}</span>
              ))}
              <span>5 roles</span>
            </div>
            <Link className="text-link arrow-link" href="/council">
              <ChatIcon width="15" height="15" /> Ask the council a question <ArrowRightIcon />
            </Link>
          </Card>
        </aside>
      </div>
    </div>
  );
}
