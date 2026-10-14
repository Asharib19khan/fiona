ID: CX-Y8
Task: Payment-timing optimiser
Status: Done
Due: 2026-10-14
Updated: 2026-10-14
Note: Implemented services/engine/decisions/payment_timing.py and tests. Verification: uv run pytest decisions/tests/test_payment_timing.py -q -> 8 passed in 0.61s; uv run pytest decisions -q -> 22 passed in 0.67s; uv run ruff check decisions -> All checks passed; uv run ruff format decisions/payment_timing.py decisions/tests/test_payment_timing.py -> clean after formatting. Earlier full-suite verification before unrelated wallet files appeared: uv run pytest -q --basetemp <temp> -> 236 passed, 1 warning in 12.46s. Current full-suite rerun: uv run pytest -q --basetemp <temp> stops during collection in untracked wallet/tests/test_audit.py with TypeError: text() got an unexpected keyword argument 'characters'. Questions: none. Note: a first full pytest run reached 100% but exited during Windows temp cleanup with PermissionError on pytest-current, so full runs used an isolated temp base.
