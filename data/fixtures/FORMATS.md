# Fiona fixture file formats (v0 — proposed for G1 sign-off)

**Status:** PROPOSED by Daniyal's lane (D2a), 13 Oct 2026; orchestrator rulings applied. Seed-42 files are generated in `ten_karachi_apparel/`. Needs Asharib's sign-off at G1 (Wed 14 Oct).
After sign-off, changes are additive only (new files, new optional columns or fields).

**All data in these files is SYNTHETIC.** It describes invented businesses, people, suppliers and
bank accounts. Nothing here comes from or refers to a real company, person or account.

Produced by:

```
python -m data.generator --seed 42 --persona karachi_apparel --months 24 --out data/fixtures/
```

The same seed, persona, months and generator version always produce byte-identical files.
**These files are reproducible byte for byte from the seed** by running the command above (the test suite
checks it). They are committed so every lane can read them without running the generator; regenerate only for a
calibration or scenario fix, batched, and never rewrite git history.
`manifest.json` lists the SHA-256 of every file so you can check this.

---

## 1. Conventions (apply to every file)

| Topic | Rule |
|---|---|
| Encoding | UTF-8 without BOM, `\n` line endings, final newline |
| CSV | Comma-delimited, one header row, RFC 4180 quoting only when needed. An empty cell means null |
| JSON | 2-space indent, UTF-8 (not ASCII-escaped). Object files have a top-level `"synthetic": true` |
| JSONL | One compact JSON object per line (`events.jsonl`) |
| Money | **Integer minor units.** Every money field ends in `_minor` (PKR: 1 rupee = 100 minor). Each record has one `currency` field (ISO 4217). There are no floats anywhere |
| Dates | `YYYY-MM-DD`, the business date in the tenant's local time zone (`Asia/Karachi`) |
| Timestamps | ISO 8601 in UTC with `Z`, e.g. `2026-10-03T14:42:10Z` |
| Booleans | `true` / `false` |
| Rates | Integer basis points, e.g. `rate_bp: 1800` = 18 %. Tax = round-half-up(base × rate_bp / 10000) |
| Sign | Bank `amount_minor`: money **in** is positive, money **out** is negative |

### Identifiers

Fixture **reference entities** use short, readable, stable IDs. The demo threads rely on these
(`sup_017`, `bill_2231`, `doc_88`). They are unique per tenant: every database key is `(tenant_id, id)`.

| Entity | Pattern | Example |
|---|---|---|
| Tenant | `ten_<slug>` | `ten_karachi_apparel` |
| Supplier | `sup_###` | `sup_017` |
| Customer | `cus_####` | `cus_0142` (POS code `C-0142`), B2B `cus_9001` (code `B-9001`) |
| Other party (landlord, utility, lender, tax authority) | `pty_###` | `pty_001` |
| Item | the SKU itself: `<CAT>-<SIZE>-<COLOUR>` | `KRT-M-BLU` |
| Purchase order / goods received | `po_####` / `grn_####` | `po_1043` / `grn_1043` |
| Supplier bill / document | `bill_####` / `doc_##` | `bill_2231` / `doc_88` |
| Customer invoice | `inv_####` | `inv_0007` |
| Supplier payment | `pay_####` | `pay_0031` |
| Mandate | `mnd_<agent>_v<version>` | `mnd_treasurer_v1` |

**Events and bank lines** get deterministic ULIDs (`evt_…`, `bln_…`) derived from their source, so
the importers (D3) reproduce exactly the IDs that the fixtures and the answer key use:

```
id = prefix + ULID( timestamp_ms = occurred_at (bank lines: posted_on 00:00 UTC),
                    randomness   = first 10 bytes of SHA-256("<tenant_id>|<source_type>|<source_key>") )
```

`source_key` is the natural key of the source record: the receipt number for a POS sale,
`<iban>#<line_no>` for a bank line, and the bill, invoice or payment ID for the others.
The importers use the same key for idempotency, so re-importing a file, or an overlapping
statement, adds nothing.

Runtime objects (proposals `prop_`, findings `fnd_`) use ordinary ULIDs. They are not part of the fixtures.

---

## 2. Files per tenant

The generator writes `data/fixtures/<tenant_id>/`:

