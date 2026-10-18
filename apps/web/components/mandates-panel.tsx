"use client";

import { useCallback, useEffect, useState } from "react";
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

const AGENTS: Record<string, { name: string; job: string }> = {
  controller: { name: "Controller", job: "Reconciles the bank and checks bills" },
  treasurer: { name: "Treasurer", job: "Plans and prepares supplier payments" },
  cfo_strategist: { name: "CFO Strategist", job: "Advises on capital decisions" },
  growth_analyst: { name: "Growth Analyst", job: "Advises on stock and growth" },
};

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

  if (problem) return <Card className="mandates-panel"><EmptyState title="Mandates could not be loaded">{problem}</EmptyState></Card>;
  if (!mandates) return <Card className="mandates-panel"><EmptyState title="Loading mandates">Reading the mandates in force…</EmptyState></Card>;

  return (
    <Card className="mandates-panel">
      <div className="panel-heading">
        <div><span className="eyebrow">MANDATES IN FORCE</span><h2>What each agent may do</h2></div>
        <span className="placeholder-tag">{canEdit ? "You can change levels" : "Read only"}</span>
      </div>
      {notice && <p className="mandate-notice" role="status">{notice}</p>}
      <div className="mandate-rows">
        {mandates.map((m) => (
          <div className="mandate-row mandate-row-live" key={m.id}>
            <div>
              <strong>{AGENTS[m.agent]?.name ?? m.agent} <span className="mandate-version">v{m.version} · {m.source === "owner" ? "set by you" : "default"}</span></strong>
              <span>{AGENTS[m.agent]?.job ?? ""}</span>
              {m.per_payment_cap.minor > 0 && (
                <span>
                  Caps: <MoneyText amountMinor={m.per_payment_cap.minor} currency={m.per_payment_cap.currency} animateCount={false} /> per payment,{" "}
                  <MoneyText amountMinor={m.daily_cap.minor} currency={m.daily_cap.currency} animateCount={false} /> a day
                  {m.allowed_categories ? ` · ${m.allowed_categories.join(", ").replaceAll("_", " ")}` : ""}
                </span>
              )}
            </div>
            <div className="mandate-levels">
              {m.allowed_action_types.length === 0 && <AutonomyBadge>Advises only</AutonomyBadge>}
              {m.allowed_action_types.map((action) => {
                const ceiling = m.ceiling[action] ?? "advise";
                const options = LEVELS.slice(0, LEVELS.indexOf(ceiling) + 1);
                return (
                  <label key={action} className="mandate-level">
                    <span className="spec-label">{action.replaceAll("_", " ")}</span>
                    {canEdit && options.length > 1 ? (
                      <select
                        value={m.autonomy[action] ?? "prepare"}
                        disabled={saving !== null}
                        onChange={(e) => change(m.agent, action, e.target.value)}
                        aria-label={`${AGENTS[m.agent]?.name ?? m.agent} autonomy for ${action}`}
                      >
                        {options.map((level) => <option key={level} value={level}>{LEVEL_TEXT[level]}</option>)}
                      </select>
                    ) : (
                      <AutonomyBadge>{LEVEL_TEXT[m.autonomy[action] ?? "prepare"]}</AutonomyBadge>
                    )}
                    <small>Ceiling: {ceiling.replaceAll("_", " ")}</small>
                  </label>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
