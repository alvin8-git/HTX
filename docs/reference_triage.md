# Reference — `analysis/triage.py` and `analysis/triage_rules.json`

Deterministic triage of a PFI metagenomic report. Reads one HTML report per sample, applies a
gate cascade, emits a tier per taxon and per AMR gene. No LLM, no ML, Python 3 standard library
only.

Design rationale: [`automated_triage_design.md`](automated_triage_design.md).
Measured behaviour: [`triage_prototype_results.md`](triage_prototype_results.md),
[`zymo_validation.md`](zymo_validation.md).
Task guide: [`howto_triage_new_sample.md`](howto_triage_new_sample.md).

---

## Command line

```bash
python3 analysis/triage.py                 # all five HTX samples
python3 analysis/triage.py WBM232          # one sample
python3 analysis/triage.py Zymo/ZymoBac_6ng   # a sample in a subdirectory
python3 analysis/triage.py --selftest      # rule checks, no data required
```

| Argument | Type | Effect |
|---|---|---|
| *(none)* | — | Runs `SAMPLES` = `WBM156 WBM174 WBM179 WBM185 WBM232` |
| `<sample>…` | positional, repeatable | Sample stem relative to the repo root. `Zymo/ZymoM_1` resolves to `Zymo/ZymoM_1_en.html`. |
| `--selftest` | flag | Runs `selftest()` and exits. Requires no report files. |

**Exit status** is 0 in all cases; `--selftest` raises `AssertionError` on failure.

### Input

`<sample>_en.html` — the PFI Vue single-page report. `load_report()` brace-matches the embedded
`globalData` object literal. **Not** the per-sample `.xlsx` files: the HTML carries QC, taxonomy,
AMR and virulence in one parse and needs no `openpyxl`.

Keys consumed:

| `globalData` path | Used for |
|---|---|
| `basicSummary.readsQc.data[0]` | read partition, classified count (gate 12) |
| `indentification_DNA.speciesData.data` | taxonomy (`Scientific Name`, `Real Read`, `Estimate Read`, `Abundance`) |
| `drugResistance.DNA.data` | AMR rows (`Group`, `Gene`, `Class`, `Mechanism`, `Type`, `Coverage(%)`, `Depth`) |
| `virulence.DNA.data` | confirmatory markers (gate 10) |
| `showRNA` | assay-detectability gate (gate 2) |

Optional, read lazily and only for taxa that survive earlier gates:
`<sample>/ExtractRead_DNA/Species/<Name>/<Name>_1.fq.gz` — unique-read fraction (gate 6).
`<sample>/{unclassify,removehost}.DNA_[12].fq.gz` — integrity (gate 12).

### Output

`analysis/triage_<sample>.tsv`, one per sample, `/` in the sample name replaced by `_`.

| Column | Values |
|---|---|
| `kind` | `taxon` or `amr` |
| `verdict` | `NO_ACTION` · `MONITOR` · `CONFIRM` · `ESCALATE` · `NOT_TESTED` |
| `cdc_tier` | `A` · `B` · `C` · empty |
| `name` | taxon name, or `GROUP (MEG_accession)` |
| `evidence` | read count, or `breadth% depth× collapsed N` |
| `reason` | the rule that produced the verdict |
| `note` | AMR annotation text |

Plus a human-readable summary on stdout.

---

## Tiers

`TIERS = ['NO_ACTION', 'MONITOR', 'CONFIRM', 'ESCALATE']` — ordered, lowest first.

| Tier | Meaning |
|---|---|
| `NO_ACTION` | Below threshold, kitome, amplification artifact, intrinsic gene, or confirmatory marker absent. |
| `NOT_TESTED` | A threat-list agent whose genome type this assay cannot see. **Deliberately outside the ladder** so it can never be compared or downgraded into `NO_ACTION`. Absence of evidence, not evidence of absence. |
| `MONITOR` | Real, but not acutely actionable: enriched non-threat taxon, weak acquired gene, a repressor worth deeper sequencing, or a threat whose definition lives below species rank. |
| `CONFIRM` | Real and actionable. **Terminal state for any AMR gene** — host attribution is unsolved, so no gene reaches `ESCALATE`. Means "culture with AST", not "resistant". |
| `ESCALATE` | A threat-list agent **with its confirmatory marker present**. The only tier that asserts a biological threat. |

