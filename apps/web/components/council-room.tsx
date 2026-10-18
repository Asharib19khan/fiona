"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, EmptyState } from "@fiona/ui";

type Json = Record<string, unknown>;

interface Pipeline {
  id: string;
  kind: string;
  status: string;
  question?: string;
  started_at?: string;
  round_1?: Record<string, { status: string; memo: Json | null }>;
  round_2?: Record<string, { status: string; rebuttal: Json | null }>;
  memo?: Json | null;
  figure_check?: { verified: string[]; unverified: string[] };
  replayed?: boolean;
}

const MEMBERS: Record<string, string> = {
  cfo_strategist: "CFO Strategist",
  treasurer: "Treasurer",
  growth_analyst: "Growth Analyst",
};

const POSITION: Record<string, string> = {
  for: "For",
  against: "Against",
  conditional: "Conditional",
  insufficient_data: "Needs more data",
};

const DEFAULT_QUESTION =
  "Our cash is forecast to fall below the buffer. Should we borrow now for working capital, or manage the gap by agreeing longer supplier terms and selling down slow stock?";

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

function figures(value: unknown): Json[] {
  return Array.isArray(value) ? (value.filter((v) => v && typeof v === "object") as Json[]) : [];
}

/** Ask the council a question, watch it deliberate, and read the memo with dissent on record. */
export function CouncilRoom() {
  const [question, setQuestion] = useState(DEFAULT_QUESTION);
  const [pipeline, setPipeline] = useState<Pipeline | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const fetchPipeline = useCallback(async (id: string) => {
    const res = await fetch(`/api/fiona/agents/pipelines/${id}`, { cache: "no-store" });
    const data = await res.json();
    if (!res.ok) throw new Error(data?.error?.message ?? "The council could not be read.");
    setPipeline(data as Pipeline);
  }, []);

  // Show the latest council on arrival.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/fiona/agents/pipelines", { cache: "no-store" });
        const data = await res.json();
        if (!res.ok) throw new Error(data?.error?.message ?? "The agent service is unavailable.");
        const latest = (data.pipelines as Pipeline[]).find((p) => p.kind === "council");
        if (latest && !cancelled) await fetchPipeline(latest.id);
      } catch (err) {
        if (!cancelled) setProblem(err instanceof Error ? err.message : "The agent service is unavailable.");
      }
    })();
    return () => { cancelled = true; };
  }, [fetchPipeline]);

  const running = pipeline?.status === "running";
  useEffect(() => {
    if (!running || !pipeline) return;
    const timer = window.setInterval(() => { fetchPipeline(pipeline.id).catch(() => undefined); }, 5_000);
    return () => window.clearInterval(timer);
  }, [running, pipeline, fetchPipeline]);

  async function convene() {
    setStarting(true);
    setProblem(null);
    try {
      const res = await fetch("/api/fiona/agents/council", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question: question.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message ?? "The council could not start.");
      await fetchPipeline(data.pipeline_id);
    } catch (err) {
      setProblem(err instanceof Error ? err.message : "The council could not start.");
    } finally {
      setStarting(false);
    }
  }

  const memo = pipeline?.memo ?? null;

  return (
    <div className="council-room">
      <Card className="tier-panel council-ask">
        <div className="panel-heading">
          <div><span className="eyebrow">ASK THE COUNCIL</span><h2>One question, three perspectives, dissent on record</h2></div>
        </div>
        <div className="council-ask-body">
          <label className="spec-label" htmlFor="council-question">Your question</label>
          <textarea
            id="council-question"
            className="council-question"
            rows={3}
            maxLength={1000}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={starting || running}
          />
          <div className="panel-actions">
            <button className="button button-primary" type="button" onClick={convene} disabled={starting || running || question.trim().length < 10}>
              {running ? "The council is deliberating…" : starting ? "Convening…" : "Convene the council"}
            </button>
          </div>
          <p className="footnote">
            The CFO Strategist, Treasurer and Growth Analyst each gather figures with their own tools, read each other&rsquo;s memos and reply. A chair with no tools writes the memo. The council advises; you decide.
          </p>
        </div>
      </Card>

      {problem && <Card className="tier-panel"><EmptyState title="The council is unavailable">{problem}</EmptyState></Card>}

      {pipeline && (
        <>
          <Card className="tier-panel">
            <div className="panel-heading">
              <div><span className="eyebrow">ROUND 1 · OPENING MEMOS</span><h2>{pipeline.question}</h2></div>
              <span className="placeholder-tag">{pipeline.replayed ? "Recorded run" : pipeline.status}</span>
            </div>
            <div className="option-list">
              {Object.keys(MEMBERS).map((name) => {
                const entry = pipeline.round_1?.[name];
                const m = entry?.memo ?? null;
                const reply = pipeline.round_2?.[name]?.rebuttal ?? null;
                return (
                  <article className="option-row" key={name}>
                    <div>
                      <span className="eyebrow">{MEMBERS[name]}{m ? ` · ${POSITION[String(m.position)] ?? String(m.position)}` : ""}</span>
                      <h3>{m ? String(m.recommendation ?? "") : entry ? `Working (${entry.status})…` : "Waiting to start…"}</h3>
                      {m && <p>{String(m.summary ?? "")}</p>}
                      {reply && (
                        <p className="council-reply">
                          <strong>After reading the others ({reply.changed_mind ? "changed position" : "kept position"}):</strong> {String(reply.summary ?? "")}
                        </p>
                      )}
                    </div>
                    <div className="option-facts">
                      {figures(m?.key_figures).slice(0, 4).map((f, i) => (
                        <span key={i}><strong>{String(f.value)}</strong> {String(f.label)}</span>
                      ))}
                    </div>
                  </article>
                );
              })}
            </div>
          </Card>

          <Card className="tier-panel">
            <div className="panel-heading">
              <div><span className="eyebrow">THE COUNCIL&rsquo;S MEMO</span><h2>{memo ? String(memo.recommendation ?? "") : running ? "The chair writes this once the debate ends." : "No memo was produced."}</h2></div>
            </div>
            {memo && (
              <div className="council-memo">
                <p>{String(memo.summary ?? "")}</p>
                <p><strong>Majority view.</strong> {String(memo.majority_view ?? "")}</p>
                <div>
                  <span className="eyebrow">DISSENT ON RECORD</span>
                  {figures(memo.dissent).length === 0 ? (
                    <p>No member dissented from the recommendation.</p>
                  ) : (
                    <ul>{figures(memo.dissent).map((d, i) => <li key={i}><strong>{MEMBERS[String(d.member)] ?? String(d.member)} ({String(d.position)}):</strong> {String(d.why)}</li>)}</ul>
                  )}
                </div>
                <div>
                  <span className="eyebrow">YOU DECIDE</span>
                  <ul>{strings(memo.owner_decides).map((q) => <li key={q}>{q}</li>)}</ul>
                </div>
                <div>
                  <span className="eyebrow">FIGURES, AS CITED BY MEMBERS</span>
                  <ul>{figures(memo.key_figures).map((f, i) => <li key={i}>{String(f.label)}: <strong>{String(f.value)}</strong> <span className="council-cite">({MEMBERS[String(f.from_member)] ?? String(f.from_member)})</span></li>)}</ul>
                </div>
                {pipeline.figure_check && (
                  <p className="footnote">
                    Figure check: {pipeline.figure_check.verified.length} rupee figures match the members&rsquo; tool results
                    {pipeline.figure_check.unverified.length > 0
                      ? `; ${pipeline.figure_check.unverified.length} are rounded or not from a tool (${pipeline.figure_check.unverified.slice(0, 4).join(", ")}), so check them before relying on them.`
                      : "; none are unverified."}
                  </p>
                )}
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
