import Link from "next/link";
import { Card, DegradedBanner, EmptyState, ErrorState, FindingCard, MoneyText, StateChip } from "@fiona/ui";
import { briefingScenarios, getMockBriefing } from "@/lib/mock-api";

export default async function Home({ searchParams }: { searchParams: Promise<{ scenario?: string | string[] }> }) {
  const params = await searchParams;
  const requestedScenario = Array.isArray(params.scenario) ? params.scenario[0] : params.scenario;
  const scenario = briefingScenarios.find((known) => known === requestedScenario) ?? "default";
  const briefing = getMockBriefing(scenario);
  if (!briefing) return <div className="briefing-page"><ErrorState requestId="req_live_sync_retry" /></div>;

  const cards = briefing.cards;
  const cashCard = cards.find((card) => card.finding_id === "fnd_01JC8R4K2M");
  const cashAtStake = cashCard?.money_at_stake?.minor ?? 175_388_100;

  return (
    <div className="briefing-page">
      <div className="page-kicker">
        <span className="eyebrow">EXECUTIVE BRIEFING · KARACHI APPAREL</span>
        <StateChip>Sovereign Node 01</StateChip>
      </div>

      <header className="page-heading">
        <div>
          <h1>Enterprise Treasury & Operational Pulse</h1>
          <p>{briefing.greeting.text}</p>
        </div>
        <Link className="button button-secondary heading-action" href="/approvals">
          Review Pending Approvals <span aria-hidden="true">↗</span>
        </Link>
      </header>

      <div className="data-note">
        <span aria-hidden="true">◈</span>
        <span>
          <strong>Live Sovereign Audit Chain</strong> · Deterministic financial telemetry verified against RFC 8785 canonical hash chain.
        </span>
        <span className="data-note-date">Ledger State · {briefing.generated_at.slice(0, 10)}</span>
      </div>

      <section className="summary-grid" aria-label="Business summary">
        <Card className="summary-card summary-cash">
          <div className="summary-label">
            <span>Minimum Liquidity Forecast</span>
            <span className="summary-icon icon-green">↓</span>
          </div>
          <strong className="summary-value">
            <MoneyText amountMinor={24_611_900} />
          </strong>
          <div className="summary-foot">
            <span className="summary-alert-dot" /> Below your <MoneyText amountMinor={200_000_000} /> policy buffer in Week 7
          </div>
          <div className="cash-meter">
            <span />
          </div>
        </Card>

        <Card className="summary-card">
          <div className="summary-label">
            <span>Action Required</span>
            <span className="summary-icon icon-amber">!</span>
          </div>
          <strong className="summary-value">
            {briefing.greeting.needs_owner_count} <small>proposals</small>
          </strong>
          <div className="summary-foot">Pending Guardian verification and owner signature</div>
          <Link className="summary-link" href="/approvals">
            Open Approvals Pipeline <span aria-hidden="true">→</span>
          </Link>
        </Card>

        <Card className="summary-card">
          <div className="summary-label">
            <span>Inventory Valuation at Cost</span>
            <span className="summary-icon icon-blue">▤</span>
          </div>
          <strong className="summary-value">
            <MoneyText amountMinor={1_055_300_000} />
          </strong>
          <div className="summary-foot">Reconciled stock holding · Dickinson Stage: Mature</div>
          <Link className="summary-link" href="/inventory">
            Inspect Inventory Health <span aria-hidden="true">→</span>
          </Link>
        </Card>
      </section>

      <div className="briefing-columns">
        <section className="briefing-main-column">
          <div className="section-heading">
            <div>
              <span className="eyebrow">PRIORITY QUEUE</span>
              <h2>Capital Allocation & Risk Items</h2>
              <p>Ranked deterministically by capital exposure. High-urgency proposals require executive sign-off.</p>
            </div>
            <details className="ranking-help">
              <summary className="text-link">Ranking logic <span aria-hidden="true">↗</span></summary>
              <p>The priority queue ranks findings by estimated money at stake, using Guardian policy severity to break ties.</p>
            </details>
          </div>

          <Card className="findings-panel">
            {briefing.degraded.length > 0 && (
              <div className="findings-state">
                <DegradedBanner>
                  {briefing.degraded.map((item) => `${item.source}: ${item.detail}`).join(" ")}
                </DegradedBanner>
              </div>
            )}
            {cards.length === 0 ? (
              <EmptyState title="All Policy Invariants Cleared">
                There are zero unresolved exposures in the priority queue.
              </EmptyState>
            ) : (
              cards.map((card) => {
                const action = card.actions[0];
                const guardian = card.kind === "guardian" ? { outcome: "block" as const } : {};
                return (
                  <FindingCard
                    key={card.id}
                    title={card.title}
                    description={card.detail ?? "No further detail is available."}
                    amountMinor={card.money_at_stake?.minor ?? 0}
                    severity={card.severity}
                    source={card.source_label}
                    time={briefing.generated_at}
                    {...guardian}
                    action={
                      action ? (
                        <Link className="button button-quiet finding-open" href={action.route}>
                          {action.label} <span aria-hidden="true">→</span>
                        </Link>
                      ) : undefined
                    }
                  />
                );
              })
            )}
          </Card>
          <p className="footnote">
            All forecasts and suggestions are generated deterministically by the engine and verified by Guardian invariants before settlement.
          </p>
        </section>

        <aside className="briefing-side-column">
          <Card className="cash-callout">
            <div className="callout-icon">↗</div>
            <span className="eyebrow">CASH FORECAST</span>
            <h3>Week 7 Liquidity Alert</h3>
            <p>Direct cash forecast projects an operating dip below the mandatory PKR 200M buffer due to seasonal stock overlapping payroll.</p>
            <div className="callout-stat">
              <span>Capital exposure at stake</span>
              <MoneyText amountMinor={cashAtStake} />
            </div>
            <Link className="button button-primary callout-button" href="/forecast">
              Explore 13-Week Forecast <span aria-hidden="true">→</span>
            </Link>
          </Card>

          <Card className="team-card">
            <div className="team-card-heading">
              <span className="eyebrow">AUTONOMOUS COUNCIL</span>
              <span className="team-sample-dot" aria-label="Autonomous roles active" />
            </div>
            <h3>Separation of Powers</h3>
            <p>Fiona mathematically decouples preparation, advice, and independent Guardian risk verification.</p>
            <div className="team-avatars" aria-label="Five AI agent roles">
              {["CT", "TR", "CF", "GA", "G"].map((label, index) => (
                <span className={`team-avatar team-avatar-${index}`} key={label}>
                  {label}
                </span>
              ))}
              <span>5 Active Roles</span>
            </div>
            <Link className="text-link" href="/audit">
              Inspect Agent Audit Chain <span aria-hidden="true">→</span>
            </Link>
          </Card>
        </aside>
      </div>
    </div>
  );
}
