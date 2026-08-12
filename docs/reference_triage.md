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
python3 analysis/triage.py                 # all five HTX samples -> TSV + stdout
python3 analysis/triage.py WBM232          # one sample
python3 analysis/triage.py Zymo/ZymoBac_6ng   # a sample in a subdirectory
python3 analysis/triage.py --html          # -> analysis/triage_report.html
python3 analysis/triage.py --with-fastq    # additionally run the FASTQ-only gates
python3 analysis/triage.py --selftest      # rule checks, no data required
python3 analysis/triage.py --independent stool_sms/A stool_sms/B   # unrelated donors
python3 analysis/triage.py --html --out=analysis/gut.html stool_sms/A   # elsewhere
```

| Argument | Type | Effect |
|---|---|---|
| *(none)* | — | Runs `SAMPLES` = `WBM156 WBM174 WBM179 WBM185 WBM232` |
| `<sample>…` | positional, repeatable | Sample stem relative to the repo root. `Zymo/ZymoM_1` resolves to `Zymo/ZymoM_1_en.html`. |
| `--html` | flag | Writes `analysis/triage_report.html` instead of the TSVs. Combines with sample arguments. |
| `--independent` | flag | The samples are not from one site — different donors, different facilities. Turns gate 8 off, so a fold-change between them is never read as site enrichment. |
| `--out=<path>` | option | Destination for `--html`, relative to the repo root. Without it, every run overwrites `analysis/triage_report.html`. |
| `--with-fastq` | flag | Opts in to the gates that read outside the HTML report — gate 6 (unique-read fraction) and the FASTQ presence checks in gate 12. **Off by default**: the baseline output must be reproducible by anyone holding only the report. |
| `--selftest` | flag | Runs `selftest()` and exits. Requires no report files. |

Use `--independent` whenever the batch is not a set of swabs from one facility. Gate 8 asks
"is this taxon enriched *here* relative to the others" — with four stool donors that question has no
meaning, and ordinary inter-individual variation comes back as "222× enriched".

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
| `virulence.DNA.data` | confirmatory and supporting markers (gate 10), genus-matched on `Pathogen` |
| `showRNA` | assay-detectability gate (gate 2) |

**The HTML report is the whole input.** This is auto-interpretation of the document a
microbiologist is already sent: every verdict must be checkable against that same page, and the
engine must run wherever the page does. Nothing above requires the raw reads.

Optional extension, **off by default**, enabled with `--with-fastq`. Read lazily and only for taxa
that survive earlier gates:

| Path | Adds |
|---|---|
| `<sample>/ExtractRead_DNA/Species/<Name>/<Name>_1.fq.gz` | unique-read fraction (gate 6) |
| `<sample>/{unclassify,removehost}.DNA_[12].fq.gz` | FASTQ presence and size checks (gate 12) |

The extension exists because starting from FASTQ is a plausible future input, not a current one.
See [What the report cannot carry](#what-the-report-cannot-carry) for what running without it costs.

### Output

`analysis/triage_<sample>.tsv`, one per sample, `/` in the sample name replaced by `_`.

| Column | Values |
|---|---|
| `kind` | `sample`, `taxon` or `amr` |
| `verdict` | `NO_ACTION` · `MONITOR` · `CONFIRM` · `ESCALATE` · `NOT_TESTED` |
| `cdc_tier` | `A` · `B` · `C` · `W` (clinical watchlist) · empty |
| `name` | taxon name, or `GROUP (MEG_accession)` |
| `evidence` | read count, or `breadth% depth× collapsed N` |
| `reason` | the rule that produced the verdict |
| `note` | AMR annotation text |

Plus a human-readable summary on stdout.

### HTML report (`--html`)

`analysis/triage_report.html`, one file for every sample in the run, written by
`analysis/triage_report.py`. Self-contained — CSS, SVG icons and JavaScript inlined, no network
requests — so it opens from disk and survives being emailed. Roughly 780 KB for five samples.

A sample switcher across the top, four tabs per sample:

| Tab | Contents |
|---|---|
| **QC** | Read QC from `readsQc`, kingdom breakdown from `idSummary`, integrity-gate output, library scope. Flags the two-classified-read-figures discrepancy where it occurs. |
| **Flaggable species** | Cards banded by severity, `ESCALATE` → `NO_ACTION`, with `NOT_TESTED` below the ladder. Threat-list taxa first in each band; non-threat community taxa collapsed behind a fold. |
| **Resistance genes** | Sample-level, severity-banded, under a standing banner that no gene is attributed to an organism. |
| **Method & verification** | The exact command, the rule fingerprint, and how to check any row against the PFI report. |

Each species card carries the evidence behind its verdict: taxonomy counts, cross-sample load,
confirmatory-marker status, **VFDB rows attributed to that species with their accessions**, and —
where applicable — the inferred host-range block described under `amr_host_hints` below.

Only rows that survived gating are embedded. Suppressed AMR groups are summarised as a count and a
class breakdown, not listed; to audit a suppression, open the PFI report.

**Cross-referencing back to the PFI report** is the point of the design. Every evidence row shows
the identifier you would search for in `<sample>_en.html`: `VFG004763(gb|WP_011274497)` for a
virulence row, `MEG_2378` for a resistance row, the taxid for an organism.

---

## Sample verdict

`sample_verdict(taxa, genes)` rolls the row verdicts up into one answer about the **swab**, which
is what the briefing deck carried and what the row tiers had no equivalent for. Printed on stdout,
written as the first row of the TSV (`kind=sample`), and shown as a banner in the HTML.

`SAMPLE_VERDICTS = ['NO ACTION', 'MONITOR', 'INVESTIGATE', 'ESCALATE']`

| Verdict | Fires when |
|---|---|
| `ESCALATE` | Any threat-list taxon at `ESCALATE` — a CDC agent with its confirmatory marker. |
| `INVESTIGATE` | Any threat-list **or watchlist** taxon at `CONFIRM`, **or** a `high_consequence` acquired gene at `CONFIRM` (`MECA`, `CTX`, `MUPA`). |
| `MONITOR` | A listed taxon that is **site-enriched** (`fold ≥ enrichment_fold`), **or** a listed taxon that **tops the host pool** of an acquired gene at `CONFIRM`. With no listed taxon in the sample at all, an acquired gene at `CONFIRM` still raises `MONITOR`. |
| `NO ACTION` | Nothing above. Community-context taxa (`tier == '-'`) never contribute. |

> **`MONITOR` requires a positive driver (changed 2026-08-12).** It previously fired on *any*
> flagged taxon sitting at `MONITOR`. A public surface carries a dozen WHO-priority organisms at
> background level as a matter of course, so that made `MONITOR` the floor rather than a finding.
> A listed organism at the same relative abundance as every other swab is what background looks
> like; it is not something to watch. Likewise an acquired gene whose host pool is topped by a
> commensal is the flora's resistome, not the site's. This moved WBM174 and WBM179 from `MONITOR`
> to `NO ACTION`.

Measured against the briefing deck's human verdicts: WBM156 `NO ACTION` → `MONITOR` (the engine
reports watchlist organisms in the tap that
the human read as ordinary water flora); WBM232 `ESCALATE` → `INVESTIGATE` (by design — a watchlist
organism cannot drive the sample past `INVESTIGATE`).

## Tiers

`TIERS = ['NO_ACTION', 'MONITOR', 'CONFIRM', 'ESCALATE']` — ordered, lowest first.

| Tier | Meaning |
|---|---|
| `NO_ACTION` | Below threshold, kitome, intrinsic gene, or confirmatory marker absent. (Also amplification artifact, when gate 6 is enabled.) |
| `NOT_TESTED` | A threat-list agent whose genome type this assay cannot see. **Deliberately outside the ladder** so it can never be compared or downgraded into `NO_ACTION`. Absence of evidence, not evidence of absence. |
| `MONITOR` | Real, but not acutely actionable: enriched non-threat taxon, weak acquired gene, a repressor worth deeper sequencing, or a threat whose definition lives below species rank. |
| `CONFIRM` | Real and actionable. **Terminal state for any AMR gene** — host attribution is unsolved, so no gene reaches `ESCALATE`. Means "culture with AST", not "resistant". |
| `ESCALATE` | A threat-list agent **with its confirmatory marker present**. The only tier that asserts a biological threat. |

---

## Gate cascade

Numbering matches [`automated_triage_design.md`](automated_triage_design.md).

| # | Gate | Function | Effect |
|---|---|---|---|
| 12 | Input integrity | `gate_integrity` | Read partition must sum. FASTQ presence/size checks only under `--with-fastq`. |
| 2 | Assay detectability | `triage_taxa` | RNA agent + `showRNA=False` → `NOT_TESTED`. Runs **before** the read-count gate. |
| 1 | Read floor | `triage_taxa` | `min_real_reads` (50). |
| 7 | Bracken inflation | `triage_taxa` | `Estimate/Real > bracken_inflation_ratio` (10) → flagged, judged on Real Read. |
| 6 | Amplification | `unique_fraction` | **Optional extension — `--with-fastq` only, inert by default.** Unique fraction below `unique_fraction_floor` (0.15) → artifact. Lazy: only for surviving taxa. |
| 8 | Cross-sample enrichment | `enrichment` | Depth-normalised load (reads per million classified) vs the highest other sample. Below `enrichment_fold` (5.0) → dropped. **Inert with <2 samples** — see below. |
| 9 | Near neighbour | `triage_taxa` | A congener at ≥ this taxon's read count → cross-mapping cannot be excluded. |
| 11 | Taxonomy currency | `taxonomy_notes` | Emits a reclassification note (e.g. *Brucella anthropi* = *Ochrobactrum*). |
| 10a | Confirmatory marker | `marker_present` | Two-way. Present → `ESCALATE`. Absent → downgrade to `NO_ACTION`. |
| — | Subspecies cap | `triage_taxa` | `subspecies_required` and still `CONFIRM` → cap at `MONITOR`. |
| 10b | Supporting marker | `marker_present` | One-way. Present → `ESCALATE` (lifts the subspecies cap). Absent → unchanged, and the row states that a miss is not an exclusion. |
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

#### Gate 8 assumes the samples are comparable, and cannot verify it

The fold-change divides this sample's load by the highest load among the others. That measures the
**site** only if everything else about the samples is equal. Depth normalisation (reads per million
classified) handles sequencing depth; it does nothing for **extraction or library-prep batch
effects**, and reagent kitome varies by lot. Run across separately-processed samples, a fold-change
confounds place with processing.

**The PFI report carries no batch metadata** — no run date, no flowcell, no library ID, only
`software:V5.1.2 database:5.1.1`, identical in every report. The engine therefore cannot detect
this condition, and `--independent` is the only control available: a blunt on/off switch the
operator must set from knowledge the data does not contain.

> **The five HTX swabs were sequenced in separate batches** (confirmed 2026-08-12, after the
> analysis was written). Gate 8 was run over them without `--independent`. What follows is which
> conclusions survive that, because the answer is not "all" or "none".

A cross-sample fold is batch-confounded. A **within-sample ratio** is not: numerator and
denominator went through the same extraction, the same library prep and the same run, so a kit lot
that delivers more of a genus raises both halves. Comparing a species against the rest of its own
genus is therefore the batch-robust test, and it is computable from the same two report columns.

| Claim | Cross-sample fold | Within-genus ratio | Survives? |
|---|---|---|---|
| *A. baumannii*, WBM232 | 6.0× | **12.7×** the next sample | **Yes** — and on stronger evidence. The rest of *Acinetobacter* is 0.5× in WBM232, i.e. the genus is at its *lowest* there while this species peaks. A kit artefact moves a genus together; this moves one species against its own genus. |
| *P. rettgeri*, WBM156 | ∞ (only sample) | **none available** — it is the entire *Providencia* signal in that sample | **No.** Present in one batch and absent from four is what a batch-specific contaminant looks like, at 193 reads. This was the sole driver of WBM156's `MONITOR`. |
| *S. marcescens*, WBM185 | 12.2× | genus-wide rise; the *marcescens* fraction is lower than in WBM232 | **No** — a genus-level effect. |
| *E. faecalis*, WBM185 | 5.4× | 0.233, the **lowest** of all five samples | **No** — entirely a genus-level rise. |

Negative enrichment findings are the conservative direction here: batch confounding predominantly
manufactures spurious enrichment, so "nothing is site-enriched" (WBM174, WBM179) is if anything
better supported across five different kitomes than across one.

**Not yet implemented.** Making the within-genus ratio the enrichment statistic — or requiring both
to agree — would flag the three genus-level effects automatically and strengthen *A. baumannii*.
It needs no new input. Two related gaps: *Acinetobacter* is absent from `kitome_genera` despite
being a documented reagent contaminant (Salter 2014, Eisenhofer 2019), and nothing records *why* a
given batch was treated as comparable.

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
| `watchlist_min_abundance_no_comparators` | 1.0 | Abundance % a watchlist organism needs to escalate when enrichment cannot be measured |
| `long_read_length_bp` | 1000.0 | Mean read length at or above which `long_read_thresholds` apply |

### `threat_list` — 46 entries

20 Category A, 18 Category B, 8 Category C; 21 DNA genomes, 25 RNA.

```json
"Bacillus anthracis": {
  "taxid": "1392",
  "tier": "A",
  "genome": "DNA",
  "markers": ["pXO1", "pXO2"],
  "near_neighbours": ["Bacillus cereus", "Bacillus thuringiensis", "Bacillus mycoides"]
}
```

| Field | Type | Effect |
|---|---|---|
| `taxid` | NCBI taxid, string | **The match key.** Compared against the report's `Taxid` column before the name is looked at |
| `tier` | `"A"`/`"B"`/`"C"` | CDC category, reported |
| `genome` | `"DNA"`/`"RNA"` | RNA + DNA-only library → `NOT_TESTED` |
| `markers` | list of `marker_patterns` keys | Two-way: present → `ESCALATE`; absent → downgrade to `NO_ACTION` |
| `supporting_markers` | list of `marker_patterns` keys | One-way: present → `ESCALATE`; absent → no change |
| `near_neighbours` | list of names | Any at ≥ this taxon's reads → cross-mapping caveat |
| `subspecies_required` | string, optional | Caps at `MONITOR`. **Only on *Salmonella enterica*** — the sole agent whose threat definition lives below species rank. |

> **Matching is taxid-first, name-second.** `triage.py` builds `{taxid: entry}` from both lists and
> tries the report's `Taxid` column before `dict.get(name)`. Name matching alone was a silent
> negative: *Candida auris* is `Candida auris` in the rule file, `[Candida] auris` in PFIDB v5 and
> `Candidozyma auris` in current NCBI — three spellings, one number (`498019`). A taxid survives a
> genus rename; a name string does not.
>
> Every entry must carry a `taxid`, and no two may share one — `--selftest` asserts both. Fill
> them with `python3 analysis/resolve_taxids.py --write`, which resolves from
> `PFI_DB/list.<Kingdom>.xls` first and NCBI E-utilities second, and verifies every remote hit
> against the record's own synonym list before writing it.
>
> The name fallback still matters for reports with no `Taxid` column, and colloquial names still
> never match: `"Junin virus"` finds nothing; the database files it as
> `"Argentinian mammarenavirus"` (taxid `2169991`). See
> [`pfidb_cdc_coverage.md`](pfidb_cdc_coverage.md) and
> [`pfidb_v5_comparison.md`](pfidb_v5_comparison.md).
>
> **Two entries are above species rank** — `Influenza A virus` (`11320`) and
> `Severe acute respiratory syndrome-related coronavirus` (`694009`). A report row for SARS-CoV-2
> carries `2697049`, the child, so neither taxid nor name matches it. Taxid keying does not fix
> rank mismatch; it makes it visible.

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

### `mechanism_classes` — 131 entries

Fallback keyed `"Type|Mechanism"` from the MEGARes columns. **One pair spans many groups**, which is
why this exists instead of a hand-written entry per group. Long-read stool added 16: the
tetracycline ribosomal-protection and inactivation mechanisms, the whole `Van*`-type glycopeptide
family, and tunicamycin resistance.

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

Resolution: `group_thresholds[group]` → `long_read_thresholds[class]` (long-read platforms only)
→ `class_thresholds[class]` → `class_thresholds._default`.

| Group override | Setting | Reason (carried in the file's `why` field) |
|---|---|---|
| `CTX` | fragment depth 8× | ESBL is clinically decisive; missing one costs more than over-calling |
| `MECA` | fragment depth 8× | A partial *mecA* still warrants culture |
| `BLAZ` | 85%/8×, **fragment route disabled** | Staphylococcal penicillinase is near-universal background |

### `long_read_thresholds`

`detect_platform(g)` reads `Mean_read_length` (or `Read_Length`) from the QC block and returns
`long` at or above `long_read_length_bp`. On a long-read platform the `acquired` gates are replaced:

| Route | Short read | Long read |
|---|---|---|
| Full length | ≥ 80% **and** ≥ 5× | **≥ 95% and ≥ 2×** |
| Fragment | ≥ 55% **and** ≥ 10× | **≥ 80% and ≥ 5×** |

The two gates move in opposite directions because they measure different things on each platform.
A 6–8 kb read spans a 1 kb gene end to end, so **breadth saturates**: 55% of long-read AMR rows in
`stool_sms/` sit at ≥99% breadth against 7% of short-read rows, and an 80% gate lets everything
through — hence 95%. Conversely **one unit of depth is one whole molecule**, not a thin pileup of
150 bp fragments, so 5× would demand five spanning reads of a gene that one read already covered —
hence 2×. Two and not one: at Q10–13 a single read cannot settle an allele.

A `group_thresholds` entry still overrides both. Short-read behaviour is unchanged, and the Zymo
control still scores 10/10 sensitivity with zero escalations.

### `marker_patterns` — 24 regexes

Searched case-insensitively against the serialised VFDB row, **restricted to rows whose reference
strain shares the taxon's genus**. That restriction is not cosmetic — see below.

There are two kinds of marker, and the difference is the direction of inference.

| Field | Present | Absent | Used when |
|---|---|---|---|
| `markers` | `ESCALATE` | **downgrade to `NO_ACTION`** | The gene is unique to the agent and reliably in VFDB, so a negative is a real negative. |
| `supporting_markers` | `ESCALATE` | **no change**, and the row says so | VFDB coverage for the agent cannot be certified from the report. A miss must not read as a clear. |

**`markers` — 9 agents, two-way.**
`pXO1` `pXO2` (anthrax), `bont` (botulism), `caf1` `lcrV` `pla` (plague), `fopA` `tul4` (tularaemia),
`etx` (*C. perfringens*), `seb` (*S. aureus*), `ctxA` `ctxB` (cholera), `stx1` `stx2` `eae` (STEC).

**`supporting_markers` — 8 agents, one-way.**

| Agent | Markers | Gene |
|---|---|---|
| *Brucella melitensis / abortus / suis* | `btp` `omp2531` `bvr` | TIR-domain effectors BtpA/BtpB, Omp25/Omp31, BvrR/BvrS |
| *Burkholderia mallei / pseudomallei* | `bsa` `bimA` `wcb` | Bsa T3SS, BimA autotransporter, capsular polysaccharide I |
| *Coxiella burnetii* | `dotAB` | Dot/Icm T4BSS core — `dotA` `dotB` `icmS/T/V/W/X` |
| *Salmonella enterica* | `tvi` | Vi capsule `tviA–E`/`viaB`, specific to Typhi and Paratyphi C |
| *Mycobacterium tuberculosis* | `esx` | ESAT-6/CFP-10 (RD1), deleted in BCG and absent from most NTM |

*Brucella* deliberately omits `virB`: the T4SS is present in *Ochrobactrum*, which was renamed into
*Brucella* in 2020 and appears in all five HTX swabs as a reagent contaminant. `btpA/btpB` is not.

For *Salmonella*, `tvi` is the marker that answers the question `subspecies_required` poses, and a
hit lifts the `MONITOR` serovar cap straight to `ESCALATE`. **`spv` was tried and removed**: the
virulence plasmid is genuinely present in ordinary Typhimurium, including the certified laboratory
strain in the ZymoBIOMICS standard, so it answers "does this *Salmonella* carry pSLT", not "is this a
notifiable serovar".

#### Why the searches are genus-restricted

Run unrestricted against the nine reports in this repo, the ten new patterns produce **23 spurious
matches**:

- `tviB` on *Acinetobacter* and *Pseudomonas* reference strains — would have escalated
  *S. enterica* in WBM232 and in the clean Zymo standard.
- `esxA`/`esxB` on *Staphylococcus aureus* — S. aureus carries its own Ess/T7SS EsxA/EsxB, so this
  would have escalated *M. tuberculosis* on a certified-clean standard.
- VFDB names Type VI secretion components `icmF/tssM`, `dotU/tssL`, `vasK/icmF` — homologues of the
  Coxiella Dot/Icm system carried by ordinary environmental Gram-negatives, hit in three of the five
  HTX swabs.

With the restriction, the same run produces **zero**. The patterns also name individual genes rather
than families for the same reason (`icm[STVWX]`, never `icm[A-Z]`, which would catch `icmF`).

Genus restriction cannot separate *M. tuberculosis* from an NTM carrying the same operon — but
**gate 9 runs first**, so a near-neighbour at equal read depth drops the verdict to `NO_ACTION` and
gate 10b never fires. That ordering is asserted in `--selftest`.

#### The four that remain unmarkable

*Variola virus*, *Cryptosporidium parvum* — VFDB is a **bacterial** virulence factor database.
*Chlamydia psittaci* — its VFDB genes (`incA`, `tarP`, T3SS) are genus-wide, so a hit would not
confirm *psittaci* over *abortus* or *trachomatis*.
*Rickettsia prowazekii* — the discriminator is an **absence** (typhus-group *Rickettsia* lack
`ompA`), which cannot be written as present-means-escalate.

All four instead carry a populated `near_neighbours` list, and `--selftest` asserts that an agent
with no marker of either kind must at least name its look-alikes. Their rows read: *"no confirmatory
or supporting marker defined for this agent — gate 10 did not run, so CONFIRM is the ceiling and the
call rests on taxonomy alone."*

The 24 `clinical_watchlist` organisms carry no markers **by design** — they escalate on enrichment
plus co-located acquired resistance, and cap at `CONFIRM`. No marker set exists for the ~27,000
species in PFIDB, and for most the concept does not apply: a confirmatory marker is only meaningful
where a virulence determinant separates a threat from a harmless near-neighbour.

### `kitome_genera` — 20 genera

Reagent contaminants (Salter 2014, Eisenhofer 2019). Secondary: the computed enrichment test is the
primary contamination filter, and this list only applies when no comparators exist.

### `clinical_watchlist` — 24 organisms

Built because `threat_list` is exclusively CDC A/B/C, so ***A. baumannii* — the most operationally
important organism in this project — could never exceed `MONITOR`**, having the wrong kind of
danger. Measured before the fix: 257 `MONITOR` and 3 `NO_ACTION` across all five samples, and not
one non-threat taxon above `MONITOR` in any of them.

Sources: WHO Bacterial Priority Pathogens List and the ESKAPE group. No overlap with `threat_list`
(asserted in `selftest`).

```json
"Acinetobacter baumannii": {
  "priority": "WHO critical",
  "escalating_classes": ["betalactams", "Aminoglycosides", "Fluoroquinolones", "Lipopeptides"],
  "note": "Carbapenem-resistant A. baumannii is WHO critical priority…"
}
```

| Field | Effect |
|---|---|
| `priority` | Rendered on the card; reported in the reasoning |
| `escalating_classes` | MEGARes `Class` values that can raise this organism to `CONFIRM` |
| `note` | Shown in the card's "why this organism is on the watchlist" block |

**Ceiling is `CONFIRM`, never `ESCALATE`.** Escalation stays reserved for a CDC threat agent with
its confirmatory marker. A watchlist organism reaches `CONFIRM` only when **all** of:

1. above `min_real_reads` and past the unique-fraction gate;
2. **enriched** ≥ `enrichment_fold` against the other samples — or, with no comparators, abundance
   ≥ `watchlist_min_abundance_no_comparators` (1.0%), because enrichment cannot be measured in one
   sample and defaulting the gate open escalated five organisms in WBM232 on one shared gene;
3. an **acquired** gene at `CONFIRM` whose MEGARes `Class` is in `escalating_classes` **and** whose
   `amr_host_hints` host range includes this genus;
4. **and this organism must plausibly own that gene** — it is either the most abundant documented
   host of it in the sample, or holds at least `escalation_host_share` (0.20) of the reads of all
   its documented hosts.

> **Condition 4 added 2026-08-12.** Being *a* documented host was enough on its own, which let
> *Serratia marcescens* (WBM185) escalate on a CTX-M whose host pool it holds **1.3%** of, among 77
> candidate organisms. Below the share bar, naming one of them is arbitrary. *A. baumannii* in
> WBM232 holds 21% **and** tops its pool, so the batch's one operational finding is unaffected.

Condition 3 is **co-location, not co-attribution** — MEGARes still has no organism column. The
reasoning string says so, and the verdict it produces is `CONFIRM`, meaning *culture with AST*,
which is the correct action whether or not the gene turns out to be this organism's.

### `amr_host_hints` — 56 groups, evidence layer

The one inference layer in the system, and it is quarantined. It is read by
`genus_amr_context()` and by `watchlist_escalation()`. **It never changes a taxon's verdict**;
the only tier it can raise is `CONFIRM` on a watchlist organism, which means "culture with AST" —
the right action whether or not the gene turns out to belong to that organism.

```json
"MECA": {
  "taxa": ["Staphylococcus", "Mammaliicoccus"],
  "basis": "mecA sits on SCCmec, a staphylococcal mobile element; it is not found outside…"
}
```

MEGARes carries no organism column, so a resistance gene cannot be placed under a species from
this data. These entries record the *literature* host range of a gene family. A hint is rendered
under a species only when that genus is independently present in the same sample, and it is drawn
in a dashed amber box headed **INFERRED, NOT MEASURED**, restating that no field in the report
joins a resistance row to a species row — the resistance table has no organism column and the
species table has no gene column — so the attribution is unavailable in principle, not merely
unattempted. (Assembly from raw reads is the analysis that could settle it; on this batch it was
run and still could not — see `biothreat_assessment.md` §2.5. That work is outside this engine's
input contract either way.)

#### Candidate-host ranking — `genus_amr_context()`

AMR and VF results are sample-wide; a species verdict is not. `genus_amr_context(name, genes,
present)` pulls the sample-wide evidence into the row of every organism it could plausibly belong
to, and adds the one thing that lets a human weigh it: **every documented host of that gene that
is actually present in this sample, ranked by read count, with this taxon's own rank marked.**

It is attached to the taxon row as `amr_context` and summarised in one `why` line. The line is
appended *before any gate runs* and no gate reads it back.

WBM179, *S. aureus* (`NO_ACTION`, 1,699 reads):

> AMR CONTEXT: 15 gene(s) expected in *Staphylococcus* co-detected in this sample (TETK, MSRA,
> BLE, LNUA, BLAZ, ERMC …); the most abundant competing host in the sample is
> *S. epidermidis* at 65,238 reads (38× this taxon), a documented host of TETK — MEGARes carries
> no organism column, so none of them is attributed to any species and none of them changed
> this verdict

The verdict stays `NO_ACTION`, set by gate 10a (`seb` absent). The context is why a reader can
*agree* with that call instead of merely accepting it: *blaZ* and *mecI* are staphylococcal, and
six other staphylococci in this sample are more abundant than *S. aureus*. In WBM156 the same
machinery reports *S. aureus* at **rank 30 of 57** candidate hosts for `ERMF` — a fact no
verdict tier can carry.

**Every listed organism gets a line — 70 of 70.** Silence is the failure mode this project exists
to avoid, so an organism with no matching gene says *why*:

| Case | Line | Count |
|---|---|---:|
| Genes matched | full candidate-host ranking | **26** |
| `amr_expectation` set on the entry | *"none detected, and none expected — …"* with the biology | **12** |
| Report `Type` is virus / fungus / eukaryotic parasite | *"not applicable — MEGARes indexes bacterial resistance genes"* | **29** |
| Genus curated, nothing from its repertoire in this sample | *"N group(s) documented in Clostridium (ERM, ERMB, ERMF), none detected here"* | — |
| Genus not curated | *"a coverage limit of the rule file, NOT evidence this organism carries no resistance"* | **2** |

`amr_expectation` is an optional string on a `threat_list` / `clinical_watchlist` entry, for agents
where the honest statement is biological rather than a gap — *Brucella*, *Coxiella*, *Rickettsia*,
*Chlamydia*, *Francisella*, *Y. pestis*, *B. anthracis*, *B. mallei/pseudomallei*, *H. pylori*:
organisms with no mobile resistome, whose resistance is chromosomal or point-mutational and
therefore invisible to read-level MEGARes calling.

The two remaining uncurated genera are ***Neisseria*** and ***Haemophilus***. Both carry plasmid
`blaTEM-1`, but which MEGARes group that lands in was not verifiable from this repository, and a
guess would put a wrong organism on a real gene. They emit the coverage-limit line until someone
checks.

The `basis` field exists so a reviewer can disagree with one row without discarding the layer.
Several entries argue *against* significance — `AAC6-PRIME` records that *aac(6')-Ii* is
chromosomal and intrinsic in *Enterococcus faecium*, and `FOSA` that *fosA* is intrinsic in
*P. aeruginosa* and most Enterobacteriaceae, which is exactly why both produce false-positive
`CONFIRM` calls on the Zymo standard.

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
triage.run(['A', 'B'], comparators=False)       # replicates or unrelated donors: gate 8 off
```

