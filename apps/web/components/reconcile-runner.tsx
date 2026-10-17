"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

type RunResponse = {
  matched_bank_lines?: number;
  unmatched_bank_lines?: number;
  exact?: number;
  rule?: number;
  one_to_many?: number;
};

export function ReconcileRunner({ enabled }: { enabled: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function run() {
    setBusy(true);
    setMessage("Running deterministic matching against the seeded ledger…");
    try {
      const response = await fetch("/api/fiona/reconcile/run", { method: "POST", cache: "no-store" });
      const result: unknown = await response.json();
      if (!response.ok) {
        const detail = result && typeof result === "object" && "error" in result && result.error && typeof result.error === "object" && "message" in result.error
          ? String(result.error.message)
          : "The reconciliation run failed.";
        throw new Error(detail);
      }
      const summary = result as RunResponse;
      setMessage(`Run complete: ${summary.matched_bank_lines ?? 0} bank lines proposed as matches; ${summary.unmatched_bank_lines ?? 0} remain unmatched. Proposals still need review.`);
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The reconciliation run failed.");
    } finally {
      setBusy(false);
    }
  }

  return <div className="reconcile-runner">
    {enabled ? <button className="button button-primary" type="button" onClick={run} disabled={busy}>{busy ? "Matching…" : "Run deterministic matching"}</button> : <span className="footnote">Run is available in local mock mode when the engine is connected.</span>}
    {message && <p className="footnote" role="status" aria-live="polite">{message}</p>}
  </div>;
}
