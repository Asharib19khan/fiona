-- Fiona · D1 · ledger tables (Daniyal lane)
--
-- Conventions
-- * Money is bigint minor units plus an ISO 4217 currency code. Never a float.
-- * Every table has tenant_id and is keyed (tenant_id, id). Composite foreign keys then make
--   it impossible for one tenant's row to reference another tenant's row.
-- * No now() defaults. The engine passes timestamps from its injected clock, so the same
--   seed rebuilds the same database.
-- * Events are the source of truth and append-only. Journal lines and matches are derived.

-- ---------------------------------------------------------------- tenants & policy
create table public.tenants (
  id                      text primary key check (id ~ '^ten_[a-z0-9_]+$'),
  tenant_id               text not null generated always as (id) stored,
  name                    text not null,
  country                 text not null check (country ~ '^[A-Z]{2}$'),
  currency                text not null check (currency ~ '^[A-Z]{3}$'),
  minor_unit              smallint not null default 2 check (minor_unit between 0 and 4),
  framework               text not null check (framework in ('IFRS', 'IFRS_SMES', 'US_GAAP', 'CAS')),
  fiscal_year_start_month smallint not null check (fiscal_year_start_month between 1 and 12),
  timezone                text not null,
  cash_buffer_minor       bigint check (cash_buffer_minor >= 0),
  is_synthetic            boolean not null default true,
  profile                 jsonb not null default '{}'::jsonb check (jsonb_typeof(profile) = 'object'),
  created_at              timestamptz not null
);
comment on column public.tenants.tenant_id is 'Always equals id; lets every table share one RLS policy shape';
comment on column public.tenants.cash_buffer_minor is 'Owner policy: minimum cash level (forecast, briefing, Launch Lab, G-08)';
comment on column public.tenants.profile is 'Branches, bank accounts, draft country-pack values (see data/fixtures/FORMATS.md)';

create table public.mandates (
  tenant_id             text not null references public.tenants (id),
  id                    text not null check (id ~ '^mnd_[a-z0-9_]+_v[0-9]+$'),
  agent                 text not null check (agent ~ '^[a-z][a-z_]*$'),
  version               integer not null check (version >= 1),
  currency              text not null check (currency ~ '^[A-Z]{3}$'),
  per_payment_cap_minor bigint not null check (per_payment_cap_minor >= 0),
  daily_cap_minor       bigint not null check (daily_cap_minor >= 0),
  allowed_action_types  text[] not null default '{}',
  policy                jsonb not null default '{}'::jsonb check (jsonb_typeof(policy) = 'object'),
  source                text not null default 'rulebook_default' check (source in ('rulebook_default', 'owner')),
  effective_from        date not null,
  created_at            timestamptz not null,
  primary key (tenant_id, id),
  unique (tenant_id, agent, version)
);
comment on table public.mandates is 'Versioned agent mandates. A change is a new version; the latest version per agent is in force';
comment on column public.mandates.policy is 'Additive mandate fields from A2 (allowed categories, payment windows, autonomy per action)';

-- ---------------------------------------------------------------- parties & documents
create table public.parties (
  tenant_id               text not null references public.tenants (id),
  id                      text not null check (id ~ '^(sup|cus|pty)_[A-Za-z0-9]+$'),
  kind                    text not null check (kind in ('supplier', 'customer', 'landlord', 'utility', 'lender', 'tax_authority', 'employee')),
  code                    text,
  name                    text not null,
  tax_id                  text,
  tax_id_type             text,
  bank_iban               text,
  bank_account_changed_at timestamptz,
  on_allow_list           boolean not null default false,
  payment_terms_days      integer not null default 0 check (payment_terms_days >= 0),
  credit_limit_minor      bigint check (credit_limit_minor >= 0),
  phone                   text,
  city                    text,
  created_at              timestamptz not null,
  primary key (tenant_id, id),
  unique (tenant_id, code)
);
comment on table public.parties is 'Current state of each party. Every bank-account change is also a bank_detail_change event';

