# Can a novel sample be triaged automatically, without an LLM?

> **Status: built and measured.** This document is the design argument. It was written before the
> engine existed; everything below still holds, and the prediction in §5 turned out close.
> The implementation is `analysis/triage.py` + `analysis/triage_rules.json`
> ([reference](reference_triage.md), [how-to](howto_triage_new_sample.md)). Measured behaviour is
> in [`triage_prototype_results.md`](triage_prototype_results.md) and, against a certified
> standard, [`zymo_validation.md`](zymo_validation.md).
>
> Two things this document got wrong, both recorded in the results:
> the "1,463 species" scope in §6 is right for taxa but wrong for AMR — group-by-group annotation
> does not scale past the samples you happen to hold, and the durable fix was to classify by
> MEGARes *mechanism* (115 pairs covering 397 groups). And §3's host-attribution limit is worse
> than stated: it costs **nine false-positive `CONFIRM` calls on a certified-clean sample**.

**Short answer: yes for the gating, no for the verdict.** A deterministic rule engine can reproduce
most of the routine determinations made in this project, and it should be deterministic rather
than an LLM. But it must terminate in *"escalate to culture"* rather than *"pathogen X confirmed"*
— because the residual questions are missing measurements, not missing reasoning, and no amount of
model capability closes them.

---

## 1. Why non-LLM is the right call, not a limitation

Biosurveillance output may become evidence. Three properties matter more than flexibility:

- **Auditable** — every flag traceable to a named rule and a number.
- **Reproducible** — same input, same output, forever.
- **Calibratable** — thresholds tunable against controls, with a measurable false-negative rate.

A rule engine has all three. Note also that **ML is the wrong tool here regardless**: five samples,
no labels, no negative control. Rules encode the domain knowledge you already have; a classifier
would need training data that does not exist.

## 2. What IS mechanically decidable

Each of these is a static table plus arithmetic — no judgment.

| # | Gate | Mechanism | Precedent in this project |
|---|---|---|---|
| 1 | **Threat-list membership** | taxid → CDC A/B/C tier | §1 of the assessment |
| 2 | **Assay-detectability** | taxid → genome type; RNA agent + DNA library = *untested*, not *negative* | 15 of 21 Cat A agents |
| 3 | **Allele collapsing** | group MEGARes rows by `Group`, keep max(breadth, depth) | 3 MECA rows → 1 *mecA* call (WBM185) |
| 4 | **Breadth × depth gate** | reject genes below threshold on either axis | LpxA 51.65%/1.90× (WBM232) |
| 5 | **Intrinsic vs acquired** | MEGARes group → annotation | AdeJ intrinsic; CTX-M acquired |
| 6 | **Amplification filter** | unique-read fraction vs sample baseline | *C. botulinum*: 11 reads → 1 molecule |
| 7 | **Bracken inflation filter** | Real Read vs Estimate Read ratio | *S. agalactiae*: 29 real / 8,301 est |
| 8 | **Kitome filter** | static contaminant list + cross-sample enrichment | 46 core taxa, §3 |
| 9 | **Near-neighbour check** | congener co-detection at similar depth | *B. anthracis* vs *B. cereus* group |
| 10 | **Confirmatory marker** | agent → required marker; absent = downgrade | pXO1/pXO2, *bont*, *mecA* |
| 11 | **Taxonomy currency** | taxid → renaming/reclassification note | *Brucella anthropi* = *Ochrobactrum* |
| 12 | **Input integrity** | full decompression + pairing + count vs reported | the two corrupt WBM232 files |

Gates 6–8 are the ones that kill most false positives, and they are pure arithmetic.

## 3. What is NOT decidable — by rules or by an LLM

