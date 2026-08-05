# Validation against the ZymoBIOMICS Microbial Community Standard

Ground truth: Zymo data sheet DS1706 (D6300 / D6305 / D6306) — eight bacteria at 12% gDNA
abundance each, two yeasts at 2% each. Five reports at different inputs, one known community.

Run: `python3 analysis/validate_zymo.py` (calls `analysis/triage.py`).
Inputs: `Zymo/{ZymoBac_3ng, ZymoBac_6ng, ZymoM_1, ZymoM_10, Zymo_Std_R1}_en.html`.

These libraries are much deeper than the HTX swabs — 20–40 M raw reads, 73–96% classified,
315–318 MEGARes groups — so they stress the engine harder than the samples it was written against.

---

## Headline

| Test | Result |
|---|---|
| Sensitivity — 10/10 expected organisms in every sample | **PASS** |
| Specificity — zero `ESCALATE` on a certified-clean standard | **PASS** |
| Quantitation — mean absolute error vs theoretical | **1.01 percentage points** |
| False-positive taxa above 1,000 reads | **1** (*Shigella flexneri*, 0.04%) |
| False-positive threat calls | **1** (*Salmonella enterica* → `CONFIRM`) |
| False-positive AMR calls | **2** (`aac(6')`, `fosA` — intrinsic, called acquired) |

## 1. Sensitivity and quantitation — passes

Observed Bracken abundance (%), theoretical 12% for bacteria, 2% for yeasts:

| Organism | GC | theo | 3ng | 6ng | M_1 | M_10 | Std_R1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| *P. aeruginosa* | 66.2 | 12 | 8.06 | 10.93 | 12.58 | 11.61 | 12.92 |
| *E. coli* | 56.8 | 12 | 9.59 | 8.98 | 10.22 | 9.95 | 10.92 |
| *S. enterica* | 52.2 | 12 | 12.93 | 12.48 | 13.06 | 12.64 | 12.56 |
| *L. fermentum* | 52.8 | 12 | 10.64 | 9.97 | 9.36 | 9.42 | 9.15 |
| *E. faecalis* | 37.5 | 12 | 11.98 | 11.72 | 11.09 | 11.46 | 11.02 |
| *S. aureus* | 32.7 | 12 | 13.68 | 13.83 | 12.70 | 13.38 | 13.37 |
| *L. monocytogenes* | 38.0 | 12 | 12.22 | 11.81 | 11.36 | 11.77 | 11.41 |
| *B. subtilis* | 43.8 | 12 | 12.78 | 12.38 | 12.24 | 12.39 | 12.06 |
| *S. cerevisiae* | 38.4 | 2 | 1.65 | 1.60 | 1.56 | 1.63 | 1.54 |
| *C. neoformans* | 48.2 | 2 | 1.51 | 1.43 | 1.43 | 1.49 | 1.30 |
| **detected** | | | 10/10 | 10/10 | 10/10 | 10/10 | 10/10 |
| **MAE (pp)** | | | 1.22 | 1.02 | 0.96 | 0.91 | 0.96 |

Accuracy improves with input (1.22 → 0.91 pp) and is stable across the 3ng/6ng and M_1/M_10 pairs.
Both yeasts sit consistently low (2.84–3.16% against a theoretical 4%) — the expected tough-to-lyse
under-recovery the standard is designed to expose.

**GC bias is present and measurable.** Correlation between GC content and signed error is
**−0.82 at 3ng**, weakening to −0.09 at the highest input. AT-rich *S. aureus* (32.7% GC) is
over-recovered by +1.39 pp pooled; the higher-GC organisms are under-recovered. This reproduces
the "Assess GC Bias" panel in Zymo's own data sheet, and it means low-input libraries systematically
under-report GC-rich organisms — worth remembering for WBM156, the lowest-biomass HTX sample.

## 2. Specificity — passes

Only **one** taxon above 1,000 reads is not in the standard, and it appears in all five samples at
the same level: ***Shigella flexneri*, ~4,000 reads, 0.04%**. *Shigella* is genomically *E. coli*,
so this is near-neighbour cross-mapping from an expected organism, not contamination. Total
off-target burden is 0.04–0.05% of classified reads.

**The marker gate did its job on a certified-negative sample.** The standard contains three CDC
Category B organisms by design, as non-toxigenic laboratory strains:

