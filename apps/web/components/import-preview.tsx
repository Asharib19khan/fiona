"use client";

import { useState, type ChangeEvent, type DragEvent } from "react";
import { UploadIcon } from "@/components/briefing-icons";
import { useRouter } from "next/navigation";

type ImportKind = "bank" | "pos";

const requiredColumns: Record<ImportKind, string[]> = {
  bank: ["account_iban", "line_no", "posted_on", "value_date", "narration", "reference", "amount_minor", "balance_minor", "currency"],
  pos: ["receipt_no", "line_no", "txn_type", "original_receipt_no", "occurred_at", "business_date", "branch_id", "register_id", "cashier_id", "customer_code", "sku", "qty", "unit_price_minor", "discount_minor", "line_total_minor", "tax_minor", "payment_method", "payment_status", "currency"],
};

function parseCsv(input: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;
  for (let index = 0; index < input.length; index += 1) {
    const char = input[index];
    if (quoted) {
      if (char === '"' && input[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        field += char;
      }
    } else if (char === '"' && field.length === 0) {
      quoted = true;
    } else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\n") {
      row.push(field.replace(/\r$/, ""));
      if (row.some((cell) => cell.length)) rows.push(row);
      row = [];
      field = "";
    } else {
      field += char;
    }
  }
  if (quoted) throw new Error("The file ends inside a quoted field.");
  row.push(field.replace(/\r$/, ""));
  if (row.some((cell) => cell.length)) rows.push(row);
  return rows;
}

export function ImportPreview({ enabled }: { enabled: boolean }) {
  const router = useRouter();
  const [kind, setKind] = useState<ImportKind>("bank");
  const [fileName, setFileName] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [headers, setHeaders] = useState<string[]>([]);
  const [previewRows, setPreviewRows] = useState<string[][]>([]);
  const [rowCount, setRowCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<{ inserted: number; skipped: number; errors: Array<{ row?: number; reason?: string }> } | null>(null);

  const [dragging, setDragging] = useState(false);

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    void readFile(event.target.files?.[0]);
    event.target.value = "";
  }

  function dropFile(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    void readFile(event.dataTransfer.files?.[0]);
  }

  async function readFile(file: File | undefined) {
    setError(null);
    setFileName(file?.name ?? null);
    setFile(file ?? null);
    setReport(null);
    setHeaders([]);
    setPreviewRows([]);
    setRowCount(0);
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      setError("Choose a CSV under 2 MB for this local preview.");
      return;
    }
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setError("Choose a .csv file.");
      return;
    }
    try {
      const rows = parseCsv(await file.text());
      const firstRow = rows[0];
      if (!firstRow) throw new Error("The file is empty.");
      const columns = firstRow.map((header: string) => header.trim());
      const missing = requiredColumns[kind].filter((column) => !columns.includes(column));
      if (missing.length) {
        setHeaders(columns);
        setError(`Missing expected ${kind.toUpperCase()} columns: ${missing.join(", ")}.`);
        return;
      }
      setHeaders(columns);
      setPreviewRows(rows.slice(1, 6).map((cells) => columns.map((_, column) => cells[column] ?? "")));
      setRowCount(Math.max(0, rows.length - 1));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The CSV could not be read.");
    }
  }

  function changeKind(next: ImportKind) {
    setKind(next);
    setFileName(null);
    setHeaders([]);
    setPreviewRows([]);
    setRowCount(0);
    setError(null);
    setFile(null);
    setReport(null);
  }

  async function importFile() {
    if (!file || !enabled) return;
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      const response = await fetch(`/api/fiona/import/${kind}`, {
        method: "POST",
        headers: { "content-type": "text/csv; charset=utf-8", "x-file-name": file.name },
        body: await file.text(),
        cache: "no-store",
      });
      const body: unknown = await response.json();
      if (!response.ok) {
        const detail = body && typeof body === "object" && "error" in body && body.error && typeof body.error === "object" && "message" in body.error ? String(body.error.message) : "The CSV was not imported.";
        throw new Error(detail);
      }
      const result = body as { inserted?: number; skipped?: number; errors?: Array<{ row?: number; reason?: string }> };
      setReport({ inserted: result.inserted ?? 0, skipped: result.skipped ?? 0, errors: result.errors ?? [] });
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The CSV could not be imported.");
    } finally {
      setBusy(false);
    }
  }

  const labels: Record<ImportKind, string> = { bank: "Bank statement", pos: "POS sales" };
  return <div className="import-preview sk-import">
    <div className="sk-import-type" role="radiogroup" aria-label="Record type">
      <span className="sk-field-label">Record type</span>
      <div className="sk-segmented">{(Object.keys(labels) as ImportKind[]).map((option) => <button key={option} type="button" role="radio" aria-checked={kind === option} className={kind === option ? "is-active" : undefined} onClick={() => changeKind(option)}>{labels[option]}</button>)}</div>
    </div>
    <label className={`sk-drop ${dragging ? "is-dragging" : ""} ${fileName && !error ? "has-file" : ""}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={dropFile}>
      <input type="file" accept=".csv,text/csv" onChange={chooseFile} />
      <span className="sk-drop-icon" aria-hidden="true"><UploadIcon width="20" height="20" /></span>
      <span className="sk-drop-text">{fileName ? <><strong>{fileName}</strong><small>{rowCount > 0 ? `${rowCount.toLocaleString()} data rows · choose another file to replace it` : "Choose another file to replace it"}</small></> : <><strong>Choose CSV</strong><small>or drop a {labels[kind].toLowerCase()} file here · up to 2 MB</small></>}</span>
    </label>
    <p className="import-privacy">The file is previewed in this tab. It is sent to the local synthetic ledger only after you choose Import.</p>
    {error && <p className="import-error" role="alert">{error}</p>}
    {file && enabled && !error && <button className="button button-primary" type="button" onClick={importFile} disabled={busy}>{busy ? "Importing…" : `Import ${kind === "bank" ? "bank statement" : "POS sales"}`}</button>}
    {file && !enabled && <p className="footnote">Import is disabled outside local mock mode.</p>}
    {report && <div className="import-report" role="status" aria-live="polite"><strong>{report.inserted} inserted · {report.skipped} already present · {report.errors.length} row errors</strong>{report.errors.slice(0, 20).map((item, index) => <p className="import-error" key={`${item.row ?? index}-${index}`}>Row {item.row ?? "?"}: {item.reason ?? "Invalid row"}</p>)}</div>}
    {headers.length > 0 && <div className="data-table-wrap sk-table-wrap sk-import-table"><table className="data-table sk-table"><thead><tr>{headers.slice(0, 8).map((header) => <th key={header}>{header}</th>)}</tr></thead><tbody>{previewRows.map((row, rowIndex) => <tr key={rowIndex}>{row.slice(0, 8).map((cell, cellIndex) => <td key={cellIndex}>{cell || "—"}</td>)}</tr>)}</tbody></table></div>}
    <div className="sk-columns"><span className="sk-field-label">Expected columns</span><div>{requiredColumns[kind].map((column) => <code className="sk-mono" key={column}>{column}</code>)}</div></div>
  </div>;
}