| Limit | Why no algorithm fixes it |
|---|---|
| **Host attribution of mobile genes** | Proven this project: assembly recovered no *mecA*/CTX-M contig, and per-taxon mapping returned **0 reads at MAPQ ≥ 20**. The classifier never assigned these elements to a species. Missing measurement. |
| **Viability / activity** | Requires RNA. `showRNA=False` in all five reports. |
| **Expression-dependent resistance** | *adeJ* needs *adeN* variant calling; ~0.25× genome coverage cannot support it. |
| **Novel organisms** | Not in any lookup by definition. The k-mer probe can say *"something dominant is unassigned"* — it cannot name it. |
| **Threshold calibration** | No blank/negative control in this batch, so the contamination floor is asserted, not measured. |

These are exactly the points where this project stopped and recommended culture. **A rule engine
should stop in the same places** — that is the design succeeding, not failing.

## 4. Architecture

```
report HTML / xlsx
   │
   ├─ parse  ──────────────  stable schema; already implemented in analysis/extract.py
   ├─ integrity gate ──────  reject sample on FASTQ/count mismatch
   ├─ per-taxon gates ─────  6,7,8,9,11  → drop artifacts and background
   ├─ per-gene gates ──────  3,4,5       → collapse alleles, classify intrinsic/acquired
   ├─ join to threat list ─  1,2,10      → tier, detectability, required marker
   └─ emit tiered verdict
```

Output must be a **tier, not a diagnosis**:

| Tier | Meaning |
|---|---|
| `NO_ACTION` | below thresholds, or kitome, or amplification artifact |
| `NOT_TESTED` | threat-list agent whose genome type this assay cannot see |
| `MONITOR` | real and site-specific, no acute risk |
| `CONFIRM` | real, actionable, requires culture + AST or targeted PCR |
| `ESCALATE` | threat-list agent with its confirmatory marker present |

Two rules keep it honest: **`NOT_TESTED` must never collapse into `NO_ACTION`** (the RNA-virus
trap), and **any resistance gene without an attributed host caps at `CONFIRM`**, never `ESCALATE`.

### Implementation notes

- **Join on NCBI taxid, never on names.** The report's `speciesData` carries a `Taxid` column.
  String matching fails silently — searching `PFIDB_v5_0.xlsx` for "Junin" or "Sabia" returns
  nothing, because those agents are filed as *Argentinian* and *Brazilian mammarenavirus*.
- **PFIDB has no taxid column** (name + flag only, 27,827 rows), so names must be resolved against
  NCBI taxonomy once, offline, and the mapping checked in.
- **Ignore the `Human Infection` flag.** All 27,827 database rows carry `Y`; it encodes database
  membership, not pathogenicity.
- Rules belong in a versioned YAML/TSV file, not in code, so thresholds are reviewable.

## 5. Realistic ceiling

Replaying this project's conclusions against the design above:

| Conclusion | Rule-derivable? |
|---|---|
| No CDC Category A agent | **Yes** — near-neighbour + missing pXO1/pXO2; *bont* absent |
| *C. botulinum* is an artifact | **Yes** — unique-read fraction |
| *S. agalactiae* inflated | **Yes** — real vs estimate ratio |
| WBM232 *A. baumannii* site-specific ESBL | **Yes** — enrichment + acquired-gene table |
| WBM232 LpxA/AdeJ not resistance evidence | **Yes** — intrinsic flag + coverage gate |
| WBM179 *mecI* is *blaI* spillover | **Yes** — same-mechanism homology + depth rank |
| Kitome assignments | **Yes** |
| Corrupt FASTQ detection | **Yes** |
| WBM185 *mecA* host unresolved | **Partly** — flags `CONFIRM`; deciding to attempt assembly and interpreting its negative was judgment |
| Unclassified-bin probe | **Partly** — can compute and threshold; interpreting the artifacts was judgment |

Roughly **80% of the routine determinations**, with the residual concentrated where a human
belongs. Most of these rules already exist in prose in `biothreat_assessment.md` and `README.md`
— the work is converting prose to executable rules, which is tractable.

## 6. Scope

Build annotations for the **1,463 species observed across these five samples**, not all 27,827
database entries. Seed from the ~50 CDC A/B/C agents and the 46 kitome taxa, which is where nearly
every decision is actually made, and extend as new taxa appear.

**Do not include an "active" column** — it can only ever be filled by an RNA library.