| Organism | Reads (6ng) | Verdict | Reason |
|---|---:|---|---|
| *S. aureus* | 3,172,304 | `NO_ACTION` | `seb` absent — correctly not staphylococcal enterotoxin B |
| *E. coli* | 395,160 | `NO_ACTION` | `stx1`/`stx2`/`eae` absent — correctly not STEC/EPEC |
| *S. enterica* | 3,221,442 | **`CONFIRM`** | **false positive, see below** |

Two of three correctly downgraded at ~13% abundance. That is the single most useful thing this
validation shows: the engine does not escalate an abundant pathogen-genus organism just because it
is abundant.

---

## 3. Defects found

### D1 — *Salmonella enterica* is called `CONFIRM` on a clean standard

Its `threat_list` entry carries `markers: []`, so gate 10 never runs and any detection above the
read floor defaults to `CONFIRM`. At 12% abundance that fires in all five samples.

This is not merely a missing marker. **It is unresolvable in principle with this database.** A
Category B *Salmonella* call means Typhi or a specific serovar, and `PFIDB_v5_0.xlsx` has no
serovar rank — 1 of 27,827 entries carries `subsp.`/`serovar`/`str.` (see
`pfidb_cdc_coverage.md`). The engine cannot distinguish the standard's laboratory strain from a
notifiable one.

**FIXED.** A new `subspecies_required` field on a threat-list entry caps it at `MONITOR` with an
explicit reason. *S. enterica* now reads *"species-level identification only — needs serovar
(Typhi / Paratyphi / Typhimurium)"* in all five Zymo samples; the HTX samples are unaffected.

**Correction to the first draft of this section:** I initially wrote that the same applies to
*Brucella*, *Cryptosporidium*, *C. psittaci* and *C. burnetii* because they also carry empty
marker lists. That was wrong. For those, the **species-level call *is* the finding** — *B.
melitensis* at species level is brucellosis, *B. pseudomallei* is melioidosis — and their
look-alikes are already handled by the near-neighbour gate. Only *Salmonella* has its threat
definition below species rank, so only it carries the flag. The selftest asserts both directions.

### D2 — `aac(6')` and `fosA` are called `CONFIRM` in every Zymo sample

