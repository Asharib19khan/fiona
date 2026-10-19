"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, EmptyState } from "@fiona/ui";

type Mode = "server" | "api_key" | "subscription_token";

interface Connection {
  mode: Mode;
  hint: string | null;
  updated_by: string | null;
  updated_at: string | null;
  storage_ready: boolean;
}

interface TestResult {
  ok: boolean;
  message: string;
  latency_ms?: number;
}

const OPTIONS: Array<{ mode: Mode; title: string; body: string; how?: string; placeholder?: string }> = [
  {
    mode: "server",
    title: "The Claude signed in on Fiona's server",
    body: "Runs on whatever Claude account is signed in where Fiona's agents run. Right for a business running Fiona on its own computer: run `claude` there once and sign in.",
  },
  {
    mode: "api_key",
    title: "Your Anthropic API key",
    body: "Pay as you go on your own Anthropic account.",
    how: "Create one at console.anthropic.com → Settings → API keys, then paste it here.",
    placeholder: "sk-ant-api…",
  },
  {
    mode: "subscription_token",
    title: "Your Claude subscription (Pro or Max)",
    body: "Uses your own Claude plan instead of an API key.",
    how: "On any computer with Claude Code, run `claude setup-token`, sign in, and paste the token it prints.",
    placeholder: "sk-ant-oat…",
  },
];

async function call(url: string, init?: RequestInit): Promise<Record<string, unknown>> {
  const res = await fetch(url, { cache: "no-store", ...init, headers: { "content-type": "application/json" } });
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) throw new Error(String((data.error as Record<string, unknown> | undefined)?.message ?? "The request failed."));
  return data;
}

/**
 * Which Claude account this workspace's agents and Guardian use. The owner chooses; finance can
 * see the choice. A key or token is sent once, sealed by the engine, and never shown again.
 */
export function AiConnectionPanel({ canEdit }: { canEdit: boolean }) {
  const [current, setCurrent] = useState<Connection | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("server");
  const [secret, setSecret] = useState("");
  const [busy, setBusy] = useState<"save" | "test" | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [test, setTest] = useState<TestResult | null>(null);

  const load = useCallback(async () => {
    try {
      const data = (await call("/api/fiona/settings/ai")) as unknown as Connection;
      setCurrent(data);
      setMode(data.mode);
      setProblem(null);
    } catch (err) {
      setProblem(err instanceof Error ? err.message : "The AI connection could not be loaded.");
    }
  }, []);

  useEffect(() => {
    const first = window.setTimeout(load, 0);
    return () => window.clearTimeout(first);
  }, [load]);

  async function save(event: { preventDefault(): void }) {
    event.preventDefault();
    setBusy("save");
    setNotice(null);
    setTest(null);
    try {
      const body: Record<string, unknown> = { mode };
      if (mode !== "server" && secret.trim()) body.secret = secret.trim();
      const data = (await call("/api/fiona/settings/ai", { method: "POST", body: JSON.stringify(body) })) as unknown as Connection;
      setCurrent(data);
      setSecret("");
      setNotice(mode === "server" ? "Using the server's own Claude. Any saved key or token was deleted." : `Saved. Connected with ${data.hint ?? "your credential"}. Test it below.`);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "The connection could not be saved.");
    } finally {
      setBusy(null);
    }
  }

  async function runTest() {
    setBusy("test");
    setTest(null);
    try {
      setTest((await call("/api/fiona/agents/ai/test", { method: "POST", body: "{}" })) as unknown as TestResult);
    } catch (err) {
      setTest({ ok: false, message: err instanceof Error ? err.message : "The test could not run." });
    } finally {
      setBusy(null);
    }
  }

  if (problem) return <EmptyState title="Couldn't load the AI connection">{problem}</EmptyState>;
  if (!current) return <p className="footnote">Loading…</p>;

  const active = OPTIONS.find((option) => option.mode === current.mode);
  const needsSecret = mode !== "server" && !(mode === current.mode && current.hint);

  return (
    <div className="admin-portal">
      <Card className="tier-panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">IN USE NOW</span>
            <h2>{active?.title ?? current.mode}</h2>
          </div>
          {current.hint && <span className="placeholder-tag tag-positive">Connected {current.hint}</span>}
        </div>
        <p className="proposal-reasoning">
          {current.updated_at ? `Changed ${current.updated_at.replace("T", " ").slice(0, 16)} UTC by ${current.updated_by ?? "the owner"}.` : "Not changed yet: Fiona uses the server's own Claude."}
        </p>
        {canEdit && (
          <div style={{ padding: "0 15px 15px" }}>
            <button className="button button-secondary" type="button" onClick={runTest} disabled={busy !== null}>
              {busy === "test" ? "Testing… (up to a minute)" : "Test connection"}
            </button>
            {test && (
              <p className="mandate-notice" role="status">
                {test.ok ? `Working: ${test.message}${test.latency_ms ? ` (${(test.latency_ms / 1000).toFixed(1)} s)` : ""}` : `Not working: ${test.message}`}
              </p>
            )}
          </div>
        )}
      </Card>

      {canEdit ? (
        <Card className="tier-panel">
          <div className="panel-heading"><div><span className="eyebrow">CHANGE</span><h2>Which Claude should run your agents?</h2></div></div>
          {!current.storage_ready && (
            <p className="mandate-notice" role="status">
              This server can&apos;t store keys yet (its SETTINGS_ENCRYPTION_KEY isn&apos;t set), so only the server&apos;s own Claude is available.
            </p>
          )}
          <form onSubmit={save} style={{ padding: "0 15px 15px" }}>
            <div className="option-list">
              {OPTIONS.map((option) => {
                const disabled = option.mode !== "server" && !current.storage_ready;
                return (
                  <label className="option-row" key={option.mode} style={{ cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.55 : 1 }}>
                    <div>
                      <span className="eyebrow">
                        <input type="radio" name="ai-mode" value={option.mode} checked={mode === option.mode} disabled={disabled} onChange={() => { setMode(option.mode); setSecret(""); }} />{" "}
                        {option.mode === current.mode ? "IN USE" : "OPTION"}
                      </span>
                      <h3>{option.title}</h3>
                      <p>{option.body}</p>
                      {option.how && <p className="footnote">{option.how}</p>}
                    </div>
                  </label>
                );
              })}
            </div>
            {mode !== "server" && (
              <label className="admin-form" style={{ display: "block", marginTop: 12 }}>
                <span className="spec-label">{mode === "api_key" ? "API key" : "Subscription token"}{!needsSecret && " (leave blank to keep the saved one)"}</span>
                <input
                  type="password"
                  autoComplete="off"
                  spellCheck={false}
                  required={needsSecret}
                  maxLength={500}
                  placeholder={OPTIONS.find((option) => option.mode === mode)?.placeholder}
                  value={secret}
                  onChange={(e) => setSecret(e.target.value)}
                />
              </label>
            )}
            <button className="button button-primary" type="submit" disabled={busy !== null} style={{ marginTop: 12 }}>
              {busy === "save" ? "Saving…" : "Save"}
            </button>
            {notice && <p className="mandate-notice" role="status">{notice}</p>}
          </form>
        </Card>
      ) : (
        <p className="footnote">Only the owner can change or test the AI connection.</p>
      )}

      <p className="footnote">
        A key or token is encrypted (AES-256-GCM, tied to this workspace) before it is stored. It is never shown again or sent to any browser; only Fiona&apos;s agents and Guardian use it, to run Claude for this workspace. If it can&apos;t be read, they stop rather than use anyone else&apos;s account.
      </p>
    </div>
  );
}
