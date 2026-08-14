# Proposal scope — answers to points 1–5

Written against what `analysis/triage.py` + `analysis/triage_rules.json` actually do today, so every
claim below can be checked against a run. Where a capability does not exist yet it is labelled as
such rather than described as if it did.

The rule of the document: **state the confidence, and state what would raise it.** A limit that is
written down can be designed around; a limit that is not gets mistaken for a clean result.

> **Every worked example below has been re-run against the current engine**, and the sample IDs,
> read counts and fold-changes quoted are the engine's own output. Two examples that circulated in
> earlier drafts were wrong and are corrected here — see [3a](#the-example-to-use-and-the-one-to-drop)
> and [4a](#a-risk-scoring--there-are-two-ladders-not-one). Anything a reviewer can check, assume
> they will.

---

## 1. Instrument connectivity — open with OmicsNest

Not answerable from this repository: whether the MiSeq can expose its run output over NFS, or
whether rsync from the instrument's output directory is the supported path, is a question for the
OmicsNest team and Illumina. Manual sample entry is accepted as unavoidable where two platforms meet.

**One thing to settle before the interface is built, not after:** the manual sample-entry step is
where sample-ID provenance breaks, and this engine keys everything — TSV rows, report labels, the
reproduce-offline command — off the PFI report filename. Agree a sample naming convention up front
and enforce it at entry. A batch whose IDs do not round-trip cannot be re-analysed later, and
longitudinal anomaly detection (§4b) is impossible without stable site identifiers.

---

## 2. Data type — RNA libraries

**Recommendation: yes, and it is the single largest coverage gain available. Paired DNA + RNA per
sample.**

### Why it matters more than it looks

The threat list holds 46 CDC agents: **21 DNA genomes and 25 RNA genomes**. Every PFI report seen so
far carries `showRNA = False`, so gate 2 (assay detectability) stamps all 25 RNA agents
`NOT_TESTED` — before the read-count gate, deliberately, so that zero reads for an RNA agent can
never be mistaken for a negative.

> **More than half the CDC agent list is currently not tested at all.** The engine says so on every
> run; it is not a silent gap. But it is a gap that only an RNA library closes.

Every viral haemorrhagic fever agent, every encephalitis virus, influenza and the SARS-related
coronaviruses sit in that 25. A DNA-only biosurveillance stream cannot see them.

> **Say "CDC", not "CDC/WHO".** All 25 RNA agents come from the CDC Category A/B/C threat list. The
> WHO Bacterial Priority Pathogens List / ESKAPE watchlist contributes **24 organisms, all
> bacterial, and therefore zero RNA agents**. The precise sentence is: *25 of the 46 CDC Category
> A/B/C agents are currently `NOT_TESTED` because the assay is DNA-only.*

### Second gain: viability

DNA reads cannot distinguish a live organism from dead cells, environmental DNA, or a reagent
contaminant. The standing entry in "Known limits" is *Viability / active species — needs RNA*. An
RNA run populates PFI's `speciesActivity` field and gives the rules an **activity axis** they do not
currently have: a taxon detected in DNA and transcriptionally active in RNA is a materially
different finding from the same taxon in DNA alone.

This is what turns a detection into an assessment.

### What it costs

| Item | Note |
|---|---|
| Bench | Total RNA extraction + rRNA depletion (environmental/clinical swabs are ≥90% rRNA without it). Separate library prep, separate flow-cell capacity. |
| PFI run config | `showRNA` must be enabled on the PFI side — a run-configuration question for PFI, not an engine change. |
| Engine | Gate 2 flips from *inert* to *live* automatically. The **new** work is the activity axis: rules and verdict ladder need an "active vs present" term. Estimated small — the gate framework already exists. |
| Interpretation | RNA is fragile. A negative RNA result on a positive DNA result may mean *dead*, or may mean *degraded in transport*. Needs an RNA-integrity control per run or the axis is uninterpretable. |

**Ask PFI to confirm**: RNA library support in the current PFIDB v5 pipeline, what `speciesActivity`
contains, and whether AMR/VF calling runs on the RNA library or only DNA.

---

## 3. Analytical capabilities, with achievable confidence

> **Detail:** [`proposal_point3_detail.md`](proposal_point3_detail.md) — measured performance,
> per-agent detection limits, the attribution measurement, and the four-tier engineered-construct
> scope.

Three distinct capabilities with very different confidence ceilings. Grouping them under one
heading in a proposal invites a promise the third cannot keep.

| Capability | From the PFI report today | Achievable confidence | Ceiling set by |
|---|---|---|---|
| Virulence factors | **Implemented** — VFDB rows per species, 24 marker regexes | **High** for a defined panel; **low** as an open survey | VFDB coverage cannot be certified from the report |
| AMR / resistome — gene presence | **Implemented** — MEGARes, gates 3/4/5 | **Medium–high** above the breadth floor | Read-level calling, no genomic context |
| AMR — which organism carries it | Not possible | **Not achievable from sequence alone** | No field joins genes to taxa; assembly *also* failed on this batch |
| AMR — point mutations | Not possible | **Zero today** | Only gene *presence* is reported |
| Engineered constructs | **Nothing exists** | **Low, and tiered** — see below | Classification cannot see **adjacency**; the parts classify to their donors |
| Mutated constructs (point substitution) | Not possible | **Zero today** | Needs variant calling, not composition |

### 3a. Virulence factor assessment — highest confidence of the three

Already built and validated. VFDB rows are attributed to the species that owns them, with
accessions, and marker searches are **genus-restricted** — not cosmetic; without that restriction a
*Brucella* marker matched *Ochrobactrum* reagent contamination in all five HTX swabs.

The honesty mechanism is the **direction of inference**, and it should survive into the proposal:

- **`markers` — 9 agents, two-way.** The gene is unique to the agent and reliably in VFDB, so
  present → escalate *and* absent → downgrade. `pXO1`/`pXO2` (anthrax), `bont` (botulism),
  `caf1`/`lcrV`/`pla` (plague), `fopA`/`tul4` (tularaemia), `etx`, `seb`, `ctxA`/`ctxB`,
  `stx1`/`stx2`/`eae`.
- **`supporting_markers` — 8 agents, one-way.** VFDB coverage cannot be certified, so present →
  escalate, absent → **no change, and the row says so**. A miss must never read as a clear.
- **Four agents remain unmarkable** at all.

Gate 10a goes further: it only downgrades on a missing marker when the marker *could have been
seen* — marker bp against genome bp against read depth. Below that power, the verdict is
`NOT_TESTED`, not negative.

#### The example to use, and the one to drop

**Do not use the HTX *S. aureus* / `seb` example.** Since the gate 10a marker-power fix
(2026-08-12), *S. aureus* is **`NOT_TESTED` in all five HTX samples**, not downgraded. The engine's
own words for WBM174:

> `seb` NOT ASSESSABLE at this coverage — 1,444 reads over a 2.82 Mb genome gives a **39% chance**
> of a read landing on the 801 bp target, so absence carries no information. The marker reverts to
> ONE-WAY: present would still escalate.

At these read counts the absence of `seb` is the *expected* outcome whether or not the strain is
toxigenic, so calling it a downgrade overstates what was demonstrated. PFI can check this against
the TSVs.

**Use the Zymo standard instead.** It is a stronger example, because the organisms are present at
~13% abundance with millions of reads, so the markers genuinely had power, on a community certified
free of toxigenic strains:

| Organism | Reads | Verdict | Reason |
|---|---:|---|---|
| *E. coli* | 395,160 | `NO_ACTION` | `stx1`/`stx2`/`eae` absent — correctly not STEC/EPEC |
| *S. aureus* | 3,172,304 | `NO_ACTION` | `seb` absent — correctly not enterotoxin-B-producing |

That is a demonstrated downgrade at depth on a certified-negative sample — the capability itself,
not an artefact of coverage.

Two points of precision worth keeping in the wording: gate 10a acts on the **taxon row**, not the
sample; and `NOT_TESTED` **never rolls up** into a sample verdict.

**To raise confidence:** assembly + VFanalyzer on contigs gives gene completeness and context, which
converts one-way markers to two-way and shrinks the unmarkable four. That needs an assembly step
(see 3c). Deeper sequencing raises marker power directly — the per-agent read requirements are
tabulated in [`proposal_point3_detail.md`](proposal_point3_detail.md#313-the-confidence-ceiling-is-a-sequencing-depth-question-and-it-is-quantified).

### 3b. AMR / resistome profiling — good at presence, structurally blind to attribution

Implemented: MEGARes rows collapsed by group (gate 3, one real gene recruits reads onto several
accessions), a 50% breadth floor (gate 4, separates a real gene from a conserved fragment), and
class annotation over **116 group overrides + 132 mechanism classes** with per-class and per-group
thresholds (gate 5). 57 `amr_host_hints` groups provide candidate-host ranking **as an evidence
layer only**, under a standing banner that no gene is attributed to an organism.

Be explicit in the proposal about the four things it cannot do:

1. **Which organism carries the gene.** No field in the report joins `drugResistance.DNA` to
   `speciesData` — sample-wide by construction. Assembly + read mapping was *attempted on this
   batch* and still failed for `mecA` and CTX-M. Culture with AST is the answer. Forcing the
   attribution cost 9 false-positive `CONFIRM` calls on a clean reference standard.

   > **This is not only a short-read limitation.** The PFI report carries **no gene-to-taxon field
   > at all**, so the join is unavailable in principle regardless of read length — and when assembly
   > was run on this batch anyway, per-taxon mapping returned **0 reads at MAPQ ≥ 20** for both
   > genes. Long reads would improve the odds; they do not guarantee an answer. Culture **with AST**
   > is what settles it, and AST additionally gives the phenotype, which no sequence method does.
2. **Point-mutation resistance is invisible.** `gyrA`, `rpoB`, `lpxA` resistance is never reported,
   so its absence is never evidence of susceptibility. Needs variant calling at depth.
3. **Plasmid vs prophage vs chromosome** — no genomic context of any kind is reported. Mobility, the
   thing that actually matters for spread, is unmeasured.
4. **No contamination floor.** Thresholds are reasoned, not fitted, because there is no negative
   extraction control in the data set.

#### What we *can* say instead of attribution — the worked example

The engine ranks every documented host of a gene that is actually present in the sample, by read
count, and marks the taxon's own position. Verified against `analysis/triage_WBM174.tsv`:

> **WBM174, `APH3-DPRIME`** (aminoglycoside phosphotransferase, `CONFIRM`, 95.46% breadth / 6.59×).
> 73 documented host species are present, totalling 225,520 reads. *S. aureus* holds **1,444 reads
> = 0.64% of that pool, rank 15 of 73**. The pool is topped by *S. hominis* at 44.4%, then
> *S. epidermidis* 16.6% and *S. capitis* 11.9%.

So the gene is real and the sample carries it, but naming *S. aureus* as its host would be
arbitrary — it is one of seventy-three candidates and holds well under one percent. That is a
defensible, quantitative statement made **without** an attribution the data cannot support, and it
is exactly the reasoning a reviewer can check.

The same machinery drives the watchlist escalation bar: an organism must top its host pool or hold
≥20% of it. *A. baumannii* in WBM232 holds 21% and tops its pool, which is why that sample's finding
stands while *Serratia marcescens* at 1.3% of a CTX-M pool was correctly stopped.

**To raise confidence, in order of value per unit cost:** (i) a negative extraction control every
run — cheap, and it converts asserted thresholds into measured ones; (ii) long-read sequencing for
gene context and mobility — `long_read_thresholds` already exist in the rule file; (iii) culture +
AST on escalated samples, which is the only definitive answer and should be the defined endpoint of
an `ESCALATE` verdict.

### 3c. Engineered-construct / mutation signatures — scope this carefully

**There is no capability here today**, and the reason is structural rather than a missing feature.

#### Agreed wording

> **Engineered/mutated construct (PFI confidence: NO)** — not detectable *as engineered* by the
> current pipeline. We do not know what we do not know. Reads classify to whatever each part most
> resembles: the chassis to the chassis species, a moved virulence gene to its donor organism. What
> makes it engineered is the **adjacency** of those parts, and read-level taxonomic classification
> cannot see adjacency. Differentiating would need **long reads or assembly** to observe the
> junction, and **variant calling at depth** for the mutated case. Culture with WGS is the
> confirmatory route, since a pure isolate closes the genome and makes both unambiguous. All of
> these require the organism to be abundant enough to assemble or call — **none is
> surveillance-grade screening at trace abundance.**

#### Why classification cannot be fixed to solve this

An engineered organism is ~99.9% its parent, so it classifies as the parent. Better databases and
better classifiers make this **worse**, not better, because they assign the parent more confidently.

And a construct is not one organism's sequence — its parts classify **piecewise**. A `bont` gene
dropped into an *E. coli* chassis produces *E. coli* reads **and** a *C. botulinum* VFDB hit. Neither
read set is anomalous on its own. Only their co-occurrence is.

> **Correction to an earlier draft.** It is *not* true that an engineered construct is
> "by definition" in the unclassified bin. The scenario that should worry us most — a known gene in
> a known chassis — produces **no unclassified reads at all**, because every part is in the database.
> The unclassified fraction is where a *novel organism* hides, which is a different problem.

Two remedies for two different problems — they are not interchangeable:

| Problem | Signal | What finds it |
|---|---|---|
| **Engineered** — gene moved or inserted | **Adjacency** — parts adjacent that never co-occur naturally | **Long reads** (observe the junction in one molecule) or **assembly** (infer it). Deeper sequencing matters only insofar as it makes assembly possible |
| **Mutated** — point substitution | **A base change** at a known locus | **Variant calling at depth.** Long reads add little; assembly adds nothing |

#### The one signature visible without long reads or assembly

For the known-chassis case the evidence is *already in the PFI report* — the toxin gene sits in the
VFDB table. What is missing is anything that asks **"is the parent organism actually here?"**

Confirmed in the code: `marker_present()` (`analysis/triage.py:265`) is only ever called from
`triage_taxa`, per taxon already in the species list. A `bont` hit with no *C. botulinum* row is
never examined. The same holds for AMR — a carbapenemase with none of its documented hosts present.

**So for this case it is a reporting gap, not a data gap.** One sweep over the gene tables asking
*"does any documented host of this gene exist in this sample?"* would surface it. Cheap,
deterministic, fits the existing gate style, needs no assembly — and it should **flag, not
escalate**, with its false-positive rate measured against the Zymo standard first. Worth listing as
a low-cost phase-1 item rather than bundling it with the assembly work.

#### The longer-term tiers

Confidence falls sharply down this list, and the proposal should say so:

| Tier | Method | Confidence | Honest caveat |
|---|---|---|---|
| 1 | **Known-part screening** — vector backbones, common origins, promoters, selection markers, epitope tags, screened against reads or contigs | **Reasonable specificity** | Only finds *known* parts. Also fires on ordinary lab plasmid contamination — needs negative controls to be interpretable at all |
| 2 | **Junction / synteny anomaly** — assemble, then detect host-foreign junctions and markers in unexpected genomic context | Medium | Requires contigs long enough to span a junction; short-read assembly of a complex metagenome often is not |
| 3 | **Compositional anomaly** — GC and k-mer deviation across the unclassified bin | **Lead generation only** | Already prototyped (`analysis/probe_unclassified.py`). Detects a *dominant unknown organism*; **has no power over a construct at any GC**, because a few-kb cassette cannot move a histogram built from 300,000 reads. Codon-optimised inserts sit *closer* to the host, not further |
| 4 | **"Signature of design"** — inferring synthesis, optimisation, or intent from sequence | **Not defensible** at metagenomic read depth | Should not be promised. If it is in scope, it is a research objective with an explicit null result as an acceptable outcome |

Tiers 1 and 2 need an **assembly step** (MEGAHIT/SPAdes + abricate-class screening). That is a real
change of shape: today the triage component runs in **1 CPU / 2 GB in 0.54 s**. Assembly of a
metagenome is tens of GB and tens of minutes per sample. It is a separate pipeline node with its own
compute budget, not an extension of the current one. Tier 3 runs on reads and needs no assembly.

**Recommendation:** take the orphan-marker check above as a cheap phase-1 item; commit to tiers 1
and 2 with defined reference part databases once assembly exists; offer tier 3 as an exploratory
analyst-facing flag with its limits stated; explicitly exclude tier 4 or reframe it as research.

**What the existing probe did and did not establish.** All five HTX samples were probed — 300,000
unclassified reads each, GC distribution and 25-mer frequency. GC distributions are broad and
multimodal with no sharp peak, and every k-mer above the noise floor resolved to a library artifact
(poly-G from 2-colour chemistry, Illumina adapter read-through). The supported conclusion is narrow
and still stands: **no large unknown organism is hiding in these samples.** It was never capable of
being an engineered-construct screen, and the `<0.1% of the unclassified fraction` figure quoted in
earlier drafts is not derived — the real blind spot is larger.

---

## 4. Predictive / AI layer — what "predictive" must mean

### The baseline that must not be broken

Today the engine is **deterministic and fully auditable**: same report in, same verdicts out,
forever. No network, no clock, no randomness. Every row carries the rule that produced it, and every
run records a SHA-256 fingerprint of the rule file. Call-caching is safe precisely because of this.

That property is the reason a verdict can be defended. **Any AI layer must sit alongside it, not
inside it.** A model that silently changes a gate outcome destroys the audit trail that makes the
system usable in an operational setting.

> **Describe the engine as more than a collator.** It applies a twelve-gate cascade and issues
> verdicts — that *is* interpretation, encoded as auditable rules. What it does not do is **learn**.
> The accurate phrasing is: *deterministic expert judgment encoded as rules; no model, no training
> data, no drift — a trained analyst still owns the final call.* Calling it "collates and curates"
> gives away a strength.

### Three things "predictive" could mean — they are not interchangeable

#### (a) Risk scoring — there are two ladders, not one

A calibrated numeric score would replace or augment the existing rule-based tiers. State them
correctly, because they are frequently merged and the merged version does not exist:

| | Values |
|---|---|
| **Taxon tier** — applies to a row | `NO_ACTION` → `MONITOR` → `CONFIRM` → `ESCALATE`, plus **`NOT_TESTED`, deliberately outside the ladder** |
| **Sample verdict** — applies to the swab | `NO ACTION` → `MONITOR` → `INVESTIGATE` → `ESCALATE` |

`INVESTIGATE` is a **sample** verdict; `CONFIRM` is a **taxon** tier. Neither appears in the other
ladder.

The two-ladder design is worth selling, not hiding. `NOT_TESTED` sits outside the ordering so it can
never be compared against, or silently degraded into, `NO_ACTION` — absence of evidence is
structurally prevented from becoming evidence of absence. And `CONFIRM` is the **terminal state for
any AMR gene**: because host attribution is unsolved, no gene can reach `ESCALATE`, and `CONFIRM`
means *"culture with AST"*, not *"resistant"*.

- *Prerequisite:* labelled ground truth. Current thresholds are **reasoned, not fitted** — there are
  no culture-confirmed samples to fit against.
- *Success criteria:* sensitivity at a fixed false-positive rate on a held-out labelled panel;
  reference standard named (culture / targeted PCR); sample count stated. A score that disagrees
  with the deterministic verdict must produce an explanation, not just a number.
- *Verdict:* **defer.** Cannot be built before the labelled data exists. Phase 2.

#### (b) Anomaly detection against a site baseline — the strongest candidate

A within-batch version already runs. Gate 8 computes depth-normalised load (reads per million
classified) for each taxon against the highest load among the *other* samples in the batch, with a
5× fold threshold. Two verified examples, quoted from the engine's own output:

| Finding | Engine output | Effect |
|---|---|---|
| *Providencia rettgeri*, **WBM156** (193 reads) | `Providencia rettgeri: detected only in this sample` | Drove the sample to `MONITOR` |
| *A. baumannii*, **WBM232** (6,496 reads vs 549 / 914 / 837 elsewhere) | `6.0x enriched vs other samples` | Contributed to `INVESTIGATE` |

> **These are within-batch, not longitudinal.** "6× enriched" means *6× the other four swabs in this
> run* — not 6× this site's historical baseline. Gate 8 goes **inert with a single sample**, and
> there is no results store, so the engine has no memory between runs. This distinction matters:
> it is precisely the gap the OmicsNest dashboard would close, and it is why (b) is scoped as
> *phase 1 conditional on persistence* rather than *already delivered*.

- Extending it to a **longitudinal per-site baseline** is the natural next step and is a
  well-defined, testable capability: "this taxon is 12× its own 90-day site median."
- Further rules of this kind can be added to the existing gate framework as needed; the framework is
  not the constraint, the stored history is.
- *Prerequisite:* a **results store**. The current design is file-based, one run at a time, with no
  memory of previous runs. This is the enabling infrastructure and it is shared with point 5.
- *Success criteria:* detects a spiked or independently-confirmed event; false-alert rate per site
  per week held under a stated bound; baseline must be robust to protocol changes (a reagent lot
  change must not read as an outbreak).
- *Verdict:* **in scope for phase 1**, conditional on the results store.

#### (c) Forecasting — seasonal / longitudinal projection

- Read as longitudinal projection against seasonality (e.g. influenza season), which is the right
  interpretation.
- *Prerequisite 1:* months of longitudinal data at fixed sites under a **stable protocol**. That
  data does not exist yet and cannot be manufactured.
- *Prerequisite 2, and it is easy to miss:* **influenza is an RNA virus.** Seasonal respiratory
  forecasting is gated on the RNA library of §2 just as hard as it is gated on longitudinal history.
  A DNA-only stream cannot forecast what it cannot detect.
- *Verdict:* **phase 3, conditional.** Propose the data collection now so forecasting becomes
  possible later; do not propose the forecast.

### Non-negotiables for the AI layer, whichever meaning is chosen

1. **Every score carries its evidence.** The engine's existing per-row `why` list is the template —
   a model output with no traceable inputs is not usable for a decision someone has to defend.
2. **No model may silently override a deterministic gate.** Disagreement is surfaced, not resolved
   in the model's favour.
3. **Version and fingerprint the model** exactly as the rule file is fingerprinted. A run that
   cannot name the model that scored it cannot be reproduced.
4. **Hold-out evaluation only.** In-sample performance on 5 samples is not evidence.
5. **State the operating point, not the accuracy.** Sensitivity and specificity at a named
   threshold, against a named reference standard, on a stated sample count.

**Suggested phase-1 wording for the proposal:** *"Predictive" in this project means anomaly
detection against a per-site longitudinal baseline, plus empirical calibration of existing decision
thresholds against culture-confirmed samples. Risk scoring and forecasting are deferred to later
phases, contingent on labelled and longitudinal data respectively.*

---

## 5. Dashboard — from prototype to operational tool

### What the prototype already is

The current `--html` output is a self-contained file (~780 KB for five samples, CSS/JS/SVG inlined,
no network) with a sample switcher and four tabs per sample:

| Tab | Contents |
|---|---|
| QC | Read QC, kingdom breakdown, integrity-gate output, library scope |
| Flaggable species | Cards banded by severity, threat-list taxa first, community taxa behind a fold |
| Resistance genes | Sample-level, severity-banded, under a standing no-attribution banner |
| Method & verification | The exact command, the rule fingerprint, how to check any row |

**Explainability is already the design principle, not a feature to be added.** Each species card
carries the evidence behind its verdict — taxonomy counts, cross-sample load, confirmatory-marker
status, VFDB rows with accessions, inferred host-range. And every evidence row shows the identifier
you would search for in the PFI report itself: `VFG004763(gb|WP_011274497)` for a virulence row,
`MEG_2378` for a resistance row, the taxid for an organism. An analyst can walk any flag back to the
primary data.

The proposal should carry that forward as a requirement, not rebuild it.

### What has to change to make it operational

Six items, in dependency order:

1. **Persistence.** The prototype is one run, one file, no memory. Everything else on this list needs
   a results store (runs → samples → taxa/genes → verdicts → evidence). **This is the single largest
   change, and it is the same infrastructure that unlocks point 4b.** Do it once.
2. **Longitudinal and cross-site views.** Per-site timeline, verdict history for a taxon, "new since
   last run", "rising over 90 days". Impossible without (1); nearly free with it.
3. **Analyst workflow.** Acknowledge / assign / comment / sign-off, with an audit trail of who
   cleared what and when. A surveillance dashboard nobody has to action is a report.
4. **Drill-down preserved to the primary record.** Card → gate-cascade trace → PFI accession →
   reproduce-offline command. Keep the rule fingerprint visible on every view; a screenshot of a
   verdict that cannot name its rules is not evidence.
5. **Access to suppressed rows.** Suppressed AMR groups currently appear only as a count and a class
   breakdown — auditing a suppression means opening the PFI report by hand. The dashboard should let
   an analyst expand them in place.
6. **Access control and identifiability.** Sample IDs are the sensitive field. Role-based access and
   a de-identified view need to be designed in, not retrofitted.

**Keep:** the self-contained export. A file that survives being emailed and opens from disk years
later is worth preserving alongside the live view, for records and for hand-off.

### Two deployment options, and they are a sequence not a choice

| Option | What it is | Gives you |
|---|---|---|
| **A — batch dashboard** | Essentially today's artefact, tidied: one run, self-contained, emailable | Per-batch review and hand-off. **No running statistics, no trends, no site baseline** — because there is no memory between runs |
| **B — OmicsNest-hosted, with running statistics** | The engine's outputs land in a store that OmicsNest reads | Everything in §4b: longitudinal baselines, "new since last run", per-site trend, analyst workflow |

**Option A is a subset of B, not an alternative to it.** Build A first if timing demands, but the
store is what turns the prototype into surveillance, and every deferred capability in this document
(§4b anomaly detection, §4c forecasting, items 2–3 above) is waiting behind it.

### Suggested shape

Leave the engine as it is — deterministic, offline, no dependencies, emitting TSV and JSON — and add
a thin store plus a web layer that reads what it emits. The engine stays reproducible and portable;
the dashboard is a **view over its outputs**, not a rewrite of it. That keeps the audit property of
point 4 intact, lets the two evolve independently, and means OmicsNest integration does not require
touching the analysis at all.

---

## Cross-cutting note for the proposal

Points 3 and 5 both hinge on two infrastructure decisions that should be named and costed
explicitly rather than assumed:

- **An assembly step** — required for engineered-construct detection (3c tiers 1–2), for improving
  virulence marker confidence (3a), and for any progress on AMR gene context (3b). Materially
  different compute from the current pipeline: **1 CPU / 2 GB / 0.54 s** today versus tens of GB and
  tens of minutes per sample.
- **A results store** — required for the dashboard (5), for anomaly detection (4b), and ultimately
  for forecasting (4c). Small engineering, large unlock.

Neither is visible in a per-sample deliverable, and both will be the reason a phase-2 capability
either exists or does not.

### Three cheap items that need neither

Worth separating in the costing, because they are small and can land in phase 1:

1. **A negative extraction control every run** (§3b) — converts asserted thresholds into measured
   ones. Bench cost only, no engineering.
2. **The orphan-marker sweep** (§3c) — asks whether any documented host of a gene is present in the
   sample. Deterministic, fits the existing gate style, no assembly.
3. **A sample naming convention agreed before the OmicsNest interface is built** (§1) — free now,
   expensive to retrofit, and a hard prerequisite for anything longitudinal.

### RNA is the one item that changes the answer to more than one point

The RNA library (§2) is not only a §2 item: it closes **25 of 46 CDC agents** currently
`NOT_TESTED`, it supplies the viability axis the rules do not have, it is what makes toxin
*expression* rather than gene presence reportable (§3a), and seasonal forecasting (§4c) is
impossible without it. If one thing is funded first, it is this.
