import { notFound } from "next/navigation";
import { Card, DegradedBanner, EmptyState, MoneyText, StateChip } from "@fiona/ui";
import { routes } from "@/lib/routes";
import { postEngine, objectValue } from "@/lib/server-read";

type Obj = Record<string, unknown>;
function object(value: unknown): Obj | null { return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Obj : null; }
function objects(value: unknown): Obj[] { return Array.isArray(value) ? value.map(object).filter((item): item is Obj => item !== null) : []; }
function amount(value: unknown): number | null { const money = object(value); return money && typeof money.minor === "number" ? money.minor : null; }

export default async function DecisionPage({ params }: { params: Promise<{ decision: string }> }) {
  const { decision } = await params;
  if (decision !== "payment-timing") notFound();
  const page = routes[decision];
  const response = await postEngine("decisions/payment-timing", { horizon_weeks: 13 });
  const data = response.kind === "ok" && response.status === 200 ? objectValue(response.data) : null;
  const bills = objects(data?.bills);
  const weeks = objects(data?.weeks);
  const cost = object(data?.cost_of_money);
  const buffer = object(data?.buffer);
  return <div className="section-page"><div className="page-kicker"><StateChip>{data ? "Engine · read only" : "Engine unavailable"}</StateChip></div><header className="page-heading"><div><h1>{page.label}</h1><p>{page.description}</p></div></header>
    {!data && <DegradedBanner>{response.kind === "unavailable" ? response.message : "Start the local engine and fixture database to load bill timing recommendations."}</DegradedBanner>}
    <div className="tier-metric-grid"><Card className="tier-metric"><span className="eyebrow">COST OF MONEY</span><strong>{typeof cost?.value === "number" ? `${(cost.value / 100).toFixed(2)}%` : "Not available"}</strong><small>{String(cost?.formula ?? "Engine-calculated funding rate")}</small></Card><Card className="tier-metric"><span className="eyebrow">CASH BUFFER</span><strong>{amount(buffer?.money) !== null ? <MoneyText amountMinor={amount(buffer?.money) ?? 0} /> : "Not available"}</strong><small>Tenant policy</small></Card><Card className="tier-metric"><span className="eyebrow">BILLS REVIEWED</span><strong>{bills.length}</strong><small>Discount must beat funding cost and preserve the cash buffer.</small></Card></div>
    <Card className="tier-panel"><div className="panel-heading"><div><span className="eyebrow">PAYMENT SUGGESTIONS</span><h2>Discount value against cash safety</h2></div><span className="placeholder-tag">No payment is scheduled</span></div>{bills.length ? <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Supplier</th><th>Bill</th><th>Due</th><th>Amount</th><th>Recommendation</th><th>Pay on</th></tr></thead><tbody>{bills.map((bill, index) => <tr key={String(bill.bill_id ?? index)}><td>{String(bill.supplier_name ?? bill.supplier_id ?? "—")}</td><td>{String(bill.bill_id ?? "—")}</td><td>{String(bill.due_date ?? "—")}</td><td><MoneyText amountMinor={amount(bill.amount) ?? 0} currency={String(object(bill.amount)?.currency ?? "PKR")} /></td><td>{String(bill.action ?? "—").replaceAll("_", " ")}</td><td>{String(bill.pay_on ?? "—")}</td></tr>)}</tbody></table></div> : <EmptyState title="No open bills returned">The optimiser reports bill-level recommendations when the seeded ledger has open supplier bills.</EmptyState>}</Card>
    <Card className="tier-panel"><div className="panel-heading"><div><span className="eyebrow">WEEKLY CASH IMPACT</span><h2>Projected payments and buffer check</h2></div></div>{weeks.length ? <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Week</th><th>Payments</th><th>Closing before</th><th>Closing after</th><th>Buffer</th></tr></thead><tbody>{weeks.map((week, index) => <tr key={index}><td>{String(week.week ?? index + 1)} · {String(week.start ?? "")}</td><td><MoneyText amountMinor={amount(week.payments) ?? 0} currency={String(object(week.payments)?.currency ?? "PKR")} /></td><td><MoneyText amountMinor={amount(week.closing_before) ?? 0} currency={String(object(week.closing_before)?.currency ?? "PKR")} /></td><td><MoneyText amountMinor={amount(week.closing_after) ?? 0} currency={String(object(week.closing_after)?.currency ?? "PKR")} /></td><td>{week.below_buffer === true ? "Below buffer" : "Within buffer"}</td></tr>)}</tbody></table></div> : <EmptyState title="No cash path returned">The optimiser needs a cash forecast to evaluate timing changes.</EmptyState>}</Card>
    <p className="footnote">Recommendations are advisory. Only the owner can approve a proposal, and the payment wallet accepts simulated payments only.</p>
  </div>;
}
