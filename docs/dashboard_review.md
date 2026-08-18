# Design review — analyst dashboard

Review of [`dashboard_design.html`](dashboard_design.html) against the question: *how does this
simplify into a general overview of biosurveillance data actively being sequenced and analyzed?*

Result: [`dashboard_overview.html`](dashboard_overview.html). Every number below is measured from
the rendered page in headless Chrome at 1280px, not estimated.

---

## The finding that governs the rest

**The current dashboard is a batch retrospective. The question asks for an operational monitor.
These are different products.**

Every sample in `dashboard_design.html` is terminal — it has a final verdict. The data model carries
`id, site, spot, verdict, reads, raw, host, tiers, amr, reason, tags`. There is **no timestamp, no
pipeline state, no duration**. A swab that is still on the sequencer cannot be represented at all;
there is no value in the schema that means "no verdict yet."

That matters beyond layout. A dashboard that can only show finished samples will silently under-report
the queue: three swabs sequencing overnight are invisible, and the page reads "5 samples, 2 need
attention" when the true position is "10 in flight, 2 need attention, 3 not yet answerable." For a
system whose entire design ethos is *never render an unknown as a result*, that is the same class of
error as painting `NOT_TESTED` green.

Fix: a pipeline strip as the first element, with counts per stage and the age of the oldest item in
each. Stage counts are ordinal, so they take the blue ramp; status colours stay reserved for verdicts.

---

## Measured problems

| # | Finding | Evidence |
|---|---|---|
| 1 | Page is 3 screens tall | **2,761 px** rendered; 900 px viewport |
| 2 | A quarter of all text is the designer explaining the design | Design-notes section: **358 px, 292 of 1,118 words (26%)**. Analyst value: zero |
| 3 | Most of the queue says "nothing here" | 3 of 5 cards are NO ACTION/MONITOR = **483 px (17.5% of page)** |
| 4 | Sample-verdicts donut is redundant | 5 data points; all 5 already listed with verdict chips ~200 px to its left |
| 5 | Species donut inverts the attention hierarchy | **99.1%** of its area is MONITOR (304) + NOT_TESTED (136). The actionable row is **0.2%** |
| 6 | Stacked bars supersede the species donut | Same 444 rows **plus** which swab. The donut adds nothing the bars lack |
| 7 | Coverage stated twice | Tile "CDC agents with no result: 25" = 46 − 21 from the band above it |
| 8 | Card mosaic instead of layout | **14** card containers. This is the "App UI made of stacked cards" hard-rejection criterion |
| 9 | No radius hierarchy | **8** distinct border-radius values (2/3/4/5/6/8 px + two split values) |
| 10 | Pinpoint hit targets | **30 of 34** interactive elements under 44 px; donut arcs (17 px band) and bar segments (20 px) under the 24 px chart-mark floor — **now fixed, see below** |
| 11 | `system-ui` as the primary face | AI-slop blacklist item 11. Constraint-driven — the artifact CSP blocks font CDNs — but real |

### On the second gauge

The WHO watchlist gauge renders **24 of 24 = a bar filled to 100%**. A meter that is always full
communicates nothing; it is a sentence wearing a chart costume. It became text.

---

## What the simplification actually is

Three zones, one screen, in the order an analyst needs them:

1. **Flow** — what is moving. Sequencing / Analysis / Triaged, with the oldest item's age per stage,
   and the count needing a human broken out as the hero figure. *This did not exist before.*
2. **Coverage** — one line. What the assay could not answer, hatched, never green.
3. **Attention** — only the swabs needing a human. The cleared ones collapse to a single line that
   still names them and still carries WBM156's MONITOR hold.

Then one 24 px composition strip for the 444 taxon rows, and everything else behind a
**Batch detail** disclosure: per-swab tiers, site history, the full evidence table.

| | Before | After |
|---|---:|---:|
| Page height | 2,761 px | **896 px** |
| Words | 1,118 | **247** |
| Card containers | 14 | **4** |
| Interactive elements under 24 px | 30 | **0** |
| Horizontal overflow | none | none |
| Console errors, both themes | clean | clean |

---

### Hit targets in `dashboard_design.html` — resolved

A later pass took the console to the same standard as the overview: **19 undersized marks → 0**,
both themes.

| Mark | Was | Fix |
|---|---|---|
| Coverage meters ×2 | 582×**14** px | 24 px hit box, 5 px padding — the bar still *looks* 14 px |
| Stacked bar segments ×14 | **20** px tall | `bh` 20→24, `gap` 14→12 so the section grows 20 px, not 40 |
| Donut arcs ×3 | **17** px band | band 17→24 — the mark-thickness cap and the hit floor are the same number |

24 px is simultaneously the maximum bar thickness and the minimum hit target, so both specs land on
one value.

**Two marks still cannot be reached by pointer, deliberately.** A 0.2% donut arc is 0.7 px wide and
a 3-row bar segment is 5.7 px; widening either to 24 px would misstate the value it encodes. Their
tooltips are removed at render time rather than faked:

```js
svg.querySelectorAll('rect[data-t]').forEach(r => {
  if (r.getBBox().width < 24) r.removeAttribute('data-t'); });
```

Because `bind()` also sets `tabindex`, dropping the attribute takes them out of the tab order too —
correct, since a 5 px target is no more usable by keyboard than by mouse. Both values stay readable:
sub-1% arcs are already direct-labelled with a leader line, and every chart has a table twin.

## The pie charts, honestly

You asked for three. My position after measuring:

- **Number of analysed swabs** — a single total has nothing to divide. Already a stat tile; now a
  pipeline stage count. Keep as a number.
- **Sample verdicts** — at n = 5 with all five listed beside it, the queue *is* the chart. Cut.
- **Species by tier** — this one has real parts, but 99% of its area is background and unmeasured
  rows. It is now a **24 px horizontal strip**: same part-to-whole reading, ~40 px instead of ~700 px
  for two donut cards, and the 0.2% CONFIRM stays visible as its own segment with the count in the
  legend.

Both donuts still exist in `dashboard_design.html`. If you want them in the overview, they belong
inside the **Batch detail** drawer, not above the fold. That is a call for you to make — I have
stated the measurement, not deleted the option.

---

## Deliberate limits

- **The three in-flight swabs are mock**, and the page says so in place. The pipeline carries no
  state or timestamp field, so they cannot be real yet. The five triaged swabs and every number
  under them are computed from `analysis/triage_WBM*.tsv`.
- **Making the pipeline strip real** needs `sample_state` and `collected_at` on the sample sheet,
  carried through the PFI report filename — the same provenance gap as proposal point 1, now with a
  second consumer.
- **`system-ui` stays.** Inlining a real face as a base64 data URI to satisfy the typography rule
  would add a few hundred KB to a proposal mockup for a marginal gain. Worth revisiting if this
  becomes a product rather than a proposal exhibit.
- **Filters are still inert** in both files.
- **`ESCALATE` never fires in this batch**, so that state is exercised only in the legend. Generate a
  synthetic escalating sample before committing to the layout.
