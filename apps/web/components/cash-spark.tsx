"use client";

import { useMemo, useState, type PointerEvent } from "react";
import { toMajor } from "@fiona/ui";

type Week = { week: number; start: string; closingMinor: number; below: boolean };

const W = 300;
const H = 64;
const PAD = 4;

const DAY = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });

/** The 13-week closing cash as a small line chart, with the buffer as a dashed line. Hover shows each week. */
export function CashSpark({ weeks, bufferMinor, currency }: { weeks: Week[]; bufferMinor: number; currency: string }) {
  const [active, setActive] = useState<number | null>(null);
  const money = useMemo(() => new Intl.NumberFormat("en", { style: "currency", currency, maximumFractionDigits: 0 }), [currency]);

  const geo = useMemo(() => {
    const values = weeks.map((w) => w.closingMinor);
    const min = Math.min(...values, bufferMinor);
    const max = Math.max(...values, bufferMinor);
    const span = max - min || 1;
    const x = (i: number) => (weeks.length < 2 ? W / 2 : (i / (weeks.length - 1)) * W);
    const y = (v: number) => PAD + (1 - (v - min) / span) * (H - PAD * 2);
    const points = weeks.map((w, i) => [x(i), y(w.closingMinor)] as const);
    const line = points.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`).join(" ");
    return { points, line, area: `${line} L${W},${H} L0,${H} Z`, bufferY: y(bufferMinor) };
  }, [weeks, bufferMinor]);

  if (weeks.length < 2) return null;

  function onMove(e: PointerEvent<HTMLDivElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    setActive(Math.round(ratio * (weeks.length - 1)));
  }

  const lowest = weeks.reduce((a, b) => (b.closingMinor < a.closingMinor ? b : a));
  const label = `13-week cash forecast. Lowest is ${money.format(toMajor(lowest.closingMinor, currency))} in week ${lowest.week}.`;
  const hit = active === null ? null : weeks[active];
  const point = active === null ? null : geo.points[active];

  return (
    <div className="cash-spark">
      <div className="cash-spark-plot" onPointerMove={onMove} onPointerLeave={() => setActive(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={label}>
        <defs>
          <linearGradient id="cash-spark-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.18" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
          <clipPath id="cash-spark-above"><rect x="0" y="0" width={W} height={geo.bufferY} /></clipPath>
          <clipPath id="cash-spark-below"><rect x="0" y={geo.bufferY} width={W} height={H - geo.bufferY} /></clipPath>
        </defs>
        <path d={geo.area} fill="url(#cash-spark-fill)" />
        <line className="cash-spark-buffer" x1="0" x2={W} y1={geo.bufferY} y2={geo.bufferY} />
        <path className="cash-spark-line" d={geo.line} clipPath="url(#cash-spark-above)" />
        <path className="cash-spark-line cash-spark-line-below" d={geo.line} clipPath="url(#cash-spark-below)" />
        {point && <line className="cash-spark-cursor" x1={point[0]} x2={point[0]} y1="0" y2={H} />}
      </svg>
      {point && hit && (
        <>
          <span className={`cash-spark-dot ${hit.below ? "is-below" : ""}`} style={{ left: `${(point[0] / W) * 100}%`, top: `${(point[1] / H) * 100}%` }} />
          <span className="cash-spark-tip" style={{ left: `${Math.min(80, Math.max(20, (point[0] / W) * 100))}%` }} role="status">
            <small>Week {hit.week} · from {DAY.format(new Date(`${hit.start.slice(0, 10)}T00:00:00Z`))}</small>
            <strong className={hit.below ? "is-below" : ""}>{money.format(toMajor(hit.closingMinor, currency))}</strong>
          </span>
        </>
      )}
      </div>
      <div className="cash-spark-axis" aria-hidden="true">
        <span>Wk {weeks[0]?.week}</span>
        <span className="cash-spark-legend"><i /> Buffer</span>
        <span>Wk {weeks[weeks.length - 1]?.week}</span>
      </div>
    </div>
  );
}
