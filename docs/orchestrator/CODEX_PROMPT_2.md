# Prompt 2 for Codex: the inventory analytics engine (task Y3)

Paste everything below the line into Codex, in a new conversation.

---

You are the CODEX lane for Fiona, an AI finance copilot for small businesses. The repository is `Y:\Fiona` (Python 3.12, uv). Your last task (`CX-Y8`, the payment-timing optimiser) passed review. Other agents share this folder, so stay strictly inside the files listed below.

## The task
Replace the hand-built **inventory analysis mock** with the real engine. It reads the shop's sales and stock, and tells the owner:
- which items are fast, slow or dead
- how much cash each one ties up
- when and how much to reorder (as draft purchase orders)

## Rule zero: do not invent anything
- The output shape already exists. Use exactly the fields in `services/engine/forecast/inventory/schemas.py`, and add none.
- **Every parameter value** (ABC cut-offs, the XYZ coefficient-of-variation bands, the days that mean slow or dead, the service level or safety-stock factor, the cover target, the analysis window) **must be copied from the `parameters` list in `services/engine/forecast/mocks/inventory.py`**, keeping each one's origin label. Don't choose your own numbers. If the mock lacks one you need, choose the conservative standard value, give it origin "assumption", and list it in `docs/status/codex.md`.
- Money is always an integer in minor units (PKR 1 = 100 minor), never a float in any output. There are no AI calls.
- Don't claim tests pass unless you ran them.

## Read first
1. `CLAUDE.md`, the repository rules.
2. `services/engine/forecast/inventory/schemas.py`: the output types `InventoryAnalysisResponse`, `InventoryItem`, `StyleRollup`, `BundleCandidate`, `DraftPurchaseOrder`.
3. `services/engine/forecast/mocks/inventory.py`: the mock you're replacing. It shows how every field is filled and which Figure, Threshold and Finding helpers to use (`engine.forecast.figures`). **Mirror it, but compute the values from data.**
4. `services/engine/forecast/api.py`: the function `_cash` (the live-with-fixture-fallback pattern) and the stub `inventory_analysis`.
5. `services/engine/forecast/ledger_source.py`: how fixtures are loaded (`load_fixture_snapshot`, `TenantDataMissing`, `FIXTURES_ROOT`).
6. `data/fixtures/FORMATS.md`, sections 3.5 (`items.csv`), 3.6 (purchase orders), 3.11 (`pos_sales.csv`) and 3.13 (`sale` and `stock_movement` events in `events.jsonl`). The tenant is `ten_karachi_apparel`.
7. `services/engine/decisions/payment_timing.py`, your own earlier work, for style.

## Files you may create or change (nothing else)
- Create: `services/engine/forecast/inventory/engine.py`, `services/engine/forecast/inventory/loader.py`, `services/engine/forecast/inventory/tests/__init__.py` and `services/engine/forecast/inventory/tests/test_inventory.py`.
- Change **only the body of `inventory_analysis()`** in `services/engine/forecast/api.py`. Follow the `_cash` pattern: run the real engine on the tenant's fixtures, and fall back to `load("inventory_analysis")` only when `TenantDataMissing` is raised.
- `docs/status/codex.md`: add a new row for CX-Y3.

## Specification
- **`loader.py`** reads, for one tenant, `items.csv`, the `sale` events (each line has item, qty, price_minor, total_minor and cost_minor; refunds have negative qty), the `stock_movement` events, and `purchase_orders.json`, `goods_received.json` and `tenant.json` (`as_of`, currency). On-hand stock is `opening_stock_qty + stock_movement qty − units sold + units refunded`, up to `as_of`. **Never negative:** if it would be, clamp it to 0 and record an `InsufficientData` note.
- **`engine.py`**: `analyse_inventory(data, *, as_of, generated_at, mode) -> InventoryAnalysisResponse`. Per SKU it computes:
  - units sold, revenue and gross margin over the window
  - ABC class by the SKU's share of window gross margin or revenue (use whatever basis the mock's parameter says)
  - XYZ class from the coefficient of variation of weekly demand, or `None` if there are fewer weeks than the mock's minimum
  - movement:
    - `new` if launched within the window
    - `dead` if no sale for N days
    - `slow` / `normal` / `fast` by days of cover against the bands
  - days of cover = on hand ÷ average daily demand (`None` if demand is 0)
  - safety stock and reorder point = demand over the lead time plus safety stock
  - suggested order quantity, if on hand is at or below the reorder point
  - turnover and GMROI in bp
  - cash tied up: all of the stock value for dead stock; otherwise the value above the cover target

  It also builds:
  - `styles`: a roll-up of size and colour variants by parent style
  - `draft_purchase_orders`: one per supplier, from the SKUs needing reorder, with order-by = as_of and expected = as_of + lead time
  - `summary` Figures
  - `findings`: the slow and dead stock with total cash tied up, ranked by money at stake, using the mock's finding style
- **`bundles`:** compute pairs bought in the same receipt (receipt number in the sale events), with `baskets_together` and lift, only if it's simple. Otherwise return `[]` plus an `InsufficientData` note. Correctness of the rest matters more.
- **Determinism:** the same data gives the same output. The `run_id` is derived from a hash of the inputs, not from randomness.

## Tests (`test_inventory.py`)
- **Small hand-made fixtures inside the test**, with numbers you can check by hand:
  - a SKU with steady sales: fast, X class, correct reorder point
  - a SKU unsold for longer than the dead threshold: dead, with cash tied up equal to the full stock value
  - a SKU with zero demand: days of cover `None`, no division error
  - refunds reduce units sold
  - ABC classes sum to 100% of the basis
  - draft purchase orders group by supplier, and their totals equal the sum of their lines
- **On the real seed-42 fixtures** (`ten_karachi_apparel`):
  - the engine runs without error
  - every money value is an `int`
  - on-hand stock is never negative
  - the output validates as `InventoryAnalysisResponse`
- **API:** `GET /v1/inventory/analysis` with header `X-Fiona-Tenant: ten_karachi_apparel` returns 200 from the real engine (not the mock: check `run_id` or the method). An unknown tenant behaves as `_cash` does. Look at `forecast/tests/test_api.py` for how the API is tested.
- **Hypothesis:** for random sales histories, units sold equal the sum of sale quantities minus refunds, and cash tied up is never greater than the stock value.

## How to run (from `Y:\Fiona\services\engine`)
- `uv run pytest forecast -q`, then `uv run pytest -q`; the whole suite must stay green.
  - If an unrelated test elsewhere fails, say so in your status note and don't fix it.
  - Your earlier `--basetemp` workaround is fine.
- `uv run ruff check forecast` and `uv run ruff format <your files>`

## Git (a shared folder; be careful)
- Never run checkout, switch, stash, reset, clean, rebase, `git add -A`, `git add .` or `commit -a`, and never push.
- When your tests pass, `git add` exactly your files (the inventory folder files, `services/engine/forecast/api.py` and `docs/status/codex.md`), then:
  `git commit -m "CX-Y3: inventory analytics engine (ABC-XYZ, movement, reorder points, draft POs) with tests" -- <the same paths>`
  If you see `index.lock`, wait and retry.

## Finish
Add a CX-Y3 row to `docs/status/codex.md` with the real pytest summary line, every parameter you had to label "assumption", any questions, and the top 3 findings the engine produced on the seed-42 data (SKU, movement, cash tied up). Then stop.