| File | What it is | Consumers |
|---|---|---|
| `manifest.json` | generator version, seed, persona, period, SHA-256 of each file | everyone (reproducibility) |
| `tenant.json` | tenant profile, branches, bank account, draft country-pack values | all mocks, D1 seed |
| `mandates.json` | default agent mandates (**DRAFT** until rulebook B2) | Guardian, agents, D5/D6 |
| `accounts.csv` | chart of accounts with framework-neutral classes | D3 postings, D8 |
| `parties.csv` | suppliers, customers, landlord, utilities, lender, tax authority | everyone |
| `items.csv` | SKU catalogue: cost, price, opening stock, reorder level | Yahya (stock, Launch Lab), D3 |
| `purchase_orders.json` | purchase orders with lines | three-way match (G-06) |
| `goods_received.json` | goods-received notes with lines | three-way match (G-06) |
| `bills.json` | supplier bills **as extracted** from documents | importers, Guardian, agents |
| `documents/<doc_id>.txt` | the rendered bill documents; `document_sha256` hashes these bytes | same-file duplicate check (G-05) |
| `customer_invoices.json` | invoices issued to B2B customers | receivables, forecast |
| `bank_statement.csv` | raw bank statement lines | importer, reconciliation |
| `pos_sales.csv` | raw POS export, one row per receipt line, **no cost column** | importer, POS reconciliation |
| `pos_z_reports.csv` | end-of-day drawer report per register | cash over/short, register outliers |
| `events.jsonl` | the canonical ledger events (ground truth) | `GET /v1/ledger/events` mock, forecast |
| `answer_key.json` | planted scenarios, true bank-line matches, clean bills, truths for other lanes | tests, scoring |
| `loans.json` | loan agreement and full repayment schedule (principal, interest, KIBOR + spread, DSCR covenant) | frameworks, decisions, D3 postings |
| `leases.json` | shop leases (term, rent schedule, escalation, renewal option, IBR); BR01 is billed monthly | frameworks lens (IFRS 16 / Section 20) |
| `fixed_assets.json` | asset register (cost, date, useful life, straight-line depreciation) | statements, Stage Detector |
| `payroll.json` | monthly payroll summary (headcount, gross, withholding, net paid) | statements, forecast |
| `opening_balances.json` | opening trial balance at the period start (also an `opening_balances` event) | statements |
| `nrv_assessments.json` | NRV assessments of dead stock: per item qty, cost, estimated selling price and NRV; allowance before and after, the part used by units sold, the write-down and the (partial) reversal; linked to their journal events | frameworks write-down lens |

**Held-out truth** lives apart, in `data/fixtures/holdout/<tenant_id>/` (`cash_weekly.json`, `demand_weekly.csv`,
own manifest): the 13 weeks after `as_of`, for backtests and the dip check only. Never train or tune on it.

**Period (v1, D2).** The history starts on the fiscal-year start on or before `as_of − months`, so every fiscal year
in it is complete (Karachi: 1 Jul 2024 to 22 Oct 2026, FY25 and FY26 whole).

---

## 3. File details

### 3.1 `tenant.json`

```json
{
  "synthetic": true,
  "id": "ten_karachi_apparel",
  "name": "Karachi Apparel Co. (synthetic)",
  "country": "PK",
  "currency": "PKR",
  "minor_unit": 2,
  "framework": "IFRS_SMES",
  "fiscal_year_start_month": 7,
  "timezone": "Asia/Karachi",
  "as_of": "2026-10-22",
  "period": { "start": "2026-08-23", "end": "2026-10-22" },
  "branches": [ { "id": "BR01", "name": "Tariq Road", "registers": ["R1", "R2", "R3"] } ],
  "bank_accounts": [ { "iban": "PK..SYNA..", "name": "Operating account", "opening_balance_minor": 0 } ],
  "policies": { "cash_buffer_minor": 200000000 },
  "country_pack_draft": { "gst_rate_bp": 1800, "prices_include_gst": true, "tax_id_type": "NTN", "tax_id_pattern": "^[0-9]{7}-[0-9]$" }
}
```

`framework` is one of `IFRS_SMES`, `IFRS`, `US_GAAP`, `CAS`. `policies` holds the owner's
tenant-level policies. `cash_buffer_minor` is the owner's minimum cash level; it is read by the
forecast, the briefing, Launch Lab affordability and G-08 (orchestrator ruling, 13 Oct).
`country_pack_draft` holds assumptions until Abdullah's country pack exists. The real values
will move to `rulebook/`.

