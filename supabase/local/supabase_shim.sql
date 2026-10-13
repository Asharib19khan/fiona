-- LOCAL ONLY. This file is not a migration and never runs on Supabase cloud.
--
-- It recreates the small part of Supabase's platform schema that migrations and engine code
-- may reference, so the same files in supabase/migrations run on plain PostgreSQL 17 and on
-- Supabase. `python -m engine.ledger.db` applies it before the migrations on local databases only.
-- Everything is idempotent.

do $$
begin
  if not exists (select 1 from pg_catalog.pg_roles where rolname = 'anon') then
    create role anon nologin noinherit;
  end if;
  if not exists (select 1 from pg_catalog.pg_roles where rolname = 'authenticated') then
    create role authenticated nologin noinherit;
  end if;
  if not exists (select 1 from pg_catalog.pg_roles where rolname = 'service_role') then
    create role service_role nologin noinherit bypassrls;
  end if;
end
$$;

create schema if not exists extensions;
create schema if not exists auth;

create table if not exists auth.users (
  id                 uuid primary key,
  email              text unique,
  raw_app_meta_data  jsonb not null default '{}'::jsonb,
  raw_user_meta_data jsonb not null default '{}'::jsonb,
  created_at         timestamptz not null default now()
);

-- Same behaviour as Supabase: claims come from the request.jwt.claims setting that PostgREST sets.
create or replace function auth.jwt()
returns jsonb
language sql
stable
as $$
  select coalesce(nullif(current_setting('request.jwt.claims', true), ''), '{}')::jsonb
$$;

create or replace function auth.uid()
returns uuid
language sql
stable
as $$
  select nullif(auth.jwt() ->> 'sub', '')::uuid
$$;

create or replace function auth.role()
returns text
language sql
stable
as $$
  select nullif(auth.jwt() ->> 'role', '')
$$;

grant usage on schema auth, extensions to anon, authenticated, service_role;
