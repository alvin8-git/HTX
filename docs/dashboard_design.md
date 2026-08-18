# Analyst dashboard — design proposal

Companion to [`dashboard_design.html`](dashboard_design.html), a working mockup rendered from the
real batch (`analysis/triage_WBM*.tsv`, 5 swabs, 444 taxon rows, 218 AMR rows). Every number on that
page is computed from those files; nothing is illustrative. This document records the decisions
behind it and the one thing it needs that we do not currently capture.

This is the concrete artefact for **proposal point 5 — dashboard with explainability**.

---

## 1. What the data forced

Three measurements taken before any layout work, each of which changed the design.

### 1.1 Ninety-eight percent of the CDC panel was never tested

Across the five swabs, **136 of the 139 CDC-listed taxon rows are `NOT_TESTED`**, not negative.
They are RNA-genome agents and the run sequenced a DNA library, so gate 2 returns `NOT_TESTED`
before the read floor is ever reached.

| CDC panel on this run | Agents | Status |
|---|---:|---|
| DNA genome — assessed | 21 | Screened, each rejection attributable to a named gate |
| RNA genome — not assessable | 25 | `NOT_TESTED` — no assay was run |
| **Coverage** | **21 / 46** | **45.7%** |

The WHO BPPL / ESKAPE watchlist is entirely bacterial, so its coverage is 24/24. **Every finding
in the batch that reached a tier above `MONITOR` came from the watchlist, not the CDC panel.**

A dashboard that renders "0 CDC agents detected" as a green tick is false. The console therefore
opens with a coverage band, above the fold and above every chart, because it qualifies all of them.
`NOT_TESTED` is drawn as a **neutral 45° hatch and never as a status colour** — the four status hues
mean good / warning / serious / critical, and an unexamined agent is none of those.

### 1.2 The signal is one row in 444

| Taxon tier | Rows | Share |
|---|---:|---:|
| `MONITOR` | 304 | 68.5% |
| `NOT_TESTED` | 136 | 30.6% |
| `NO_ACTION` | 3 | 0.7% |
| `CONFIRM` | 1 | 0.2% |
| `ESCALATE` | 0 | 0% |

The one `CONFIRM` is *A. baumannii* in WBM232. In a pie it is a 0.7° sliver — invisible. It is
direct-labelled with a leader line for exactly that reason, and it also gets its own stat tile.
This is the general shape of the problem: the dashboard's job is not to summarise the batch, it is
to surface the one row that matters out of hundreds that do not.

### 1.3 MONITOR and INVESTIGATE are the hardest pair to tell apart

Running the palette validator on the status colours:

```
[PASS] CVD separation      worst adjacent #ec835a↔#fab219  ΔE 11.3 (deutan)
[FAIL] Normal-vision floor worst adjacent #ec835a↔#fab219  ΔE 13.6 — below the 15 floor
```

`warning` (MONITOR) and `serious` (INVESTIGATE / CONFIRM) sit **adjacent on the ladder** and measure
below the separation floor even for full-colour vision. So **every verdict carries an icon and a
word, never a colour alone** — in chips, legends, grid cells and bar segments alike. This is a
measurement, not a preference.

---

## 2. Layout, in reading order

| # | Component | Job |
|---|---|---|
| 1 | **Coverage band** | What the batch could and could not answer. Governs everything below it. |
| 2 | **Triage queue** | Hero figure "2 of 5 need an analyst", then one card per swab, worst first, carrying the engine's reason string **verbatim**. |
| 3 | **Stat tiles** | Swabs analysed · taxon rows at CONFIRM · AMR genes at CONFIRM · CDC agents with no result. |
| 4 | **Donut — sample verdicts** | 5 swabs across 4 classes. |
| 5 | **Donut — species by tier** | 444 rows across 5 classes, sub-1% slices direct-labelled. |
| 6 | **Stacked bars per swab** | Which swab the tiers are in — the donut only says how many. |
| 7 | **Site × run grid** | Location and longitudinal tracking, one component. |
| 8 | **Table view** | Every chart has a table twin; nothing is reachable by hover alone. |