IBANs are synthetic but well-formed. Each has valid ISO 13616 mod-97 check digits, so format
validators pass. The bank codes (`SYNA`, `SYNB`, `SYNC`, …) belong to no real bank, so the
accounts are obviously synthetic.

### 3.2 `mandates.json`

The mandates are copied verbatim from `rulebook/mandates.yaml` → `persona_mandates.<tenant_id>`,
Abdullah's source of truth. The generator never hand-copies the numbers. `source` names the
rulebook version. Mandate fields beyond the core columns (`autonomy`, `allowed_categories`,
`payee_scope`, `payment_windows`, `approved_by`) pass through unchanged.

```json
{
  "synthetic": true,
  "source": "rulebook/mandates.yaml v1.0.0",
  "mandates": [
    { "tenant_id": "ten_karachi_apparel", "id": "mnd_treasurer_v1", "agent": "treasurer", "version": 1,
      "currency": "PKR", "autonomy": { "payment": "act_within_mandate" },
      "per_payment_cap_minor": 15000000, "daily_cap_minor": 45000000,
      "allowed_action_types": ["payment"], "allowed_categories": ["inventory_supplier", "utilities", "rent", "logistics"],
      "payee_scope": "allow_list_only", "payment_windows": { "...": "..." },
      "effective_from": "2026-08-01", "approved_by": "usr_owner" }
  ]
}
```

The cash buffer is **not** a mandate field; it lives in `tenant.json → policies`.

### 3.3 `accounts.csv`

`code,name,class,neutral_class`

`class` ∈ `asset, liability, equity, income, expense`. `neutral_class` is the framework-neutral
bucket used for postings and the framework lens, e.g. `cash`, `clearing`, `receivables`,
`inventory`, `tax_receivable`, `payables`, `tax_payable`, `borrowings`, `equity`, `revenue`,
`sales_returns`, `cost_of_sales`, `payroll`, `occupancy`, `utilities`, `bank_charges`, `cash_over_short`, `interest`.

```
1000,Bank - operating account,asset,cash
4000,Sales revenue,income,revenue
```

### 3.4 `parties.csv`

`party_id,kind,code,name,tax_id,tax_id_type,bank_iban,bank_account_changed_at,on_allow_list,payment_terms_days,phone,city`

`kind` ∈ `supplier, customer, landlord, utility, lender, tax_authority`. The columns hold each
party's **current** state as of `as_of`. Each bank change also appears in `events.jsonl` as a
`bank_detail_change`. Phone numbers use the impossible prefix `+92-000-…` so they can never reach
a real person.

```
sup_017,supplier,S-017,Mehran Garments,4417023-6,NTN,PK..SYNB..,2026-10-20T06:30:00Z,true,30,+92-000-000-0017,Karachi
cus_0142,customer,C-0142,Customer C-0142,,,,,false,0,,Karachi
```

### 3.5 `items.csv`

`sku,name,category,size,colour,season,unit_cost_minor,price_minor,currency,opening_stock_qty,reorder_level,supplier_id,lead_time_days,launched_on`

Each size and colour variant is its own SKU. `season` ∈ `all, summer, winter`. `price_minor`
includes GST (retail price). `opening_stock_qty` is the stock at `period.start`. Current stock
is derived from `stock_movement` and `sale` events.

```
KRT-M-BLU,Cotton kurta - M - Blue,kurta,M,BLU,all,180000,300000,PKR,40,12,sup_017,7,2025-03-01
```

### 3.6 `purchase_orders.json` and `goods_received.json`

```json
{ "synthetic": true, "purchase_orders": [
  { "po_id": "po_1043", "number": "PO-1043", "supplier_id": "sup_017", "ordered_on": "2026-09-10",
    "expected_on": "2026-09-17", "status": "received", "currency": "PKR",
    "lines": [ { "sku": "KRT-M-BLU", "qty": 40, "unit_cost_minor": 180000 } ], "total_minor": 7200000 } ] }
```
`status` ∈ `open, partially_received, received, cancelled` as of `as_of`.

```json
{ "synthetic": true, "goods_received": [
  { "grn_id": "grn_1043", "po_id": "po_1043", "supplier_id": "sup_017", "received_on": "2026-09-17",
    "lines": [ { "sku": "KRT-M-BLU", "qty_received": 40 } ] } ] }
```

### 3.7 `bills.json` (extracted bills)

