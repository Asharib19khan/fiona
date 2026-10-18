-- Reconciliation pass 3 (D4) proposes fuzzy matches: description, party and reference scored,
-- with the amount still verified exactly. The pass check predates it, so every full run that
-- found a fuzzy candidate failed to store any match. Fuzzy matches stay 'proposed' until a
-- person confirms them, like every other pass.
alter table public.matches drop constraint matches_pass_check;
alter table public.matches add constraint matches_pass_check
  check (pass in ('exact', 'rule', 'one_to_many', 'fuzzy', 'agent_verified', 'manual'));
