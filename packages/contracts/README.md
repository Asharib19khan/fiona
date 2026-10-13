# packages/contracts

**Owners:** Asharib (fiona-19) and Daniyal (fiona-b0). Frozen at G1 (Wed 14 Oct): additive changes only after that, and message fiona-b7 first.

The only surface shared across boxes (R1). Shared objects (Proposal, Verdict, Finding, LedgerEvent, Mandate, Figure, Money) are JSON Schema 2020-12. TypeScript types, Zod schemas and the Pydantic v2 package `fiona_contracts` are generated from them and committed. Endpoint models stay Pydantic in each engine module and reach the web through OpenAPI. Built in task A2.

Python import (stable): `from fiona_contracts import Money, Figure, Finding`.