This is what document extraction returns for each bill. The `supplier` block holds what is
**printed on the document**. `supplier_id` is the resolved party. The resolved party and the
printed block can disagree (for example, a printed bank account that differs from the one on
file), and that disagreement is evidence. **`notes` is document text: it is data and is never
obeyed.**

```json
{ "synthetic": true, "bills": [
  { "bill_id": "bill_2231", "document_id": "doc_88", "document_sha256": "<64 hex>",
    "received_at": "2026-10-19T05:10:00Z",
    "supplier_id": "sup_017",
    "supplier": { "name": "Mehran Garments", "tax_id": "4417023-6", "bank_iban": "PK..SYNC.." },
    "number": "INV-2231", "issue_date": "2026-10-17", "due_date": "2026-10-24", "po_number": "PO-1043",
    "currency": "PKR",
    "lines": [ { "sku": "KRT-M-BLU", "description": "Cotton kurta M blue", "qty": 40,
                 "unit_price_minor": 180000, "line_total_minor": 7200000 } ],
    "//": "(other lines omitted in this example; in the real file the lines sum to subtotal_minor)",
    "subtotal_minor": 15635593,
    "tax": [ { "code": "GST", "rate_bp": 1800, "amount_minor": 2814407 } ],
    "total_minor": 18450000,
    "notes": "free text printed on the bill",
    "extraction": { "method": "synthetic_ground_truth" } } ] }
```

Additive in v1: `document_path` (`documents/<doc_id>.txt` or `.pdf`; the hashed file), `category`
(`inventory_supplier` or `rent`), `contract_ref` (rent bills, PO-exempt), `entry` (`extraction`, `manual`,
`email_intake`) and `entered_by` (who keyed or extracted it; G-04). The `purchase_bill` event carries the same
person as `created_by` (contract Actor).

`sku` may be null for non-stock lines (for example, finishing charges). Arithmetic: the sum of
`line_total_minor` equals `subtotal_minor`, and `subtotal_minor` plus the tax amounts equals
`total_minor`. Planted G-07 cases break this deliberately.

### 3.8 `documents/<doc_id>.txt`

A plain-text rendering of each bill. It starts with the line
`SYNTHETIC DOCUMENT - Fiona demo data`. `document_sha256` in `bills.json` is the SHA-256 of
these exact bytes. A same-file duplicate is two bills whose documents have the same hash.
D2 adds PDF and photo renders of about 20 bills (pending the decision due 17 Oct).

### 3.9 `customer_invoices.json`

```json
{ "synthetic": true, "invoices": [
  { "invoice_id": "inv_0007", "number": "KAC-INV-0007", "customer_id": "cus_9001",
    "issue_date": "2026-09-02", "due_date": "2026-10-02", "currency": "PKR",
    "lines": [ { "sku": "KRT-M-WHT", "description": "Cotton kurta M white", "qty": 120,
                 "unit_price_minor": 254237, "line_total_minor": 30508440 } ],
    "subtotal_minor": 30508440, "tax": [ { "code": "GST", "rate_bp": 1800, "amount_minor": 5491519 } ],
    "total_minor": 35999959 } ] }
```

### 3.10 `bank_statement.csv`

`account_iban,line_no,posted_on,value_date,narration,reference,amount_minor,balance_minor,currency`

`line_no` runs 1..N in statement order. `balance_minor` is the running balance after the line,
so the opening balance is `balance_minor - amount_minor` of line 1.

```
PK..SYNA..,1,2026-08-24,2026-08-24,POS CARD SETTL MID 448120 BATCH 0823,ST2608240001,1843500,912843500,PKR
PK..SYNA..,57,2026-09-28,2026-09-28,IBFT TO MEHRAN GARMENTS INV 2231,FT2609280057,-18450000,804112300,PKR
```

Narration patterns (D4 reconciliation keys on them):
`POS CARD SETTL …`, `RAAST P2M SETTL …`, `QR SETTL …`, `JAZZCASH MERCH SETTL …`,
`EASYPAISA MERCH SETTL …`, `CASH DEPOSIT BR01 …`, `IBFT TO <SUPPLIER> <INV NO>`,
`IBFT FROM <CUSTOMER> <INV NO(S)>`, `SALARY BULK TRF <MON-YYYY>`, `RENT <MON-YYYY> <BRANCH>`,
`ELECTRICITY BILL …`, `GAS BILL …`, `LOAN INSTALMENT nn/36`, `MDR CHARGES <MON-YYYY>`,
`BANK CHARGES …`, `FBR SALES TAX <MON-YYYY>`.

