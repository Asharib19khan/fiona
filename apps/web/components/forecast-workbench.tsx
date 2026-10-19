"use client";

import { useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import { MoneyText, toMajor } from "@fiona/ui";
import type { ForecastLine, ForecastWeek } from "@/lib/forecast";

const CATEGORY: Record<string, string> = {
  pos_sales: "Shop sales",
  customer_receipts: "Customer payments",
  other_inflow: "Other money in",
  supplier_bills: "Supplier bills",
  payroll: "Payroll",
  rent: "Rent",
  utilities: "Utilities",
  loan_repayment: "Loan repayments",
  tax: "Tax",
  other_outflow: "Other payments",
};
const categoryLabel = (c: string) => CATEGORY[c] ?? c.replace(/_/g, " ");

const DAY = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
const day = (iso: string) => (iso ? DAY.format(new Date(`${iso.slice(0, 10)}T00:00:00Z`)) : "");
const range = (w: ForecastWeek) => `${day(w.start)} – ${day(w.end)}`;

function useMoney(currency: string) {
  return useMemo(() => {
    const full = new Intl.NumberFormat("en", { style: "currency", currency, maximumFractionDigits: 0 });
    const compact = new Intl.NumberFormat("en", { style: "currency", currency, notation: "compact", maximumFractionDigits: 1 });
    return {
      full: (m: number) => full.format(toMajor(m, currency)),
      compact: (m: number) => compact.format(toMajor(m, currency)),
    };
  }, [currency]);
}

/** Round tick steps (1, 2 or 5 × 10^k) so the axis reads cleanly. */
function ticks(min: number, max: number, count = 4): number[] {
  const raw = (max - min) / count || 1;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max; v += step) out.push(v + 0);
  return out;
}

type Props = { weeks: ForecastWeek[]; bufferMinor: number; currency: string; initialWeek: number };