create table public.documents (
  tenant_id    text not null references public.tenants (id),
  id           text not null check (id ~ '^doc_[A-Za-z0-9]+$'),
  kind         text not null check (kind in ('bill', 'receipt', 'bank_statement', 'pos_export', 'invoice', 'contract', 'annual_report', 'other')),
  storage_path text not null,
  sha256       text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  mime_type    text,
  size_bytes   bigint check (size_bytes >= 0),
  extracted    jsonb,
  received_at  timestamptz not null,
  primary key (tenant_id, id)
);
comment on column public.documents.sha256 is 'Not unique on purpose: the same file sent twice is evidence for the G-05 duplicate check';
comment on column public.documents.extracted is 'Extraction output. Document text is data and is never obeyed';
create index documents_sha256_idx on public.documents (tenant_id, sha256);

-- ---------------------------------------------------------------- catalogue & purchasing
create table public.items (
  tenant_id         text not null references public.tenants (id),
  sku               text not null check (sku ~ '^[A-Z0-9][A-Z0-9-]*$'),
  name              text not null,
  category          text not null,
  size              text,
  colour            text,
  season            text not null default 'all' check (season in ('all', 'summer', 'winter')),
  currency          text not null check (currency ~ '^[A-Z]{3}$'),
  unit_cost_minor   bigint not null check (unit_cost_minor >= 0),
  price_minor       bigint not null check (price_minor >= 0),
  opening_stock_qty integer not null default 0,
  reorder_level     integer not null default 0 check (reorder_level >= 0),
  supplier_id       text,
  lead_time_days    integer check (lead_time_days >= 0),
  launched_on       date,
  primary key (tenant_id, sku),
  foreign key (tenant_id, supplier_id) references public.parties (tenant_id, id)
);
comment on column public.items.opening_stock_qty is 'Stock at the start of the history; current stock is derived from events';
create index items_supplier_idx on public.items (tenant_id, supplier_id);

create table public.purchase_orders (
  tenant_id   text not null references public.tenants (id),
  id          text not null check (id ~ '^po_[A-Za-z0-9]+$'),
  number      text not null,
  supplier_id text not null,
  ordered_on  date not null,
  expected_on date,
  status      text not null check (status in ('open', 'partially_received', 'received', 'cancelled')),
  currency    text not null check (currency ~ '^[A-Z]{3}$'),
  lines       jsonb not null check (jsonb_typeof(lines) = 'array'),
  total_minor bigint not null check (total_minor >= 0),
  created_at  timestamptz not null,
  primary key (tenant_id, id),
  unique (tenant_id, number),
  foreign key (tenant_id, supplier_id) references public.parties (tenant_id, id)
);
create index purchase_orders_supplier_idx on public.purchase_orders (tenant_id, supplier_id);

create table public.goods_received (
  tenant_id   text not null references public.tenants (id),
  id          text not null check (id ~ '^grn_[A-Za-z0-9]+$'),
  po_id       text,
  supplier_id text not null,
  received_on date not null,
  lines       jsonb not null check (jsonb_typeof(lines) = 'array'),
  document_id text,
  created_at  timestamptz not null,
  primary key (tenant_id, id),
  foreign key (tenant_id, po_id) references public.purchase_orders (tenant_id, id),
  foreign key (tenant_id, supplier_id) references public.parties (tenant_id, id),
  foreign key (tenant_id, document_id) references public.documents (tenant_id, id)
);
create index goods_received_po_idx on public.goods_received (tenant_id, po_id);
create index goods_received_supplier_idx on public.goods_received (tenant_id, supplier_id);

