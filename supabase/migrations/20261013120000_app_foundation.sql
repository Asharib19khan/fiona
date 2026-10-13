-- Fiona · D1 · foundation (Daniyal lane)
-- Helper schema, tenant context, the engine role and shared integrity triggers.
-- Runs unchanged on local PostgreSQL 17 and on Supabase.

create schema if not exists app;
comment on schema app is 'Fiona engine helpers: tenant context and integrity triggers';

-- Tenant context. The engine sets it once per transaction:
--   select set_config('app.tenant_id', 'ten_karachi_apparel', true);
-- When the setting is missing or empty this returns NULL. NULL matches no row, so a query
-- that forgot to set the tenant sees nothing and can write nothing (fail closed).
create or replace function app.current_tenant()
returns text
language sql
stable
set search_path = ''
as $$
  select nullif(pg_catalog.current_setting('app.tenant_id', true), '')
$$;

-- The engine runs all tenant work as this role (SET LOCAL ROLE fiona_engine).
-- It has no BYPASSRLS, so row-level security always applies to it.
do $$
begin
  if not exists (select 1 from pg_catalog.pg_roles where rolname = 'fiona_engine') then
    create role fiona_engine nologin nobypassrls;
  end if;
  if not pg_catalog.pg_has_role(current_user, 'fiona_engine', 'member') then
    execute pg_catalog.format('grant fiona_engine to %I', current_user);
  end if;
end
$$;

grant usage on schema app to fiona_engine;
grant execute on function app.current_tenant() to fiona_engine;

-- Append-only guard for events, bank_lines, proposals, verdicts and audit_log.
-- A correction is a new row, never an edit.
create or replace function app.reject_mutation()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception 'fiona: % on %.% is not allowed; the table is append-only, record a correction instead',
    tg_op, tg_table_schema, tg_table_name
    using errcode = 'restrict_violation';
end
$$;
