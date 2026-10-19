import type { CSSProperties, ReactNode } from "react";
import { Card, StateChip } from "@fiona/ui";

/**
 * The shared building blocks for the workspace screens: one header, one stat card, one panel and
 * one status pill, so every screen reads the same way the briefing and forecast do.
 */

export type Tone = "neutral" | "blue" | "green" | "amber" | "danger";

/** Staggered entrance delay for `.sk-rise` (kept short: the page loads into a task). */
export const rise = (index: number): CSSProperties => ({ "--d": `${Math.min(index, 8) * 45}ms` }) as CSSProperties;

/** Turns an engine code such as `not_computable` or `shake_out` into readable text. */
export function nice(value: unknown, fallback = "—"): string {
  if (value === null || value === undefined || value === "") return fallback;
  const text = String(value).replaceAll("_", " ").trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : fallback;
}

export function PageHeader({ title, description, chips = [], actions, children }: { title: string; description?: ReactNode | undefined; chips?: Array<string | null | false | undefined>; actions?: ReactNode | undefined; children?: ReactNode | undefined }) {
  const shown = chips.filter((chip): chip is string => Boolean(chip));
  return (
    <header className="page-heading sk-header sk-rise" style={rise(0)}>
      <div>
        {shown.length > 0 && <div className="page-kicker sk-chips">{shown.map((chip) => <StateChip key={chip}>{chip}</StateChip>)}</div>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
        {children}
      </div>
      {actions && <div className="sk-header-actions">{actions}</div>}
    </header>
  );
}

export function Kpi({ label, icon, tone = "blue", value, note, index = 1, emphasis }: { label: string; icon?: ReactNode | undefined; tone?: Tone | undefined; value: ReactNode; note?: ReactNode | undefined; index?: number | undefined; emphasis?: "negative" | "warning" | "positive" | undefined }) {
  return (
    <Card className={`sk-kpi sk-rise sk-tone-${tone}`} style={rise(index)}>
      <div className="sk-kpi-top">
        <span>{label}</span>
        {icon && <span className={`summary-icon sk-icon-${tone}`} aria-hidden="true">{icon}</span>}
      </div>
      <strong className={emphasis ? `is-${emphasis}` : undefined}>{value}</strong>
      {note && <small>{note}</small>}
    </Card>
  );
}

export function KpiGrid({ children, columns = 3, label }: { children: ReactNode; columns?: 2 | 3 | 4 | undefined; label?: string | undefined }) {
  return <section className={`sk-kpis sk-cols-${columns}`} aria-label={label}>{children}</section>;
}

export function Panel({ eyebrow, title, tag, tagTone = "neutral", actions, children, index = 4, className = "" }: { eyebrow?: string | undefined; title: ReactNode; tag?: ReactNode | undefined; tagTone?: Tone | undefined; actions?: ReactNode | undefined; children: ReactNode; index?: number | undefined; className?: string | undefined }) {
  return (
    <Card className={`tier-panel sk-panel sk-rise ${className}`.trim()} style={rise(index)}>
      <div className="panel-heading sk-panel-heading">
        <div>
          {eyebrow && <span className="eyebrow">{eyebrow}</span>}
          <h2>{title}</h2>
        </div>
        {(tag || actions) && <div className="sk-panel-side">{tag && <Pill tone={tagTone}>{tag}</Pill>}{actions}</div>}
      </div>
      {children}
    </Card>
  );
}

export function Pill({ tone = "neutral", children, dot = false }: { tone?: Tone | undefined; children: ReactNode; dot?: boolean | undefined }) {
  return <span className={`sk-pill sk-pill-${tone}`}>{dot && <i aria-hidden="true" />}{children}</span>;
}

/** A tone for common engine words (bands, statuses, outcomes). */
export function toneFor(value: unknown): Tone {
  const text = String(value ?? "").toLowerCase();
  if (/(healthy|ok|eligible|verified|approve|paid|matched|exact|recommended|active|strong)/.test(text) && !/(in|not|un)eligible/.test(text)) return "green";
  if (/(stressed|critical|block|fail|refused|ineligible|danger|disabled)/.test(text)) return "danger";
  if (/(watch|warning|escalate|needs|insufficient|proposed|review|conditional|weak|pending)/.test(text)) return "amber";
  if (/(not_applicable|not applicable|not computable|not_computable|unavailable|none)/.test(text)) return "neutral";
  return "blue";
}

/** A thin meter for a 0–1 share (confidence, coverage). */
export function Meter({ value, tone = "blue", label }: { value: number; tone?: Tone | undefined; label?: string | undefined }) {
  const share = Math.max(0, Math.min(1, value));
  return <span className={`sk-meter sk-meter-${tone}`} role="img" aria-label={label ?? `${Math.round(share * 100)}%`}><i style={{ width: `${share * 100}%` }} /></span>;
}
