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

The appliance reaches CWL through `wdl_script/miniwdl/tools/wdlAcwlTransformer.py`, which parses
WDL with miniwdl and converts it. **Submitting the Create Task form runs that transformer too** —
if it fails, the component is never created and simply does not appear in the PIPELINE COMPONENT
list, with no error shown in the UI. See
[When the component does not appear](#when-the-component-does-not-appear).

Two consequences:

1. **[`wdl/triage.wdl`](../wdl/triage.wdl) is not what runs on ZTRON.** It stays in the repo for
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
| **Command** | `triage --html` | See below. Keep it to the program and fixed flags — pass paths as Inputs |
| **Category** / **Tag** | `metagenomics` / `triage` | Free text, for the component search box |
| **Compute Resource** | **1 CPU, 2 GB** | Measured: 80 MB peak RSS and 0.54 s wall for a five-sample batch. It parses HTML and applies rules — there is no alignment and no database |

**Command — `triage --html`**

- `triage` is a wrapper on `PATH` inside the image. The image sets **no `ENTRYPOINT`** deliberately
  (a Python entrypoint breaks WDL engines the same way it would confuse CWL's command assembly).
- `--html` adds the self-contained evidence report.
- **`--outdir` is an Input, not part of Command** — see the table below. It has to be `.`, the
  task's working directory, because that is what CWL collects outputs from; anything written
  elsewhere in the container is discarded when the task ends. Keeping it in the Inputs table means
  every generated argument is spaced by the platform, and nothing abuts the fixed Command text.

The platform appends the Inputs to the Command, exactly as the manual's Samtools example shows
(`Samtools view` becoming `Samtools view -b … -o … `).

### Check the generated command line before you submit

The form previews the line it will build, using placeholder values (`/path/to/report_1.ext`). Read
it. It should be spaced:

```
triage --html --outdir=. /path/to/report_1.ext /path/to/report_2.ext --independent
```

If arguments run together — `--outdir=./path/to/report_1.ext/path/to/report_2.ext--independent` —
the **Position** values are the thing to check first; give every input its own, and leave nothing
in Command but the program and its fixed flags. Temporarily setting Command to `echo` previews the
argument list on its own, which isolates the Inputs table from anything Command contributes.

## 3. Inputs — one File item per report

**CWL's type list here has no array type** — the manual offers File, string, int, float, boolean,
enum. So each report is its own input item. Add as many as your largest batch:

| ID | Type | Required | Include in the command line | Prefix | Position |
|---|---|---|---|---|---|
| `outdir` | string | on | on | `--outdir=` | 0 |
| `report_1` | File | **on** | on | *(blank)* | 1 |
| `report_2` | File | off | on | *(blank)* | 2 |
| `report_3` | File | off | on | *(blank)* | 3 |
| `report_4` | File | off | on | *(blank)* | 4 |
| `report_5` | File | off | on | *(blank)* | 5 |
| `independent` | boolean | off | on | `--independent` | 9 |

- **`outdir` is a string with Default `.`** Leave **Separate value and prefix** however you like:
  the engine accepts `--outdir=.`, `--outdir= .` and `--outdir .` alike, so neither the toggle nor
  a trailing `=` in the prefix can break it. All three are covered by `--selftest`, which the image
  build runs. Give every input a distinct Position.
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

### Wiring the PFI app to this component

The input ports are **hidden until you show them**. Click the node, **View**, the **Input** tab,
the **FILES** section, and switch each `report_N` to display state; only Required inputs (the
asterisked ones) get a port automatically. A node showing outputs but no input dot is this, not a
broken component.

An upstream app hands you its whole output slot, not the one file inside it. ZTRON's PFI app exposes
`STDOUT`, `STDERR` and `Results`; `Results` is a directory, which will not drop onto a `File` input.
So **a report argument may also be a directory** — the engine takes every `*_en.html` in it, sorted,
falling back to any `*.html`.

**A single PFI run already batches its samples**, which makes this one wire. A five-sample run
produces one `Result/` holding every report:

```
.../mps.result/Result/
  WBM156_en.html  WBM156_cn.html  WBM156.tar.gz  WBM156/
  WBM174_en.html  WBM174_cn.html  WBM174.tar.gz  WBM174/
  …
```

Connect `Results` to `report_1` and stop. The `_en.html` files are picked up in sorted order; the
`_cn.html` translations, the per-sample subdirectories and the tarballs are ignored — matching
`*_en.html` first is what keeps each sample from being read twice, once per language.

That also satisfies gate 8 for free: all five reports enter one process, so the cross-sample
comparison is live. **No CWL scatter, and no second htx_triage node.** `report_2`…`report_5` exist
for the case where reports arrive as separate files from separate upstream nodes; leave them empty
here.

Verified against this exact layout: five reports in, five TSVs and one report out, verdicts
`MONITOR`, `NO ACTION`, `NO ACTION`, `INVESTIGATE`, `INVESTIGATE` — identical to running the five
files by name.

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

## When the component does not appear

A submitted task that never shows up in *Pipeline Component* is an appliance fault, not a fault in
the form. Check the platform log for a traceback ending:

```
File ".../miniwdl/tools/wdlAcwlTransformer.py", line 9, in <module>
...
ModuleNotFoundError: No module named 'regex._regex'
```

`regex` is a Python package with a compiled C extension, and the error means that extension cannot
be imported. It fails at **import** time, before any input is read, so no component definition,
container or command line can affect it.

```bash
ls /home/ztron/app_software/wdl_script/miniwdl/tools/venv/regex/
```

Look at the **interpreter tag** on the `.so`, not merely whether one exists. On the appliance seen
here the file was present as `_regex.cpython-310-x86_64-linux-gnu.so` — built for Python 3.10,
while the transformer runs Python 3.6, which will not load it. A `.so` for the wrong Python is as
unimportable as no `.so` at all, and reads as "installed" to anyone checking with `ls`.

The repair is to reinstall the package into that same directory with the interpreter the
transformer runs under:

```bash
python3 -m pip install --target /home/ztron/app_software/wdl_script/miniwdl/tools/venv \
  --upgrade --force-reinstall regex
```

Check the wheel pip reports: a `cp36` tag confirms it matched the transformer's interpreter (this
fix landed `regex-2023.8.8-cp36-cp36m-manylinux_2_17_x86_64`). A source build would need `gcc` and
`python3-devel`.

**Tell MGI support even though the workaround holds.** This is vendor software on a production
instrument: the next appliance update will overwrite the directory and the symptom returns, and a
Python-3.10 extension sitting in a Python-3.6 tool suggests other vendored packages may carry the
same mismatch.

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
