# Adding the triage engine to MGI ZTRON as a Custom Workflow component

Field-by-field mapping from this repo's container to the **Create Task** form in
*Analysis > Custom Workflow > Pipeline Component*, described in chapter 14 of the ZTRON PRO
user manual (H-020-000634-00, printed p.173-179).

## Read this first: ZTRON is CWL, not WDL

The manual never says so, but the Create Task form is a **CWL `CommandLineTool`** with a GUI on
top. The tell is the Expression Editor on printed p.177, which offers `$(inputs.input_1.path)`
and an inputs object carrying `class "File"`, `basename`, `nameroot`, `nameext`,
`secondaryFiles[]` — those are CWL's file object fields, verbatim. `Prefix`, `Position`,
`Separate value and prefix` and `Shell reference` are the GUI names for CWL's
`inputBinding.prefix`, `.position`, `.separate` and `shellQuote`.

Two consequences:

1. **[`wdl/triage.wdl`](../wdl/triage.wdl) is not used on ZTRON.** It stays in the repo for
   Cromwell and miniwdl. The container is the portable part; the workflow language is not.
2. **The platform generates ONE command line.** You do not write a shell script, so a component
   cannot chain two invocations. This is why `--html` was changed to emit the TSVs in the same run
   when `--outdir` is given — see [One component, all outputs](#one-component-all-outputs).

## 1. Pack the image as a tar

*Pkg Upload* wants "the tar package packed with Docker", i.e. the output of `docker save`:

```bash
docker build -t htx-triage:1.0.0 .
docker save htx-triage:1.0.0 -o htx_triage_1_0_0.tar      # ~118 MB
```

**Name the file with underscores only.** ZTRON's Pkg Upload rejects `htx-triage-1.0.0.tar` — it
validates the *filename*, and dots and hyphens outside the extension do not pass. The tar's name
carries no meaning to Docker; `docker load` reads the image tag from the manifest inside, so
renaming the file changes nothing about what gets loaded. Match the Task **Name** while you are
here, so the uploaded package and the component are obviously the same thing.

Verify the tar before uploading it — a corrupt or wrong-architecture layer will not be diagnosable
from the platform's task log:

```bash
docker rmi htx-triage:1.0.0
docker load -i htx_triage_1_0_0.tar
docker run --rm htx-triage:1.0.0 triage --version         # htx-triage 1.0.0  rules=257ef531791a
```

The image is still tagged `htx-triage:1.0.0` after loading — hyphens and dots are fine in a Docker
tag, which is why only the file needs renaming.

**Record the rules fingerprint with the component version.** The engine is stable; the rule file
is the part that moves, and a platform run that cannot name its rules cannot be reproduced.

## 2. Create Task

| Form field | Value | Why |
|---|---|---|
| **Name** | `htx_triage_1_0_0` | Cannot be all numbers. Encode the image tag — the component is a snapshot of one image |
| **Pkg Upload** | `htx-triage-1.0.0.tar` | From step 1 |
| **Command** | `triage --html --outdir=.` | See below |
| **Category** / **Tag** | `metagenomics` / `triage` | Free text, for the component search box |
| **Compute Resource** | **1 CPU, 2 GB** | Measured: 80 MB peak RSS and 0.54 s wall for a five-sample batch. It parses HTML and applies rules — there is no alignment and no database |

**Command — `triage --html --outdir=.`**

- `triage` is a wrapper on `PATH` inside the image. The image sets **no `ENTRYPOINT`** deliberately
  (a Python entrypoint breaks WDL engines the same way it would confuse CWL's command assembly).
- `--outdir=.` writes into the task's working directory, which is what CWL collects outputs from.
  Anything written elsewhere in the container is discarded when the task ends.
- `--html` adds the self-contained evidence report.

The report paths and inputs are appended by the platform from the Inputs table, exactly as the
manual's Samtools example shows (`Samtools view` becoming `Samtools view -b … -o … `).

## 3. Inputs — one File item per report

**CWL's type list here has no array type** — the manual offers File, string, int, float, boolean,
enum. So each report is its own input item. Add as many as your largest batch:

| ID | Type | Required | Include in the command line | Prefix | Position |
|---|---|---|---|---|---|
| `report_1` | File | **on** | on | *(blank)* | 1 |
| `report_2` | File | off | on | *(blank)* | 2 |
| `report_3` | File | off | on | *(blank)* | 3 |
| `report_4` | File | off | on | *(blank)* | 4 |
| `report_5` | File | off | on | *(blank)* | 5 |
| `independent` | boolean | off | on | `--independent` | 9 |

- **No prefix on the reports.** The engine takes them as positional arguments.
- **File Type**: `html`.
- Leave **Separate value and prefix** at its default; it is irrelevant with no prefix.
- Only `report_1` is Required, so the same component serves a one-sample and a five-sample run.
  Unfilled optional inputs are simply omitted from the command line.
- `independent` is a boolean whose prefix appears alone when true. Set it when the samples are
  **not** one batch from one site.

The generated command line becomes:

```
triage --html --outdir=. /path/stg1/WBM156_en.html /path/stg2/WBM232_en.html
```

which is the shape verified in this repo — reports staged in separate directories, outputs in the
working directory.

### Why all reports go to ONE component instance

Gate 8 divides a taxon's depth-normalised load by the highest load among *the other samples in the
same run*. That comparison is what separates a site-specific finding from ordinary background, and
it needs every report inside one process.

Wiring five single-report components in parallel on the workflow canvas will run, produce output,
and **silently discard the comparison** — every non-threat row comes back tagged *"NOT shown to be
site-specific"*. There is no error. Connect all reports to one node.

## 4. Outputs

| ID | Type | Required | Expression | File Type |
|---|---|---|---|---|
| `triage_report` | File | on | `triage_report.html` | `html` |
| `results` | File | off | `./` | |

The manual's own advice (printed p.177): outputs that feed downstream steps and need no separate
directory are collected with `./` in the Expression field. That picks up the per-sample
`triage_<sample>.tsv` files, whose count varies with how many report inputs were filled.

`triage_report` is named explicitly and marked Required so a task that produces no report **fails**
rather than reporting success with nothing in it.

## One component, all outputs

`triage --outdir=<dir>` writes TSVs; `triage --html` writes the report. A WDL task can call both
because it writes a shell script. A CWL component gets one command line.

So `--html` now **also emits the TSVs when `--outdir` is given** — one invocation, every output.
Interactive use in the repo (`--html --out=page.html`) is unchanged and still writes only the page.

## Enabling and wiring

After Submit, the component appears in *Pipeline Component* in **Off** state. Click the enable
arrow before it can be used (manual, printed p.179). To edit it later, disable it first.

Then *Workflow Management > Add*, drag the component from the **PIPELINE COMPONENT** column of the
right-hand panel onto the canvas, and drag out its input port to attach the report files. The red
dot marks the required input — `report_1` — and the workflow will not advance until it is
connected.

## What this component does not do

It reads a **PFI HTML report**, not FASTQ and not BAM. It is an interpretation step that belongs
*after* the PFI pipeline in a workflow, consuming that pipeline's HTML output. It has no reference
genome, so the *Reference Genome Management* configuration in chapter 13 does not apply to it.

Verdicts are triage tiers, never diagnoses — see
[`reference_triage.md`](reference_triage.md) for what each tier means and what the HTML-only input
contract can and cannot see.
