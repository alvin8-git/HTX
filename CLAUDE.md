# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Biosurveillance analysis of five Singapore transport-hub surface swabs (PFI shotgun metagenomic
reports), plus a deterministic **triage engine** (`analysis/triage.py`) that turns one PFI report
into an auditable verdict. No LLM, no ML, no aligner, no reference DB. The engine and its
rule file are the product; the docs in `docs/` are the deliverable. Read `README.md` first and
`101_Documentation.md` for the long-form intro. `TODO.md` is the roadmap for the hosted system.

## Commands

All run from the repo root. The engine is **Python 3 stdlib only** — do not add pip
dependencies to anything the WDL/Docker path calls (`triage.py`, `sample_registry.py`,
`triage_report.py`, `pfi_folder.py`). `openpyxl`/`python-pptx` are allowed only in the
workstation reporting scripts (`extract.py`, `analyze.py`, `export_rules.py`, `build_deck.py`).

```bash
python3 analysis/triage.py --selftest           # rule/regression checks, no data needed — run after any engine or rules change
python3 analysis/test_flagged_layer.py          # second test file: flagged-species cover sheet properties (needs WBM*_en.html)
python3 analysis/validate_zymo.py               # engine vs ZymoBIOMICS known-truth standard (needs Zymo/)

python3 analysis/triage.py                      # all five HTX samples -> analysis/triage_<sample>.tsv
python3 analysis/triage.py WBM232               # one sample (still compared against the cohort registry)
python3 analysis/triage.py --html [WBM185 ...]  # -> analysis/triage_report.html evidence report
python3 analysis/triage.py --per-sample ...     # one standalone report per sample
python3 analysis/triage.py --cohort stool ...   # pick a registry: default / zymo / stool
python3 analysis/triage.py --independent        # no comparators at all (gate 8 degrades; see sample_registry.py docstring)
python3 analysis/triage.py --with-fastq         # extra FASTQ-only gates, outside the input contract
python3 analysis/triage.py --version            # prints engine version + rules fingerprint

python3 analysis/export_rules.py                # triage_rules.json -> docs/reference_rules.md + analysis/triage_rules.xlsx (generated, never hand-edit)
python3 analysis/extract.py WBM*_en.html        # HTML -> analysis/WBM<id>.json   (table-level analysis path)
python3 analysis/analyze.py                     # -> species_all.tsv, amr.tsv, vf.tsv
python3 analysis/build_deck.py                  # -> HTX_biosurveillance_briefing.pptx

docker build -t htx-triage:1.0.0 .              # build runs --selftest and fails on inconsistent rules
docker run --rm -v "$PWD:/data" htx-triage:1.0.0 triage --outdir=/data/out /data/WBM232_en.html
bash docs/img/render.sh                         # re-render docs/img/*.mmd -> .svg
```

There is no pytest/Makefile. "Tests" are `--selftest` (assertions inside `triage.py:selftest()`)
and `test_flagged_layer.py`. When you fix an engine defect, add a regression assertion to
`selftest()` and mutation-test it (revert the fix, confirm the assertion fails) — that is the
convention in `docs/engine_code_review.md`.

## Architecture

**Input contract.** The PFI HTML report (`WBM<id>_en.html`, a Vue SPA with data in an embedded
`globalData` JS object) is the whole input. Every verdict must be checkable against that page.
`pfi_folder.py` can build the same `globalData` dict from a PFI result folder's XLSX files
instead; both feed `triage.load_report()`.

**Gate cascade.** `triage.py` applies the numbered gates described in
`docs/automated_triage_design.md` (reference for every threshold: `docs/reference_triage.md`).
Two ladders: per-row tiers `NO_ACTION < MONITOR < CONFIRM < ESCALATE` (`TIERS`), and per-sample
verdicts `NO ACTION < MONITOR < INVESTIGATE < ESCALATE` (`SAMPLE_VERDICTS`, derived from the rows
by `sample_verdict()`). `NOT_TESTED` sits outside both (absence of evidence — this is a DNA-only assay, so RNA viruses are never "absent") and
must never be compared against or downgraded. Each output row carries the rule that produced it.

**Rules vs code.** `analysis/triage_rules.json` holds all thresholds and biology (threat list,
kitome genera, AMR classes, marker patterns, long-read thresholds, clinical watchlist, VF core
sets, AMR host hints). Change biology there, not in Python. `--version` prints a fingerprint of
this file so runs record which rules produced them. `docs/reference_rules.md` and
`triage_rules.xlsx` are generated from it by `export_rules.py`.

**Cohort registry (gate 8).** "Unusually abundant *here*" needs comparators. `sample_registry.py`
maintains one registry per cohort — `analysis/sample_registry.json` (field swabs),
`sample_registry_zymo.json`, `sample_registry_stool.json` — written by the pipeline, never by
hand, and tracked in git as durable state. `analysis/sample_metadata.tsv` is the hand-written
sidecar (site metadata; source of truth is `sampleInfo.xlsx`). A single-sample run is *not* the
batch run filtered to one sample: without comparators verdicts and row counts change.

**Evidence report.** `triage_report.py` renders the self-contained HTML (inlined CSS/JS, opens
from disk). It uses the BEC v1 evidence-code scheme (`[DSMPU][RL]<n>` / `U<n>`), deliberately
distinct from ACMG codes. AMR→host associations are literature hints rendered INFERRED and never
feed a verdict (MEGARes has no organism column).

