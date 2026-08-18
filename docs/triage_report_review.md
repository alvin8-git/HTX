# Design review — triage evidence report

Review of [`analysis/triage_report.html`](../analysis/triage_report.html) against the question:
*how does the flagged-species section become succinct, ranked and auditable?*

Result: [`flagged_species_mockup.html`](flagged_species_mockup.html), rendered from the real batch.
Every number below is measured — from the file, or from headless Chrome at 1280×900.

---

## What the report currently spends its words on

808 KB, **53,006 visible words**, 319 organism cards, 135 tables, and **5 `<details>` elements** in
the whole file — so essentially nothing is collapsed and everything competes at the same level.

| Block | Cards | Words | Share |
|---|---:|---:|---:|
| **MONITOR** | 304 | 31,256 | **59.0%** |
| `NOT_TESTED` | 11 | 9,632 | 18.2% |
| Documentation, repeated verbatim ×5 | 35 | 4,348 | 8.2% |
| `NO_ACTION` | 3 | 615 | 1.2% |
| **CONFIRM** | **1** | 1,574 | **3.0%** |

**One taxon in the entire batch reaches CONFIRM** — *A. baumannii* in WBM232. The report gives the
rows requiring no action **20× more page** than the one row requiring an analyst. That is the wall
of text, and it is a ranking problem, not a volume problem: the evidence density is the asset.

Two structural notes:

- The seven documentation sections (*How to read a row verdict*, *The input contract*, *Measured
  accuracy* …) are re-emitted in full for each of the 5 samples. They are page-level content
  repeated sample-level times.
- `NOT_TESTED` labels two different findings. *S. aureus* at **3,654 reads** in WBM232 — the most
  abundant CDC-listed organism in the batch — carries the same label as an RNA agent at 0 reads.
  One means "present, but the marker gate could not run at this coverage"; the other means "the
  assay cannot see this agent at all". The report has separate headings for them but styles them
  identically and buries both.

---

## The answers already exist in the ruleset — they are just not rendered

This is the central finding. Nothing below requires new science; two of the three answers are
already computed and then discarded at render time.

### 1 · Which AMR genes must be co-detected

`clinical_watchlist["Acinetobacter baumannii"].escalating_classes` already names them:
**betalactams, Aminoglycosides, Fluoroquinolones, Lipopeptides** — four classes, fixed before the
run. The report renders the raw 13-gene co-detection list instead of the class verdict.

| Class | This sample | Evidence |
|---|---|---|
| betalactams | **detected** | CTX MEG_2378 60.6%/11.69× · BLAA MEG_1247 62.1%/5.18× |
| Aminoglycosides | **detected** | ANT3-DPRIME MEG_899 72.6%/20.94× · AAC6-PRIME MEG_105 63.7%/14.08× · APH3-DPRIME MEG_1019 62.2%/11.97× |
| Fluoroquinolones | none | efflux only (ADEN, ADEL, MEXT) — multidrug, not FQ-specific |
| Lipopeptides | none | no colistin / `mcr` gene — **last-line agent intact** |

Four rows replace the gene wall, and the two *absent* classes carry as much information as the
present ones. Every call here is **PARTIAL** (breadth < 80%): family established, allele not.

### 2 · Which virulence factors matter — the one real gap

326 raw VFDB rows collapse to **121 distinct factors**, ranked by depth. Depth measures how much
was sequenced, not how dangerous a gene is, so the ranked list cannot answer the question as asked.
There is no `vf_core` set in the ruleset — the 24 `marker_patterns` cover CDC threat agents only.

**This is the one item requiring new curation**: a core-determinant set per watchlist organism
(25 species), same shape as `marker_patterns`. Until it exists the mockup shows only what is
measured (`csuB` 48.5%/13.32×, `pgaC` 46.2%/12.37×) and marks the rest `NOT YET CURATED` rather
than asserting absence — the report currently displays 39 of the 121 factors, so absence is not
observable from it anyway.

### 3 · Criteria ledger — the ACMG analogue

The 12 gates already behave as an evidence-code system: each contributes a signed, named, measured
piece of evidence, and fixed rules combine them. They simply never publish the tick-list.
**The gates keep deciding the verdict; the ledger only shows their work.** No change to
`triage.py`'s decision logic, so no regression risk to an engine validated across 3 datasets.

