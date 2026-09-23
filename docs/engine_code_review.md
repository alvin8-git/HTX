# Code review of the BTIE engine

Scope: `analysis/triage.py`, `analysis/sample_registry.py`, `analysis/triage_report.py`. Every
finding below was reproduced by running the code against the five pilot reports, not inferred from
reading. Documentation gaps are out of scope — see `docs/proposal_technical_verification.md`.

`--selftest` and `analysis/test_flagged_layer.py` both pass. None of these findings was caught by
either.

**Status: all nine findings are fixed** (`analysis/triage.py`), each with a regression assertion added to
`selftest()`, each mutation-tested: reverting a fix makes its assertion fail.

> **Finding 6 was worse than catalogued.** The write-up called the unanchored patterns latent. They were not: `pXO2` was matching `capA/B/C/dep-capD` from *Bacillus subtilis* and *B. licheniformis* in 6 of the 14 reports, and the surviving *B. anthracis*-referenced `capB` row sits at 2.73% breadth / 0.20x depth. The marker gate applied **no coverage threshold at all** - it fired on a row existing - while gate 4 already refused a resistance gene under 50% breadth. Three changes were needed, not one: anchor the patterns, match the species rather than the genus, and put a breadth floor on the gate that produces ESCALATE.

> **Deliverables are now stale.** Fix 4 adds 20 rows across the five swabs, so the shipped
> `WBM*_report.html` / `_report.json` and `HTX Phase 1 - APPENDIX - BTIE Sample Report.docx` no
> longer match what the engine produces. Sample verdicts are unchanged; only the evidence tables
> grow. Regenerate before these go out.

---

## 1. ~~HIGH~~ FIXED — the documented single-sample invocation crashes

`analysis/triage.py:1233`. The module docstring advertises:

    python3 analysis/triage.py WBM232          # one sample

From the repo root this raises `ValueError: WBM156/Classify.DNA.html: no globalData in report`, for
**every** sample. The directory-expansion rule fires before the bare-stem rule: `os.path.isdir('WBM156')`
is true because the PFI output directory sits beside the report, so the argument is expanded to
`WBM156/*.htm*` → `Classify.DNA.html`, which is a different page with no `globalData`.

`report_path()` already knows how to resolve a bare stem; it just never gets the chance. Resolve the
stem to `<stem>_en.html` **before** testing `isdir`, or only treat an argument as a directory when it
contains a path separator.

## 2. ~~HIGH~~ FIXED — the TSV path and the report path give different verdicts for the same swab

`analysis/triage.py:855` (`run`) builds its enrichment baseline from `loads_by_taxon(reports, classified)`
— the samples named on the command line, nothing else. Only `triage_report.build()` merges
`SR.cohort_loads()` from the registry. Reproduced:

| Entry point | WBM156 sample verdict |
|---|---|
| `python3 analysis/triage.py WBM156_en.html` | **NO ACTION** |
| registry-backed report (`analysis/WBM156_report.json`) | **MONITOR** |

This is exactly the flip `sample_registry.py`'s own docstring documents as the reason the registry
exists. The stdout path prints a `[gate 8] single sample` caveat, but it does not say a registry with
prior swabs exists and was not consulted, and the TSV carries no cohort field at all — so the
degraded answer is indistinguishable from the full one once the file leaves the terminal.

Either have `run()` consult the registry too, or make it refuse to emit a TSV when a non-empty
registry exists and `--independent` was not given.

## 3. ~~HIGH~~ FIXED — the registry joins on species name, not taxid

`analysis/sample_registry.py:157` (`loads_from_report`) stores `{Scientific Name: reads}`, and
`cohort_loads` / `triage.enrichment` look up by that string.

`triage.py:548` states the opposite doctrine for the rule base, and gives the reason:

> Taxid is the primary key. A name string is re-spelled every time a genus moves and the match is
> exact, so drift is a silent negative: *Candida auris* reaches this engine as `[Candida] auris` from
> PFIDB v5 and `Candidozyma auris` from current NCBI — three spellings, one number (498019).

The rule base obeys this; the persistence layer does not. The registry is the component designed to
accumulate ~618 samples across months and at least one PFI upgrade — precisely the horizon over
which names move. When a species is renamed, its entire history becomes unreachable and
`enrichment()` returns `inf`, which the report renders as **"detected only in this sample"** — the
strongest enrichment statement the engine can make, produced by a database upgrade.

Store `{taxid: reads}` with the name as a display label. This is a migration, not a patch: existing
`sample_registry.json` entries need a one-off name→taxid backfill.

## 4. ~~HIGH~~ FIXED — watchlist organisms under the read floor vanish from the report entirely

`analysis/triage.py:597`:

```python
w = w0
if w:
    if real < TH['min_real_reads']:
        continue                      # <- no row is emitted at all
```

A threat-list agent below the same floor gets an explicit `NO_ACTION` row carrying its read count and
reasoning (`triage.py:676`). A watchlist organism gets nothing: no row, no tier, no trace.

Measured across the five pilot swabs — **20 dropped detections**:

