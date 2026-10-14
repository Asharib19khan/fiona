-- Fiona · D5/D6 · verdict IDs, owner decisions and the simulated wallet (Daniyal lane)
--
-- 1. verdicts: contract Verdict fields (id vrd_, policy_version, previous_verdict_id) and the exact
--    hashed object in `body`, so the wallet re-verifies verdict_hash byte for byte. Key (tenant_id, id).
-- 2. proposals: `created_by` (contract Actor) for maker-checker (G-04). There is deliberately no
--    status column: a proposal's status is a projection over its verdicts, decisions and wallet
--    events, and the proposal row itself stays immutable.
-- 3. decisions: owner decisions on proposals (contract Decision). Append-only.
-- 4. wallet_accounts: one simulated account per tenant. SIMULATED: no real money moves.
-- No now() defaults and no random IDs: the engine passes IDs and timestamps from its clock.

-- ---------------------------------------------------------------- verdicts
alter table public.verdicts disable trigger verdicts_append_only;

alter table public.verdicts add column id text check (id ~ '^vrd_[A-Za-z0-9_]+$');
alter table public.verdicts add column policy_version text;
alter table public.verdicts add column previous_verdict_id text
  check (previous_verdict_id is null or previous_verdict_id ~ '^vrd_[A-Za-z0-9_]+$');
alter table public.verdicts add column body jsonb check (body is null or jsonb_typeof(body) = 'object');

-- Rows written before this migration get a deterministic id derived from their key.
update public.verdicts set id = 'vrd_' || substr(md5(tenant_id || '|' || proposal_id), 1, 26) where id is null;
alter table public.verdicts alter column id set not null;

alter table public.verdicts drop constraint verdicts_pkey;
alter table public.verdicts add primary key (tenant_id, id);
create index verdicts_proposal_idx on public.verdicts (tenant_id, proposal_id);
alter table public.verdicts add foreign key (tenant_id, previous_verdict_id) references public.verdicts (tenant_id, id);

alter table public.verdicts enable trigger verdicts_append_only;

comment on column public.verdicts.body is 'The Verdict object exactly as hashed (without verdict_hash); the wallet re-verifies it';

-- ---------------------------------------------------------------- proposals
-- Adding a column rewrites no rows through UPDATE, so the append-only trigger is untouched.
alter table public.proposals add column created_by jsonb
  check (created_by is null or (jsonb_typeof(created_by) = 'object' and created_by ? 'kind' and created_by ? 'id'));
comment on column public.proposals.created_by is 'Contract Actor who originated the work; G-04 compares it with the approver';

-- ---------------------------------------------------------------- decisions (owner approvals)
create table public.decisions (
  tenant_id        text not null references public.tenants (id),
  id               text not null check (id ~ '^dec_[0-9A-Za-z_]+$'),
  proposal_id      text not null,
  verdict_id       text not null,
  decision         text not null check (decision in ('approve', 'reject')),
  note             text,
  decided_by       text not null check (decided_by ~ '^usr_[A-Za-z0-9_]+$'),
  decided_at       timestamptz not null,
  passkey_verified boolean not null default false,
  idempotency_key  text,
  primary key (tenant_id, id),
  unique (tenant_id, idempotency_key),
  foreign key (tenant_id, proposal_id) references public.proposals (tenant_id, id),
  foreign key (tenant_id, verdict_id) references public.verdicts (tenant_id, id)
);
comment on table public.decisions is 'Owner decisions (contract Decision). Only a user can decide; releases escalate, never block. Append-only';
create index decisions_proposal_idx on public.decisions (tenant_id, proposal_id);
create index decisions_verdict_idx on public.decisions (tenant_id, verdict_id);

-- ---------------------------------------------------------------- wallet accounts
create table public.wallet_accounts (
  tenant_id     text not null references public.tenants (id),
  id            text not null check (id ~ '^wal_[0-9A-Za-z_]+$'),
  iban          text not null,
  currency      text not null check (currency ~ '^[A-Z]{3}$'),
  balance_minor bigint not null check (balance_minor >= 0),
  created_at    timestamptz not null,
  updated_at    timestamptz not null,
  primary key (tenant_id, id),
  unique (tenant_id, iban)
);
comment on table public.wallet_accounts is 'SIMULATED agent-wallet account per tenant (D6). The balance can never go negative';

-- ---------------------------------------------------------------- row-level security (same shape as 20261013120200)
do $$
declare
  t text;
begin
  foreach t in array array['decisions', 'wallet_accounts'] loop
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
grant select, insert on public.decisions to fiona_engine;
grant select, insert, update on public.wallet_accounts to fiona_engine;

do $$
declare
  r text;
  t text;
begin
  foreach r in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_catalog.pg_roles where rolname = r) then
      foreach t in array array['decisions', 'wallet_accounts'] loop
        execute format('revoke all on public.%I from %I', t, r);
      end loop;
    end if;
  end loop;
end
$$;

-- ---------------------------------------------------------------- append-only
create trigger decisions_append_only before update or delete on public.decisions
  for each row execute function app.reject_mutation();
create trigger decisions_no_truncate before truncate on public.decisions
  for each statement execute function app.reject_mutation();