| Code | Criterion | Gate |
|---|---|---|
| `PVS1` | CDC threat-list agent **with** its confirmatory two-way marker detected | 10a |
| `PS1` | Supporting one-way marker detected | 10b |
| `PS2` | Acquired AMR in an escalating class, **full-length** (≥80% / 5×) | 3–5 |
| `PS3` | Most abundant documented host of the gene, or ≥20% of the host pool | 8 |
| `PM1` | Organism on the clinical watchlist | 1b |
| `PM2` | Acquired AMR in an escalating class, **partial** (≥50% / 10×) | 3–5 |
| `PM3` | Core virulence determinant detected — *pending `vf_core`* | — |
| `PP1` | Real reads above the floor (50) | 1 |
| `PP2` | Cross-sample enrichment ≥5× | 8 |
| `BS1` | Confirmatory two-way marker **absent** where the gate ran — counts against | 10a |
| `BM1` | Bracken estimate inflated >10× over real reads — judged on real | 7 |
| `BM2` | Near-neighbour co-detected at comparable depth | 9 |
| `BP1` | Genus on the kitome list (reagent contaminant) | — |
| `BP2` | Below the read floor | 1 |
| `NA1` | Assay cannot see this agent — RNA genome, DNA library | 2 |
| `NA2` | Confirmatory marker not assessable at this coverage | 10a |
| `NA3` | No confirmatory or supporting marker defined for this agent | 10 |
| `NA4` | Input integrity failure | 12 |

**The `NA` axis is the deliberate departure from ACMG.** ACMG has pathogenic and benign directions
only. Here an unexamined agent is neither — that distinction is the project's central semantic
commitment, and collapsing it into "benign" is exactly the error the design exists to prevent.
Any `NA1` forces `NOT_TESTED` regardless of what else fired.

Ceiling rules stay as the engine already applies them: a watchlist-only organism cannot exceed
`CONFIRM`; `ESCALATE` is reserved for a threat-list agent with its confirmatory marker.

#### What the ledger exposes that the prose hides

For *A. baumannii* / WBM232 the ledger reads **4 met, 1 against, 3 not applicable** — and the met
criteria are `PM1` (WHO critical watchlist), `PP2` (6.0× enrichment) and `PP1` (6,496 reads).
`PS3` is **not** met: *S. epidermidis* is 4× more abundant and is itself a documented host of
AAC6-PRIME.

> **The CONFIRM rests on watchlist membership plus 6× enrichment — not on the 13 co-detected
> resistance genes.** The current card leads with the gene table, which reads as though the AMR
> drove the call. The engine's own reason string says the opposite ("none of them changed this
> verdict"), 1,300 words in. The ledger puts it on the first line.

---

## Measured result

| | `triage_report.html` | `flagged_species_mockup.html` |
|---|---:|---:|
| Visible words | 53,006 | **865** |
| Page height, all collapsed | — | **fits 1280×900** |
| Page height, flagged row expanded | ~2,700 px/sample | 2,016 px |
| Top-level containers | 319 cards | **4 bands** |
| Interactive elements under 24 px | — | **0** |
| WCAG AA text failures, light / dark | — | **0 / 0** |
| Horizontal overflow | — | none |
| Console errors, both themes | — | none |

Disclosure is native `<details>` — no JavaScript in the file at all.

### Four contrast defects found and fixed across all three pages

A full leaf-node contrast scan (every rendered text node, both themes, 1280×900) found **133
failures** in the two existing dashboards. The cause was not one token but four, and they split
cleanly along the same line: a token is safe as a **graphic** (3:1 floor) and unsafe as **text**
(4.5:1). Each fix keeps the original value for graphic use and adds a `-tx` variant for text.

| # | Defect | Worst measured | Fix |
|---|---|---:|---|
| 1 | `--muted` `#898781` as text — theme-invariant | 3.20:1 light · 4.38:1 dark | `#6d6b66` light / `#a3a199` dark (4.74 · 6.08) |
| 2 | `--axis` used as text — ghosted `R2…R6` run headers, `no run` cells, separators | **1.48:1** | new `--ghost` `#6f6f68` / `#8a8a88` (4.51 · 4.55) |
| 3 | White label on `--stage-2` of the ordinal ramp | 4.42:1 light · 3.64:1 dark | `#2976d2` / `#3277ca` (4.55 · 4.54) |
| 4 | `--serious` as text — the 46 px hero figure, the batching warning | 2.57:1 | new `--serious-tx` `#a35a3e` light (4.58); dark already 6.60 |

Defect 2 was the worst and the least visible: at **1.48:1** the ghosted run columns were essentially
invisible, which read as intentional de-emphasis rather than as a failure.

Defect 3 is the one worth carrying forward. **The ordinal blue ramp was validated for fills, not for
text on fills** — and its mid-tone was the failure: white measured 4.42:1 and dark ink 4.46:1, so
*neither* direction cleared 4.5. The nudge to `#2976d2` is imperceptible and the ramp keeps
ΔE 32.9 / 25.4 (light) and 53.4 / 17.0 (dark) against the 15 floor, so ordinal separation is intact.
The general rule: **validate a ramp twice — once as fills, once as a text ground.**