---

## Gate cascade

Numbering matches [`automated_triage_design.md`](automated_triage_design.md).

| # | Gate | Function | Effect |
|---|---|---|---|
| 12 | Input integrity | `gate_integrity` | Read partition must sum; FASTQs present and non-empty. Reports "no FASTQs delivered" as a note, not four failures. |
| 2 | Assay detectability | `triage_taxa` | RNA agent + `showRNA=False` → `NOT_TESTED`. Runs **before** the read-count gate. |
| 1 | Read floor | `triage_taxa` | `min_real_reads` (50). |
| 7 | Bracken inflation | `triage_taxa` | `Estimate/Real > bracken_inflation_ratio` (10) → flagged, judged on Real Read. |
| 6 | Amplification | `unique_fraction` | Unique fraction below `unique_fraction_floor` (0.15) → artifact. Lazy: only for surviving taxa. |
| 8 | Cross-sample enrichment | `enrichment` | Depth-normalised load (reads per million classified) vs the highest other sample. Below `enrichment_fold` (5.0) → dropped. **Inert with <2 samples** — see below. |
| 9 | Near neighbour | `triage_taxa` | A congener at ≥ this taxon's read count → cross-mapping cannot be excluded. |
| 11 | Taxonomy currency | `taxonomy_notes` | Emits a reclassification note (e.g. *Brucella anthropi* = *Ochrobactrum*). |
| 10 | Confirmatory marker | `marker_present` | Present → `ESCALATE`. Absent → downgrade. No marker but `subspecies_required` → cap at `MONITOR`. |
| 3 | Allele collapsing | `triage_genes` | Group MEGARes rows by `Group`, keep `max(breadth, depth)`. |
| 4 | Breadth floor | `triage_genes` | Below `gene_breadth_floor` (50%) → `NO_ACTION`. |
| 5 | Class annotation | `annotate_group` | group override → mechanism map → keyword fallback. |

### Single-sample mode

`run(samples, comparators=None)`. When `comparators` is `None` it becomes `len(samples) > 1`.
With one sample the fold-change is undefined, so gate 8 is disabled rather than waving everything
through. The run prints:

```
[gate 8] single sample - cross-sample enrichment is inert; non-threat taxa are
         reported on read count alone and are NOT shown to be site-specific.
```

The kitome genus list becomes the only contamination filter, and every non-threat row is tagged
*"no comparator samples — NOT shown to be site-specific"*. Threat-list gating is unaffected: it
never used cross-sample context. Pass `comparators=False` explicitly for replicates of one
community.

---

## Rule file — `analysis/triage_rules.json`

All thresholds and biology live here, not in code. Keys prefixed `_` are comments.

### `thresholds`

| Key | Default | Meaning |
|---|---:|---|
| `min_real_reads` | 50 | Read floor for any taxon call |
| `bracken_inflation_ratio` | 10 | `Estimate/Real` above this is flagged |
| `enrichment_fold` | 5.0 | Fold-change vs other samples for site-specificity |
| `gene_breadth_confident` | 80.0 | Legacy global; superseded by `class_thresholds` |
| `gene_depth_confident` | 5.0 | Legacy global; superseded by `class_thresholds` |
| `gene_breadth_floor` | 50.0 | Below this, a gene is a conserved fragment |
| `unique_fraction_floor` | 0.15 | Below this, reads are amplification not molecules |
| `unique_probe_reads` | 40000 | Reads sampled per taxon for the unique-fraction probe |

### `threat_list` — 46 entries

