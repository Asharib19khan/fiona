-- Fiona · D1 · ledger security (Daniyal lane)
-- Row-level security on every ledger table, least-privilege grants for the engine role,
-- append-only triggers, and the balanced-journal check.

-- ---------------------------------------------------------------- row-level security
-- FORCE makes RLS apply to the table owner too. Only superusers and BYPASSRLS roles
-- (for example Supabase's service_role) skip it, and the engine uses neither.
do $$
declare
  t text;
begin
  foreach t in array array[
    'tenants', 'mandates', 'parties', 'documents', 'items', 'purchase_orders', 'goods_received',
    'events', 'bank_lines', 'accounts', 'journal_lines', 'matches', 'proposals', 'verdicts', 'audit_log'
  ] loop
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
grant usage on schema public to fiona_engine;

-- Mutable reference data.
grant select, insert, update on public.tenants, public.parties, public.documents, public.items,
  public.purchase_orders, public.accounts to fiona_engine;
-- Versioned or append-only: insert and read, never update or delete.
grant select, insert on public.mandates, public.goods_received, public.events, public.bank_lines,
  public.journal_lines, public.proposals, public.verdicts, public.audit_log to fiona_engine;
-- Reconciliation can re-run: unconfirmed matches are replaced and statuses change.
grant select, insert, update, delete on public.matches to fiona_engine;

-- On Supabase the anon and authenticated roles get table grants by default. The web app reaches
-- the ledger only through the engine API, so those roles get nothing here.
do $$
declare
  r text;
  t text;
begin
  foreach r in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_catalog.pg_roles where rolname = r) then
      foreach t in array array[
        'tenants', 'mandates', 'parties', 'documents', 'items', 'purchase_orders', 'goods_received',
        'events', 'bank_lines', 'accounts', 'journal_lines', 'matches', 'proposals', 'verdicts', 'audit_log'
      ] loop
        execute format('revoke all on public.%I from %I', t, r);
      end loop;
    end if;
  end loop;
end
$$;

-- ---------------------------------------------------------------- append-only tables
-- The grants already stop the engine from editing these tables. The triggers also stop the
-- owner and migrations, so an edit can only happen by deliberately disabling a trigger.
do $$
declare
  t text;
begin
  foreach t in array array['events', 'bank_lines', 'proposals', 'verdicts', 'audit_log'] loop
    execute format(
      'create trigger %I before update or delete on public.%I
         for each row execute function app.reject_mutation()', t || '_append_only', t);
    execute format(
      'create trigger %I before truncate on public.%I
         for each statement execute function app.reject_mutation()', t || '_no_truncate', t);
  end loop;
end
$$;

-- ---------------------------------------------------------------- balanced journals
-- Checked at commit (deferred), so a journal's lines can be inserted one by one.
create or replace function app.assert_journal_balanced()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  debits  bigint;
  credits bigint;
begin
  select coalesce(sum(debit_minor), 0), coalesce(sum(credit_minor), 0)
    into debits, credits
    from public.journal_lines
   where tenant_id = new.tenant_id
     and journal_id = new.journal_id
     and currency = new.currency;
  if debits <> credits then
    raise exception 'fiona: journal % (%) is unbalanced: debits % <> credits %',
      new.journal_id, new.currency, debits, credits
      using errcode = 'check_violation';
  end if;
  return null;
end
$$;

create constraint trigger journal_lines_balanced
  after insert on public.journal_lines
  deferrable initially deferred
  for each row execute function app.assert_journal_balanced();
-- The unique index on (tenant_id, journal_id, line_no) serves this lookup.
