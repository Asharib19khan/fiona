# Fiona — 5-Minute Demonstration Video Script

**Competition:** FinTechathon 2026 International Track (Tsinghua PBCSF & WeBank)  
**Topic:** E — SME Finance Copilot  
**Deliverable:** 03 — Demonstration Video Script  
**Target Duration:** 4 Minutes 45 Seconds (285 seconds; strictly under the 5-minute / 300-second hard limit)  
**Target Architecture Base:** Commit `b57503b` (Wed 14 Oct 2026)  
**Persona & Dataset:** Karachi Apparel Retail SME (`ten_karachi_apparel`, synthetic seed-42, currency PKR)  
**Classification:** Public Evaluation Document  

---

## 1. Video Overview & Timing Summary Table

| Scene # | Scene Title | Key Moment / Action | Duration | Cumulative Time | Claim Proved |
|:---:|---|---|:---:|:---:|---|
| **01** | **Introduction & The Stage Reveal** | Onboarding; Dickinson 2011 Lifecycle Stage Detection | 45 s | 0:00 – 0:45 | Operating cash flows disprove founder bias (Shake-Out vs. Growth). |
| **02** | **The Executive Morning Briefing** | Action-oriented briefing cards replacing balance sheets | 35 s | 0:45 – 1:20 | Real-time working capital intelligence without accounting clutter. |
| **03** | **The Guardian in Action (DEMO-1)** | Fraudulent duplicate bill with altered bank coordinates | 55 s | 1:20 – 2:15 | G-03, G-05, G-12, G-01 fire; strictest outcome blocks payout cold. |
| **04** | **Financing Matching & Council Debate** | SBP concessionary matching + Council Mode with dissent | 55 s | 2:15 – 3:10 | 20 regional instruments; DSCR 1.45×; majority memo + dissent. |
| **05** | **13-Week Cash Alert & Payment Timing** | Week-7 buffer breach warning + Compounded 44.6% APR | 45 s | 3:10 – 3:55 | Forward-looking direct cash forecast; G-08 conditional execution date. |
| **06** | **Approval, Sandbox Wallet & Audit Chain** | Human approval above mandate, sandbox payout & audit log | 35 s | 3:55 – 4:30 | Autonomy ladder; zero unverified execution; SHA-256 audit chaining. |
| **07** | **Conclusion & Architectural Sign-Off** | Architecture recap and compliance sign-off | 15 s | 4:30 – 4:45 | Deterministic safety: The model decides, the engine computes, the Guardian checks. |
| **Total** | | | **285 s** | **4 min 45 s** | **Fully compliant with official ≤ 5-minute rule.** |

---

## 2. Shot-by-Shot Production Script

---

### Scene 01: Introduction & The Stage Reveal
- **Duration:** 45 seconds (Timecode: `0:00 – 0:45`)
- **Screen Route:** Browser at `http://localhost:3000/` $\longrightarrow$ Click **Analysis** in the left navigation rail (`http://localhost:3000/analysis`)
- **Visuals:**
  - Fast-cut open on the Fiona web shell showing active tenant: *Karachi Apparel Retailers* (`ten_karachi_apparel`).
  - Screen displays the **Lifecycle Stage Card**: The owner selected "Growth" during setup, but the screen renders a clear amber badge: **Stage: Shake-Out (Confidence: High)**.
  - Mouse clicks the card, opening the **Explain-Any-Number Drawer** displaying the Dickinson (2011) cash-flow sign pattern matrix:
    - Operating Cash Flow (CFO): **Negative** ($-$ PKR 4.2M)
    - Investing Cash Flow (CFI): **Negative** ($-$ PKR 1.8M)
    - Financing Cash Flow (CFF): **Negative** ($-$ PKR 0.9M)
    - Pattern P6 ($---$) resolves mathematically to *Shake-Out*.