### 3.11 `pos_sales.csv`

`receipt_no,line_no,txn_type,original_receipt_no,occurred_at,business_date,branch_id,register_id,cashier_id,customer_code,sku,qty,unit_price_minor,discount_minor,line_total_minor,tax_minor,payment_method,payment_status,currency`

- One row per receipt line. `receipt_no` is `<register>-<seq>`, for example `R1-004412`.
- `txn_type` ∈ `sale, refund, void`. A refund has negative `qty` and totals and names `original_receipt_no`. A void keeps the original amounts and moves no money.
- `payment_method` ∈ `cash, card, bank_qr, raast, jazzcash, easypaisa`. There is one method per receipt (assumption: no split tenders).
- `payment_status` ∈ `settled, reversed`. Refunds and voids are `reversed`.
- `line_total_minor = qty × unit_price_minor − discount_minor`. Prices include GST. `tax_minor` = round-half-up(line_total × rate_bp / (10000 + rate_bp)).
- **There is no cost column.** The D3 importer joins `unit_cost_minor` from `items.csv`.
- `customer_code` is empty for walk-in customers.

```
R1-004412,1,sale,,2026-10-03T09:42:10Z,2026-10-03,BR01,R1,CSH-03,C-0142,KRT-M-BLU,3,300000,0,900000,137288,bank_qr,settled,PKR
```

### 3.12 `pos_z_reports.csv`

`z_no,business_date,branch_id,register_id,opening_float_minor,cash_sales_minor,cash_refunds_minor,expected_cash_minor,counted_cash_minor,over_short_minor,card_total_minor,bank_qr_total_minor,raast_total_minor,jazzcash_total_minor,easypaisa_total_minor,receipt_count,refund_count,void_count,currency`

`expected_cash = opening_float + cash_sales + cash_refunds` (cash refunds are negative), and
`over_short = counted_cash − expected_cash`. The next banking day's cash deposit for a branch
is the sum over its registers of `counted_cash − opening_float`.

### 3.13 `events.jsonl` (canonical ledger events)

These are flat objects in the Blueprint's shape, plus `id`, `tenant_id` and `occurred_at`. In the
database, the envelope fields are columns and the rest is `payload`. Lines are sorted by
`(occurred_at, id)`. Every amount is `*_minor` in the event's `currency`.

| `event` | Type-specific fields |
|---|---|
| `sale` | `party`, `receipt_no`, `txn`, `original_receipt_no`, `branch`, `register`, `cashier`, `lines[{item, qty, price_minor, discount_minor, total_minor, tax_minor, cost_minor}]`, `total_minor`, `tax_minor`, `payment{method, status}` |
| `purchase_bill` | `party`, `bill_id`, `number`, `issue_date`, `due_date`, `po_number`, `lines`, `subtotal_minor`, `tax_minor`, `total_minor`, `document_id`, `document_sha256` |
| `supplier_payment` | `party`, `payment_id`, `bill_id`, `amount_minor`, `from_iban`, `to_iban`, `method`, `wallet_ref` (null for historical payments) |
| `customer_invoice` | `party`, `invoice_id`, `number`, `issue_date`, `due_date`, `lines`, `subtotal_minor`, `tax_minor`, `total_minor` |
| `customer_receipt` | `party`, `invoice_ids`, `bank_line_id`, `amount_minor`. **Not in fixtures.** Reconciliation (D4) creates these when a credit is matched to invoices |
| `bank_line` | `bank_line_id`, `account_iban`, `line_no`, `narration`, `reference`, `amount_minor`, `balance_minor` |
| `stock_movement` | `item`, `qty` (+ in / − out), `unit_cost_minor`, `reason` ∈ `goods_received, adjustment`, `ref`. Sales imply stock out, so they are not repeated here |
| `bank_detail_change` | `party`, `old_iban`, `new_iban`, `confirmed_via` ∈ `email, phone, none`, `confirmed_by` |
| `journal_adjustment` | `lines[{account, debit_minor, credit_minor}]`, `reason`, `approver` (the opening balances are one of these) |

Every event carries `source{type, file?, row?, key}`, where `type` ∈ `pos_export, bank_statement,
bill_extraction, invoicing, manual`.