| Function | Returns |
|---|---|
| `load_report(sample)` | `globalData` dict. Raises `ValueError` if absent or unbalanced. |
| `gate_integrity(sample, g)` | `(problems: list[str], classified: int)` |
| `triage_genes(g, platform=None)` | list of `{group, allele, alleles_collapsed, breadth, depth, class, platform, verdict, why, note}`; platform auto-detected when omitted |
| `triage_taxa(sample, g, loads, groups, comparators=True)` | list of `{taxon, tier, real, verdict, why}` |
| `annotate_group(group, type_, mechanism)` | `{class, note}` |
| `gene_thresholds(group, cls, platform='short')` | resolved threshold dict |
| `detect_platform(g)` | `'long'` or `'short'` from the report's mean read length |
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

---

## What the report cannot carry

The engine's limits are mostly limits of its **input**, not of its rules. This is the standing list
of what a PFI HTML report cannot answer, what it would take to answer it, and — where it has been
measured — what running without it actually costs. It is maintained deliberately: a limit that is
written down can be designed around, and a limit that is not gets mistaken for a clean result.

| Question | Why the report cannot answer it | What would answer it |
|---|---|---|
| **Is this taxon distinct molecules or one amplified fragment?** | The report gives read counts. One fragment read 10,000× and 10,000 distinct fragments produce an identical row. | Unique-read fraction from `ExtractRead_DNA` — implemented as gate 6, behind `--with-fastq`. |
| **Which organism carries this resistance gene?** | No field joins `drugResistance.DNA` to `speciesData`. Sample-wide by construction. | Assembly + read mapping. Attempted on this batch (§2.5) and it *still* failed for `mecA`/CTX-M, so even the raw reads do not guarantee an answer. Culture with AST does. |
| **What is in the 72–90% unclassified reads?** | The report says nothing about them. Any organism absent from the PFI database lands here and is invisible to every row. | Direct k-mer and GC interrogation of the unclassified bin. |
| **Is resistance conferred by a point mutation?** | Only gene *presence* is reported. `gyrA`, `rpoB`, `lpxA` resistance is invisible, so its absence is never evidence of susceptibility. | Variant calling at sufficient depth. |
| **Is this gene on a plasmid, a prophage or the chromosome?** | No genomic context of any kind is reported. | Assembly and replicon typing. |
| **Is anything alive?** | Not in the DNA reads either. Needs an RNA library at the bench. | An RNA run; the report then carries `speciesActivity` and the rules gain an activity axis. |