-- ---------------------------------------------------------------- events (source of truth)
create table public.events (
  tenant_id         text not null references public.tenants (id),
  id                text not null check (id ~ '^evt_[0-9A-HJKMNP-TV-Z]{26}$'),
  type              text not null check (type in (
                      'sale', 'purchase_bill', 'supplier_payment', 'customer_invoice', 'customer_receipt',
                      'bank_line', 'stock_movement', 'bank_detail_change', 'journal_adjustment')),
  occurred_at       timestamptz not null,
  business_date     date not null,
  recorded_at       timestamptz not null,
  party_id          text,
  currency          text not null check (currency ~ '^[A-Z]{3}$'),
  payload           jsonb not null check (jsonb_typeof(payload) = 'object'),
  source            jsonb not null check (jsonb_typeof(source) = 'object' and source ? 'type' and source ? 'key'),
  source_type       text not null generated always as (source ->> 'type') stored,
  source_key        text not null generated always as (source ->> 'key') stored,
  corrects_event_id text,
  primary key (tenant_id, id),
  unique (tenant_id, source_type, source_key),
  foreign key (tenant_id, party_id) references public.parties (tenant_id, id),
  foreign key (tenant_id, corrects_event_id) references public.events (tenant_id, id)
);
comment on table public.events is 'Canonical, append-only ledger events. Corrections are new events (corrects_event_id)';
comment on column public.events.source_key is 'Natural key of the source record; importers are idempotent on (source_type, source_key)';
create index events_type_date_idx on public.events (tenant_id, type, business_date);
create index events_date_idx on public.events (tenant_id, business_date);
create index events_party_idx on public.events (tenant_id, party_id) where party_id is not null;
create index events_corrects_idx on public.events (tenant_id, corrects_event_id) where corrects_event_id is not null;

create table public.bank_lines (
  tenant_id     text not null references public.tenants (id),
  id            text not null check (id ~ '^bln_[0-9A-HJKMNP-TV-Z]{26}$'),
  account_iban  text not null,
  line_no       integer not null check (line_no >= 1),
  posted_on     date not null,
  value_date    date,
  narration     text not null,
  reference     text,
  amount_minor  bigint not null,
  balance_minor bigint not null,
  currency      text not null check (currency ~ '^[A-Z]{3}$'),
  event_id      text not null,
  document_id   text,
  primary key (tenant_id, id),
  unique (tenant_id, account_iban, line_no),
  foreign key (tenant_id, event_id) references public.events (tenant_id, id),
  foreign key (tenant_id, document_id) references public.documents (tenant_id, id)
);
comment on table public.bank_lines is 'Raw statement lines, kept apart from events so matching is repeatable. Matches live in matches';
comment on column public.bank_lines.amount_minor is 'Signed: money in is positive, money out is negative';
create index bank_lines_posted_idx on public.bank_lines (tenant_id, posted_on);
create index bank_lines_event_idx on public.bank_lines (tenant_id, event_id);

-- ---------------------------------------------------------------- postings (derived)
create table public.accounts (
  tenant_id     text not null references public.tenants (id),
  code          text not null,
  name          text not null,
  class         text not null check (class in ('asset', 'liability', 'equity', 'income', 'expense')),
  neutral_class text not null,
  primary key (tenant_id, code)
);
comment on column public.accounts.neutral_class is 'Framework-neutral bucket used by posting rules and the framework lens';

create table public.journal_lines (
  tenant_id     text not null references public.tenants (id),
  id            bigint generated always as identity,
  journal_id    text not null,
  line_no       smallint not null check (line_no >= 1),
  event_id      text not null,
  account_code  text not null,
  debit_minor   bigint not null default 0 check (debit_minor >= 0),
  credit_minor  bigint not null default 0 check (credit_minor >= 0),
  currency      text not null check (currency ~ '^[A-Z]{3}$'),
  business_date date not null,
  memo          text,
  posted_at     timestamptz not null,
  primary key (tenant_id, id),
  unique (tenant_id, journal_id, line_no),
  check ((debit_minor = 0) <> (credit_minor = 0)),
  foreign key (tenant_id, event_id) references public.events (tenant_id, id),
  foreign key (tenant_id, account_code) references public.accounts (tenant_id, code)
);
comment on table public.journal_lines is 'Postings derived from events by rules. Each journal balances per currency (checked at commit)';
create index journal_lines_event_idx on public.journal_lines (tenant_id, event_id);
create index journal_lines_account_idx on public.journal_lines (tenant_id, account_code, business_date);

