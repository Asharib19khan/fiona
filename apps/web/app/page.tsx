import Link from "next/link";
import { Card, DegradedBanner, EmptyState, ErrorState, FindingCard, MoneyText, StateChip } from "@fiona/ui";
import { briefingScenarios, getMockBriefing } from "@/lib/mock-api";

export default async function Home({ searchParams }: { searchParams: Promise<{ scenario?: string | string[] }> }) {
  const params = await searchParams;
  const requestedScenario = Array.isArray(params.scenario) ? params.scenario[0] : params.scenario;
  const scenario = briefingScenarios.find((known) => known === requestedScenario) ?? "default";
  const briefing = getMockBriefing(scenario);
  if (!briefing) return <div className="briefing-page"><ErrorState requestId="req_demo_unavailable" /></div>;

  const cards = briefing.cards;
  const cashCard = cards.find((card) => card.finding_id === "fnd_01JC8R4K2M");
  const cashAtStake = cashCard?.money_at_stake?.minor ?? 175_388_100;

  return <div className="briefing-page">
    <div className="page-kicker"><span className="eyebrow">BUSINESS BRIEFING</span>{briefing.meta.replayed ? <StateChip>Replayed</StateChip> : <StateChip>Seed-42 mock</StateChip>}</div>
    <header className="page-heading"><div><h1>Your business, at a glance</h1><p>{briefing.greeting.text}</p></div><Link className="button button-secondary heading-action" href="/approvals">Review approvals <span aria-hidden="true">↗</span></Link></header>
    <div className="data-note"><span aria-hidden="true">◈</span><span><strong>Synthetic demo data</strong> · Contract-backed Seed-42 mock response. No real accounts or transactions.</span><span className="data-note-date">Snapshot · {briefing.generated_at.slice(0, 10)}</span></div>
    <section className="summary-grid" aria-label="Business summary">
      <Card className="summary-card summary-cash"><div className="summary-label"><span>Cash at lowest point</span><span className="summary-icon icon-green">↓</span></div><strong className="summary-value"><MoneyText amountMinor={24_611_900} /></strong><div className="summary-foot"><span className="summary-alert-dot" /> Below your <MoneyText amountMinor={200_000_000} /> buffer in week 7</div><div className="cash-meter"><span /></div></Card>
      <Card className="summary-card"><div className="summary-label"><span>Needs your attention</span><span className="summary-icon icon-amber">!</span></div><strong className="summary-value">{briefing.greeting.needs_owner_count} <small>items</small></strong><div className="summary-foot">Across cash flow and Guardian review</div><Link className="summary-link" href="/approvals">See what needs you <span aria-hidden="true">→</span></Link></Card>
      <Card className="summary-card"><div className="summary-label"><span>Stock at cost</span><span className="summary-icon icon-blue">▤</span></div><strong className="summary-value"><MoneyText amountMinor={1_055_300_000} /></strong><div className="summary-foot">Inventory snapshot · synthetic ledger</div><Link className="summary-link" href="/inventory">Explore inventory <span aria-hidden="true">→</span></Link></Card>
    </section>
    <div className="briefing-columns">
      <section className="briefing-main-column">
        <div className="section-heading"><div><span className="eyebrow">PRIORITY QUEUE</span><h2>Worth a closer look</h2><p>Ranked by estimated money at stake. Suggestions need your review.</p></div><details className="ranking-help"><summary className="text-link">How ranking works <span aria-hidden="true">↗</span></summary><p>The sample feed ranks findings by estimated money at stake and uses severity to break ties. Values are illustrative.</p></details></div>
        <Card className="findings-panel">
          {briefing.degraded.length > 0 && <div className="findings-state"><DegradedBanner>{briefing.degraded.map((item) => `${item.source}: ${item.detail}`).join(" ")}</DegradedBanner></div>}
          {cards.length === 0 ? <EmptyState title={scenario === "clean" ? "You’re all caught up" : "No demo findings"}>{scenario === "clean" ? "There are no open items in this clean scenario." : "This scenario has no findings to show."}</EmptyState> : cards.map((card) => {
            const action = card.actions[0];
            const guardian = card.kind === "guardian" ? { outcome: "block" as const } : {};
            return <FindingCard key={card.id} title={card.title} description={card.detail ?? "No further detail is available."} amountMinor={card.money_at_stake?.minor ?? 0} severity={card.severity} source={card.source_label} time={briefing.generated_at} {...guardian} action={action ? <Link className="button button-quiet finding-open" href={action.route}>{action.label} <span aria-hidden="true">→</span></Link> : undefined} />;
          })}
        </Card>
        <p className="footnote">Values are from synthetic demo fixtures. Forecasts and recommendations are examples, not financial advice.</p>
      </section>
      <aside className="briefing-side-column">
        <Card className="cash-callout"><div className="callout-icon">↗</div><span className="eyebrow">CASH FORECAST</span><h3>A tighter week is ahead</h3><p>The contract-backed mock forecast shows a shortfall against the demo cash buffer in week 7.</p><div className="callout-stat"><span>Estimated money at stake</span><MoneyText amountMinor={cashAtStake} /></div><Link className="button button-primary callout-button" href="/forecast">Explore cash forecast <span aria-hidden="true">→</span></Link></Card>
        <Card className="team-card"><div className="team-card-heading"><span className="eyebrow">YOUR FINANCE TEAM</span><span className="team-sample-dot" aria-label="Illustrative team roles" /></div><h3>Five roles, one finance team</h3><p>The demo shows how Fiona separates preparation, advice and independent review.</p><div className="team-avatars" aria-label="Five AI agent roles">{["CT", "TR", "CF", "GA", "G"].map((label, index) => <span className={`team-avatar team-avatar-${index}`} key={label}>{label}</span>)}<span>5 agent roles</span></div><Link className="text-link" href="/audit">See sample activity <span aria-hidden="true">→</span></Link></Card>
      </aside>
    </div>
  </div>;
}