**Import graph.** `triage` is the root; `sample_registry` and `triage_report` import it;
`build_deck`, `validate_zymo`, `test_flagged_layer` import `triage`. Scripts insert their own
directory on `sys.path`, so run them as `python3 analysis/<script>.py` from the repo root.

**Container/WDL.** `Dockerfile` installs a `triage` wrapper on PATH rather than an ENTRYPOINT
(a Python ENTRYPOINT breaks Cromwell/miniwdl) and sets no `USER`. `wdl/triage.wdl` wraps it.
See `docs/howto_run_containerized.md` before touching either.

## Data and files not in git

`WBM*/`, `*.fq.gz`, `WBM*_en.html`, `Zymo/`, `stool_sms/`, `assembly/`, generated
`analysis/*_report.html` and `triage_rules.xlsx` are gitignored (not ours to redistribute, or
rebuildable). A fresh clone runs `--selftest` and `--version` only. The `.docx`/`.pptx`/`.pdf`
proposal files at the root are working documents, not code; `HTX_biosurveillance_briefing_modifed.pptx`
is a read-only geometry reference.

## Docs conventions

Figures are Mermaid sources in `docs/img/*.mmd` rendered to SVG by `docs/img/render.sh`, pinned
with `<img width=...>` in markdown — never ASCII art. Markdown docs follow the Diátaxis split
(reference / explanation / how-to) in the README table; add new docs to that table.

# context-mode — MANDATORY routing rules

You have context-mode MCP tools available. These rules are NOT optional — they protect your context window from flooding. A single unrouted command can dump 56 KB into context and waste the entire session.

## BLOCKED commands — do NOT attempt these

### curl / wget — BLOCKED
Any Bash command containing `curl` or `wget` is intercepted and replaced with an error message. Do NOT retry.
Instead use:
- `ctx_fetch_and_index(url, source)` to fetch and index web pages
- `ctx_execute(language: "javascript", code: "const r = await fetch(...)")` to run HTTP calls in sandbox

### Inline HTTP — BLOCKED
Any Bash command containing `fetch('http`, `requests.get(`, `requests.post(`, `http.get(`, or `http.request(` is intercepted and replaced with an error message. Do NOT retry with Bash.
Instead use:
- `ctx_execute(language, code)` to run HTTP calls in sandbox — only stdout enters context

### WebFetch — BLOCKED
WebFetch calls are denied entirely. The URL is extracted and you are told to use `ctx_fetch_and_index` instead.
Instead use:
- `ctx_fetch_and_index(url, source)` then `ctx_search(queries)` to query the indexed content

## REDIRECTED tools — use sandbox equivalents

### Bash (>20 lines output)
Bash is ONLY for: `git`, `mkdir`, `rm`, `mv`, `cd`, `ls`, `npm install`, `pip install`, and other short-output commands.
For everything else, use:
- `ctx_batch_execute(commands, queries)` — run multiple commands + search in ONE call
- `ctx_execute(language: "shell", code: "...")` — run in sandbox, only stdout enters context

### Read (for analysis)
If you are reading a file to **Edit** it → Read is correct (Edit needs content in context).
If you are reading to **analyze, explore, or summarize** → use `ctx_execute_file(path, language, code)` instead. Only your printed summary enters context. The raw file content stays in the sandbox.

### Grep (large results)
Grep results can flood context. Use `ctx_execute(language: "shell", code: "grep ...")` to run searches in sandbox. Only your printed summary enters context.

## Tool selection hierarchy

1. **GATHER**: `ctx_batch_execute(commands, queries)` — Primary tool. Runs all commands, auto-indexes output, returns search results. ONE call replaces 30+ individual calls.
2. **FOLLOW-UP**: `ctx_search(queries: ["q1", "q2", ...])` — Query indexed content. Pass ALL questions as array in ONE call.
3. **PROCESSING**: `ctx_execute(language, code)` | `ctx_execute_file(path, language, code)` — Sandbox execution. Only stdout enters context.
4. **WEB**: `ctx_fetch_and_index(url, source)` then `ctx_search(queries)` — Fetch, chunk, index, query. Raw HTML never enters context.
5. **INDEX**: `ctx_index(content, source)` — Store content in FTS5 knowledge base for later search.

## Subagent routing

When spawning subagents (Agent/Task tool), the routing block is automatically injected into their prompt. Bash-type subagents are upgraded to general-purpose so they have access to MCP tools. You do NOT need to manually instruct subagents about context-mode.

## Output constraints

- Keep responses under 500 words.
- Write artifacts (code, configs, PRDs) to FILES — never return them as inline text. Return only: file path + 1-line description.
- When indexing content, use descriptive source labels so others can `ctx_search(source: "label")` later.

## ctx commands

| Command | Action |
|---------|--------|
| `ctx stats` | Call the `ctx_stats` MCP tool and display the full output verbatim |
| `ctx doctor` | Call the `ctx_doctor` MCP tool, run the returned shell command, display as checklist |
| `ctx upgrade` | Call the `ctx_upgrade` MCP tool, run the returned shell command, display as checklist |