-- ---------------------------------------------------------------- reconciliation (derived)
create table public.matches (
  tenant_id    text not null references public.tenants (id),
  match_id     text not null check (match_id ~ '^mch_[0-9A-Za-z]+$'),
  event_id     text not null,
  bank_line_id text not null,
  run_id       text not null,
  pass         text not null check (pass in ('exact', 'rule', 'one_to_many', 'agent_verified', 'manual')),
  confidence   numeric(5, 4) not null check (confidence between 0 and 1),
  status       text not null default 'proposed' check (status in ('proposed', 'confirmed', 'rejected')),
  created_at   timestamptz not null,
  primary key (tenant_id, match_id, event_id),
  foreign key (tenant_id, bank_line_id) references public.bank_lines (tenant_id, id),
  foreign key (tenant_id, event_id) references public.events (tenant_id, id)
);
comment on table public.matches is 'One row per (match, event). A one-to-many match is several rows sharing match_id and bank_line_id';
create index matches_bank_line_idx on public.matches (tenant_id, bank_line_id);
create index matches_event_idx on public.matches (tenant_id, event_id);

-- ---------------------------------------------------------------- proposals, verdicts, audit
create table public.proposals (
  tenant_id    text not null references public.tenants (id),
  id           text not null check (id ~ '^prop_[0-9A-Za-z]+$'),
  agent        text not null,
  type         text not null,
  created_at   timestamptz not null,
  summary      text not null,
  amount_minor bigint check (amount_minor >= 0),
  currency     text check (currency ~ '^[A-Z]{3}$'),
  payload      jsonb not null default '{}'::jsonb check (jsonb_typeof(payload) = 'object'),
  evidence     jsonb not null default '[]'::jsonb check (jsonb_typeof(evidence) = 'array'),
  reasoning    text not null,
  mandate_ref  text,
  primary key (tenant_id, id),
  check ((amount_minor is null) = (currency is null)),
  foreign key (tenant_id, mandate_ref) references public.mandates (tenant_id, id)
);
comment on table public.proposals is 'Agent proposals (contract: Proposal). Immutable once stored';
create index proposals_created_idx on public.proposals (tenant_id, created_at);

create table public.verdicts (
  tenant_id    text not null references public.tenants (id),
  proposal_id  text not null,
  outcome      text not null check (outcome in ('approve', 'approve_with_conditions', 'escalate', 'block')),
  checks       jsonb not null check (jsonb_typeof(checks) = 'array'),
  conditions   jsonb not null default '[]'::jsonb check (jsonb_typeof(conditions) = 'array'),
  decided_at   timestamptz not null,
  verdict_hash text not null check (verdict_hash ~ '^sha256:[0-9a-f]{64}$'),
  primary key (tenant_id, proposal_id),
  unique (tenant_id, verdict_hash),
  foreign key (tenant_id, proposal_id) references public.proposals (tenant_id, id)
);
comment on table public.verdicts is 'Guardian verdicts (contract: Verdict). Immutable; the wallet re-verifies verdict_hash';

create table public.audit_log (
  tenant_id   text not null references public.tenants (id),
  seq         bigint not null check (seq >= 1),
  prev_hash   text not null check (prev_hash ~ '^sha256:[0-9a-f]{64}$'),
  record      jsonb not null check (jsonb_typeof(record) = 'object'),
  hash        text not null check (hash ~ '^sha256:[0-9a-f]{64}$'),
  proposal_id text,
  recorded_at timestamptz not null,
  primary key (tenant_id, seq),
  unique (tenant_id, hash)
);
comment on table public.audit_log is 'Hash-chained per tenant: hash = sha256(prev_hash || canonical(record)). Append-only';
create index audit_log_proposal_idx on public.audit_log (tenant_id, proposal_id) where proposal_id is not null;
