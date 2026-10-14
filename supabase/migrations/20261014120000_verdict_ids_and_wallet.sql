-- Fiona · D6 · verdict IDs and wallet migration (AntiGravity lane)
-- Additive migration:
-- 1. Updates verdicts table to support Verdict contract (id, policy_version, previous_verdict_id),
--    changes primary key to (tenant_id, id), and indexes proposal_id for re-runs.
-- 2. Adds optional status column to proposals table.
-- 3. Adds wallet_accounts and approvals tables with RLS and append-only triggers.

-- ---------------------------------------------------------------- verdicts schema update
alter table public.verdicts disable trigger verdicts_append_only;

alter table public.verdicts
  add column if not exists id text not null default ('vrd_' || substr(md5(random()::text || clock_timestamp()::text), 1, 26))
  check (id ~ '^vrd_[A-Za-z0-9_]+$');

alter table public.verdicts
  add column if not exists policy_version text;

alter table public.verdicts
  add column if not exists previous_verdict_id text
  check (previous_verdict_id is null or previous_verdict_id ~ '^vrd_[A-Za-z0-9_]+$');

alter table public.verdicts drop constraint if exists verdicts_pkey;
alter table public.verdicts add primary key (tenant_id, id);
create index if not exists verdicts_proposal_idx on public.verdicts (tenant_id, proposal_id);

alter table public.verdicts enable trigger verdicts_append_only;

-- ---------------------------------------------------------------- proposals status column
alter table public.proposals disable trigger proposals_append_only;

alter table public.proposals
  add column if not exists status text default 'submitted'
  check (status in ('submitted', 'under_review', 'cleared', 'needs_owner', 'blocked', 'approved', 'rejected', 'executed', 'expired', 'failed', 'superseded'));

alter table public.proposals enable trigger proposals_append_only;

-- ---------------------------------------------------------------- wallet tables
create table if not exists public.wallet_accounts (
  tenant_id     text not null references public.tenants (id),
  id            text not null check (id ~ '^wal_[0-9A-Za-z_]+$'),
  iban          text not null,
  currency      text not null check (currency ~ '^[A-Z]{3}$'),
  balance_minor bigint not null check (balance_minor >= 0),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  primary key (tenant_id, id),
  unique (tenant_id, iban)
);
comment on table public.wallet_accounts is 'Simulated autonomous wallet accounts per tenant (D6). Balance cannot go negative.';

create table if not exists public.approvals (
  tenant_id   text not null references public.tenants (id),
  id          text not null check (id ~ '^app_[0-9A-Za-z_]+$'),
  proposal_id text not null,
  user_id     text not null,
  decision    text not null check (decision in ('approved', 'rejected')),
  notes       text,
  created_at  timestamptz not null default now(),
  primary key (tenant_id, id),
  foreign key (tenant_id, proposal_id) references public.proposals (tenant_id, id)
);

comment on table public.approvals is 'Owner and authorized user approvals releasing escalated proposals (maker-checker). Append-only.';
create index if not exists approvals_proposal_idx on public.approvals (tenant_id, proposal_id);

-- ---------------------------------------------------------------- row-level security
do $$
declare
  t text;
begin
  foreach t in array array['wallet_accounts', 'approvals'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('alter table public.%I force row level security', t);
    execute format(
      'create policy tenant_isolation on public.%I
         using (tenant_id = (select app.current_tenant()))
         with check (tenant_id = (select app.current_tenant()))', t);
  end loop;
end
$$;

-- ---------------------------------------------------------------- grants
grant select, insert, update on public.wallet_accounts to fiona_engine;
grant select, insert on public.approvals to fiona_engine;

do $$
declare
  r text;
  t text;
begin
  foreach r in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_catalog.pg_roles where rolname = r) then
      foreach t in array array['wallet_accounts', 'approvals'] loop
        execute format('revoke all on public.%I from %I', t, r);
      end loop;
    end if;
  end loop;
end
$$;

-- ---------------------------------------------------------------- append-only triggers
create trigger approvals_append_only before update or delete on public.approvals
  for each row execute function app.reject_mutation();
create trigger approvals_no_truncate before truncate on public.approvals
  for each statement execute function app.reject_mutation();