### On the three requested pie charts

Two work, one does not:

- **Sample verdicts** — 4 classes, well-separated counts, part-to-whole at a glance. A donut is right.
- **Species by tier** — 5 classes, kept as a donut with the 0.2% `CONFIRM` pulled out on a leader.
  It answers *how many*; it cannot answer *which swab*, which is why the stacked bars sit below it.
- **Number of analysed swabs** — this is a single total. A pie of one number is one full circle with
  nothing to divide, so it is a **stat tile** instead. The number is the chart.

---

## 3. Explainability

The queue card shows what the engine wrote, unedited, including its hedges. From WBM232:

> *Acinetobacter baumannii*: acquired Aminoglycosides resistance in the same sample
> (ANT3-DPRIME MEG_899, 72.6% / 20.94x) and this genus is a documented host —
> **CO-LOCATION, NOT CO-ATTRIBUTION**.

A confidence percentage would be easier to render and far harder to defend. The reason string is
already the auditable object: it names the gene, the accession, the breadth/depth that cleared the
threshold, and the limit of the inference. Alongside it the console carries the **rules fingerprint**
and PFI software/DB versions in the masthead, so any screenshot is traceable to the ruleset that
produced it.

---

## 4. What the site and longitudinal views need — and do not have

**Location is not currently captured anywhere in the pipeline.** The site names in the mockup were
keyed by hand from the run notes in `101_Documentation.md`. There is no `site` field in the PFI
report, the TSV, or the sample sheet.

Location and longitudinal tracking are deliberately **the same component** — a site × run grid. Today
it has one real column and five ghosted ones; each future run adds a column with no redesign. That
only becomes real with three fields:

| Field | Why | Where it must live |
|---|---|---|
| `site_id` | Stable key across runs. Free-text descriptions will not join — "Changi T3 departure" and "T3 dep." are different strings. | Sample sheet, carried into the PFI report filename |
| `collected_at` | Orders the columns and separates collection date from sequencing date. | Sample sheet |
| `run_id` / `batch_id` | Needed for the caveat below. | Sample sheet |

The engine keys everything — TSV rows, report labels, the reproduce-offline command — off the PFI
report filename. That filename is the only provenance channel that already exists, so the naming
convention is where these fields have to land. This is the same gap flagged under proposal point 1.

> **The batching caveat, which must ship on the panel itself.** These five swabs were sequenced in
> *separate batches*, so a raw cross-swab fold change confounds site with processing run. A
> longitudinal panel invites exactly that inference, which is why the caveat is rendered inside the
> card rather than in a footnote. Cross-site enrichment claims that survive a batch-robust check are
> reported as such; those that do not are labelled *"reported on read count alone, NOT shown to be
> site-specific"*. Making the longitudinal view trustworthy is a **study-design** fix — same-batch
> processing of a site series — not a dashboard fix.

---

## 5. Deployment

Matches the two options in `proposal_scope_answers.md` §5, and they are a sequence, not a choice.

- **A — batch dashboard.** The console is a single self-contained HTML file with no external
  dependencies, written next to the existing `triage_report.html` at the end of a run. Nothing new to
  operate; it opens from a file share and survives being pasted into a report as a PDF.
- **B — OmicsNest-hosted.** The same components backed by a store that accumulates runs, which is what
  turns the site × run grid from one column into a real series. B needs the three fields in §4 first;
  without them it is A with a database behind it.

---

## 6. Known limits of this mockup

- Filter controls are rendered but inert — the interaction spec is one filter row scoping every chart,
  not per-card filters.
- Site names are hand-keyed (§4).
- The AMR panel is summarised to a count per swab. Gene-level triage has 218 rows and its own two
  call routes (full-length ≥80%/5× vs fragment ≥55%/10×); it needs a drill-down of its own, and the
  `CONFIRM` ceiling means "culture with AST", never "resistant".
- `ESCALATE` is empty in this batch, so that state is exercised only in the legend. Worth generating
  a synthetic escalating sample before committing to the layout.