20 Category A, 18 Category B, 8 Category C; 21 DNA genomes, 25 RNA.

```json
"Bacillus anthracis": {
  "tier": "A",
  "genome": "DNA",
  "markers": ["pXO1", "pXO2"],
  "near_neighbours": ["Bacillus cereus", "Bacillus thuringiensis", "Bacillus mycoides"]
}
```

| Field | Type | Effect |
|---|---|---|
| `tier` | `"A"`/`"B"`/`"C"` | CDC category, reported |
| `genome` | `"DNA"`/`"RNA"` | RNA + DNA-only library → `NOT_TESTED` |
| `markers` | list of `marker_patterns` keys | Present → `ESCALATE`; absent → downgrade |
| `near_neighbours` | list of names | Any at ≥ this taxon's reads → cross-mapping caveat |
| `subspecies_required` | string, optional | Caps at `MONITOR`. **Only on *Salmonella enterica*** — the sole agent whose threat definition lives below species rank. |

> **Names must be PFIDB-exact.** A report can only emit names from the classifier's own namespace,
> which makes name matching safe — but colloquial names never match. `"Junin virus"` finds nothing;
> the database files it as `"Argentinian mammarenavirus"`. See
> [`pfidb_cdc_coverage.md`](pfidb_cdc_coverage.md).

### `amr_classes` — 116 group overrides

Authoritative, because they carry host-specific knowledge a mechanism string cannot: *adeJ* is
intrinsic **only because its host is *A. baumannii***.

```json
"ADEN": {
  "class": "regulator",
  "requires": "ADEJ",
  "actionable_when_partner": true,
  "note": "AdeN, TetR-family repressor of the AdeIJK efflux pump…"
}
```

| Class | Count | Verdict | Meaning |
|---|---:|---|---|
| `acquired` | 38 | `CONFIRM` / `MONITOR` | Horizontally acquired. The only class that can raise a tier alone. |
| `environmental` | 21 | `NO_ACTION` | Metal and biocide resistance. Real, not clinically actionable. |
| `intrinsic` | 15 | `NO_ACTION` | Chromosomal in its host; resistance needs overexpression. |
| `efflux_ubiquitous` | 12 | `NO_ACTION` | Near-universal pumps, expression-dependent. |
| `point_mutation` | 9 | `NO_ACTION` | Resistance needs a substitution; presence is universal. |
| `regulator` | 9 | see below | Meaningful only against its operon. |
| `rrna_conserved` | 7 | `NO_ACTION` | 16S/23S — the whole community piles onto it. |
| `core_essential` | 5 | `NO_ACTION` | Housekeeping; presence is the default state. |

`regulator` resolution:

- `requires` names the partner group. Absent from the sample → `NO_ACTION`, *"incoherent as a resistance call"*. This is what dismisses `MECI` without `MECA`.
- `actionable_when_partner: true` and the partner is present → `MONITOR`. For repressors whose **loss of function is the resistance mechanism** (`ADEN`, `ADEL`, `ADES`, `MEXT`, and `TETR` without the flag). Presence does not prove overexpression; it names the gene worth sequencing deeper.

### `mechanism_classes` — 115 entries

Fallback keyed `"Type|Mechanism"` from the MEGARes columns. **115 pairs span 397 distinct groups**,
which is why this exists instead of 397 hand-written entries.

```json
"Drugs|Class C betalactamases": "intrinsic",
"Metals|Copper resistance protein": "environmental"
```

Unmatched pairs fall through to `_MECH_FALLBACK` in `triage.py` — an ordered keyword list on the
mechanism string — so a deeper library or a newer MEGARes release never yields `unannotated`.

### `class_thresholds` and `group_thresholds`

Two routes to a gene call. **PFI reports depth over *covered* bases**, so breadth and depth are
independent: a gene can sit at 11.69× across 60% of a reference allele. That is a well-sequenced
fragment, not a weak hit — the allele is uncertain, not the gene.

