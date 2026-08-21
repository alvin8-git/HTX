# Phase 1 — the triage script

Scope of this page: **the analysis script only**. The hosted server, the database and the managing
dashboard are Phase 2 and are not costed here.

Hours are effort to build the thing conventionally, not wall-clock time already spent.

---

## Part A — already built

| # | Item | What it is, plainly | Hours |
|---|---|---|---:|
| A1 | Knowledge base of 447 rules | The list of dangerous organisms, resistance genes and virulence markers the script judges against. Each entry is a literature decision, not data entry — this is the slowest and most valuable item. | 95–130 |
| A2 | The decision engine | The script itself: reads a sequencing report and walks every organism through 12 checks in order to reach a verdict — no action, monitor, investigate, escalate. | 90–115 |
| A3 | Reading the instrument's output | Pulling the numbers out of the sequencer's own HTML report reliably, including the odd cases where it changes shape. | 20–30 |
| A4 | The analyst's report | The one-page-per-swab HTML report: flagged organisms first, then the evidence behind each one, in tabs. | 75–105 |
| A5 | Plain-English reasons for every call | The criteria badges — for each organism, which rules fired, which did not, and how strongly each one counts. Lets an analyst re-trace any verdict without reading code. | 30–45 |
| A6 | Comparing a swab to its own history | Keeping a running record of every swab analysed so a new one can be judged against what is normal for that site, kept separate per sample type. | 25–35 |
| A7 | Machine-readable output for the database | Alongside the report, a data file holding the same evidence, so Phase 2 can load it without re-reading the report. | 10–15 |
| A8 | Testing on three independent datasets | 14 real samples: field swabs, a known-answer control mix, and a long-read stool run. Found and fixed 10 real faults. | 80–115 |
| A9 | Self-checks that run on demand | Built-in tests so a change to the rules or the engine cannot silently break a verdict. | 25–40 |
| A10 | Supporting tools | Ten small scripts around the main one — control-sample checking, briefing-deck generation, rule-base maintenance. | 35–55 |
| A11 | Documentation | ~120 pages: how it decides, what it can and cannot see, why each rule exists, and the review record. | 65–100 |
| A12 | Packaging so it runs anywhere | Container and workflow definitions so the same script runs on a laptop, a server or the sequencing appliance and gives the same answer. | 40–65 |
| | **Subtotal** | | **590–850** |

---

## Part B — still needed to close Phase 1

| # | Item | What it is, plainly | Hours |
|---|---|---|---:|
| B1 | Fill in the missing sample details | Collection date, site and sequencing run ID are blank on the sample sheet. Small job, but it blocks all of the Phase 2 over-time analysis and has to happen before the next collection, not after. | 4–8 |
| B2 | Finish the virulence marker list | The "is this strain actually the dangerous one" markers currently cover 1 of 25 watchlist organisms. The other 24 need a literature pass. | 40–70 |
| B3 | Detect engineered organisms | Look for gene combinations that do not occur together naturally, and measure how often that raises a false alarm. Cheapest item here, and the only one that addresses deliberate modification. | 20–40 |
| B4 | Formal validation protocol | A written, repeatable acceptance test with pass/fail thresholds — the evidence that the system works, rather than the belief that it does. | 60–100 |
| B5 | Hardening for unattended use | Sensible behaviour on bad input, clear error messages, exit codes and logs, so a scheduler can run it instead of a person. | 25–40 |
| B6 | Handover and training | Walkthrough materials for the analysts who will read the reports. | 20–35 |
| | **Subtotal** | | **169–293** |

---

## Totals

| | Hours |
|---|---:|
| Part A — built | 590–850 (mid ~720) |
| Part B — remaining | 169–293 (mid ~231) |
| **Phase 1 total** | **759–1,143 (mid ~950)** |

**Phase 2** — RNA virus coverage, the database, the managing dashboard, tracking sites over time and
forecasting — is **1,170–1,820 h (mid ~1,495)**. Full item-by-item breakdown, with costs, in
`HTX_phase1_phase2_estimate.xlsx`.

**Not included anywhere:** wet-lab work for RNA (reagents, protocol, instrument time — may exceed the
analysis work attached to it); sequencing consumables; hardware; accreditation.

**The one thing to decide early.** B1 costs under a day and unblocks roughly half of Phase 2. It has
to be done before the next batch of samples is collected, not after.