- **Spoken Narration (Voiceover):**
  > *"Small enterprise operators are masters of their trade, but few are trained in financial risk. Welcome to Fiona—an autonomous, multi-agent finance copilot built for the FinTechathon 2026 International Track.*  
  >  
  > *Let's begin where every SME starts: understanding reality. Our Karachi retailer believes their business is in rapid Growth. But Fiona’s deterministic Stage Detector doesn't rely on intuition. Implementing Victoria Dickinson’s cash-flow framework, Fiona analyzes empirical operating, investing, and financing flows across trailing periods.*  
  >  
  > *The verdict? All three cash flows are negative. This is Pattern P6: Shake-Out. Fiona immediately explains the divergence to the owner: revenue is up, but aggressive working capital expansion is bleeding operational cash. The copilot anchors on facts, not founder optimism."*
- **Technical Claim Proved:**
  - Implements `services/engine/analysis/stage.py` (Dickinson 2011 P1–P8 classification).
  - Rule STG-07 (Owner-Disagreement Explanation) actively flags founder bias.
  - Explain-Any-Number drawer renders live `Figure` provenance contract.

---

### Scene 02: The Executive Morning Briefing
- **Duration:** 35 seconds (Timecode: `0:45 – 1:20`)
- **Screen Route:** Click **Briefing** in the left navigation rail (`http://localhost:3000/`)
- **Visuals:**
  - Clean, prioritized dashboard replacing dense balance sheets.
  - Top Metrics Ribbon (Summary Grid):
    - Current Cash at Lowest Point: **PKR 246,119** (below policy buffer)
    - Owner Cash Buffer Policy: **PKR 2,000,000**
    - 13-Week Runway Status: **Breach Alert in Week 7** (amber warning pill)
  - Feed displays prioritized actionable cards:
    1. *Security Alert:* 1 blocked suspicious disbursement.
    2. *Strategic Opportunity:* Concessionary SBP refinance match available.
    3. *Working Capital Action:* Early-payment discount opportunity yielding 44.6% APR.
- **Spoken Narration (Voiceover):**
  > *"SME owners don't have time to decipher three-statement models every morning. Fiona replaces balance sheet clutter with the Morning Briefing—a prioritized, real-time command feed.*  
  >  
  > *At a glance, the owner sees today’s cash position: 3.1 million rupees. Beneath it sits the immutable tenant liquidity buffer of 2 million rupees, alongside a predictive alert: a projected cash dip in Week 7.*  
  >  
  > *Directly below, Fiona surfaces three mission-critical items: an attempted fraud blocked by the Guardian, a subsidized government financing match, and an early-payment discount. Let's look at the blocked transaction."*
- **Technical Claim Proved:**
  - Direct ledger feed parsing in `apps/web/app/page.tsx`.
  - Cash buffer decoupling (Ruling R2): Buffer lives in tenant policy, not in agent parameters.

---

### Scene 03: The Guardian in Action (DEMO-1)
- **Duration:** 55 seconds (Timecode: `1:20 – 2:15`)
- **Screen Route:** Press `Ctrl+Shift+D` to toggle scenario `planted-bill` $\longrightarrow$ Click **Approvals** in the left navigation rail (`http://localhost:3000/approvals` or `/?scenario=planted-bill`)
- **Visuals:**
  - Incoming vendor bill arrives from *Mehran Garments* (`sup_017`), invoice `INV-2231`, amount **PKR 184,500.00** (`bill_2231`).
  - Invoice preview highlights 3 critical red flags:
    1. Red flag 1: Bank IBAN changed on 2026-10-20 (just 2 days ago), confirmed via email only.
    2. Red flag 2: Invoice number `INV-2231` is a near-duplicate of already-paid `INV 2231` (`bill_2188`, settled on 28 Sep).
    3. Red flag 3: Urgent memo text: *"Urgent settlement required immediately or raw material supply will halt."*
  - The Controller agent extracted the data and the Treasurer drafted payment proposal `prop_demo_01`.
  - **The Guardian Inspection Panel / Modal displays:**
    - G-05 (Duplicate Invoice): **FAIL $\longrightarrow$ BLOCK** (Normalized ID match: `INV2231`).
    - G-03 (Bank Details Changed < 7 Days / Unconfirmed): **FAIL $\longrightarrow$ BLOCK** (Changed 2 days ago via email).
    - G-12 (Adversarial Prompt Injection / Urgency): **FAIL $\longrightarrow$ ESCALATE** (Urgency coercive language flagged).
    - G-01 (Mandate Cap Exceeded): **FAIL $\longrightarrow$ ESCALATE** (PKR 184,500 exceeds Treasurer cap of PKR 150,000).
    - Strictest-Outcome Resolver: **FINAL VERDICT: BLOCK** (rendered in prominent red badge).
  - System shows execution refused by the sandbox wallet; payment button is hard-disabled.