```json
{"id":"evt_01K…","tenant_id":"ten_karachi_apparel","event":"sale","occurred_at":"2026-10-03T09:42:10Z","date":"2026-10-03","currency":"PKR","party":"cus_0142","receipt_no":"R1-004412","txn":"sale","original_receipt_no":null,"branch":"BR01","register":"R1","cashier":"CSH-03","lines":[{"item":"KRT-M-BLU","qty":3,"price_minor":300000,"discount_minor":0,"total_minor":900000,"tax_minor":137288,"cost_minor":180000}],"total_minor":900000,"tax_minor":137288,"payment":{"method":"bank_qr","status":"settled"},"source":{"type":"pos_export","file":"pos_sales.csv","row":4412,"key":"R1-004412"}}
```

### 3.14 `answer_key.json`

```json
{
  "synthetic": true, "tenant_id": "ten_karachi_apparel", "seed": 42, "as_of": "2026-10-22",
  "scenarios": [
    { "id": "DEMO-1", "rules": ["G-03", "G-05", "G-12"], "also_fires": ["G-01"], "expected_outcome": "block",
      "refs": { "bill_ids": ["bill_2231", "bill_2188"], "document_ids": ["doc_88", "doc_61"],
                "party_ids": ["sup_017"], "event_ids": ["evt_…"] },
      "note": "INV-2231 re-sent after last month's INV 2231 was paid; bank account changed 2 days ago" }
  ],
  "matches": [ { "bank_line_id": "bln_…", "line_no": 57, "kind": "supplier_payment", "event_ids": ["evt_…"] } ],
  "unmatched_bank_lines": [ { "bank_line_id": "bln_…", "line_no": 3, "category": "payroll" } ],
  "clean_bill_ids": ["bill_1001"],
  "open_bill_ids": ["bill_2231"],
  "other_lanes": { }
}
```

`also_fires` lists rules that also trigger but do not decide the outcome (for example, INV-2231
is above the treasurer cap as well). `open_bill_ids` lists bills still unpaid at `as_of`.
A `cash_deposit` match carries `over_short_minor`: deposit = sum of its events + over/short.
`matches[].kind` ∈ `supplier_payment, customer_receipt, pos_settlement, cash_deposit`. A
one-to-many match lists several `event_ids`. `unmatched_bank_lines` are lines that have no book
event by design (payroll, rent, utilities, loan, fees, tax) with their category. In v1 (D2):

- `scenarios` follows `rulebook/scenarios.yaml` exactly (DEMO-1, S-01..S-13, S-05b, S-08a/b/c, C-01..C-04): its IDs,
  rules and expected outcomes, plus `refs` to the real planted rows and `proposals[]`, each a contract
  `ProposalDraft` (with `approval` for S-04). Totals that integer GST cannot produce are 1 minor unit above the
  scenario figure (for example 14,950,001).
- `bill_size` reports how many supplier bills fit the treasurer's per-payment cap.
- `other_lanes`: `cash_dip` (weekly closings from the held-out run, first week below the buffer, drivers and open
  bills by week; weeks start the day after `as_of`, as in Y1), `fiscal_year_cash_flows` (direct-method CFO/CFI/CFF
  per whole FY with revenue), `dead_stock`, `slow_stock`, `nrv_events`, `pos_anomalies` (refund spike, cash
  shortage), `seasonal_peaks`, `launch_lab_history_categories`, `loan_id`, `lease_ids`.

---

## 4. Open points for sign-off

1. **Units in the Blueprint sale example.** `"price":3000,"cost":1800` reads as rupees, which breaks the integer-minor-units rule. These formats use `price_minor: 300000`. Please confirm.
2. **Cash buffer** → CHANGED by the orchestrator: it is a tenant-level policy (`tenant.json → policies.cash_buffer_minor`, plus a `tenants` column), not a Mandate field.
3. **`customer_receipt` comes from reconciliation** → APPROVED. The answer key still lists the true customer-receipt matches, so open receivables can be derived before D4 runs.
4. **Deterministic event IDs** → APPROVED.
5. **Proposal `type` values** → fiona-19 decides in A2. The orchestrator recommends `payment` (with `payload.channel` = `wallet` or `bank_file`), `bill_approval`, `journal_adjustment`, `send_document`, `purchase_order` and `reconciliation_match`.

Item 1 (minor units) → APPROVED. The orchestrator ruled on items 1 to 5 on 13 Oct; fiona-19 may object until G1.
