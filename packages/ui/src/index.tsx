import type { ReactNode, ButtonHTMLAttributes, HTMLAttributes } from "react";

export const UI_PACKAGE = "@fiona/ui" as const;

export function Button({
  children,
  variant = "primary",
  className = "",
  type = "button",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "quiet" }) {
  return (
    <button type={type} className={`button button-${variant} ${className}`.trim()} {...props}>
      {children}
    </button>
  );
}

export function Card({
  children,
  className = "",
  ...props
}: HTMLAttributes<HTMLElement> & { children: ReactNode }) {
  return (
    <section className={`card ${className}`.trim()} {...props}>
      {children}
    </section>
  );
}

export function StateChip({ children }: { children: ReactNode }) {
  return <span className="state-chip"><span className="state-dot" />{children}</span>;
}

export function OutcomeBadge({ outcome }: { outcome: "approve" | "conditions" | "escalate" | "block" }) {
  const labels = { approve: "Approved", conditions: "With conditions", escalate: "Needs review", block: "Blocked" };
  return <span className={`outcome-badge outcome-${outcome}`}><span aria-hidden="true">{outcome === "approve" ? "✓" : outcome === "block" ? "×" : outcome === "escalate" ? "!" : "•"}</span>{labels[outcome]}</span>;
}

export function AgentChip({ name, role }: { name: string; role: string }) {
  const initials = name.split(" ").map((part) => part[0]).join("").slice(0, 2);
  return <span className="agent-chip"><span className="agent-avatar" aria-hidden="true">{initials}</span><span><strong>{name}</strong><small>{role}</small></span></span>;
}

export function AutonomyBadge({ children }: { children: ReactNode }) {
  return <span className="autonomy-badge">{children}</span>;
}

export function MoneyText({ amountMinor, currency = "PKR", className = "" }: { amountMinor: number; currency?: string; className?: string }) {
  const digits = new Intl.NumberFormat("en", { style: "currency", currency }).resolvedOptions().maximumFractionDigits ?? 2;
  const amount = new Intl.NumberFormat("en", { style: "currency", currency }).format(amountMinor / 10 ** digits);
  return <span className={`money-text ${className}`.trim()}>{amount}</span>;
}

export function TimeText({ dateTime, timeZone = "Asia/Karachi" }: { dateTime: string; timeZone?: string }) {
  const date = new Date(dateTime);
  if (Number.isNaN(date.valueOf())) return <time dateTime={dateTime}>Time unavailable</time>;
  return <time dateTime={dateTime}>{new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short", timeZone }).format(date)}</time>;
}

export function EmptyState({ title, children }: { title: string; children: ReactNode }) {
  return <div className="empty-state"><span className="empty-mark" aria-hidden="true">○</span><h3>{title}</h3><p>{children}</p></div>;
}

export function ErrorState({ title = "This view could not load", requestId }: { title?: string; requestId?: string }) {
  return <div className="error-state" role="alert"><strong>{title}</strong><p>Try again in a moment. If this continues, share the request ID with your administrator.</p>{requestId && <code>Request ID: {requestId}</code>}</div>;
}

export function DegradedBanner({ children }: { children: ReactNode }) {
  return <aside className="degraded-banner" role="status"><span aria-hidden="true">◷</span>{children}</aside>;
}

export function ProvenancePopover({ label = "Sources", sourceRefs }: { label?: string; sourceRefs: string[] }) {
  return <details className="provenance-popover"><summary>{label}</summary><ul>{sourceRefs.length ? sourceRefs.map((ref) => <li key={ref}>{ref}</li>) : <li>No source references were attached.</li>}</ul></details>;
}

export function FigureWithExplain({ label, amountMinor, currency = "PKR", explanation, sourceRefs = [] }: { label: string; amountMinor: number; currency?: string; explanation: string; sourceRefs?: string[] }) {
  return <div className="figure-explain"><span className="eyebrow">{label}</span><strong><MoneyText amountMinor={amountMinor} currency={currency} /></strong><p>{explanation}</p><ProvenancePopover sourceRefs={sourceRefs} /></div>;
}

export function VerdictPanel({ outcome, title = "Guardian review", children }: { outcome: "approve" | "conditions" | "escalate" | "block"; title?: string; children?: ReactNode }) {
  return <section className="verdict-panel"><div className="verdict-heading"><div><span className="eyebrow">INDEPENDENT CHECK</span><h3>{title}</h3></div><OutcomeBadge outcome={outcome} /></div>{children ?? <p>Verdict details and source evidence will appear here.</p>}</section>;
}

export function FindingCard({
  title,
  description,
  amountMinor,
  severity,
  source,
  time,
  outcome,
  action,
}: {
  title: string;
  description: string;
  amountMinor: number;
  severity: "high" | "medium" | "low";
  source: string;
  time: string;
  outcome?: "approve" | "conditions" | "escalate" | "block";
  action?: ReactNode;
}) {
  return (
    <article className="finding-card">
      <div className="finding-main">
        <span className={`severity severity-${severity}`}>{severity} priority</span>
        <h3>{title}</h3>
        <p>{description}</p>
        <div className="finding-meta"><span>{source}</span><span aria-hidden="true">·</span><TimeText dateTime={time} /></div>
      </div>
      <div className="finding-side"><span className="eyebrow">At stake</span><MoneyText amountMinor={amountMinor} /><div className="finding-actions">{outcome && <OutcomeBadge outcome={outcome} />}{action}</div></div>
    </article>
  );
}
