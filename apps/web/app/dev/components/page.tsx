import { notFound } from "next/navigation";
import { AgentChip, AutonomyBadge, Card, DegradedBanner, EmptyState, ErrorState, FindingCard, MoneyText, OutcomeBadge, StateChip } from "@fiona/ui";

export default function ComponentsPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <div className="section-page component-gallery"><span className="eyebrow">DEVELOPMENT ONLY</span><h1>Window components</h1><p className="gallery-intro">A visual reference for the building blocks shared across Fiona’s screens.</p>
    <section className="gallery-section"><h2>Status and outcomes</h2><div className="gallery-row"><StateChip>Mock data</StateChip><StateChip>Synthetic business</StateChip><OutcomeBadge outcome="approve" /><OutcomeBadge outcome="conditions" /><OutcomeBadge outcome="escalate" /><OutcomeBadge outcome="block" /></div></section>
    <section className="gallery-section"><h2>People and policy</h2><div className="gallery-row"><AgentChip name="Treasurer" role="Payments" /><AutonomyBadge>PKR 150,000 per payment</AutonomyBadge></div></section>
    <section className="gallery-section"><h2>Money</h2><div className="gallery-row gallery-money"><MoneyText amountMinor={18450000} /><MoneyText amountMinor={-1250000} currency="CNY" /></div></section>
    <section className="gallery-section"><h2>Feedback states</h2><DegradedBanner>Inventory data is a labelled synthetic sample.</DegradedBanner><ErrorState requestId="req_demo_82c19" /><Card><EmptyState title="Nothing needs your attention">Your team has no new items right now.</EmptyState></Card></section>
    <section className="gallery-section"><h2>Finding card</h2><Card><FindingCard title="Cash dips below your buffer in week 7" description="Winter stock bills overlap payroll, rent and the loan instalment." amountMinor={175388100} severity="high" source="Cash forecast · seed-42 mock" time="2026-10-22T04:00:00Z" outcome="escalate" /></Card></section>
  </div>;
}
