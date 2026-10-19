-- Fiona · A8 · per-workspace settings (written by fiona-19 on Asharib's instruction)
-- One row per workspace and setting: Launch Lab defaults, the AI connection, and so on.
-- A secret (an Anthropic API key or a Claude subscription token) is stored only as AES-GCM
-- ciphertext; the key lives in the engine's SETTINGS_ENCRYPTION_KEY, never in the database.

create table public.tenant_settings (
  tenant_id         text not null references public.tenants (id),
  key               text not null check (key ~ '^[a-z][a-z0-9_]{1,40}$'),
  value             jsonb not null default '{}'::jsonb check (jsonb_typeof(value) = 'object'),
  secret_ciphertext text,
  updated_by        text not null,
  updated_at        timestamptz not null,
  primary key (tenant_id, key)
);

alter table public.tenant_settings enable row level security;
alter table public.tenant_settings force row level security;
create policy tenant_isolation on public.tenant_settings
  using (tenant_id = (select app.current_tenant()))
  with check (tenant_id = (select app.current_tenant()));

grant select, insert, update, delete on public.tenant_settings to fiona_engine;

-- The web app never reads this table directly (Supabase's anon and authenticated roles).
do $$
declare
  r text;
begin
  foreach r in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_catalog.pg_roles where rolname = r) then
      execute format('revoke all on public.tenant_settings from %I', r);
    end if;
  end loop;
end
$$;
