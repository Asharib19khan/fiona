"use client";

import {
  useState,
  useRef,
  useEffect,
  type ReactNode,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
} from "react";
import { motion, animate, useMotionValue } from "motion/react";

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
  interactive = false,
  ...props
}: HTMLAttributes<HTMLElement> & { children: ReactNode; interactive?: boolean }) {
  return (
    <section className={`card ${interactive ? "card-interactive" : ""} ${className}`.trim()} {...props}>
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

/**
 * ISO 4217 minor-unit exponents (Money.minor is in these units). Not Intl's display digits:
 * Intl shows PKR with 0 decimals, but PKR minor units are paisa (exponent 2).
 */
const ISO_EXPONENT: Record<string, number> = { JPY: 0, KRW: 0, VND: 0, CLP: 0, ISK: 0, UGX: 0, BHD: 3, KWD: 3, OMR: 3, JOD: 3, TND: 3 };

export function minorExponent(currency: string): number {
  return ISO_EXPONENT[currency.toUpperCase()] ?? 2;
}

/** Major units from integer minor units, for display only. */
export function toMajor(amountMinor: number, currency: string): number {
  return amountMinor / 10 ** minorExponent(currency);
}

export function MoneyText({
  amountMinor,
  currency = "PKR",
  className = "",
  animateCount = true,
}: {
  amountMinor: number;
  currency?: string;
  className?: string;
  animateCount?: boolean;
}) {
  const targetMajor = toMajor(amountMinor, currency);

  const count = useMotionValue(0);
  const [displayValue, setDisplayValue] = useState(() => {
    return new Intl.NumberFormat("en", { style: "currency", currency }).format(targetMajor);
  });

  useEffect(() => {
    if (!animateCount) {
      setDisplayValue(new Intl.NumberFormat("en", { style: "currency", currency }).format(targetMajor));
      return;
    }
    count.set(0);
    const controls = animate(count, targetMajor, {
      duration: 0.9,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (latest) => {
        setDisplayValue(new Intl.NumberFormat("en", { style: "currency", currency }).format(latest));
      },
    });
    return () => controls.stop();
  }, [targetMajor, currency, animateCount, count]);

  return <span className={`money-text ${className}`.trim()}>{displayValue}</span>;
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

/** A figure's source references. Shows the first `limit` and counts the rest (a ratio can rest on tens of thousands of ledger events). */
export function ProvenancePopover({ label = "Sources", sourceRefs, total, limit = 12 }: { label?: string; sourceRefs: string[]; total?: number; limit?: number }) {
  const count = Math.max(total ?? 0, sourceRefs.length);
  const shown = sourceRefs.slice(0, limit);
  return <details className="provenance-popover"><summary>{count > 1 ? `${label} (${count.toLocaleString("en-US")})` : label}</summary><ul>{shown.length ? shown.map((ref) => <li key={ref}>{ref}</li>) : <li>No source references were attached.</li>}{count > shown.length && <li>…and {(count - shown.length).toLocaleString("en-US")} more</li>}</ul></details>;
}

export function FigureWithExplain({ label, amountMinor, currency = "PKR", explanation, sourceRefs = [] }: { label: string; amountMinor: number; currency?: string; explanation: string; sourceRefs?: string[] }) {
  return <div className="figure-explain"><span className="eyebrow">{label}</span><strong><MoneyText amountMinor={amountMinor} currency={currency} /></strong><p>{explanation}</p><ProvenancePopover sourceRefs={sourceRefs} /></div>;
}

export function VerdictPanel({
  outcome,
  title = "Guardian review",
  children,
  className = "",
}: {
  outcome: "approve" | "conditions" | "escalate" | "block";
  title?: string;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`verdict-panel ${className}`.trim()}>
      <div className={`verdict-panel-mesh verdict-panel-mesh-${outcome}`} aria-hidden="true" />
      <div className="verdict-heading">
        <div>
          <span className="eyebrow">INDEPENDENT CHECK</span>
          <h3>{title}</h3>
        </div>
        <OutcomeBadge outcome={outcome} />
      </div>
      {children ?? <p>Verdict details and source evidence will appear here.</p>}
    </section>
  );
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
  className = "",
}: {
  title: string;
  description: string;
  amountMinor: number;
  severity: "high" | "medium" | "low";
  source: string;
  time: string;
  outcome?: "approve" | "conditions" | "escalate" | "block";
  action?: ReactNode;
  className?: string;
}) {
  const cardRef = useRef<HTMLElement | null>(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const [isHovered, setIsHovered] = useState(false);

  function handleMouseMove(e: React.MouseEvent<HTMLElement>) {
    if (!cardRef.current) return;
    const rect = cardRef.current.getBoundingClientRect();
    setMousePos({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    });
  }

  return (
    <motion.article
      ref={cardRef}
      onMouseMove={handleMouseMove}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      whileHover={{ y: -2 }}
      transition={{ type: "spring", stiffness: 400, damping: 28 }}
      className={`finding-card ${className}`.trim()}
    >
      <div
        className="finding-card-spotlight"
        style={{
          opacity: isHovered ? 1 : 0,
          background: `radial-gradient(380px circle at ${mousePos.x}px ${mousePos.y}px, var(--accent-glow), transparent 80%)`,
        }}
        aria-hidden="true"
      />
      <div className="finding-card-glow-indicator" aria-hidden="true" />

      <div className="finding-main">
        <div style={{ display: "flex", alignItems: "center", marginBottom: "4px" }}>
          <span className={`severity severity-${severity}`}>
            <span className="severity-pulse-dot" />
            {severity} priority
          </span>
        </div>
        <h3>{title}</h3>
        <p>{description}</p>
        <div className="finding-meta">
          <span>{source}</span>
          <span aria-hidden="true">·</span>
          <TimeText dateTime={time} />
        </div>
      </div>
      <div className="finding-side">
        <span className="eyebrow">At stake</span>
        <MoneyText amountMinor={amountMinor} animateCount={true} />
        <div className="finding-actions">
          {outcome && <OutcomeBadge outcome={outcome} />}
          {action}
        </div>
      </div>
    </motion.article>
  );
}
