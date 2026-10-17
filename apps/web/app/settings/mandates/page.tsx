import { AutonomyBadge, Card, EmptyState, MoneyText, StateChip } from "@fiona/ui";
import { getMockMandates } from "@/lib/mock-api";
import { routes } from "@/lib/routes";

const limits = [
  { agent: "Controller", job: "Prepare and classify records", limit: "Cannot move money" },
  { agent: "Treasurer", job: "Prepare payment proposals", limit: "Within an owner mandate" },
  { agent: "CFO Strategist", job: "Analyze and recommend", limit: "Owner decides" },
  { agent: "Growth Analyst", job: "Model business scenarios", limit: "Owner decides" },
];

export default function MandatesPage() {
  const [treasurer] = getMockMandates();
  return <div className="section-page"><div className="page-kicker"><span className="eyebrow">KARACHI APPAREL</span><StateChip>Mock data</StateChip></div><header className="page-heading"><div><h1>{routes.mandates.label}</h1><p>{routes.mandates.description}</p></div></header>
    <Card className="mandates-panel"><div className="panel-heading"><div><span className="eyebrow">DEMO OWNER POLICY</span><h2>What each agent can do</h2></div><span className="placeholder-tag">MOCK API</span></div><div className="mandate-rows">{limits.map((item) => <div className="mandate-row" key={item.agent}><div><strong>{item.agent}</strong><span>{item.job}</span></div><AutonomyBadge>{item.limit}</AutonomyBadge></div>)}{treasurer && <div className="mandate-row"><div><strong>Treasurer’s active contract mandate</strong><span>Daily cap <MoneyText amountMinor={treasurer.daily_cap_minor} currency={treasurer.currency} /></span></div><AutonomyBadge><MoneyText amountMinor={treasurer.per_payment_cap_minor} currency={treasurer.currency} /> per payment</AutonomyBadge></div>}</div><EmptyState title="Policy editing is not enabled">These values are read from a synthetic contract fixture. Changes need a connected owner session and server-side enforcement.</EmptyState></Card>
    <p className="footnote">Illustrative policy values only. The live wallet and approval enforcement are not connected to this page.</p></div>;
}