| Route | `acquired` default | Reported as |
|---|---|---|
| Full length | breadth ≥ 80% **and** depth ≥ 5× | `acquired, full length` |
| Fragment | breadth ≥ 55% **and** depth ≥ 10× | `acquired, PARTIAL — family established, allele not` |

Resolution: `group_thresholds[group]` → `class_thresholds[class]` → `class_thresholds._default`.

| Group override | Setting | Reason (carried in the file's `why` field) |
|---|---|---|
| `CTX` | fragment depth 8× | ESBL is clinically decisive; missing one costs more than over-calling |
| `MECA` | fragment depth 8× | A partial *mecA* still warrants culture |
| `BLAZ` | 85%/8×, **fragment route disabled** | Staphylococcal penicillinase is near-universal background |

### `marker_patterns` — 15 regexes

`pXO1` `pXO2` `bont` `caf1` `lcrV` `pla` `fopA` `tul4` `etx` `seb` `ctxA` `ctxB` `stx1` `stx2` `eae`.
Searched case-insensitively against the serialised VFDB row.

### `kitome_genera` — 20 genera

Reagent contaminants (Salter 2014, Eisenhofer 2019). Secondary: the computed enrichment test is the
primary contamination filter, and this list only applies when no comparators exist.

### `taxonomy_notes` — 3 entries

Emitted alongside any call for *Brucella anthropi*, *Bacillus cereus*, *Staphylococcus argenteus*.

---

## Python API

```python
import sys; sys.path.insert(0, 'analysis')
import triage

g     = triage.load_report('WBM232')            # dict — the globalData object
genes = triage.triage_genes(g)                  # list of dicts, sorted by verdict then breadth
probs, classified = triage.gate_integrity('WBM232', g)
triage.run(['WBM232'])                          # full pass + TSV, single-sample mode
triage.run(['A', 'B'], comparators=False)       # replicates: disable gate 8 explicitly
```

| Function | Returns |
|---|---|
| `load_report(sample)` | `globalData` dict. Raises `ValueError` if absent or unbalanced. |
| `gate_integrity(sample, g)` | `(problems: list[str], classified: int)` |
| `triage_genes(g)` | list of `{group, allele, alleles_collapsed, breadth, depth, class, verdict, why, note}` |
| `triage_taxa(sample, g, loads, groups, comparators=True)` | list of `{taxon, tier, real, verdict, why}` |
| `annotate_group(group, type_, mechanism)` | `{class, note}` |
| `gene_thresholds(group, cls)` | resolved threshold dict |
| `loads_by_taxon(reports, classified)` | `{taxon: {sample: reads-per-million}}` |
| `enrichment(loads, taxon, sample)` | fold-change, or `inf` if unique to the sample |
| `unique_fraction(sample, taxon)` | `(fraction, n_reads)` or `(None, None)` if no FASTQ |
| `marker_present(g, marker)` | `(bool, evidence)` |
| `selftest()` | prints and returns; raises `AssertionError` on drift |

## Validation

`python3 analysis/validate_zymo.py` — the engine against the ZymoBIOMICS standard (8 bacteria at
12%, 2 yeasts at 2%). Sensitivity 10/10 in every sample, zero `ESCALATE`, quantitation MAE 1.01 pp.
Exit 0 on pass, 1 on fail. Full results and the five known defects:
[`zymo_validation.md`](zymo_validation.md).

## Known limits

| Limit | Status |
|---|---|
| Host attribution of AMR genes | **Unsolvable here.** Costs 9 false-positive `CONFIRM` calls on a clean standard. |
| Viability / "active species" | Needs RNA. `showRNA=False` in every report. |
| Site-specificity from one sample | Impossible; the run says so. |
| Contamination floor | Needs a negative extraction control; thresholds are asserted, not measured. |
| Threshold calibration | Reasoned, not fitted. Needs culture-confirmed samples. |