| Sample | Silently dropped (reads) |
|---|---|
| WBM156 | *A. baumannii* 36, *N. gonorrhoeae* 34, *M. abscessus* 28, *M. morganii* 29, *E. cloacae* 12 |
| WBM174 | *S. marcescens* 34, *E. hormaechei* 33, *E. faecium* 25, *M. morganii* 11 |
| WBM179 | *S. marcescens* 42, *M. morganii* 35, *H. influenzae* 26, *C. freundii* 25, *E. faecium* 16, *E. hormaechei* 14 |
| WBM185 | *E. faecium* 49, *H. influenzae* 36, *S. pneumoniae* 25, *C. freundii* 19, *P. mirabilis* 14 |

*Acinetobacter baumannii* is WHO critical priority and the organism the proposal names as its
flagship example; in WBM156 it is present at 36 reads and the report does not mention it. *E. faecium*
at 49 reads in WBM185 misses the floor by one read.

Dropping them from *escalation* is defensible — 36 reads cannot support a verdict. Dropping them from
the *page* is not, and it contradicts the engine's own stated principle at `triage.py:492`: *"Silence
is the failure mode this whole project exists to avoid."* Emit a `NO_ACTION` row with the read count
and the floor, exactly as the threat-list branch does.

## 5. ~~MEDIUM~~ FIXED — gate 9 near-neighbours are matched by name

`analysis/triage.py:686`: `if present.get(nb, 0) >= real`. All 40 `near_neighbours` entries are bare
strings joined against `Scientific Name`. Same drift exposure as finding 3, in the gate whose whole
job is to catch cross-mapping between organisms that get reclassified into each other — the rule base
already carries `Brucella anthropi` (renamed from *Ochrobactrum anthropi*) as a near neighbour. Give
near-neighbour entries taxids.

## 6. ~~MEDIUM~~ FIXED — unanchored marker patterns gate the ESCALATE verdict

12 of 24 entries in `marker_patterns` carry no `\b` anchor, and `marker_present()` regex-searches
`json.dumps(row)` — the whole row, including accessions and URLs. Measured against the pilot VFDB
tables:

- `pXO2` = `(cap[ABCDE]|acpA|pXO2)` matches **`capA` in *Staphylococcus aureus*** (WBM185)
- `pXO1` = `(pag|lef|cya|pXO1)` matches **`spaG`** in *C. diphtheriae* and **`upaG/ehaG`** in *E. coli*

Only the genus filter added for the Coxiella `icmF`/`tssM` case stops these from firing. Nothing
currently misfires — I tested `marker_present('pXO1'|'pXO2', 'Bacillus anthracis')` against every
Bacillus row in all five samples and both return False — so this is latent, not a live defect. But
`pXO1`/`pXO2` are the markers that take *B. anthracis* to **ESCALATE**, the engine's highest verdict,
and a three-letter unanchored alternation is one database revision away from a false anthrax
escalation. Anchor them, and match against the gene/factor fields rather than the serialised row.

## 7. ~~MEDIUM~~ FIXED — a defensive branch silently discards all gene evidence

`analysis/triage.py:552`: `genes = list(genes) if not isinstance(genes, set) else []`

If a caller passes a set, every gene is dropped and the sample is triaged as though no resistance
gene existed — no error, no warning. There is no code path that passes a set; the guard protects
against something that cannot happen while creating a silent-wrong-answer mode. Delete it, or
`raise TypeError`.

## 8. ~~LOW/MEDIUM~~ FIXED — two host-pool candidate tests disagree

`watchlist_escalation` (`triage.py:434`) matches candidate hosts with `n.startswith(t + ' ') or n == t`.
`genus_amr_context` (`triage.py:466`) omits the `n == t` arm. A genus-level row (`Acinetobacter` with
no species epithet) therefore counts as a host for escalation but is invisible to the ranked pool
shown to the analyst, and its `self_rank` comes back `None` — which in `sample_verdict` means it can
never be the `led` organism. Two functions answering the same question should not disagree.

## 9. ~~LOW~~ FIXED — `unique_fraction` denominator is off by one

`triage.py:175`: `n` is incremented, then the loop breaks before `seen.add()`, so the denominator is
`unique_probe_reads + 1` over at most `unique_probe_reads` sequences. Biases the fraction low by
1/40000. Cosmetic, noted only so it is not mistaken for a real signal later.

---

## Verified sound

- Two-pass registry ingest (`triage_report.py:1547`) genuinely removes run-order asymmetry — every
  member of a batch is judged against every other.
- `save()` writes via `os.replace` on a tempfile, so a crash cannot truncate the registry.
- `cohort_fp` includes per-sample sequencing depth, so a re-sequenced member correctly invalidates
  the baseline identity.
- Allele collapsing picks the best allele on both breadth and depth; `mecI`-without-`mecA`
  suppression and the `adeN`/`adeIJK` repressor pair behave as the assertions claim.
- `marker_power` correctly puts read length in the numerator and treats uniform coverage as the
  optimistic bound.
- NOT_TESTED is genuinely outside `TIERS`, so it cannot be compared or downgraded into NO_ACTION.
- The end-of-loop sweep emits a row for every RNA threat-list agent absent from the species table,
  so the RNA blind spot cannot collapse into silence.