- **Spoken Narration (Voiceover):**
  > *"Here is Fiona’s crown jewel: the independent Guardian verification engine.*  
  >  
  > *An invoice arrives from Mehran Garments for 184,500 rupees. The AI Controller extracts the data, and the Treasurer prepares a payment. In standard LLM copilots, this invoice would be paid. In Fiona, it hits the Guardian verification ring.*  
  >  
  > *Notice what Fiona detects: First, rule G-05 catches that 'INV-2231' normalizes to 'INV2231', an invoice already settled last month. Second, rule G-03 flags that the supplier's bank account was changed just two days ago, confirmed only by email, violating the 7-day cooling-off lock.*  
  >  
  > *Third, the adversarial reviewer flags coercive urgency cues in the notes. Finally, the amount exceeds the Treasurer’s 150,000 rupee mandate cap.*  
  >  
  > *Fiona's strictest-outcome combiner resolves the verdict to a hard BLOCK. The sandbox wallet refuses execution. Zero money moves. The business is protected from Vendor Email Compromise."*
- **Technical Claim Proved:**
  - Demonstrates authoritative scenario `DEMO-1` (`rulebook/scenarios.yaml`).
  - Proves concurrent execution of rules G-01, G-03, G-05, and G-12 (`services/engine/guardian_checks/`).
  - Validates that the sandbox wallet is gated strictly by valid cleared verdicts.

---

### Scene 04: Financing Matching & The Strategic Council
- **Duration:** 55 seconds (Timecode: `2:15 – 3:10`)
- **Screen Route:** Click **Financing** (`http://localhost:3000/financing`) $\longrightarrow$ Click **Council** (`http://localhost:3000/council`)
- **Visuals:**
  - Financing Matcher Screen (`/financing`):
    - User evaluates a PKR 2,000,000 working-capital facility for peak season inventory.
    - Matcher queries `rulebook/financing.yaml` across 20 regional options.
    - Ranked Matches:
      1. **SBP SAAF Scheme:** Concessionary rate 9.00% APR; collateral-free SME credit. Status: *Recommended*.
      2. **Commercial Running Finance:** 17.30% Effective Annual Cost. Status: *Alternative*.
      3. **Equity Financing:** Status: *Not Recommended (Dilutive)*.
    - Debt-Service Coverage: Post-borrowing DSCR calculated at **1.45× ($14,500\text{ bp}$)**, beating the 1.25× policy threshold.
  - User navigates to **Council** (`/council`):
    - Structured debate between 4 agent roles:
      - **CFO Strategist:** Recommends subsidized debt to preserve equity.
      - **Treasurer:** Flags liquidity risk and ongoing 13-week forecast buffer breach.
      - **Growth Analyst:** Explores equity partnership to avoid fixed debt burdens.
      - **Guardian:** Ensures comparative review does not emit automated borrowing instructions.
    - Screen renders the **Dissent on Record** card, preserving the multi-agent debate permanently.
- **Spoken Narration (Voiceover):**
  > *"To resolve the working capital crunch, the owner turns to financing. Fiona’s matching engine scans an authoritative regional catalogue of 20 SME credit instruments.*  
  >  
  > *Evaluating the retailer's cash flows, Fiona identifies the State Bank of Pakistan’s SAAF refinance scheme—a concessionary 9% facility for small enterprises. Running through our universal coverage engine, Fiona proves that borrowing 2 million rupees maintains a healthy forward Debt Service Coverage Ratio of 1.45 times, safely above the 1.25 minimum threshold.*  
  >  
  > *When trade-offs are complex, Fiona enters Council Mode. Here, our agents debate: the CFO Strategist recommends subsidized debt to preserve equity, while the Growth Analyst dissents, noting inventory risk. Fiona produces a formal executive memo while recording the dissent permanently in the audit log. The owner makes the final call with complete clarity."*
