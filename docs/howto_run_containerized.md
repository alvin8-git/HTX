# How to run the triage engine in a container, and as a WDL task

Take a PFI HTML report on any machine with Docker and get the same verdicts this repo produces,
without installing Python packages, cloning the repo, or having the rules to hand. The image
carries the engine and the rule file; reports arrive as mounted inputs.

The end result is a TSV per sample plus a self-contained HTML evidence report, byte-identical to
a host run of the same reports.

## Prerequisites

- **Docker** (or Podman, or any OCI runtime). Nothing else — no Python, no `pip install`, no
  reference database, no aligner, no network at run time.
- **The PFI HTML reports**, `<sample>_en.html`.

## Build

```bash
cd /data/alvin/HTX
docker build -t htx-triage:1.0.0 .
```

~120 MB, built on `python:3.12-slim`, and **the build installs nothing** — the engine is Python
standard library only, so there is no `pip install` layer and no network fetch. It builds on an
air-gapped host once the base image is present.

**The build runs `--selftest` and fails if the rules are inconsistent** — an image that ships
broken rules is worse than no image, because a workflow will run it and produce verdicts anyway.

### Building on an old host (CentOS 7 and similar)

Building on CentOS 7 with the legacy (pre-BuildKit) builder used to fail here:

```
RuntimeError: can't start new thread
The command '/bin/sh -c pip install ...' returned a non-zero code: 2
```

That is not a Python or a pip fault. CentOS 7 ships a Docker whose seccomp profile predates the
`clone3` syscall; Debian bookworm's glibc uses `clone3` for `pthread_create`, so the call is
denied and any thread creation fails. pip's progress bar runs on a thread, so pip died first.

**The build no longer installs anything, so this cannot happen** — `triage.py` never spawns a
thread. If you hit `clone3` denials elsewhere on such a host, the general fix is
`--security-opt seccomp=unconfined`, or upgrading Docker to 20.10.10+.

The image carries `analysis/` only. No sample data, no reports, nothing site- or
patient-identifying, so it is safe to push to a registry.

## Run it directly

```bash
# rules and engine are intact
docker run --rm htx-triage:1.0.0 triage --selftest

# which rules am I about to use?
docker run --rm htx-triage:1.0.0 triage --version
# htx-triage 1.0.0  rules=257ef531791a

# a batch, reports mounted from the host
docker run --rm -v "$PWD:/data" htx-triage:1.0.0 \
  triage --outdir=/data/out /data/WBM156_en.html /data/WBM232_en.html

# the evidence report as well
docker run --rm -v "$PWD:/data" htx-triage:1.0.0 \
  triage --html --out=/data/out/evidence.html /data/WBM156_en.html /data/WBM232_en.html
```

