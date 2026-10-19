import Link from "next/link";
import type { CSSProperties } from "react";
import { Card, DegradedBanner, EmptyState, FindingCard, MoneyText, StateChip } from "@fiona/ui";
import { getForecast, type ForecastNote } from "@/lib/forecast";
import { readable, sourceLabel } from "@/lib/finding-text";
import { routes } from "@/lib/routes";
import { basisPointsText } from "@/lib/figure-format";
import { ForecastWorkbench } from "@/components/forecast-workbench";
import { PagedList } from "@/components/paged";
import { ArrowRightIcon, ChatIcon, CompassIcon, InfoIcon, ShieldCheckIcon, TrendDownIcon, TrendUpIcon } from "@/components/briefing-icons";

const delay = (ms: number) => ({ "--d": `${ms}ms` }) as CSSProperties;
const LONG = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const SHORT = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
const date = (iso: string, f = SHORT) => f.format(new Date(`${iso.slice(0, 10)}T00:00:00Z`));

function noteValue(n: ForecastNote, currency: string) {
  if (n.minor !== null) return <MoneyText amountMinor={n.minor} currency={currency} animateCount={false} />;
  if (n.value === null) return "—";
  if (n.unit === "bp") return (n.value / 10_000).toLocaleString("en", { maximumFractionDigits: 4 });
  return `${n.value.toLocaleString("en")} ${n.unit}`;
}

