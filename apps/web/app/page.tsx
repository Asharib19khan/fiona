import Link from "next/link";
import { Card, DegradedBanner, EmptyState, FindingCard, MoneyText } from "@fiona/ui";
import { getBriefing } from "@/lib/briefing";
import { getSession } from "@/lib/session";
import { LiveClock } from "@/components/live-clock";
import { Greeting } from "@/components/greeting";

export const dynamic = "force-dynamic";

/** First name from the account's display name; an email-only account uses the part before the @. */
function firstNameOf(name: string | undefined): string {
  const raw = (name ?? "").trim();
  if (!raw) return "there";
  const base = raw.includes("@") ? (raw.split("@")[0] ?? "").split(/[._-]+/)[0] : raw.split(/\s+/)[0];
  return base ? base.charAt(0).toUpperCase() + base.slice(1) : "there";
}

export default async function Home() {
  const [briefing, session] = await Promise.all([getBriefing(), getSession()]);
  const { cash, approvals, stock, findings } = briefing;
  const firstName = firstNameOf(session?.name);
  const needsYou = (approvals?.waiting ?? 0) + (cash && cash.firstWeekBelow ? 1 : 0);
  const meter = cash && cash.bufferMinor > 0 ? Math.max(4, Math.min(100, Math.round((Math.max(cash.lowestMinor, 0) / cash.bufferMinor) * 100))) : 0;

  return (
    <div className="briefing-page">
      <div className="page-kicker">
        <LiveClock />
      </div>

      <header className="page-heading">
        <div>
          <Greeting firstName={firstName} />
          <p>
            {needsYou === 0
              ? "Nothing needs you right now."
              : `${needsYou} ${needsYou === 1 ? "thing needs" : "things need"} you today.`}
          </p>
        </div>
        <Link className="button button-secondary heading-action" href="/approvals">
          Review approvals <span aria-hidden="true">↗</span>
        </Link>
      </header>


      {briefing.unavailable.length > 0 && (
        <DegradedBanner>Could not load: {briefing.unavailable.join(", ")}. The rest of the briefing is current.</DegradedBanner>
      )}

      <section className="summary-grid" aria-label="Business summary">
        <Card className="summary-card summary-cash">
          <div className="summary-label">
            <span>Lowest cash in the next 13 weeks</span>
            <span className={`summary-icon ${cash?.firstWeekBelow ? "icon-amber" : "icon-green"}`}>↓</span>
          </div>
          <strong className="summary-value">
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
          <div className="cash-meter"><span style={{ width: `${meter}%` }} /></div>
        </Card>

        <Card className="summary-card">
          <div className="summary-label">
            <span>Waiting for your approval</span>
            <span className="summary-icon icon-amber">!</span>
          </div>
          <strong className="summary-value">
            {approvals ? <>{approvals.waiting} <small>{approvals.waiting === 1 ? "proposal" : "proposals"}</small></> : "Unavailable"}
          </strong>
          <div className="summary-foot">
            {approvals && approvals.waiting > 0 ? (
              <><MoneyText amountMinor={approvals.waitingMinor} currency={briefing.currency} animateCount={false} />&nbsp;in payments, checked by the Guardian</>
            ) : approvals ? "Run the team to plan this week's payments." : "Proposals could not be read."}
            {approvals && approvals.blocked > 0 ? ` · ${approvals.blocked} blocked` : ""}
          </div>
          <Link className="summary-link" href="/approvals">
            Open approvals <span aria-hidden="true">→</span>
          </Link>
        </Card>

        <Card className="summary-card">
          <div className="summary-label">
            <span>Stock at cost</span>
            <span className="summary-icon icon-blue">▤</span>
          </div>
          <strong className="summary-value">
            {stock ? <MoneyText amountMinor={stock.atCostMinor} currency={briefing.currency} /> : "Unavailable"}
          </strong>
          <div className="summary-foot">
            {stock?.slowMinor ? <><MoneyText amountMinor={stock.slowMinor} currency={briefing.currency} animateCount={false} />&nbsp;in slow stock</> : "Inventory analysis"}
          </div>
          <Link className="summary-link" href="/inventory">
            Inspect inventory <span aria-hidden="true">→</span>
          </Link>
        </Card>
      </section>

      <div className="briefing-columns">
        <section className="briefing-main-column">
          <div className="section-heading">
            <div>
              <span className="eyebrow">PRIORITY QUEUE</span>
              <h2>Worth a closer look</h2>
              <p>Ranked by money at stake. At most two items per source, so one issue cannot crowd out the rest.</p>
            </div>
            <details className="ranking-help">
              <summary className="text-link">How ranking works <span aria-hidden="true">↗</span></summary>
              <p>Findings from the cash forecast, inventory analysis and bank reconciliation, ranked by the money each puts at stake.</p>
            </details>
          </div>

          <Card className="findings-panel">
            {findings.length === 0 ? (
              <EmptyState title={briefing.unavailable.includes("findings") ? "Findings could not be loaded" : "Nothing needs a closer look"}>
                {briefing.unavailable.includes("findings") ? "Try again in a moment." : "The engine found no open issues in your ledger."}
              </EmptyState>
            ) : (
              findings.map((f) => (
                <FindingCard
                  key={f.id}
                  title={f.title}
                  description={f.detail ?? `From ${f.source === "forecast" ? "the cash forecast" : f.source === "reconciliation" ? "bank reconciliation" : `the ${f.source} analysis`}.`}
                  amountMinor={f.moneyMinor}
                  severity={f.severity === "critical" ? "high" : f.severity}
                  source={f.source === "forecast" ? "Cash forecast" : f.source === "reconciliation" ? "Reconciliation" : "Inventory"}
                  time={f.createdAt}
                  action={f.action ? (
                    <Link className="button button-quiet finding-open" href={f.action.route}>
                      {f.action.label} <span aria-hidden="true">→</span>
                    </Link>
                  ) : undefined}
                />
              ))
            )}
          </Card>
          <p className="footnote">Forecasts and recommendations are decision support from your own data, not financial advice.</p>
        </section>

        <aside className="briefing-side-column">
          <Card className="cash-callout">
            <div className="callout-icon">↗</div>
            <span className="eyebrow">CASH FORECAST</span>
            <h3>{cash?.firstWeekBelow ? `Week ${cash.firstWeekBelow} needs a plan` : "Cash stays above your buffer"}</h3>
            <p>
              {cash?.firstWeekBelow
                ? `The 13-week forecast drops below your cash buffer from week ${cash.firstWeekBelow}. Ask the council whether to borrow, delay suppliers or sell down stock.`
                : "The 13-week forecast stays above the buffer you set."}
            </p>
            {cash && cash.shortfallMinor > 0 && (
              <div className="callout-stat">
                <span>Largest shortfall against the buffer</span>
                <MoneyText amountMinor={cash.shortfallMinor} currency={briefing.currency} />
              </div>
            )}
            <Link className="button button-primary callout-button" href="/forecast">
              Explore the forecast <span aria-hidden="true">→</span>
            </Link>
          </Card>

          <Card className="team-card">
            <div className="team-card-heading">
              <span className="eyebrow">YOUR FINANCE TEAM</span>
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
            <Link className="text-link" href="/council">
              Ask the council a question <span aria-hidden="true">→</span>
            </Link>
          </Card>
        </aside>
      </div>
    </div>
  );
}
