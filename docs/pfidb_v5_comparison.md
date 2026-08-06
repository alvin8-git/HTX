# PFIDB v5.0 vs the kingdom-split lists — and what the rule file should join on

Two reference lists now sit in `PFI_DB/`. They are not two copies of the same thing, and the
difference decides how `triage_rules.json` should be keyed.

| | `PFIDB_v5_0.xlsx` | `list.<Kingdom>.xls` × 5 |
|---|---|---|
| Rows | 27,827 | **47,982** unique names |
| Columns | name, flag | **taxid**, name |
| Meta type | none | **in the filename** — Bacteria / Fungi / Metazoa / Protozoa / Viruses |
| Format | Excel, one sheet, no header | TSV (despite the `.xls` extension), no header |
| Dated | Mar 2025 | Sep 2025 |
| Flag column | `Y` on all 27,827 rows — carries no information | — |

**Overlap is poorer than the row counts suggest.** Matching on the name string:
21,030 names are in both, **6,797 are in v5 only**, and **26,952 are in the kingdom lists only**.
A file six months newer that still drops 6,797 names is not a superset; the two were built from
different NCBI snapshots at different ranks.

| Kingdom | Names | Strain- or infraspecific-looking |
|---|---:|---:|
| Bacteria | 28,193 | 3,310 (12%) |
| Fungi | 9,594 | 28 (0%) |
| Metazoa | 134 | 0 |
| Protozoa | 586 | 14 (2%) |
| Viruses | 9,475 | 54 (1%) |

Three defects in the kingdom lists worth knowing before trusting a count:

- **`list.Protozoa.xls` is contaminated with plasmids** — `Plasmid NR79`, `Plasmid R387`,
  `Plasmid pAM77` and others. They are not protozoa and not organisms.
- **Bacteria carries strain rows** (`Mycobacteroides abscessus ATCC 19977`,
  `Mycobacteroides abscessus subsp. bolletii 1S-151-0930`). v5.0 is species-rank. A "how many
  species" comparison between the two files is not like-for-like.
- **Viruses uses 2024–25 ICTV binomials** — `Henipavirus nipahense`, `Orthomarburgvirus
  marburgense` — where v5.0 uses `Nipah henipavirus`, `Marburg marburgvirus`. Same organism,
  no shared string. Influenza A appears only at strain level
  (`Influenza A virus (A/Puerto Rico/8/1934(H1N1))`).

## The finding that matters: three WHO organisms could never fire

`triage.py:319` and `:338` look taxa up with `dict.get(name)` — **exact string match** against the
report's `Scientific Name`. Checked all 70 rule-file organisms against v5.0:

| Rule-file key | PFIDB v5.0 actually says | Consequence before the fix |
|---|---|---|
| `Candida auris` | `[Candida] auris` | **WHO critical priority fungus, silently invisible** |
| `Candida haemulonii` | `[Candida] haemulonis` | never fires (bracketed genus *and* `-is` ending) |
| `Mycobacterium abscessus` | `Mycobacteroides abscessus` | never fires (genus moved, Gupta 2018) |

All 46 threat-list agents matched. The failures were all in `clinical_watchlist`, and all three
are naming-vintage drift, not missing organisms — the database has them, under a name the rule
file did not use. This is the exact failure mode the project is built to avoid: a silent negative
that looks identical to a clean sample.

**Fixed** by adding the PFIDB spelling as an additional key alongside the clinical one, so either
name fires. `analysis/export_rules.py` now re-checks all 70 on every export and prints
`NO - name mismatch` in the *In PFIDB v5* column, so the next drift is caught by running the
exporter rather than by missing an outbreak.

## What the rule file should join on

The PFI report's `speciesData` rows carry **`Taxid`** and **`Type`** as well as
`Scientific Name` — `triage.py:323` already reads the taxid and passes it through to the output,
but nothing keys on it.

The kingdom lists supply exactly that missing column. **This is now done.** All 70 organisms
carry a `taxid`, and `triage.py:319` matches on it before falling back to the name:

```python
threat_ids = {v['taxid']: v for v in threat.values() if v.get('taxid')}
...
t = threat_ids.get(taxid) or threat.get(name)
```

Resolution used `PFI_DB/list.<Kingdom>.xls` for 54 of the 70 and NCBI E-utilities for the rest —
all viruses, where PFIDB v5.0 and the kingdom lists disagree on naming. Every remote hit was
verified against the record's own synonym list before being written, so nothing was guessed:
`Marburg marburgvirus` → `3052505` is accepted because the NCBI record for
`Orthomarburgvirus marburgense` lists that exact string as a synonym. Re-run with
`python3 analysis/resolve_taxids.py --write`.

`--selftest` now asserts that every entry has a taxid, that no two share one, and that a report
row reading `[Candida] auris` / `498019` reaches the watchlist rule.

**What taxid keying does not fix.** Two entries sit above species rank — `Influenza A virus`
(`11320`) and `Severe acute respiratory syndrome-related coronavirus` (`694009`). A SARS-CoV-2
row carries the child taxid `2697049` and matches neither. That was equally true of name matching;
the difference is that the rank is now written down. `near_neighbours` (gate 9) is still a list of
name strings — lower value, since a near-neighbour miss weakens a caveat rather than dropping an
agent.

## Related

- [`pfidb_cdc_coverage.md`](pfidb_cdc_coverage.md) — v5.0 against the CDC A/B/C list, and why
  species-level-only is the harder limit
- [`reference_rules.md`](reference_rules.md) — the generated species-and-marker reference
- [`reference_triage.md`](reference_triage.md) — thresholds, flags, rule-file schema
