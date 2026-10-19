"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Card, MoneyText } from "@fiona/ui";
import { UploadIcon } from "@/components/briefing-icons";

interface Sourced { value: string | null; quote: string | null; quote_verified: boolean }
interface Party { id: string; name: string; tax_id: string | null; bank_iban: string | null; on_allow_list: boolean }
interface Reading {
  fields: Record<string, Sourced>;
  amounts_minor: { subtotal: number | null; tax: number | null; total: number | null };
  dates: { issue_date: string | null; due_date: string | null };
  embedded_instructions: string[];
  warnings: string[];
  document: { filename: string; text: string };
  meta: { model: string; cost_usd: number | null };
  supplier_candidates: Party[];
}

type Step = "choose" | "reading" | "review" | "recording" | "treasurer" | "done";

/** The four stages shown above the form, and which internal steps belong to each. */
const BILL_STAGES: Array<[string, Step[]]> = [
  ["Read", ["choose", "reading"]],
  ["Review", ["review"]],
  ["Record", ["recording"]],
  ["Treasurer", ["treasurer", "done"]],
];

const FIELD_LABELS: Array<[string, string]> = [
  ["supplier_name", "Supplier"],
  ["supplier_tax_id", "Tax ID (NTN)"],
  ["invoice_number", "Invoice number"],
  ["purchase_order_ref", "PO reference"],
  ["bank_iban", "Bank account on the bill"],
];

function toBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
    reader.onerror = () => reject(new Error("The file could not be read."));
    reader.readAsDataURL(file);
  });
}

function minorFromInput(value: string): number | null {
  const cleaned = value.replace(/,/g, "").trim();
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null;
  const [whole = "0", fraction = ""] = cleaned.split(".");
  return Number(whole) * 100 + Number((fraction + "00").slice(0, 2));
}

function majorText(minor: number | null): string {
  if (minor === null) return "";
  return `${Math.floor(minor / 100)}.${String(minor % 100).padStart(2, "0")}`;
}

async function post(url: string, body: unknown): Promise<Record<string, unknown>> {
  const res = await fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) throw new Error(String((data.error as Record<string, unknown> | undefined)?.message ?? "The request failed."));
  return data;
}

