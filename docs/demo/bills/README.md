# Demo bills (synthetic)

Two bills for showing the full flow in the browser (Bills → Add a bill). Both are fictional,
from the demo supplier Lyari Stitching House (sup_002), and are not in the generated ledger,
so they are new bills rather than duplicates.

| File | What it shows |
|---|---|
| `lyari-stitching-LSH-2310-clean.txt` | An ordinary bill paid to the account on file: read, recorded, proposed by the Treasurer, checked by the Guardian, approved by the owner, paid by the sandbox wallet, posted, audited. |
| `lyari-stitching-LSH-2311-injection.txt` | A bill that demands payment to a new bank account, urges secrecy and carries instructions addressed to an AI. The reader reports the instructions instead of following them, the intake flags the bank-account mismatch, and the Guardian's independent review escalates it. |

Uploading either a second time is (rightly) caught by the Guardian's duplicate check (G-05).
