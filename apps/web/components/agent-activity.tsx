"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

interface RunRow {
  id: string;
  agent: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  summary: string | null;
  replayed?: boolean;
}

const AGENT_NAMES: Record<string, string> = {
  controller: "Controller",
  treasurer: "Treasurer",
  cfo_strategist: "CFO Strategist",
  growth_analyst: "Growth Analyst",
  council_chair: "Council chair",
};

const MARK: Record<string, { cls: string; glyph: string }> = {
  completed: { cls: "mark-green", glyph: "✓" },
  running: { cls: "mark-blue", glyph: "◌" },
  queued: { cls: "mark-blue", glyph: "…" },
  failed: { cls: "mark-red", glyph: "!" },
};

function when(iso: string | null): string {
  if (!iso) return "waiting";
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  return hours < 24 ? `${hours} h ago` : new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

/** What the agent team has actually done: their recorded runs, newest first. */
export function AgentActivity() {
  const [runs, setRuns] = useState<RunRow[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/fiona/agents/team/runs", { cache: "no-store" });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message ?? "The agent service is unavailable.");
      setRuns((data.runs as RunRow[]).slice(0, 6));
      setProblem(null);
    } catch (err) {
      setProblem(err instanceof Error ? err.message : "The agent service is unavailable.");
    }
  }, []);

  useEffect(() => {
    const first = window.setTimeout(load, 0);
    return () => window.clearTimeout(first);
  }, [load]);

  const busy = runs?.some((run) => run.status === "running" || run.status === "queued") ?? false;
  useEffect(() => {
    if (!busy) return;
    const timer = window.setInterval(load, 5_000);
    return () => window.clearInterval(timer);
  }, [busy, load]);

  async function runTeam() {
    setStarting(true);
    try {
      const res = await fetch("/api/fiona/agents/team/run", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ pipeline: "daily" }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message ?? "The team could not start.");
      setProblem(null);
      window.setTimeout(load, 1_500);
    } catch (err) {
      setProblem(err instanceof Error ? err.message : "The team could not start.");
    } finally {
      setStarting(false);
    }
  }

  return (
    <>
      <div className="inspector-heading activity-heading">
        <div>
          <span className="eyebrow">AGENT ACTIVITY</span>
          <h2>What the team did</h2>
        </div>
        <Link className="text-button" href="/audit">Audit trail ↗</Link>
      </div>

      {problem && <p className="agent-activity-note" role="status">{problem}</p>}
      {runs === null && !problem && <p className="agent-activity-note">Loading recent runs…</p>}
      {runs !== null && runs.length === 0 && (
        <p className="agent-activity-note">No runs yet. Start the team and the Controller reconciles the bank, then the Treasurer plans payments for you to approve.</p>
      )}

      {runs && runs.length > 0 && (
        <ol className="activity-list-luxury">
          {runs.map((run) => {
            const mark = MARK[run.status] ?? { cls: "mark-amber", glyph: "?" };
            return (
              <li key={run.id}>
                <span className={`activity-glow-mark ${mark.cls}`} aria-hidden="true">{mark.glyph}</span>
                <div>
                  <strong>
                    {AGENT_NAMES[run.agent] ?? run.agent} · {run.status}
                    {run.replayed ? " · replayed" : ""}
                  </strong>
                  <p>{run.summary ? `${run.summary.slice(0, 140)}${run.summary.length > 140 ? "…" : ""}` : when(run.started_at)}</p>
                  {run.summary && <p className="agent-activity-time">{when(run.finished_at ?? run.started_at)}</p>}
                </div>
              </li>
            );
          })}
        </ol>
      )}

      <button className="button button-secondary agent-run-button" type="button" onClick={runTeam} disabled={starting || busy}>
        {busy ? "The team is working…" : starting ? "Starting…" : "Run the team now"}
      </button>
    </>
  );
}