/** Upload a bill, check what Fiona read, record it, and let the Treasurer take it from there. */
export function BillIntake() {
  const [step, setStep] = useState<Step>("choose");
  const [dragging, setDragging] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [reading, setReading] = useState<Reading | null>(null);
  const [form, setForm] = useState({ supplierId: "", number: "", issueDate: "", dueDate: "", subtotal: "", tax: "", total: "", category: "inventory_supplier" });
  const [billId, setBillId] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [runSummary, setRunSummary] = useState<string | null>(null);
  const [proposalId, setProposalId] = useState<string | null>(null);

  async function read(file: File) {
    setProblem(null);
    setStep("reading");
    try {
      const data = (await post("/api/fiona/agents/read-bill", { filename: file.name, content_base64: await toBase64(file) })) as unknown as Reading;
      setReading(data);
      setForm({
        supplierId: data.supplier_candidates[0]?.id ?? "",
        number: data.fields.invoice_number?.value ?? "",
        issueDate: data.dates.issue_date ?? "",
        dueDate: data.dates.due_date ?? "",
        subtotal: majorText(data.amounts_minor.subtotal),
        tax: majorText(data.amounts_minor.tax),
        total: majorText(data.amounts_minor.total),
        category: "inventory_supplier",
      });
      setStep("review");
    } catch (err) {
      setProblem(err instanceof Error ? err.message : "The bill could not be read.");
      setStep("choose");
    }
  }

  async function record() {
    if (!reading) return;
    const subtotal = minorFromInput(form.subtotal);
    const tax = minorFromInput(form.tax);
    const total = minorFromInput(form.total);
    if (!form.supplierId || subtotal === null || tax === null || total === null || !form.issueDate || !form.dueDate) {
      setProblem("Choose the supplier and fill in the dates and amounts (for example 72033.90).");
      return;
    }
    setProblem(null);
    setStep("recording");
    try {
      const recorded = await post("/api/fiona/bills/intake", {
        supplier_id: form.supplierId,
        number: form.number,
        issue_date: form.issueDate,
        due_date: form.dueDate,
        subtotal_minor: subtotal,
        tax_minor: tax,
        total_minor: total,
        category: form.category,
        po_number: reading.fields.purchase_order_ref?.value ?? null,
        bank_iban: reading.fields.bank_iban?.value ?? null,
        document_filename: reading.document.filename,
        document_text: reading.document.text,
        embedded_instructions: reading.embedded_instructions,
        warnings: reading.warnings,
      });
      const id = String(recorded.bill_id);
      setBillId(id);
      const supplier = reading.supplier_candidates.find((c) => c.id === form.supplierId)?.name ?? form.supplierId;
      const started = await post("/api/fiona/agents/team/run", {
        agent: "treasurer",
        task: `A new bill was just recorded: ${id} from ${supplier}, due ${form.dueDate}. Look at it with your tools and decide whether and when to propose paying it. If you propose it, use propose_payment for ${id}. Report what you decided and why.`,
      });
      setRunId(String(started.run_id));
      setStep("treasurer");
    } catch (err) {
      setProblem(err instanceof Error ? err.message : "The bill could not be recorded.");
      setStep("review");
    }
  }

  // Follow the Treasurer's run until it finishes, then find its proposal for this bill.
  useEffect(() => {
    if (step !== "treasurer" || !runId) return;
    const timer = window.setInterval(async () => {
      const res = await fetch(`/api/fiona/agents/team/runs/${runId}`, { cache: "no-store" });
      const run = (await res.json().catch(() => ({}))) as Record<string, unknown>;
      if (run.status === "completed" || run.status === "failed") {
        window.clearInterval(timer);
        setRunSummary(String(run.summary ?? run.error ?? ""));
        const list = (await (await fetch("/api/fiona/proposals", { cache: "no-store" })).json()) as { proposals?: Array<{ id: string; payload?: { bill_id?: string } }> };
        setProposalId(list.proposals?.find((p) => p.payload?.bill_id === billId)?.id ?? null);
        setStep("done");
      }
    }, 4_000);
    return () => window.clearInterval(timer);
  }, [step, runId, billId]);

  const candidates = reading?.supplier_candidates ?? [];
  const chosen = candidates.find((c) => c.id === form.supplierId);
  const billIban = reading?.fields.bank_iban?.value?.replace(/\s/g, "") ?? null;

  return (
    <Card className="tier-panel sk-panel bill-intake">
      <div className="panel-heading sk-panel-heading">
        <div><span className="eyebrow">Add a bill</span><h2>Upload a bill and follow it through</h2></div>
        <span className="sk-pill sk-pill-neutral">Read by Claude · checked by code · you confirm</span>
      </div>

      <ol className="sk-progress" aria-label="Where this bill is">
        {BILL_STAGES.map(([label], index) => {
          const at = BILL_STAGES.findIndex(([, s]) => s.includes(step));
          const state = index < at || step === "done" ? "is-done" : index === at ? "is-current" : "";
          return <li key={label} className={state} aria-current={index === at && step !== "done" ? "step" : undefined}><i aria-hidden="true" />{label}</li>;
        })}
      </ol>

      <div className="bill-intake-body">
        {(step === "choose" || step === "reading") && (
          <label
            className={`sk-drop ${dragging ? "is-dragging" : ""} ${step === "reading" ? "is-busy" : ""}`}
            onDragOver={(e) => { e.preventDefault(); if (step === "choose") setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files?.[0]; if (f && step === "choose") read(f); }}
          >
            <input type="file" accept=".pdf,.txt,application/pdf,text/plain" disabled={step === "reading"} onChange={(e) => { const f = e.target.files?.[0]; if (f) read(f); }} />
            <span className="sk-drop-icon" aria-hidden="true">{step === "reading" ? <span className="sk-spinner" /> : <UploadIcon width="20" height="20" />}</span>
            <span className="sk-drop-text">
              <strong>{step === "reading" ? "Reading the bill…" : "Choose a bill (PDF or text)"}</strong>
              <small>{step === "reading" ? "Claude transcribes it with quotes; code checks every quote against the document." : "or drop it here · nothing is posted until you confirm"}</small>
            </span>
          </label>
        )}
        {problem && <p className="login-error" role="alert">{problem}</p>}

        {reading && step !== "choose" && step !== "reading" && (
          <>
            {reading.embedded_instructions.length > 0 && (
              <div className="bill-alert" role="alert">
                <strong>This bill contains instructions aimed at software. Fiona reported them and did not follow them.</strong>
                <ul>{reading.embedded_instructions.map((t) => <li key={t}>&ldquo;{t}&rdquo;</li>)}</ul>
              </div>
            )}
            {reading.warnings.length > 0 && (
              <ul className="bill-warnings">{reading.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
            )}

            <div className="bill-read-grid">
              {FIELD_LABELS.map(([key, label]) => {
                const f = reading.fields[key];
                return (
                  <div key={key} className="bill-read-field">
                    <span className="spec-label">{label}</span>
                    <strong>{f?.value ?? "Not on the bill"}</strong>
                    {f?.value && <small className={f.quote_verified ? "quote-ok" : "quote-bad"}>{f.quote_verified ? "✓ found in the document" : "⚠ quote not found, check by hand"}</small>}
                  </div>
                );
              })}
            </div>

            <div className="admin-form">
              <label>
                <span className="spec-label">Supplier in your ledger</span>
                <select value={form.supplierId} onChange={(e) => setForm({ ...form, supplierId: e.target.value })} disabled={step !== "review"}>
                  <option value="">Choose…</option>
                  {candidates.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.id}){c.on_allow_list ? "" : " · not allow-listed"}</option>)}
                </select>
              </label>
              <label><span className="spec-label">Invoice number</span><input value={form.number} onChange={(e) => setForm({ ...form, number: e.target.value })} disabled={step !== "review"} /></label>
              <label><span className="spec-label">Issue date</span><input type="date" value={form.issueDate} onChange={(e) => setForm({ ...form, issueDate: e.target.value })} disabled={step !== "review"} /></label>
              <label><span className="spec-label">Due date</span><input type="date" value={form.dueDate} onChange={(e) => setForm({ ...form, dueDate: e.target.value })} disabled={step !== "review"} /></label>
              <label><span className="spec-label">Subtotal (PKR)</span><input inputMode="decimal" value={form.subtotal} onChange={(e) => setForm({ ...form, subtotal: e.target.value })} disabled={step !== "review"} /></label>
              <label><span className="spec-label">Tax (PKR)</span><input inputMode="decimal" value={form.tax} onChange={(e) => setForm({ ...form, tax: e.target.value })} disabled={step !== "review"} /></label>
              <label><span className="spec-label">Total (PKR)</span><input inputMode="decimal" value={form.total} onChange={(e) => setForm({ ...form, total: e.target.value })} disabled={step !== "review"} /></label>
            </div>

            {chosen && billIban && chosen.bank_iban && chosen.bank_iban !== billIban && (
              <p className="bill-alert" role="alert">
                <strong>Bank account mismatch.</strong> The bill asks for payment to {billIban}; the account on file for {chosen.name} is {chosen.bank_iban}. The Guardian will see this.
              </p>
            )}

            {step === "review" && (
              <div className="panel-actions">
                <button className="button button-primary" type="button" onClick={record}>Record the bill and ask the Treasurer</button>
                <button className="button button-quiet" type="button" onClick={() => { setReading(null); setStep("choose"); }}>Start again</button>
              </div>
            )}
            {step === "recording" && <p className="agent-activity-note">Recording the bill and posting it to the ledger…</p>}
            {step === "treasurer" && <p className="agent-activity-note">Bill {billId} recorded and posted. The Treasurer is looking at it now (about a minute)…</p>}
            {step === "done" && (
              <div className="bill-done">
                <p><strong>Bill {billId} recorded.</strong> {runSummary}</p>
                {proposalId ? (
                  <p>
                    The Treasurer proposed a payment; the Guardian is checking it now.{" "}
                    <Link className="text-link" href={`/proposals/${proposalId}`}>Follow it step by step →</Link>{" "}
                    <Link className="text-link" href="/approvals">Decide in Approvals →</Link>
                  </p>
                ) : (
                  <p>The Treasurer did not propose paying it yet; its reasons are above.</p>
                )}
              </div>
            )}
            <p className="footnote">
              Read by {reading.meta.model}. Amounts: subtotal {reading.amounts_minor.subtotal !== null ? <MoneyText amountMinor={reading.amounts_minor.subtotal} animateCount={false} /> : "?"}, tax {reading.amounts_minor.tax !== null ? <MoneyText amountMinor={reading.amounts_minor.tax} animateCount={false} /> : "?"}, total {reading.amounts_minor.total !== null ? <MoneyText amountMinor={reading.amounts_minor.total} animateCount={false} /> : "?"}, converted by code from the printed figures.
            </p>
          </>
        )}
      </div>
    </Card>
  );
}
