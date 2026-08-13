# Long-read stool samples — the run, and the five defects it exposed

> **Donor labels.** The four samples are `DonorA`-`DonorD`. Their lab specimen accession
> numbers are deliberately absent: this repository is public and those numbers identify human
> donors' samples. The mapping lives with the source data, not in git.

Four PFI long-read reports in `stool_sms/` (5,900–7,800 bp mean read length) were first put through
`analysis/triage.py` exactly as it stood, with no rule added and no threshold touched. That run is
the reason for everything below.

## The first run

It completed cleanly on all four: no crash, integrity gate reported the two structural NOTEs
correctly, all 25 RNA threat agents backfilled as `NOT_TESTED`, HTML built. The verdicts were
defensible. But five things were wrong, and two of them were under-calling clinically real genes.

| # | Defect | Fix |
|---|---|---|
| 1 | **Breadth stopped discriminating.** 55% of long-read AMR rows sat at ≥99% breadth against 7% of short-read rows — a 7 kb read spans a 1 kb gene end to end, so the 80% gate was free. | `long_read_thresholds`, breadth 80 → **95%** |
| 2 | **Depth under-called.** 28 acquired genes sat at ≥99% breadth with <5× depth and landed in `MONITOR` — `CTX`, `SHV`, `OXA`, `CBLA`, `ERMF`, `FOSA`, `AAC6-PRIME`. One unit of long-read depth is one whole molecule, not a thin pileup of 150 bp fragments. | depth 5 → **2×** (two spanning molecules; at Q10–13 one read cannot settle an allele) |
| 3 | **13 MEGARes groups had no rule** — `TETQ TETW TETO TETM TET32/40/44 TETX TMRB VANG VANTG VANWG VANYD`, 37 rows all defaulting to `MONITOR`. Coverage fell to 173/186. | 16 `mechanism_classes` entries: tetracycline ribosomal-protection and inactivation, the whole `Van*` glycopeptide family, tunicamycin |
| 4 | **Gate 8 does not fit unrelated donors.** Four stool donors are four gut communities, so "222× enriched" and "detected only in this sample" fired on ordinary inter-individual variation. | `--independent` flag |
| 5 | **Long-read QC fields were not read.** Read length, GC, Q20 and Q30 rendered blank — the report asked for `Read_Length`/`Raw_Q20`/`Raw_Q30`, the long-read report supplies `Mean_read_length`/`Q10`/`Q7`. | per-key fallback, label names the bin that supplied the number, plus a **Platform** row |

