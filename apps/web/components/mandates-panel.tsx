"use client";

import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { AutonomyBadge, Card, EmptyState, MoneyText } from "@fiona/ui";

interface Mandate {
  id: string;
  agent: string;
  version: number;
  per_payment_cap: { minor: number; currency: string };
  daily_cap: { minor: number; currency: string };
  allowed_action_types: string[];
  autonomy: Record<string, string>;
  ceiling: Record<string, string>;
  allowed_categories: string[] | null;
  source: string;
  effective_from: string;
}

const AGENTS: Record<string, { name: string; job: string; code: string; color: string }> = {
  controller: { name: "Controller", job: "Reconciles the bank and checks bills", code: "CT", color: "agent-ct" },
  treasurer: { name: "Treasurer", job: "Plans and prepares supplier payments", code: "TR", color: "agent-tr" },
  cfo_strategist: { name: "CFO Strategist", job: "Advises on capital decisions", code: "CF", color: "agent-cf" },
  growth_analyst: { name: "Growth Analyst", job: "Advises on stock and growth", code: "GA", color: "agent-ga" },
};

const LEVEL_SHORT: Record<string, string> = { advise: "Advise", prepare: "Prepare", act_within_mandate: "Act within mandate" };

const LEVEL_TEXT: Record<string, string> = {
  advise: "Advise: recommends only",
  prepare: "Prepare: drafts it, you approve",
  act_within_mandate: "Act within mandate: pays alone after Guardian clearance, inside the caps",
};

const LEVELS = ["advise", "prepare", "act_within_mandate"];

/** The permission tiers, live: each agent's level per action, its caps and its ceiling.
 * The owner can change a level; it becomes a new mandate version with an audit record. */
export function MandatesPanel({ canEdit }: { canEdit: boolean }) {
  const [mandates, setMandates] = useState<Mandate[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/fiona/mandates", { cache: "no-store" });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message ?? "Mandates could not be loaded.");
      setMandates(data.mandates as Mandate[]);
      setProblem(null);
    } catch (err) {
      setProblem(err instanceof Error ? err.message : "Mandates could not be loaded.");
    }
  }, []);

  useEffect(() => {
    const first = window.setTimeout(load, 0);
    return () => window.clearTimeout(first);
  }, [load]);

  async function change(agent: string, actionType: string, level: string) {
    setSaving(`${agent}:${actionType}`);
    setNotice(null);
    try {
      const res = await fetch(`/api/fiona/mandates/${agent}/autonomy`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action_type: actionType, level }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message ?? "The change was refused.");
      setNotice(data.changed ? `${AGENTS[agent]?.name ?? agent} is now at "${level.replaceAll("_", " ")}" for ${actionType.replaceAll("_", " ")} (mandate v${data.mandate.version}, recorded in the audit trail).` : "No change.");
      await load();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "The change was refused.");
    } finally {
      setSaving(null);
    }
  }

  if (problem) return <Card className="mandates-panel sk-panel"><EmptyState title="Mandates could not be loaded">{problem}</EmptyState></Card>;
  if (!mandates) return <div className="sk-skeleton-list" role="status" aria-label="Loading mandates">{[0, 1, 2, 3].map((i) => <div key={i} className="sk-skeleton-card" style={{ animationDelay: `${i * 100}ms` }}><span /><span /><span /></div>)}<span className="sr-only">Reading the mandates in force…</span></div>;

  return (
    <Card className="mandates-panel sk-panel sk-rise" style={{ "--d": "90ms" } as CSSProperties}>
      <div className="panel-heading sk-panel-heading">
        <div><span className="eyebrow">Mandates in force</span><h2>What each agent may do</h2></div>
        <span className={`sk-pill ${canEdit ? "sk-pill-blue" : "sk-pill-neutral"}`}>{canEdit ? "You can change levels" : "Read only"}</span>
      </div>
      {notice && <p className="mandate-notice sk-notice" role="status">{notice}</p>}
      <div className="mandate-cards">
        {mandates.map((m, index) => {
          const meta = AGENTS[m.agent];
          return (
            <section className="mandate-card sk-rise" key={m.id} style={{ "--d": `${120 + index * 60}ms` } as CSSProperties} aria-label={meta?.name ?? m.agent}>
              <header>
                <span className={`council-avatar ${meta?.color ?? ""}`} aria-hidden="true">{meta?.code ?? m.agent.slice(0, 2).toUpperCase()}</span>
                <div>
                  <strong>{meta?.name ?? m.agent}</strong>
                  <span>{meta?.job ?? ""}</span>
                </div>
                <span className="sk-pill sk-pill-neutral mandate-version">v{m.version} · {m.source === "owner" ? "set by you" : "default"}</span>
              </header>
              {m.per_payment_cap.minor > 0 && (
                <div className="mandate-caps">
                  <div><span>Per payment</span><strong><MoneyText amountMinor={m.per_payment_cap.minor} currency={m.per_payment_cap.currency} animateCount={false} /></strong></div>
                  <div><span>Per day</span><strong><MoneyText amountMinor={m.daily_cap.minor} currency={m.daily_cap.currency} animateCount={false} /></strong></div>
                  {m.allowed_categories && <div className="mandate-cats"><span>Categories</span><strong>{m.allowed_categories.join(", ").replaceAll("_", " ")}</strong></div>}
                </div>
              )}
              <div className="mandate-actions">
                {m.allowed_action_types.length === 0 && <div className="mandate-advise"><AutonomyBadge>Advises only</AutonomyBadge><small>Recommends; never drafts or acts.</small></div>}
                {m.allowed_action_types.map((action) => {
                  const ceiling = m.ceiling[action] ?? "advise";
                  const allowed = LEVELS.slice(0, LEVELS.indexOf(ceiling) + 1);
                  const current = m.autonomy[action] ?? "prepare";
                  const editable = canEdit && allowed.length > 1;
                  const busy = saving === `${m.agent}:${action}`;
                  return (
                    <div key={action} className={`mandate-action ${busy ? "is-saving" : ""}`}>
                      <div className="mandate-action-head">
                        <span className="spec-label">{action.replaceAll("_", " ")}</span>
                        <small>Ceiling: {ceiling.replaceAll("_", " ")}</small>
                      </div>
                      <div className="mandate-ladder" role="radiogroup" aria-label={`${meta?.name ?? m.agent} autonomy for ${action}`}>
                        {LEVELS.map((level) => {
                          const locked = !allowed.includes(level);
                          const active = current === level;
                          return (
                            <button
                              key={level}
                              type="button"
                              role="radio"
                              aria-checked={active}
                              className={`${active ? "is-active" : ""} ${locked ? "is-locked" : ""}`}
                              disabled={!editable || locked || saving !== null}
                              title={locked ? "Above this agent's ceiling" : LEVEL_TEXT[level]}
                              onClick={() => { if (!active) void change(m.agent, action, level); }}
                            >
                              {LEVEL_SHORT[level]}
                            </button>
                          );
                        })}
                      </div>
                      <p className="mandate-level-text">{busy ? "Saving as a new mandate version…" : LEVEL_TEXT[current]}</p>
                    </div>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </Card>
  );
}