- **Technical Claim Proved:**
  - Evaluates `services/engine/financing/matcher.py` against `rulebook/financing.yaml`.
  - Uses authoritative shared DSCR engine in `services/engine/analysis/coverage.py`.
  - Implements multi-agent Council deliberation with immutable dissenting opinion tracking.

---

### Scene 05: 13-Week Cash Alert & Payment Timing Optimization
- **Duration:** 45 seconds (Timecode: `3:10 – 3:55`)
- **Screen Route:** Click **Cash forecast** (`http://localhost:3000/forecast`) $\longrightarrow$ Navigate to **Payment timing** (`http://localhost:3000/decisions/payment-timing` or via `Ctrl+K`)
- **Visuals:**
  - Interactive 13-week cash-flow table (`/forecast`):
    - Week 7 turns bright amber: Status renders **Below buffer** (projected cash dips beneath PKR 2,000,000 buffer).
    - Causal decomposition: advance tax instalment + major winter inventory shipment arrival.
  - Screen transitions to **Payment Timing Optimizer** (`/decisions/payment-timing`):
    - Supplier *Chenab Fabrics* offers invoice discount terms: 2/10 net 30 on a PKR 500,000 invoice.
    - Fiona calculates the Compounded Effective Annual Return: **44.59% APR**.
    - Cost of capital comparison: 44.59% return vs. 22.00% cost of debt.
    - Rule G-08 in action: Paying immediately on Day 3 would deepen the Week 7 breach. The Guardian issues:
      `Verdict: APPROVE_WITH_CONDITIONS { pay_on: "2026-12-08" }`.
- **Spoken Narration (Voiceover):**
  > *"In the cash forecast, Fiona peers 13 weeks into the future using direct ledger commitments. Notice Week 7: scheduled tax instalments and inventory arrivals create an impending 420,000 rupee breach below the owner’s safety buffer.*  
  >  
  > *Simultaneously, a fabric supplier offers 2/10 net 30 payment terms. Most SME owners think this is a 2% discount. Fiona calculates the true compounded effective annual rate: an astonishing 44.6% annualized return.*  
  >  
  > *Can we afford to pay early? Guardian Rule G-08 runs an incremental liquidity stress test. It finds that paying today would drain the Week 7 buffer. Instead of rejecting the discount, the Guardian issues a conditional approval: execute payment on December 8th—the latest safe date that captures the cash recovery without violating the buffer."*
- **Technical Claim Proved:**
  - Direct cash forecast engine in `services/engine/forecast/cash/engine.py`.
  - Compounded EAR calculation ($44.59\%$) in `services/engine/decisions/tvm.py`.
  - Invariant rule G-08 attaching machine-verifiable execution conditions (`rulebook/guardian.yaml`).

---

### Scene 06: Human Approval, Sandbox Wallet & Audit Chain
- **Duration:** 35 seconds (Timecode: `3:55 – 4:30`)
- **Screen Route:** Click **Sandbox wallet** (`http://localhost:3000/wallet`) $\longrightarrow$ Click **Audit trail** (`http://localhost:3000/audit`)
- **Visuals:**
  - `/wallet` screen:
    - Displays the 5-step zero-trust payment lifecycle (Proposal $\to$ Guardian checks $\to$ Owner reviews $\to$ Wallet verifies verdict $\to$ Audit chain records).
    - Highlights tenant mandate caps: Per-payment cap PKR 150,000, Daily cap PKR 450,000.
  - `/audit` screen:
    - Shows sequential ledger entries in `public.audit_log`.
    - Prominent green badge: **VERIFIED** (Audit chain verified untampered).
    - Displays RFC 8785 canonical SHA-256 hash chaining: `Hash_n = HMAC-SHA256(Hash_{n-1} + Sequence + Payload)`.