`triage` is on `PATH` inside the image. **There is deliberately no `ENTRYPOINT`** — see
[Two container gotchas](#two-container-gotchas-both-hit-during-this-work).

## Run it as a WDL task

[`wdl/triage.wdl`](../wdl/triage.wdl) wraps the same container. Validate and run:

```bash
miniwdl check wdl/triage.wdl

miniwdl run wdl/triage.wdl \
  reports=/path/WBM156_en.html reports=/path/WBM174_en.html \
  reports=/path/WBM179_en.html reports=/path/WBM185_en.html \
  reports=/path/WBM232_en.html \
  batch_name=htx_2026_08
```

or with Cromwell:

```bash
java -jar cromwell.jar run wdl/triage.wdl -i wdl/inputs.example.json
```

| Workflow input | Default | Meaning |
|---|---|---|
| `reports` | — | `Array[File]`, one PFI HTML report per sample |
| `independent` | `false` | **Set true when the samples are not one batch from one site.** Turns gate 8 off |
| `html_report` | `true` | Also emit the self-contained evidence report |
| `batch_name` | `"batch"` | Prefix for the summary and evidence filenames |
| `docker` | `htx-triage:1.0.0` | Image tag; point at your registry copy |

| Output | What it is |
|---|---|
| `tsvs` | One per sample: the sample verdict, then a row per taxon and per AMR gene, each carrying the rule that produced it |
| `evidence` | The self-contained HTML report for the whole batch |
| `summary` | The engine's stdout — verdicts and the rows that drove them |
| `versions` | Engine version and rule-file fingerprint |

### Why the batch goes to ONE task, not one task per sample

Gate 8 (cross-sample enrichment) divides a taxon's depth-normalised load by the highest load among
the *other* samples. That comparison is what separates a site-specific finding from ordinary
background, and it needs every report in the same process. Fanning a batch out across parallel
`TriageOne` tasks would run, produce output, and silently discard the comparison — every non-threat
row would come back tagged *"NOT shown to be site-specific"*.

`TriageOne` exists for the genuinely-one-sample case. It is not a parallelisation strategy.

### Always record which rules ran

`versions.txt` carries the engine version and a SHA-256 prefix of `triage_rules.json`. The engine
is stable; **the rule file is the part that moves**, and a run that cannot name its rules cannot be
reproduced. Keep it with the outputs.

### Call-caching is safe

The task is deterministic and side-effect free: same report in, same verdicts out, forever. No
network, no clock, no randomness. Enable call-caching without reservation.

## Two container gotchas, both hit during this work

Recording these because each cost real time and neither produces a useful error message.

**1. A Python `ENTRYPOINT` breaks every WDL engine.** Cromwell and miniwdl run `/bin/bash <script>`
as the container *command*, and Docker appends that to the entrypoint — yielding
`python3 triage.py /bin/bash script`. The symptom is **exit 2 with a completely empty stderr**.
The fix is a wrapper on `PATH` (`/usr/local/bin/triage`) and no `ENTRYPOINT`, which also keeps the
interactive `docker run … triage --selftest` usage working.

**2. Never hardcode `USER` in an image a workflow engine will run.** The right uid is the engine's
business and it breaks in both directions:

- **rootless Docker** maps the invoking host user to container root, so a hardcoded non-root
  `USER 1000` cannot write to its own mounted work directory;
- a **rootful** daemon running as container root writes host files the user cannot delete.

Symptom is again exit 2 and empty stderr — what a permission-denied `mkdir` looks like under
`set -e`. Every engine already has a uid policy (Cromwell runs as root, miniwdl passes `--user`
and takes `--no-outside-user` to opt out), so a portable image states no preference.

### One host-environment note

Under **rootless Docker**, miniwdl's post-run `chmod` of the task directory fails with
`PermissionError: Operation not permitted` *after the task has already succeeded with exit 0*.
That is miniwdl interacting with the daemon, not a fault in the image or the WDL. Work around it
with:

```bash
MINIWDL__FILE_IO__CHOWN=false miniwdl run wdl/triage.wdl …
```

Cromwell and rootful daemons are unaffected.

## Verification

The container must reproduce a host run exactly. This was checked, not assumed:

```bash
python3 analysis/triage.py                    # host
docker run --rm -v "$PWD:/data" htx-triage:1.0.0 \
  triage --outdir=/data/out /data/WBM*_en.html  # container

for s in WBM156 WBM174 WBM179 WBM185 WBM232; do
  cmp analysis/triage_$s.tsv out/triage_$s.tsv && echo "$s identical"
done
```

All five TSVs are byte-identical, host and container, and identical again through the full WDL
workflow. Verdicts: `MONITOR`, `NO ACTION`, `NO ACTION`, `INVESTIGATE`, `INVESTIGATE`.

Getting there needed three portability fixes, each of which was a real bug for any caller outside
this repo:

- `load_report()` resolved a bare stem against the repo root, so a localised input path could not
  be read at all. It now takes a path directly (`report_path()`).
- TSVs were written to `<repo>/analysis/`, unreachable from a task container. `--outdir=` added.
- The sample-identifier column, the stdout header, the report's sample labels and its
  *"Reproduce this page offline"* command all recorded the **raw argument**. Under WDL that is
  `/mnt/…/_miniwdl_inputs/0/WBM185_en.html`, which is not a sample name and made the TSV
  unreadable outside the run that produced it. All four now use `sample_id()`.

## What is NOT in the image

`build_deck.py` (briefing deck) and `export_rules.py` (xlsx) are in the image but **will not run
there** — they need `python-pptx` and `openpyxl`, which are deliberately not installed. They are
reporting paths a human runs on a workstation, not pipeline steps, and the WDL never calls them;
run them on the host with `pip install openpyxl python-pptx`. Keeping them out of the image means
the build needs no network and no thread (see [Building on an old
host](#building-on-an-old-host-centos-7-and-similar)).
`annotate_contigs.py` needs `abricate`, `megahit` and `bwa-mem2` and is
**outside the engine's input contract** entirely (see
[`reference_triage.md`](reference_triage.md#what-the-report-cannot-carry)); it is not containerised
here.