Threshold rationale is in [`reference_triage.md`](reference_triage.md#long_read_thresholds); the
platform gates move in opposite directions because breadth and depth mean different things on each
platform.

## The run that stands

```bash
python3 analysis/triage.py --independent \
  stool_sms/DonorA stool_sms/DonorC_18 stool_sms/DonorC_b17 stool_sms/DonorB

python3 analysis/triage.py --html --independent \
  --out=analysis/triage_report_stool_sms.html \
  stool_sms/DonorA stool_sms/DonorC_18 stool_sms/DonorC_b17 stool_sms/DonorB
```

Report: `analysis/triage_report_stool_sms.html` (443 KB, self-contained).
Per-sample TSVs: `analysis/triage_stool_sms_*.tsv`.

| Sample | Raw reads | Mean length | Classified | Verdict | Driver |
|---|---|---|---|---|---|
| DonorA | 147,178 | 6,678 bp | 38,911 (28.9%) | **INVESTIGATE** | CTX-M MEG_2430 100%/14.89× |
| DonorC_18 | 128,104 | 7,688 bp | 47,152 (39.5%) | MONITOR | 24 acquired CONFIRM |
| DonorC_b17 | 1,961,869 | 7,790 bp | 405,695 (22.3%) | MONITOR | 34 acquired CONFIRM |
| DonorB | 1,767,328 | 5,933 bp | 334,297 (20.9%) | MONITOR | *P. rettgeri*; 30 acquired CONFIRM |

**Rule coverage is now 100% on all four** (129/129, 140/140, 186/186, 178/178). CONFIRM counts rose
— 11 → 24, 22 → 34, 18 → 30 — which is the recalibration working: those genes were always full
length, the short-read depth gate was asking for evidence long reads do not produce.

The `INVESTIGATE` on DonorA rests on a full-length CTX-M at 14.89×: gut ESBL carriage, flagged and
correctly **not** attributed to an organism.

## Why CTX-M drove DonorA, and whose gene it is

**Why this gene and not the other eleven CONFIRMs.** Nothing to do with its depth. `sample_verdict()`
promotes a sample to `INVESTIGATE` for an acquired gene at `CONFIRM` only if the rule file marks the
group `high_consequence`. Three groups carry that flag — `MECA`, `CTX` and `MUPA` (added 2026-08-12) — because they are
the two that change clinical management on their own: CTX-M removes third-generation
cephalosporins, *mecA* removes the anti-staphylococcal β-lactams. `CFX` at 130× and `TETQ` at 41×
are higher-depth and lower-consequence; they land in the "24 acquired genes, none high-consequence"
line instead.

**Whose gene is it.** MEGARes has no organism column, so the engine never attributes — but the
arithmetic here is worth stating, because it rules candidates *out*. Three documented CTX-M host
genera are present in DonorA, and all three are trace:

| Candidate host | Real reads | Genome coverage at 6,678 bp | CTX-M depth ÷ that |
|---|---:|---:|---:|
| *Klebsiella pneumoniae* | 33 | 0.041× | **365×** |
| *Klebsiella quasipneumoniae* | 21 | 0.026× | **573×** |
| *Enterobacter kobei* | 12 | 0.017× | **892×** |

A single-copy chromosomal gene cannot sit at 14.89× while its host's genome sits at 0.04×. Even a
plasmid does not close a 365-fold gap — clinical ESBL plasmids are typically 1–5 copies per cell.
The comparison is depth-over-depth from one pipeline, so reference length cancels; only the genome
sizes are literature values.

The control is the other three samples, where the same ratio is **4–9×** — exactly what a
low-copy plasmid in the Enterobacteriaceae actually present would give:

| Sample | CTX-M depth | Enterobacteriaceae genome cov | Ratio |
|---|---:|---:|---:|
| DonorA | 14.89× | 0.083× | **179×** |
| DonorC_18 | 1.28× | 0.222× | 6× |
| DonorC_b17 | 3.67× | 0.423× | 9× |
| DonorB | 2.91× | 0.727× | 4× |

So DonorA is a genuine outlier, and the host is **not** any Enterobacteriaceae the report names.
The parsimonious explanation is not a novel species: it is that the host's reads are in the
**71.1% unclassified bin** — 95,773 reads ≈ 640 Mb, sixteen times more sequence than everything
classified — or were assigned above species rank, which this report does not expose (it carries
`speciesData` and `subspeciesData`, no genus table). CTX-M-15 is the commonest ESBL on earth; an
ordinary *E. coli* that Kraken2 could not place is far likelier than something new. Settling it
needs assembly to put CTX-M on a contig with a taxonomic marker, or culture.

## Gate 10 did not cover the threat list — now it covers 8 of the 12

Only 9 of the 46 threat-list agents had confirmatory markers. Of the 37 without, 25 are RNA and moot
on a DNA run, but **12 were DNA genomes this assay can see and had no marker**. Eight now do, and
the remaining four are documented as unmarkable rather than left silent. Full table and rationale:
[`reference_triage.md`](reference_triage.md#marker_patterns--24-regexes).

**They are one-way.** A new `supporting_markers` field escalates when the gene is present and
changes nothing when it is absent. The asymmetry is deliberate: VFDB coverage for *Brucella* or
*Coxiella* cannot be certified from the report, and a two-way gate would then let the engine
silently downgrade a real Category B detection to `NO_ACTION` on a marker that was never in the
database to find. A one-way gate can only add evidence.

**Searches are now genus-restricted**, matched against the VFDB row's reference strain. Run
unrestricted over the nine reports in this repo, the ten new patterns produce **23 spurious
matches** — `tviB` on *Acinetobacter* and *Pseudomonas* strains would have escalated *S. enterica*
in WBM232 and on the clean Zymo standard; *S. aureus* carries its own `esxA`/`esxB`, which would
have escalated *M. tuberculosis* on a certified-clean standard. With the restriction: **zero**.

**One marker was tried and removed.** `spv` fired on the Zymo standard's *Salmonella*. It was not a
bug — the virulence plasmid really is in ordinary Typhimurium — but it answers "does this
*Salmonella* carry pSLT", not "is this a notifiable serovar". `tvi` (Vi capsule) answers the
question `subspecies_required` actually poses, and a hit lifts the `MONITOR` serovar cap to
`ESCALATE`. Zymo's *S. enterica* row now reads: Vi capsule searched in *Salmonella* rows, not found,
**and that is not an exclusion**.

The 24 clinical-watchlist organisms still have no markers by design — they escalate on enrichment
plus co-located acquired resistance and cap at `CONFIRM`. Nothing of the kind exists, or is planned,
for the ~27,000 species in PFIDB.

## What did not change

Short-read behaviour is untouched — `detect_platform()` returns `short` for the HTX and Zymo sets,
so they never reach the override.

| Control | Before | After |
|---|---|---|
| HTX five verdicts | MONITOR MONITOR MONITOR INVESTIGATE INVESTIGATE | identical |
| Zymo sensitivity | 10/10 in every sample | 10/10 |
| Zymo specificity | zero ESCALATE | zero ESCALATE |
| Zymo false-positive CONFIRM | 9 | 9 |

`--selftest` gained assertions that the platform gates move in opposite directions, that a group
override still beats the platform override, that the same gene at 100%/2.4× is `CONFIRM` on long
reads and `MONITOR` on short, and that the five new mechanism strings resolve.

## Still true, and not fixable here

- **No gene is attributed to an organism.** A stool sample carrying a 30-gene mobile resistome says
  nothing about which commensal holds which gene. `CONFIRM` still means "ask a laboratory".
- **`--independent` costs you gate 8.** Non-threat taxa are then reported on read count alone and
  are explicitly *not* shown to be site-specific. That is the honest trade, not a free win.
- **Long-read basecall accuracy is the ceiling on 2×.** If a future batch runs at Q20+, the
  two-molecule floor is arguably conservative — but it should be moved on measured accuracy, not on
  a hunch.

## Related

- [`reference_triage.md`](reference_triage.md) — thresholds, flags, rule-file schema
- [`howto_triage_new_sample.md`](howto_triage_new_sample.md) — when to pass `--independent`
- [`zymo_validation.md`](zymo_validation.md) — the short-read ground truth