/** The Cash forecast screen: the verdict first, then the chart and the week behind it, then what to do. */
export async function ForecastScreen() {
  const page = routes.forecast;
  const result = await getForecast();

  if (result.kind === "unavailable") {
    return (
      <div className="section-page fc-page">
        <header className="page-heading"><div><h1>{page.label}</h1><p>{page.description}</p></div></header>
        <DegradedBanner>The cash forecast could not be computed right now (the engine did not answer). No figures are shown rather than old ones.</DegradedBanner>
      </div>
    );
  }

  const { forecast: f, findings, findingsLoaded } = result;
  const c = f.currency;
  const breach = f.weeks.find((w) => w.week === f.firstWeekBelow) ?? null;
  const lowWeek = f.weeks.find((w) => w.week === f.lowestWeek) ?? null;
  const weeksBelow = f.weeks.filter((w) => w.below).length;
  const blocking = f.gaps.filter((g) => g.blocking);

  return (
    <div className="section-page fc-page">
      <header className="page-heading fc-rise" style={delay(0)}>
        <div>
          <div className="page-kicker fc-kicker">
            <StateChip>Computed from your ledger</StateChip>
            {f.asOf && <StateChip>Ledger as of {date(f.asOf, LONG)}</StateChip>}
            <StateChip>{f.weeks.length}-week view</StateChip>
          </div>
          <h1>{page.label}</h1>
          <p>
            {breach ? (
              <><strong>Cash drops below your <MoneyText amountMinor={f.bufferMinor} currency={c} animateCount={false} /> buffer in week {breach.week}</strong> ({date(breach.start)} – {date(breach.end)}){weeksBelow > 1 ? ` and stays below for ${weeksBelow} weeks` : ""}.</>
            ) : (
              <><strong>Cash stays above your <MoneyText amountMinor={f.bufferMinor} currency={c} animateCount={false} /> buffer</strong> for all {f.weeks.length} weeks.</>
            )}
          </p>
        </div>
        <div className="fc-heading-actions">
          <Link className="button button-secondary arrow-link" href="/council"><ChatIcon width="15" height="15" /> Ask the council</Link>
          {breach && <Link className="button button-primary arrow-link" href="/financing">Compare financing <ArrowRightIcon /></Link>}
        </div>
      </header>

      {blocking.length > 0 && <DegradedBanner>Missing data: {blocking.map((g) => g.need).join("; ")}. Figures that need it are not shown.</DegradedBanner>}

      <section className="fc-kpis" aria-label="Forecast summary">
        <Card className="fc-kpi fc-rise" style={delay(60)}>
          <div className="fc-kpi-top"><span>Cash today</span><span className="summary-icon icon-blue"><ShieldCheckIcon /></span></div>
          <strong>{f.openingMinor !== null ? <MoneyText amountMinor={f.openingMinor} currency={c} /> : "Not available"}</strong>
          <small className="fc-kpi-lines">
            {f.receivablesMinor !== null && <span>Customers owe you <b><MoneyText amountMinor={f.receivablesMinor} currency={c} animateCount={false} /></b></span>}
            {f.payablesMinor !== null && <span>You owe suppliers <b><MoneyText amountMinor={f.payablesMinor} currency={c} animateCount={false} /></b></span>}
          </small>
        </Card>
        <Card className={`fc-kpi fc-rise ${f.lowestMinor < f.bufferMinor ? "is-alert" : ""}`} style={delay(110)}>
          <div className="fc-kpi-top"><span>Lowest point</span><span className={`summary-icon ${f.lowestMinor < f.bufferMinor ? "icon-danger" : "icon-green"}`}>{f.lowestMinor < f.bufferMinor ? <TrendDownIcon /> : <TrendUpIcon />}</span></div>
          <strong className={f.lowestMinor < 0 ? "is-negative" : ""}><MoneyText amountMinor={f.lowestMinor} currency={c} /></strong>
          <small>{lowWeek ? <>Week {lowWeek.week} · {date(lowWeek.start)} – {date(lowWeek.end)}</> : "Across the forecast"}</small>
        </Card>
        <Card className={`fc-kpi fc-rise ${breach ? "is-alert" : ""}`} style={delay(160)}>
          <div className="fc-kpi-top"><span>First week below buffer</span><span className={`summary-icon ${breach ? "icon-amber" : "icon-green"}`}><CompassIcon /></span></div>
          <strong>{breach ? `Week ${breach.week}` : "None"}</strong>
          <small>{breach ? <>{date(breach.start)} – {date(breach.end)} · {weeksBelow} {weeksBelow === 1 ? "week" : "weeks"} below in total</> : "No week falls below the buffer"}</small>
        </Card>
        <Card className="fc-kpi fc-rise" style={delay(210)}>
          <div className="fc-kpi-top"><span>Largest shortfall</span><span className={`summary-icon ${f.shortfallMinor > 0 ? "icon-danger" : "icon-green"}`}>{f.shortfallMinor > 0 ? <TrendDownIcon /> : <ShieldCheckIcon />}</span></div>
          <strong className={f.shortfallMinor > 0 ? "is-warning" : ""}><MoneyText amountMinor={f.shortfallMinor} currency={c} /></strong>
          <small>How far the lowest week falls under the buffer</small>
        </Card>
      </section>

      {f.weeks.length ? (
        <ForecastWorkbench weeks={f.weeks} bufferMinor={f.bufferMinor} currency={c} initialWeek={f.firstWeekBelow ?? f.lowestWeek ?? f.weeks[0]?.week ?? 1} />
      ) : (
        <Card className="fc-table-card"><EmptyState title="No forecast weeks">The engine returned a forecast with no weeks in it.</EmptyState></Card>
      )}

      <div className="fc-bottom">
        <section className="fc-alerts fc-rise" style={delay(400)}>
          <div className="section-heading">
            <div>
              <span className="eyebrow">Ranked alerts</span>
              <h2>Alerts by money at stake {findings.length > 0 && <span className="count-badge">{findings.length}</span>}</h2>
              <p>From the cash forecast and the analyses that feed it, largest first.</p>
            </div>
          </div>
          <Card className="findings-panel">
            {findings.length ? <PagedList className="fc-findings" pageSize={6} noun="alerts" items={findings.map((x) => {
              const severity = x.severity === "critical" ? "high" : x.severity;
              return (
                <FindingCard
                  key={x.id}
                  className={`finding-sev-${severity}`}
                  title={x.title}
                  description={x.detail ? readable(x.detail) : `Raised by ${sourceLabel(x.source).toLowerCase()}.`}
                  amountMinor={x.moneyMinor}
                  severity={severity}
                  source={sourceLabel(x.source)}
                  time={x.createdAt}
                  action={x.action && x.action.route !== "/forecast" ? <Link className="button button-quiet finding-open arrow-link" href={x.action.route}>{x.action.label} <ArrowRightIcon /></Link> : undefined}
                />
              );
            })} /> : (
              <EmptyState title={findingsLoaded ? "No alerts" : "Alerts could not be loaded"}>
                {findingsLoaded ? "No alerts are open right now." : "The forecast itself is current; try the alerts again in a moment."}
              </EmptyState>
            )}
          </Card>
        </section>

        <aside className="fc-side">
          <Card className={`fc-plan fc-rise ${breach ? "" : "is-calm"}`} style={delay(460)}>
            <span className="eyebrow">{breach ? "Close the gap" : "Next steps"}</span>
            <h3>{breach ? <>Find <MoneyText amountMinor={f.shortfallMinor} currency={c} /> before week {breach.week}</> : "Keep the buffer intact"}</h3>
            <ul className="fc-plan-list">
              <li><Link className="arrow-link" href="/financing"><span><b>Compare financing</b><small>Eligible options sized to the shortfall</small></span><ArrowRightIcon /></Link></li>
              <li><Link className="arrow-link" href="/decisions/payment-timing"><span><b>Move payment dates</b><small>Weigh supplier discounts against the buffer</small></span><ArrowRightIcon /></Link></li>
              <li><Link className="arrow-link" href="/inventory"><span><b>Free up cash from stock</b><small>Slow-moving stock you could sell down</small></span><ArrowRightIcon /></Link></li>
              <li><Link className="arrow-link" href="/council"><span><b>Ask the council</b><small>The CFO Strategist and Treasurer weigh the options</small></span><ArrowRightIcon /></Link></li>
            </ul>
          </Card>

          <Card className="fc-method fc-rise" style={delay(520)}>
            <details>
              <summary><InfoIcon /> How this forecast is made</summary>
              <div className="fc-method-body">
                {f.method.description && <p>{f.method.description}</p>}
                {f.method.history && <p><b>History used:</b> {date(f.method.history.start, LONG)} to {date(f.method.history.end, LONG)}</p>}
                {f.method.band && <p><b>Likely range:</b> {f.method.band}</p>}
                {f.assumptions.length > 0 && (
                  <ul>
                    {f.assumptions.map((a) => (
                      <li key={a.label}><span>{a.label}</span><span>{noteValue(a, c)}{!a.verified && <em> · unverified</em>}</span></li>
                    ))}
                  </ul>
                )}
                {f.method.backtest.length > 0 && (
                  <>
                    <p><b>Backtest:</b> how past forecasts compared with what happened.</p>
                    <ul>
                      {f.method.backtest.map((b) => (
                        <li key={b.metricId || b.label}><span>{b.label}</span><span>{b.minor !== null ? <MoneyText amountMinor={b.minor} currency={c} animateCount={false} /> : b.value !== null ? (b.unit === "bp" ? basisPointsText(b.value, b.metricId) : `${b.value.toLocaleString("en")} ${b.unit}`) : "—"}</span></li>
                      ))}
                    </ul>
                  </>
                )}
                {f.gaps.filter((g) => !g.blocking).map((g) => <p className="fc-gap" key={g.need}><b>Would improve with:</b> {g.need}. {g.why}</p>)}
              </div>
            </details>
          </Card>
        </aside>
      </div>

      <p className="footnote">Forecasts are decision support, computed from your posted ledger: last year&rsquo;s seasonal pattern scaled to recent trading, plus the bills, invoices and loan payments already due. This page does not schedule a payment.</p>
    </div>
  );
}