| Gene | Breadth / depth (6ng) | Reality |
|---|---|---|
| `AAC6-PRIME` | 91.76% / 42.22× | *aac(6')-Ii* is **chromosomal and intrinsic** in *E. faecalis* |
| `FOSA` | 91.40% / 23.60× | *fosA* is **chromosomal and intrinsic** in *P. aeruginosa* and Enterobacteriaceae |

Both are annotated `acquired` in `triage_rules.json`. Both are genuinely present — and genuinely
not acquired resistance, because of *which organism carries them*. The `AAC6-PRIME` note already
warns that some alleles are intrinsic in *Acinetobacter*; the rule cannot act on it because
**intrinsic vs acquired is host-dependent and the engine has no host.**

This is the same root cause as every other unresolved question in the project (§2.5 of the
assessment): AMR tables do not link a gene to an organism. A clean standard makes it unmissable.

### D3 — ~~the "108/108 groups annotated" claim was over-scoped~~ — FIXED by mechanism-level rules

That figure was measured on the five HTX swabs. At 20–40 M reads the Zymo libraries surfaced far
more of MEGARes: 315–318 groups, of which only ~31 had a rule. 287 `MONITOR` rows per sample is not
usable triage.

**Fix: classify by mechanism, not by group.** MEGARes already ships `Type` and `Mechanism` on every
row, and across all ten reports **115 (Type, Mechanism) pairs span 397 distinct groups**. Writing
397 group entries by hand would have been wrong twice over — laborious, and still silent on the
next group. Resolution order is now:

1. **group override** — authoritative, encodes host-specific knowledge a mechanism string cannot
   carry (*adeJ* is intrinsic only because its host is *A. baumannii*);
2. **`mechanism_classes` map** — 115 entries in the rule file;
3. **keyword fallback in code** — catches a mechanism string never seen before, so a deeper library
   or a newer MEGARes release still lands somewhere sane rather than `unannotated`.

| | Groups seen | Unannotated before | Unannotated after |
|---|---:|---:|---:|
| HTX swabs | 24–52 | 0 | **0** |
| Zymo standards | 315–318 | 285–287 | **0** |

Zymo triage output went from 290 `MONITOR` / 2 `CONFIRM` to **~299 `NO_ACTION`, 2–7 `MONITOR`,
9–12 `CONFIRM`**. 143 of the ~300 suppressions are metal and biocide resistance.

### D3b — and that immediately made D2 worse, which is the point

With every group classified, the clean standard produced **15 `CONFIRM` AMR calls**. It should
produce approximately none: the ZymoBIOMICS organisms are wild-type laboratory strains.

Three of those were genuine misclassifications, corrected on biology alone:

| Group | Was | Now | Why |
|---|---|---|---|
| Class C β-lactamases (`AMPC`, `PDC`, `BLAEC`) | acquired | **intrinsic** | AmpC is chromosomal in Enterobacteriaceae and *Pseudomonas*; plasmid AmpC is the exception |
| `RLMH` | acquired | **core_essential** | RlmH is a housekeeping 23S methyltransferase; MEGARes files it under the same mechanism string as *erm* |
| `FOSX`, `CRPP` | acquired | **intrinsic** | chromosomal in *L. monocytogenes* and *P. aeruginosa* respectively |

That took 15 → **9**. The remaining nine — `APH3-PRIME`, `AAC3`, `CAT`, `MPHB`, `DFRE`,
`AAC6-PRIME`, `OXA`, `FOSA`, `LIN` — are all genes that are **chromosomal in one of the ten Zymo
organisms and acquired in others**. *aac(6')-Ii* is intrinsic in *E. faecalis*; *fosA* is intrinsic
in *P. aeruginosa*; the *lsa/lin* family is intrinsic in enterococci.

**I stopped here deliberately.** Reclassifying them would make the standard score better and the
engine worse, because in a clinical isolate those same genes *are* acquired resistance. The
distinction is not a property of the gene — it is a property of the gene's host, and the engine has
no host. This is D2, now quantified: **nine false-positive `CONFIRM` calls on a certified-clean
sample, none of them fixable by any rule.**

The operational consequence is concrete. `CONFIRM` means *"culture this"*, and on a clean sample it
fires nine times. **Do not read AMR `CONFIRM` counts as a resistance burden.** They are a list of
genes worth asking a laboratory about, and the laboratory answers by identifying the host.

### D4 — the cross-sample enrichment gate is inert on replicate designs — now stated, not silent

Gate 8 asks whether a taxon is enriched ≥5× relative to the other samples. Five replicates of one
community means nothing is enriched, so **no non-threat taxon is reported at all** — including the
ten organisms we know are there. The same applies to a single novel sample: with nothing to compare
against, the fold-change is undefined and the gate would have waved everything through.

`triage.run()` now detects this (`comparators=False` when fewer than two samples, overridable) and
prints:

> `[gate 8] single sample - cross-sample enrichment is inert; non-threat taxa are reported on read
> count alone and are NOT shown to be site-specific.`

In that mode the kitome genus list becomes the only contamination filter, and every non-threat row
carries *"no comparator samples — reported on read count alone, NOT shown to be site-specific"*.
Threat-list gating is unaffected: it never depended on cross-sample context. The gate is still
inert on replicates — but it now says so instead of failing quietly.

### D5 — Real Read badly under-counts organisms that have close relatives

This qualifies the project's own rule (`README.md`, "Judge on Real Read, not Abundance"). Against
known truth, on ZymoBac_6ng:

| | MAE vs theoretical |
|---|---|
| Judging on **Real Read** | **4.12 pp** |
| Judging on **Bracken Abundance** | **1.02 pp** |

*P. aeruginosa* has 335,540 species-specific reads — **1.55%** of the library against a true 12%.
*E. coli* has 395,160 — **1.83%** against a true 12%. Both are surrounded by close relatives in the
database, so the classifier assigns most of their reads above species level and Real Read collapses.
Bracken redistribution recovers them to 10.93% and 8.98%.

Both rules are true in their own regime and the README should say so:

- **Trace taxa** — Bracken *inflates*. WBM174 *S. agalactiae*: 29 real reads → 8,301 estimated.
  Judge on Real Read.
- **Abundant taxa with close relatives** — Real Read *deflates*, by up to 8×. Judge on Bracken.

The discriminator is the presence of congeners in the sample, not the metric itself.

---

## Verdict

Sensitivity, specificity and quantitation all pass, on a certified standard, at five inputs. The
marker gate correctly refused to escalate two abundant Category B organisms. That is a real result
and it is the strongest evidence so far that the gate cascade is sound.

The five defects are all diagnosable, and four are fixable in the rule file. D2 is not fixable —
it is the host-attribution gap again, and a clean standard simply makes it legible.

Priority order: **D1** (false positive on a threat list — fix first), **D5** (documented rule is
wrong in one regime), **D3** (over-claimed coverage), **D4** (silent no-op), **D2** (record as a
known limit, do not attempt to fix).