export function ForecastWorkbench({ weeks, bufferMinor, currency, initialWeek }: Props) {
  const [selected, setSelected] = useState(() => Math.max(0, weeks.findIndex((w) => w.week === initialWeek)));
  const detailRef = useRef<HTMLDivElement>(null);
  const week = weeks[selected] ?? weeks[0];

  function select(index: number, reveal = false) {
    setSelected(Math.min(weeks.length - 1, Math.max(0, index)));
    if (reveal) detailRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  if (!week) return null;
  return (
    <>
      <div className="fc-main">
        <section className="card fc-chart-card fc-rise" style={{ "--d": "180ms" } as CSSProperties} aria-label="13-week cash path">
          <div className="fc-card-head">
            <div>
              <span className="eyebrow">Weekly cash path</span>
              <h2>Closing balance against your buffer</h2>
            </div>
            <div className="fc-legend" aria-hidden="true">
              <span><i className="fc-key-line" /> Closing</span>
              <span><i className="fc-key-band" /> Likely range</span>
              <span><i className="fc-key-buffer" /> Buffer</span>
            </div>
          </div>
          <CashChart weeks={weeks} bufferMinor={bufferMinor} currency={currency} selected={selected} onSelect={select} />
          <p className="fc-chart-hint">Hover to compare weeks. Click a week, or use the arrow keys, to see what moves the cash.</p>
        </section>
        <div ref={detailRef} className="fc-detail-slot fc-rise" style={{ "--d": "260ms" } as CSSProperties}>
          <WeekDetail week={week} bufferMinor={bufferMinor} currency={currency} onPrev={selected > 0 ? () => select(selected - 1) : undefined} onNext={selected < weeks.length - 1 ? () => select(selected + 1) : undefined} />
        </div>
      </div>
      <WeekTable weeks={weeks} bufferMinor={bufferMinor} currency={currency} selected={selected} onSelect={(i) => select(i, true)} />
    </>
  );
}

function CashChart({ weeks, bufferMinor, currency, selected, onSelect }: { weeks: ForecastWeek[]; bufferMinor: number; currency: string; selected: number; onSelect: (i: number) => void }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(760);
  const [hover, setHover] = useState<number | null>(null);
  const money = useMoney(currency);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => entry && setWidth(Math.max(280, Math.round(entry.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const narrow = width < 560;
  const padL = narrow ? 58 : 76;
  const padR = 14;
  const top = 18;
  const lineH = narrow ? 180 : 230;
  const gap = 20;
  const barsH = narrow ? 52 : 66;
  const height = top + lineH + gap + barsH + 24;
  const plotW = width - padL - padR;
  const step = plotW / weeks.length;
  const x = (i: number) => padL + (i + 0.5) * step;

  const geo = useMemo(() => {
    const lo = Math.min(...weeks.map((w) => w.lowMinor), bufferMinor);
    const hi = Math.max(...weeks.map((w) => w.highMinor), bufferMinor);
    const pad = (hi - lo) * 0.08 || 1;
    const min = lo - pad;
    const max = hi + pad;
    const y = (v: number) => top + (1 - (v - min) / (max - min)) * lineH;
    const pts = weeks.map((w, i) => [x(i), y(w.closingMinor)] as const);
    const line = pts.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`).join("");
    const upper = weeks.map((w, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(w.highMinor).toFixed(1)}`).join("");
    const lower = weeks.map((w, i) => `L${x(i).toFixed(1)},${y(w.lowMinor).toFixed(1)}`).reverse().join("");
    const flowMax = Math.max(1, ...weeks.flatMap((w) => [w.inflowsMinor, w.outflowsMinor]));
    return { y, pts, line, band: `${upper}${lower}Z`, ticks: ticks(min, max), min, max, flowMax };
    // x depends on width; recompute when it changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [weeks, bufferMinor, width, lineH]);

  const bufferY = geo.y(bufferMinor);
  const zeroY = geo.min < 0 && geo.max > 0 ? geo.y(0) : null;
  const barsTop = top + lineH + gap;
  const mid = barsTop + barsH / 2;
  const barW = Math.min(16, step * 0.32);
  const firstBelow = weeks.findIndex((w) => w.below);
  const active = hover ?? selected;
  const tip = hover !== null ? weeks[hover] : null;

  function indexAt(e: { clientX: number; currentTarget: SVGSVGElement }) {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * width;
    return Math.min(weeks.length - 1, Math.max(0, Math.floor((px - padL) / step)));
  }

  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    const moves: Record<string, number> = { ArrowLeft: selected - 1, ArrowRight: selected + 1, Home: 0, End: weeks.length - 1 };
    if (e.key in moves) {
      e.preventDefault();
      onSelect(moves[e.key] as number);
    }
  }

  const lowest = weeks.reduce((a, b) => (b.closingMinor < a.closingMinor ? b : a));
  const summary = `13-week cash forecast. Starts at ${money.full(weeks[0]?.openingMinor ?? 0)}, lowest ${money.full(lowest.closingMinor)} in week ${lowest.week}. ${firstBelow >= 0 ? `Falls below the ${money.full(bufferMinor)} buffer in week ${weeks[firstBelow]?.week}.` : "Stays above the buffer."} Selected: week ${weeks[selected]?.week}.`;

  return (
    <div ref={wrapRef} className="fc-chart" tabIndex={0} onKeyDown={onKey} role="group" aria-label={summary}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} onPointerMove={(e) => setHover(indexAt(e))} onPointerLeave={() => setHover(null)} onClick={(e) => onSelect(indexAt(e))} aria-hidden="true">
        <defs>
          <clipPath id="fc-above"><rect x="0" y="0" width={width} height={Math.max(0, bufferY)} /></clipPath>
          <clipPath id="fc-below"><rect x="0" y={bufferY} width={width} height={Math.max(0, top + lineH - bufferY)} /></clipPath>
          <linearGradient id="fc-danger-zone" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--danger)" stopOpacity="0.09" />
            <stop offset="100%" stopColor="var(--danger)" stopOpacity="0.02" />
          </linearGradient>
        </defs>

        {/* Week columns: selected and hovered */}
        <rect className="fc-col fc-col-selected" x={padL + selected * step + 2} y={top - 6} width={step - 4} height={height - top - 18} rx="8" />
        {hover !== null && hover !== selected && <rect className="fc-col" x={padL + hover * step + 2} y={top - 6} width={step - 4} height={height - top - 18} rx="8" />}

        {/* Grid and axis */}
        {geo.ticks.map((t) => (
          <g key={t}>
            <line className="fc-grid" x1={padL} x2={width - padR} y1={geo.y(t)} y2={geo.y(t)} />
            <text className="fc-axis" x={padL - 8} y={geo.y(t) + 4} textAnchor="end">{money.compact(t)}</text>
          </g>
        ))}
        {zeroY !== null && <line className="fc-zero" x1={padL} x2={width - padR} y1={zeroY} y2={zeroY} />}

        {/* Below-buffer zone */}
        <rect x={padL} y={bufferY} width={plotW} height={Math.max(0, top + lineH - bufferY)} fill="url(#fc-danger-zone)" />

        <path className="fc-band" d={geo.band} />
        <line className="fc-buffer" x1={padL} x2={width - padR} y1={bufferY} y2={bufferY} />
        <text className="fc-buffer-label" x={width - padR - 4} y={bufferY - 7} textAnchor="end">Buffer {money.compact(bufferMinor)}</text>

        {firstBelow >= 0 && (
          <g className="fc-breach">
            <line x1={x(firstBelow)} x2={x(firstBelow)} y1={top} y2={top + lineH} />
            <text x={x(firstBelow) + 6} y={top + 10}>Below buffer from W{weeks[firstBelow]?.week}</text>
          </g>
        )}

        <path className="fc-line" d={geo.line} pathLength={1} clipPath="url(#fc-above)" />
        <path className="fc-line fc-line-below" d={geo.line} pathLength={1} clipPath="url(#fc-below)" />

        {geo.pts.map(([px, py], i) => (
          <circle key={i} className={`fc-dot ${weeks[i]?.below ? "is-below" : ""} ${i === active ? "is-active" : ""}`} cx={px} cy={py} r={i === active ? 6 : 3.5} style={{ "--i": i } as CSSProperties} />
        ))}

        {/* Money in and out per week */}
        <line className="fc-grid" x1={padL} x2={width - padR} y1={mid} y2={mid} />
        <text className="fc-axis" x={padL - 8} y={barsTop + 10} textAnchor="end">In</text>
        <text className="fc-axis" x={padL - 8} y={barsTop + barsH} textAnchor="end">Out</text>
        {weeks.map((w, i) => {
          const hIn = (w.inflowsMinor / geo.flowMax) * (barsH / 2 - 2);
          const hOut = (w.outflowsMinor / geo.flowMax) * (barsH / 2 - 2);
          return (
            <g key={w.week} style={{ "--i": i } as CSSProperties}>
              <rect className="fc-bar fc-bar-in" x={x(i) - barW / 2} y={mid - hIn} width={barW} height={hIn} rx="3" />
              <rect className="fc-bar fc-bar-out" x={x(i) - barW / 2} y={mid} width={barW} height={hOut} rx="3" />
              {(!narrow || i % 2 === 0 || i === active) && (
                <text className={`fc-week-label ${i === active ? "is-active" : ""}`} x={x(i)} y={height - 6} textAnchor="middle">W{w.week}</text>
              )}
            </g>
          );
        })}
      </svg>

      {tip && hover !== null && (
        <div className={`fc-tip ${x(hover) > width * 0.62 ? "is-left" : ""}`} style={{ left: x(hover), top: (geo.pts[hover]?.[1] ?? 0) }}>
          <small>Week {tip.week} · {range(tip)}</small>
          <strong className={tip.below ? "is-below" : ""}>{money.full(tip.closingMinor)}</strong>
          <span className="fc-tip-range">Likely {money.compact(tip.lowMinor)} to {money.compact(tip.highMinor)}</span>
          <span className="fc-tip-flows"><b className="in">+{money.compact(tip.inflowsMinor)}</b><b className="out">−{money.compact(tip.outflowsMinor)}</b></span>
        </div>
      )}
    </div>
  );
}

type Group = { key: string; category: string; basis: ForecastLine["basis"]; minor: number; refs: string[] };

function groupLines(lines: ForecastLine[], direction: "in" | "out"): Group[] {
  const map = new Map<string, Group>();
  for (const l of lines.filter((l) => l.direction === direction)) {
    const key = `${l.category}:${l.basis}`;
    const g = map.get(key) ?? { key, category: l.category, basis: l.basis, minor: 0, refs: [] };
    g.minor += l.minor;
    g.refs.push(...l.refs);
    map.set(key, g);
  }
  return [...map.values()].sort((a, b) => b.minor - a.minor);
}

function WeekDetail({ week, bufferMinor, currency, onPrev, onNext }: { week: ForecastWeek; bufferMinor: number; currency: string; onPrev?: (() => void) | undefined; onNext?: (() => void) | undefined }) {
  const money = useMoney(currency);
  const ins = groupLines(week.lines, "in");
  const outs = groupLines(week.lines, "out");
  const biggest = Math.max(1, ...ins.map((g) => g.minor), ...outs.map((g) => g.minor));
  const gap = bufferMinor - week.closingMinor;

  // Likely range on one strip, with the buffer marked, so the owner sees how close it runs.
  const lo = Math.min(week.lowMinor, bufferMinor);
  const hi = Math.max(week.highMinor, bufferMinor);
  const pos = (v: number) => `${((v - lo) / (hi - lo || 1)) * 100}%`;

  const rows = (groups: Group[], dir: "in" | "out") =>
    groups.length ? (
      <ul className="fc-lines">
        {groups.map((g, i) => (
          <li key={g.key} style={{ "--i": i } as CSSProperties}>
            <div className="fc-line-top">
              <span className="fc-line-name">{categoryLabel(g.category)}</span>
              <span className={`fc-basis fc-basis-${g.basis}`} title={g.basis === "scheduled" ? "A known bill, invoice or recurring commitment" : "A statistical estimate from your trading history"}>{g.basis === "scheduled" ? "Booked" : "Estimate"}</span>
              <span className={`fc-line-amount ${dir}`}>{dir === "in" ? "+" : "−"}{money.full(g.minor)}</span>
            </div>
            <div className={`fc-line-bar ${dir}`}><span style={{ width: `${(g.minor / biggest) * 100}%` }} /></div>
            {g.basis === "scheduled" && g.refs.length > 0 && <small className="fc-refs">{g.refs.slice(0, 3).join(" · ")}{g.refs.length > 3 ? ` +${g.refs.length - 3}` : ""}</small>}
          </li>
        ))}
      </ul>
    ) : <p className="fc-none">Nothing {dir === "in" ? "coming in" : "going out"} this week.</p>;

  return (
    <section className={`card fc-detail ${week.below ? "is-below" : ""}`} aria-live="polite" aria-label={`Week ${week.week} detail`}>
      <div className="fc-detail-nav">
        <button type="button" onClick={onPrev} disabled={!onPrev} aria-label="Previous week">‹</button>
        <span className="eyebrow">Week {week.week} · {range(week)}</span>
        <button type="button" onClick={onNext} disabled={!onNext} aria-label="Next week">›</button>
      </div>
      <div key={week.week} className="fc-detail-body">
        <div className="fc-detail-summary">
        <span className="fc-detail-label">Closes at</span>
        <strong className={`fc-detail-close ${week.closingMinor < bufferMinor ? "is-below" : ""}`}>
          <MoneyText amountMinor={week.closingMinor} currency={currency} />
        </strong>
        <span className={`fc-status ${gap > 0 ? "is-below" : "is-ok"}`}>
          {gap > 0 ? `${money.full(gap)} below your buffer` : `${money.full(-gap)} above your buffer`}
        </span>

        <div className="fc-flow-grid">
          <div><small>Opens</small><b>{money.compact(week.openingMinor)}</b></div>
          <div><small>Money in</small><b className="in">+{money.compact(week.inflowsMinor)}</b></div>
          <div><small>Money out</small><b className="out">−{money.compact(week.outflowsMinor)}</b></div>
        </div>

        <div className="fc-range" aria-label={`Likely closing between ${money.full(week.lowMinor)} and ${money.full(week.highMinor)}`}>
          <div className="fc-range-head"><small>Likely range</small><small>{money.compact(week.lowMinor)} to {money.compact(week.highMinor)}</small></div>
          <div className="fc-range-track">
            <span className="fc-range-fill" style={{ left: pos(week.lowMinor), width: `calc(${pos(week.highMinor)} - ${pos(week.lowMinor)})` }} />
            <span className="fc-range-buffer" style={{ left: pos(bufferMinor) }} title="Your buffer" />
            <span className="fc-range-point" style={{ left: pos(week.closingMinor) }} />
          </div>
        </div>
        </div>
        <div className="fc-detail-lines">
          <h4>Money in</h4>
          {rows(ins, "in")}
          <h4>Money out</h4>
          {rows(outs, "out")}
        </div>
      </div>
    </section>
  );
}

function WeekTable({ weeks, bufferMinor, currency, selected, onSelect }: { weeks: ForecastWeek[]; bufferMinor: number; currency: string; selected: number; onSelect: (i: number) => void }) {
  const money = useMoney(currency);
  const maxNet = Math.max(1, ...weeks.map((w) => Math.abs(w.netMinor)));
  return (
    <section className="card fc-table-card fc-rise" style={{ "--d": "340ms" } as CSSProperties} aria-label="Week by week">
      <div className="fc-card-head">
        <div>
          <span className="eyebrow">Week by week</span>
          <h2>Every week at a glance</h2>
        </div>
      </div>
      <div className="data-table-wrap">
        <table className="data-table fc-table">
          <thead>
            <tr><th>Week</th><th>Opens</th><th>Money in</th><th>Money out</th><th>Net change</th><th>Closes</th><th className="fc-col-range">Likely range</th><th>Buffer</th></tr>
          </thead>
          <tbody>
            {weeks.map((w, i) => (
              <tr key={w.week} className={`${w.below ? "is-below" : ""} ${i === selected ? "is-selected" : ""}`} onClick={() => onSelect(i)} aria-selected={i === selected}>
                <td><button type="button" className="fc-row-button" onClick={(e) => { e.stopPropagation(); onSelect(i); }}>Week {w.week}</button><small className="fc-dates">{range(w)}</small></td>
                <td>{money.full(w.openingMinor)}</td>
                <td className="fc-pos">+{money.full(w.inflowsMinor)}</td>
                <td className="fc-out">−{money.full(w.outflowsMinor)}</td>
                <td>
                  <span className="fc-net">
                    <span className="fc-net-track"><span className={w.netMinor >= 0 ? "in" : "out"} style={{ width: `${(Math.abs(w.netMinor) / maxNet) * 50}%` }} /></span>
                    <span className={w.netMinor >= 0 ? "fc-pos" : "fc-neg"}>{w.netMinor >= 0 ? "+" : "−"}{money.full(Math.abs(w.netMinor))}</span>
                  </span>
                </td>
                <td className={w.closingMinor < bufferMinor ? "money-negative" : ""}>{money.full(w.closingMinor)}</td>
                <td className="fc-muted fc-col-range">{money.compact(w.lowMinor)} – {money.compact(w.highMinor)}</td>
                <td>{w.below ? <span className="fc-pill is-below">Below</span> : <span className="fc-pill is-ok">Above</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
