# Fiona: Status Board

Maintained by fiona-b7. Updated Tue 13 Oct 2026, night. Plan: [PLAN.md](PLAN.md).

**Deadline: Tue 20 Oct, 20:59 PKT (registration and submission).** Next gate: G1, Wed 14 at 23:59.

| Lane | Session | Done | Now | Next due | Risk |
| --- | --- | --- | --- | --- |
| Asharib | fiona-19 | A1 repository and workspace (9c0aa77): web, engine, agents and guardian skeletons; 11 of 11 checks green | S2 kit, CI | A2 contracts, Wed 14 | No API key or accounts yet |
| Abdullah | fiona-fa | S1 rules (deadline found); B1 threshold register | B1 rulebook, then B2 | B1 and B2, Wed 14 | The Mandate shape gates A2 |
| Daniyal | fiona-b0 | D1 schema with forced RLS and 45 isolation tests (e6d6758); FORMATS.md | D2a real files, seed loader | D2a, Wed 14 | Shared local Postgres: start it once, never inside a test run |
| Yahya | fiona-79 | Y5 core with 119 engine tests passing (15773ee) | Y0 mocks | Y0, Wed 14 | `ruff format` pending on forecast/ |

Rule checks: clean. Status files carried the old dates; each lane has been told to update them.

## Waiting on Asharib (the user)

- **Register the team** (closes with the submission deadline)
- Anthropic API key in `Y:\Fiona\.env.local`; Supabase, Vercel and Fly.io accounts; GitHub repository plus `gh auth login`