### Measured cost of the HTML-only default

Gate 6 is the only baseline gate genuinely lost, and it is a **removal** gate — its absence can
leave noise in, never take a real finding out. Across the five HTX samples, running without it:

| | With gate 6 | HTML-only |
|---|---|---|
| Sample verdicts | MONITOR, NO ACTION, NO ACTION, INVESTIGATE, INVESTIGATE | **identical** |
| Threat-list / watchlist rows changed | — | **0** |
| Taxon rows changed (of 444) | — | **3**, all `NO_ACTION` → `MONITOR` |

The three are *Scardovia inopinata* (13% unique of 67 reads), *Hyphomicrobium* sp. MC1 (10% of 78)
and *Amycolatopsis methanolica* (9% of 55) — all environmental or oral commensals, all carrying
`detected only in this sample`. That is the real interaction: **gate 6 protects gate 8**, because
a stack of PCR duplicates found nowhere else counterfeits site-specificity exactly.

Threat-list rows are insulated by redundancy rather than by gate 6. It fired on *C. botulinum* and
*V. cholerae*, and neither moved — each already had two independent grounds for `NO_ACTION` (the
50-read floor, and confirmatory-marker absence), both computed from the report alone.

> Generalise with care. Gate 6 fired on 5 of 305 measured taxa here (1.6%), on swabs whose median
> unique fraction is 0.33. A low-biomass, over-cycled library would sit far closer to the 15% floor
> and the false-positive count would rise with it. Three rows is the cost for *these* samples, not
> a general bound.

### These rules are expected to change

The gate cascade encodes what is decidable from today's report shape. A new library type (RNA), a
new PFI database version, or simply more sample data changes what is decidable — and that change
belongs in `triage_rules.json`, not in `triage.py`. The engine is the part that should stay still.