One visible consequence to accept: an `INVESTIGATE` icon (graphic, `--serious`) and the hero figure
beside it (text, `--serious-tx`) are now two shades of the same semantic level. That is the
graphic/text split doing its job, not an inconsistency to reconcile.

**Result — all three pages, both themes:**

| | Before | After |
|---|---:|---:|
| `dashboard_overview.html` | 30 | **0** |
| `dashboard_design.html` | 103 | **0** |
| `flagged_species_mockup.html` | 12 | **0** |

`dashboard_design.html`'s **19 undersized hit targets** were fixed in the same pass — see
`dashboard_review.md`. All three pages now measure clean on contrast, hit targets, overflow and
console errors in both themes.

---

## Implemented

Shipped in `analysis/triage_report.py` (+`vf_core` in `triage_rules.json`, +`test_flagged_layer.py`).
`python3 analysis/triage.py --html` now renders a **Flagged species** cover sheet above the sample
switcher: 798 px, 3 bands, every row a native `<details>` linking down to its full evidence card.
Nothing was deleted — the report is 840 KB where it was 789 KB.

Five defects the implementation surfaced that the mockup had not:

1. **The virulence block manufactured a positive.** Binarising any VFDB row into `DETECTED`
   reported *"5 of 5 core determinants present"* for *A. baumannii* when `bap` covered **8.75%** at
   **0.83×**. VFDB rows carry no verdict and the pipeline defines no VFDB threshold, so the fix is
   not to invent one silently: the block now splits at the AMR fragment floor, **names the
   borrowing as a reporting convention**, and reads *"0 of 5 core determinants above the breadth
   floor, 5 more at trace level"*. That is a real finding — every curated determinant for this
   organism is at trace coverage at this depth. It has a regression test.
2. **`PS3` scored the wrong gene.** Any-gene rank-1 let the taxon lead on an irrelevant gene while
   *S. epidermidis* outranked it 4× on AAC6-PRIME, the gene that mattered. Now restricted to
   escalating-class `CONFIRM` genes, and it **names the gene**: *rank 1 of 63 candidate hosts of
   ANT3-DPRIME*.
3. **A single-sample run had no criterion for the route that fired.** With no comparators the
   engine falls back from enrichment to abundance ≥ 1.0%; the ledger named only enrichment and
   went silent. Added `PP3`, which states that enrichment is untestable rather than omitting it.
4. **The masthead counted rows, not agents** — 25 RNA agents × 5 samples read as *"125 agents the
   assay could not see"*, overstating the gap fivefold.
5. **`S. aureus` filled 4 of 6 slots in band 2** with one finding repeated per sample. Rows are now
   one per organism, worst instance ranked, other samples named on the row.

Two report-wide palette tokens were nudged to clear AA, since the new section inherits them:
`grey` `#777777`→`#6D6D6D` (was 3.98:1 on the `#EDF2F8` ground) and `amber` `#B86A00`→`#AD6400`
(white chip label was 4.12:1). Both imperceptible; both fix every existing use too.

**The engine is untouched.** `triage.py` was not modified, no gate consults `vf_core`, and the
ledger only reports fields the cascade already wrote. Zymo validation still passes
10/10 sensitivity and 0 escalations.

Verified: cover sheet 798 px · 0 hit targets under 24 px · 0 WCAG AA failures across 539 text
nodes · 0 console errors · no horizontal overflow · 8 of 8 deep links resolve to a real anchor.

Outstanding: **`vf_core` covers 1 of 25 watchlist organisms.** The machinery ships and an uncurated
organism says so rather than ranking its factors by depth — but the other 24 need a literature pass
before that block says anything for them.

---

## Deliberate limits

- **`vf_core` does not exist.** Block 2 of the mockup shows the shape, and labels itself as the
  proposal rather than the current state. Curating 25 species is the only genuinely new work here.
- **The report truncates VFDB to 39 of 121 factors.** Absence of `ompA`/`bap` is therefore not
  observable from the rendered page, and the mockup does not claim it.
- **Ranking within a band is by read count.** Once the ledger exists, ranking by criteria weight is
  the better sort, but that needs the codes emitted first.
- **`ESCALATE` never fires in this batch**, so that state is exercised only by the ceiling rule text.
- **The AMR ladder is separate.** 31 AMR rows reach CONFIRM across the batch and 2 samples reach
  INVESTIGATE on AMR alone (WBM185: MECA, MUPA, CTX). Those are gene-level calls with their own two
  routes (full-length ≥80%/5× vs fragment ≥55%/10×) and need their own drill-down; the `CONFIRM`
  ceiling there means "culture with AST", never "resistant".