- **Spoken Narration (Voiceover):**
  > *"When a legitimate payment exceeds an agent’s cap, Fiona escalates to the human owner. The owner reviews the three-way match on their phone and provides multi-factor approval.*  
  >  
  > *The sandbox wallet verifies the cryptographic signature of the verdict and executes the transfer within the simulated banking sandbox.*  
  >  
  > *Every event—from document extraction and mandate checks to human approvals and final settlement—is written to an append-only ledger protected by PostgreSQL Row-Level Security. Each audit record is cryptographically linked to its predecessor via SHA-256 hash chaining. If any record is modified offline, the chain breaks instantly."*
- **Technical Claim Proved:**
  - Segregation of duties and human-in-the-loop escalation.
  - Zero-trust wallet execution gated by verdict proof.
  - Cryptographic tamper-evident hash chaining in PostgreSQL audit log (`scripts/verify_audit_chain.py`).

---

### Scene 07: Command Bar, Multi-Lingual Voice & Architectural Sign-Off
- **Duration:** 15 seconds (Timecode: `4:30 – 4:45`)
- **Screen Route:** Press `Ctrl+K` (Global Command Bar) $\longrightarrow$ Closing Title Card
- **Visuals:**
  - User presses `Ctrl+K` from any screen to reveal the **Multi-Lingual Command Palette** (`apps/web/components/command-bar.tsx`).
  - Demonstrates instant multi-lingual command switching:
    - English (`/briefing`, `/forecast`, `/audit`)
    - Urdu (`اردو`: تجزیہ, پیشگوئی, منظوری)
    - Chinese (`简体中文`: 简报, 预测, 审核)
  - Microphone icon activates Web Speech API voice command recognition.
  - Fast cut to full-screen architectural closing card:
    - *The Model Decides* (Multi-Agent Council)
    - *The Engine Computes* (Dickinson Stage, 13-Week Cash, Financing Matcher, DSCR)
    - *The Guardian Checks* (15 Invariant Rules, Strictest Outcome Combiner)
    - *The Wallet Moves Money* (Sandbox Gated Execution)
    - 430 Passing Unit & Property Tests Monorepo-Wide
    - GitHub Repo: `https://github.com/Asharib19khan/fiona`
    - FinTechathon 2026 International Track badge (Tsinghua PBCSF & WeBank).
- **Spoken Narration (Voiceover):**
  > *"With multi-lingual voice navigation and independent mathematical governance, Fiona proves that autonomous finance copilots can be fast, intelligent, and mathematically safe. By separating reasoning from deterministic computation and invariant verification, we give small businesses the financial intelligence of an elite enterprise treasury. Thank you."*
- **Technical Claim Proved:**
  - Tier 2 Command Bar with Web Speech API voice input and multi-lingual support (`apps/web/components/command-bar.tsx`).
  - Complete thematic and structural alignment with official Topic E submission requirements.
  - Video length clocked at **285 seconds (4 minutes 45 seconds)**.

---

## 3. Production & Recording Instructions (For Asharib)

1. **Resolution & Framing:** 1920×1080 (1080p), 60 fps. Cursor smoothed via screen capture software (OBS Studio / Loom / Camtasia).
2. **Audio Track:** Voiceover delivered in clear, confident, professional English. Background music ducked to $-24\text{ dB}$ during speech.
3. **Data Authenticity Notice:** The lower third of the video must display the persistent banner: *"All data shown is synthetic; financial math and security invariants run live on repo commit `b57503b` (430 tests passing)."*
4. **Export Format:** MP4 (H.264 / AAC), strictly under 500 MB.
5. **Browser Keyboard Shortcuts Reference:**
   - `Ctrl+K`: Open Multi-Lingual Quick Command Palette (with voice assist).
   - `Ctrl+Shift+D`: Open Developer Scenario Switcher (`default`, `planted-bill`, `clean`, `escalate-over-cap`).
   - `[`: Toggle left navigation rail on/off.
   - `]`: Toggle right agent inspector on/off.
   - `?`: Open keyboard shortcuts help modal.
