# How to triage a new metagenomic sample

Take a PFI report you have never seen before and get a ranked list of what deserves a human's
attention. Takes about a minute.

The end result is a tier per organism and per resistance gene, each carrying the rule and the
numbers that produced it, plus a TSV you can hand to someone else.

## Prerequisites

- **Python 3.7+.** Standard library only — no `pip install`, no reference database, no aligner.
- **The PFI HTML report**, `<sample>_en.html`. This is the single-page report with the embedded
  `globalData` object, not the `.xlsx` exports.
- Optional: the sample's `ExtractRead_DNA/` and `*.fq.gz` files. Without them two gates skip
  themselves and say so.

Check the engine is intact before trusting it on new data:

```bash
cd /data/alvin/HTX
python3 analysis/triage.py --selftest
```

```
selftest: all rule checks pass
```

## Steps

### 1. Put the report where the engine can find it

Sample names are stems relative to the repo root, and subdirectories work:

```bash
cp /path/to/NEWSAMPLE_en.html /data/alvin/HTX/
# or, to keep a batch together:
mkdir -p /data/alvin/HTX/batch7 && cp /path/to/*_en.html /data/alvin/HTX/batch7/
```

### 2. Run it

```bash
python3 analysis/triage.py NEWSAMPLE
```

For a batch, name every sample in one command. **This matters**: the cross-sample enrichment gate
is what separates a site-specific finding from ordinary background, and it needs at least two
samples to work.

```bash
python3 analysis/triage.py batch7/S1 batch7/S2 batch7/S3
```

### 3. Read the output top-down

```
====================================================================================
Zymo/ZymoBac_6ng   classified=38,367,696
====================================================================================
  [integrity] NOTE: no FASTQs delivered alongside this report - integrity and
              unique-read gates cannot run; verdicts rest on the report tables alone
  [integrity] NOTE: DNA-only run - RNA agents are untested, and no species can be
              called active (speciesActivity is empty by construction)

  -- TAXA ---------------------------------------------------------------------------
  MONITOR    B  Salmonella enterica       3,221,442  species-level identification only…
  NO_ACTION  B  Staphylococcus aureus     3,172,304  confirmatory marker(s) seb ABSENT…
  NO_ACTION  B  Shigella dysenteriae             16  near-neighbour Escherichia coli…

  -- AMR GENES ----------------------------------------------------------------------
  CONFIRM    APH3-PRIME   MEG_1060   100.00%   80.30x  x2  acquired, full length…
  MONITOR    MEXT         MEG_3933    99.14%   24.74x  x1  repressor of MEXE…
  suppressed: {'environmental': 143, 'efflux_ubiquitous': 75, 'point_mutation': 37, …}
  rule coverage: 316/316 MEGARes groups annotated; 0 need a rule:
```

Read it in this order:

1. **`[integrity]` lines.** If the read partition does not sum, or FASTQs are missing or empty,
   stop and fix the delivery before believing anything below.
2. **`ESCALATE`** — a threat-list agent with its confirmatory marker present. This is the only
   tier that asserts a biological threat. If it fires, escalate; do not re-derive it yourself.
3. **`CONFIRM`** — real and actionable. For AMR genes it is the terminal tier and it means
   *"ask a laboratory about this gene"*, **not** *"the sample is resistant"*.
4. **`NOT_TESTED`** — a threat-list agent this assay structurally cannot see. **Never read this as
   a negative.** A DNA library cannot detect an RNA virus; the test did not run.
5. **`MONITOR`** — worth knowing, not worth acting on today.
6. **`suppressed` and `rule coverage`.** `rule coverage` must read `N/N … 0 need a rule`. Anything
   else means MEGARes groups landed in the engine that no rule describes.

### 4. Read the TSV for the detail

```bash
column -t -s$'\t' analysis/triage_NEWSAMPLE.tsv | less -S
```

Every row carries `reason` (the rule that fired) and, for AMR, `note` (what the gene actually is).
Nothing is dropped silently — rows suppressed from stdout are all present here.

## Verification

Run the known-truth control and confirm it still passes:

```bash
python3 analysis/validate_zymo.py
```

```
  sensitivity  10/10 organisms in every sample : PASS
  specificity  zero ESCALATE on a clean standard: PASS (0 escalations)
```

If either fails, the rules have drifted and no verdict on your new sample is trustworthy.

## Troubleshooting

**`ValueError: NEWSAMPLE: no globalData in report`**
The file is not a PFI single-page report, or it is a template with an unfilled
`<%= GLOBAL_DATA %>` placeholder. Confirm with `grep -c 'globalData:' NEWSAMPLE_en.html` — it must
print `1`.

**`[gate 8] single sample - cross-sample enrichment is inert`**
Working as designed, not an error. With one sample no fold-change exists, so non-threat taxa are
reported on read count alone and cannot be shown to be site-specific. Pass the whole batch in one
command to get the gate back.

**Every non-threat taxon is missing, on a batch that ran fine**
Your samples are replicates of one community, so nothing is enriched relative to anything.
Re-run with the gate off:

```bash
python3 -c "import sys; sys.path.insert(0,'analysis'); import triage; \
            triage.run(['batch7/S1','batch7/S2'], comparators=False)"
```

**`rule coverage: … N need a rule`**
A MEGARes group and mechanism the rule file has never seen. Those groups default to `MONITOR`, so
nothing is lost — but add the pair to `mechanism_classes` in `analysis/triage_rules.json`, keyed
`"Type|Mechanism"`. See [`reference_triage.md`](reference_triage.md#mechanism_classes--115-entries).

**A resistance gene you expected is `MONITOR`, not `CONFIRM`**
Check breadth and depth against the two routes: full length is ≥80%/≥5×, fragment is ≥55%/≥10×.
A gene below both is genuinely weak evidence. If the gene is clinically decisive and you can argue
the threshold, add a `group_thresholds` entry with its `why` field filled in.

**An organism you know is present does not appear**
Three gates can remove it: fewer than 50 real reads, a unique-read fraction below 15%
(amplification, not molecules), or enrichment below 5× against the other samples. The TSV records
which one fired.

## What this will not tell you

- **Whether anything is alive.** DNA comes off dry surfaces from live cells, dead cells and spores
  alike. The report's "active species" table needs an RNA library and is empty in every DNA run.
- **Which organism carries a resistance gene.** The AMR table never links gene to host, and
  assembly could not close the gap either. This costs nine false-positive `CONFIRM` calls on a
  certified-clean standard — see [`zymo_validation.md`](zymo_validation.md).
- **Whether a trace call is contamination.** Without a negative extraction control the
  contamination floor is asserted, not measured.

## Related

- [`reference_triage.md`](reference_triage.md) — every threshold, field and function
- [`automated_triage_design.md`](automated_triage_design.md) — why the gates are what they are
- [`zymo_validation.md`](zymo_validation.md) — measured accuracy and the five known defects
