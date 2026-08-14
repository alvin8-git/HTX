# Point 3 in detail — analytical capabilities and achievable confidence

Expansion of §3 of [`proposal_scope_answers.md`](proposal_scope_answers.md).

Point 3 bundles three capabilities under one heading. They have very different confidence ceilings,
set by different causes, and only one of them exists today. Presenting them as a single line item
invites a commitment the third cannot honour, so they are separated here — each with what runs
today, what has been *measured*, where the ceiling sits and what would raise it.

Everything below is checkable against a run of the current engine. Where a number is quoted it comes
from [`zymo_validation.md`](zymo_validation.md) (certified mock community),
[`biothreat_assessment.md`](biothreat_assessment.md) (the five HTX swabs) or
[`stool_sms_longread_run.md`](stool_sms_longread_run.md) (long-read platform).

---

## 3.0 The one quantified performance figure we have

Everything in this section rests on a single validation, and the proposal should cite it rather than
assert accuracy in general terms.

**ZymoBIOMICS Microbial Community Standard** (data sheet DS1706; eight bacteria at 12% gDNA each,
two yeasts at 2%), five reports at different DNA inputs, 20–40 M raw reads, 73–96% classified.

| Test | Result |
|---|---|
| Sensitivity — 10/10 expected organisms in every sample | **PASS** |
| Quantitation — mean absolute error vs theoretical | **1.01 percentage points** |
| Specificity — `ESCALATE` calls on a certified-clean standard | **0** |
| False-positive taxa above 1,000 reads | **1** — *Shigella flexneri*, 0.04% (genomically *E. coli*; near-neighbour cross-mapping, not contamination) |
| False-positive threat calls | **1** — *Salmonella enterica* → `CONFIRM` |
| False-positive AMR calls | **2** — `aac(6')`, `fosA`, both intrinsic and called acquired |

Two caveats that belong in the proposal, not in a footnote:

1. **GC bias is real and input-dependent.** Correlation between GC content and signed error is
   **−0.82 at 3 ng input**, weakening to **−0.09** at the highest input. Low-input libraries
   systematically under-report GC-rich organisms. This matters directly for low-biomass
   environmental swabs.
2. **This is one community, ten organisms, five libraries.** It establishes that the engine does not
   invent findings and quantifies well. It does **not** establish sensitivity for a trace agent, and
   nothing in the current data set does.

---

## 3.1 Virulence factor assessment

**Status: implemented and validated. Highest confidence of the three.**

### 3.1.1 What runs today

VFDB rows from the PFI report are attributed to the species that owns them, with accessions carried
through to the report so any row can be walked back to the primary data. Marker searches are
**genus-restricted** — not cosmetic: without that restriction a *Brucella* marker matched
*Ochrobactrum* reagent contamination, which appears in all five HTX swabs.

The design decision worth carrying into the proposal is that markers have a **declared direction of
inference**, because a virulence-gene miss means different things for different agents:

| Kind | Count | Present | Absent |
|---|---:|---|---|
| `markers` — two-way | **9 agents** | `ESCALATE` | **downgrade to `NO_ACTION`** — the gene is unique to the agent and reliably in VFDB, so a negative is a real negative |
| `supporting_markers` — one-way | **8 agents** | `ESCALATE` | **no change, and the row says so** — VFDB coverage for the agent cannot be certified from the report, so a miss must never read as a clear |
| No marker | **4 agents** | — | gate 10 does not run; `CONFIRM` is the ceiling and the row states the call rests on taxonomy alone |

Two-way panel: `pXO1`/`pXO2` (anthrax), `bont` (botulism), `caf1`/`lcrV`/`pla` (plague),
`fopA`/`tul4` (tularaemia), `etx` (*C. perfringens*), `seb` (*S. aureus*), `ctxA`/`ctxB` (cholera),
`stx1`/`stx2`/`eae` (STEC).

The four unmarkable agents are unmarkable for stated reasons, not through neglect: *Variola* and
*Cryptosporidium parvum* because VFDB is a **bacterial** database; *Chlamydia psittaci* because its
VFDB genes are genus-wide and would not separate it from *abortus* or *trachomatis*;
*Rickettsia prowazekii* because the discriminator is an **absence** (typhus-group *Rickettsia* lack
`ompA`), which cannot be expressed as present-means-escalate.

### 3.1.2 Measured performance

The Zymo standard contains three CDC Category B organisms by design, as non-toxigenic laboratory
strains. This is the cleanest available test of the marker gate:

| Organism | Reads | Verdict | Reason |
|---|---:|---|---|
| *S. aureus* | 3,172,304 | `NO_ACTION` | `seb` absent — correctly not enterotoxin-B-producing |
| *E. coli* | 395,160 | `NO_ACTION` | `stx1`/`stx2`/`eae` absent — correctly not STEC/EPEC |
| *S. enterica* | 3,221,442 | **`CONFIRM`** | **false positive** |

**Two of three correctly downgraded at ~13% abundance.** That is the single most useful result in
the validation: at high depth, on a certified-negative sample, the marker gate distinguished
"organism present" from "threat present" — which is the entire job.

### 3.1.3 The confidence ceiling is a sequencing-depth question, and it is quantified

Gate 10a only downgrades on a missing marker **when the marker could have been seen**. Detection
power is modelled as Poisson over uniform coverage from genome size, marker length and read length;
below 90% power the marker reverts to one-way and the row reads *"marker NOT ASSESSABLE at this
coverage"*.

This converts "how confident can you be?" into a number, which is what a proposal needs:

| Agent | Genome | Marker | Species-specific reads for 90% power |
|---|---|---|---:|
| *B. anthracis* | 5.51 Mb | pXO1/pXO2, 12,600 bp | **~1,000** |
| *C. botulinum* | 3.89 Mb | bont, 3,876 bp | **~2,200** |
| *S. aureus* | 2.82 Mb | seb, 801 bp | **~6,800** |
| *V. cholerae* | 4.03 Mb | ctxA+ctxB, 1,152 bp | **~7,100** |

A bigger marker is cheaper to confirm. The operational consequence is the one to put in front of
stakeholders: **at 0.1% abundance and a 7.9% classified yield, reaching 7,100 species-specific reads
requires roughly 90 M raw reads.** Toxin confirmation for a trace agent is a depth problem, not an
algorithm problem, and it should be costed as such.

The concrete example this came from: WBM179 carried 11 reads of *V. cholerae* — 0.0004× genome
coverage, P(seeing ctxA/ctxB at all) = **0.35%**. Absence was the expected outcome whether or not
the organism was toxigenic, and until this was fixed the engine reported that non-result as an
exclusion. Across the five HTX samples the fix moved **14 rows** from `NO_ACTION` to `NOT_TESTED`
and **changed no sample verdict** — it removed false exclusions without manufacturing alarms.

### 3.1.4 What limits it

- **VFDB is bacterial.** Viral and eukaryotic agents cannot be marker-confirmed at all.
- **Coverage cannot be certified from the report**, which is why 8 agents are one-way.
- **A marker in a minority of strains** (`seb` in a minority of *S. aureus*, `ctxAB` only in
  toxigenic *V. cholerae*) means genuine absence is common — it just is not *demonstrated*.
- **Uniform coverage is optimistic.** Real coverage is patchier, so the power figures above are
  upper bounds.

### 3.1.5 What would raise it

| Action | Effect | Cost |
|---|---|---|
| **Assembly + VFanalyzer on contigs** | Gene completeness and genomic context; converts one-way markers to two-way; shrinks the unmarkable four | New pipeline node — see §3.3.4 |
| **Deeper sequencing on escalated samples** | Directly buys marker power per the table above | Flow-cell time; re-run only, not routine |
| **RNA library** | Toxin *expression* rather than gene presence — a categorically stronger statement | See point 2 |

---

## 3.2 AMR / resistome profiling

**Status: implemented. Good at gene presence. Structurally unable to attribute genes to organisms —
and that limit has been measured, not assumed.**

### 3.2.1 What runs today

Four stages over the MEGARes table in the PFI report:

1. **Allele collapsing (gate 3)** — group rows by MEGARes `Group`, keep max(breadth, depth). One
   real gene recruits reads onto several accessions: WBM185's three MECA rows and two CTX rows are
   **one** *mecA* read pool and **one** CTX-M read pool, not five genes.
2. **Two routes to a call** — because PFI reports depth over *covered* bases, breadth and depth are
   independent and a gene can sit at 11.69× across 60% of a reference allele. That is a
   well-sequenced fragment, not a weak hit; the allele is uncertain, the gene is not.

   | Route | Threshold (`acquired` default) | Reported as |
   |---|---|---|
   | Full length | breadth ≥ 80% **and** depth ≥ 5× | `acquired, full length` |
   | Fragment | breadth ≥ 55% **and** depth ≥ 10× | `acquired, PARTIAL — family established, allele not` |

   With clinically-motivated per-group overrides: `CTX` and `MECA` drop fragment depth to 8×
   (missing an ESBL costs more than over-calling; a partial *mecA* still warrants culture), and
   `BLAZ` raises to 85%/8× with the fragment route **disabled** (staphylococcal penicillinase is
   near-universal background).
3. **Class annotation (gate 5)** — 116 curated group overrides → 132 mechanism-class entries →
   ordered keyword fallback. Nothing ever returns `unannotated`.
4. **Candidate-host evidence layer** — see §3.2.3.

### 3.2.2 The main value is suppression, and it is measurable

Of 116 curated groups, only one class can raise a verdict on its own:

| Class | Count | Verdict | Why |
|---|---:|---|---|
| **`acquired`** | **38** | **`CONFIRM` / `MONITOR`** | Horizontally acquired — the only class that can raise a tier alone |
| `environmental` | 21 | `NO_ACTION` | Metal/biocide resistance; real, not clinically actionable |
| `intrinsic` | 15 | `NO_ACTION` | Chromosomal in its host; resistance needs overexpression |
| `efflux_ubiquitous` | 12 | `NO_ACTION` | Near-universal pumps, expression-dependent |
| `point_mutation` | 9 | `NO_ACTION` | Presence is universal; resistance needs a substitution |
| `regulator` | 9 | conditional | Meaningful only against its operon |
| `rrna_conserved` | 7 | `NO_ACTION` | 16S/23S — the whole community piles onto it |
| `core_essential` | 5 | `NO_ACTION` | Housekeeping; presence is the default state |

**Roughly one curated group in three is clinically actionable.** The rest are correctly suppressed.
Without that layer the resistance tab is a list of everything the community carries, which is not a
finding.

`regulator` shows the pattern at its sharpest: `requires` names the partner group, and absent from
the sample the call is *"incoherent as a resistance call"* — which is what dismisses `MECI` without
`MECA`. WBM179 carried `blaZ` + `mecI` and no `mecA`; *mecI* is the **repressor** of *mecA*, so with
nothing to regulate the finding is biologically incoherent as evidence of methicillin resistance.

Annotation coverage has been stress-tested on data the rules were not written against:

| Data set | Groups seen | Unannotated before | Unannotated after |
|---|---:|---:|---:|
| HTX swabs (short read) | 24–52 | 0 | **0** |
| Zymo standards (deep) | 315–318 | 285–287 | **0** |
| Long-read stool | 186 | 13 | **0** |

### 3.2.3 Host attribution — measured as unachievable, and worked around

No field in the PFI report joins `drugResistance.DNA` to `speciesData`. The resistome is sample-wide
**by construction**. This was not merely unattempted:

> Assembly was run on the HTX batch and recovered **no *mecA* and no CTX-M contig**, with per-taxon
> read mapping returning **0 reads at MAPQ ≥ 20** (§2.5, `biothreat_assessment.md`).

So even the raw reads do not guarantee an answer. And forcing the attribution has a measured price:
it produced **9 false-positive `CONFIRM` calls** on a certified-clean standard.

What runs instead is an **evidence layer, not an attribution**. `genus_amr_context()` pulls the
sample-wide gene evidence into the row of every organism it could plausibly belong to, and adds the
one fact that lets a human weigh it: every documented host of that gene actually present in this
sample, ranked by read count, with this taxon's own rank marked. From WBM179:

> AMR CONTEXT: 15 gene(s) expected in *Staphylococcus* co-detected in this sample (TETK, MSRA, BLE,
> LNUA, BLAZ, ERMC …); the most abundant competing host in the sample is *S. epidermidis* at 65,238
> reads (**38× this taxon**), a documented host of TETK — MEGARes carries no organism column, so
> none of them is attributed to any species and none of them changed this verdict

That is why a reader can *agree* with the `NO_ACTION` rather than merely accept it. In WBM156 the
same machinery places *S. aureus* at **rank 30 of 57** candidate hosts for `ERMF` — a fact no
verdict tier can carry. **All 70 listed organisms get a line**, including the ones with nothing to
report, because silence is the failure mode this project exists to avoid: 26 full rankings, 12
biological *"none expected"* statements, 29 *"not applicable — MEGARes indexes bacterial genes"*, 2
explicit *"a coverage limit of the rule file, NOT evidence this organism carries no resistance"*.

Escalation on this evidence is deliberately hard. A WHO-priority watchlist organism reaches
`CONFIRM` — never `ESCALATE` — only when it is enriched, carries a co-located acquired gene of a
matching class, **and plausibly owns it**: it must top its host pool or hold ≥20% of the reads of
all documented hosts of that gene. The rule that added this: *Serratia marcescens* had escalated on
a CTX-M whose host pool it holds **1.3%** of, among 77 candidate organisms. *A. baumannii* in WBM232
holds **21%** and tops its pool, so the batch's one operational finding was unaffected.

### 3.2.4 Four things it cannot do

| Limit | Consequence | What would answer it |
|---|---|---|
| **Which organism carries the gene** | A resistance finding is sample-level; the action is "culture with AST", which is correct whether or not the gene turns out to be that organism's | Culture + AST. Assembly alone demonstrably insufficient on this data |
| **Point-mutation resistance** | `gyrA`, `rpoB`, `lpxA` resistance is never reported, so **its absence is never evidence of susceptibility** | Variant calling at sufficient depth |
| **Plasmid vs prophage vs chromosome** | Mobility — the property that actually drives spread — is unmeasured | Assembly + replicon typing; long reads |
| **No contamination floor** | Thresholds are reasoned, not fitted; trace calls below ~100 reads cannot be formally separated from reagent background | A negative extraction control every run |

### 3.2.5 Thresholds are platform-specific — a finding, not a footnote

Running the unmodified engine on long-read stool data exposed that breadth and depth mean different
things on different platforms, and the gates move in **opposite directions**:

- **Breadth stopped discriminating.** 55% of long-read AMR rows sat at ≥99% breadth against 7% of
  short-read rows — a 7 kb read spans a 1 kb gene end to end, so an 80% gate is free. Raised to
  **95%**.
- **Depth over-called absence.** 28 acquired genes sat at ≥99% breadth with <5× depth and were
  under-called — one unit of long-read depth is one whole molecule, not a thin pileup of 150 bp
  fragments. Lowered to **2×**.

Any proposal that spans platforms needs per-platform calibration as a line item, and any change of
library prep or instrument invalidates the thresholds until re-checked.

### 3.2.6 What would raise it, ranked by value per unit cost

1. **A negative extraction control every run** — cheap, and it converts asserted thresholds into
   measured ones. The single highest-value change on this list.
2. **Culture + AST as the defined endpoint of a `CONFIRM`** — the only definitive answer to
   attribution and to phenotype. Should be written into the workflow, not left implicit.
3. **Long-read sequencing** for gene context and mobility — `long_read_thresholds` already exist.
4. **Assembly + replicon typing** — partial answers on mobility; measured as insufficient for
   attribution on this batch.
5. **Variant calling** for point-mutation resistance — the largest true blind spot, and the most
   expensive to close.

---

## 3.3 Engineered constructs and mutation signatures

**Status: no capability today. The most careful scoping of the three, and the one most likely to be
over-promised.**

### 3.3.1 Where the capability has to live

**72–90% of clean reads in the HTX samples are unclassified.** Any organism absent from the PFI
database lands there and is invisible to every row of every output. An engineered construct is, close
to by definition, in that bin — so this capability is not an extension of the taxonomic pipeline, it
is a new pipeline over the fraction the taxonomic pipeline discards.

Worth stating plainly for stakeholders: PFIDB coverage of the reference threat list is **not** the
gap. Every CDC agent that has a genome is in the database — 21/21 Category A, 16/17 B, 11/12 C; the
two absences are ricin (a plant protein toxin, no pathogen genome) and prions (no nucleic acid at
all), neither detectable by any sequencing assay. The gap is everything the database has never seen.

### 3.3.2 A first probe has already been run, and its sensitivity limit is known

This is the strongest position available in the proposal, because it is not speculative. The
unclassified fraction of all five HTX samples was probed directly — 300k reads sampled per sample,
GC distribution and 25-mer frequency:

| Sample | Unique | GC modes | Top 25-mer |
|---|---:|---|---:|
| WBM156 | 79% | 45 / 40 / 50% | 0.26% |
| WBM174 | 49% | 35 / 40 / 45% | 0.01% |
| WBM179 | 44% | 35 / 40 / 45% | 0.02% |
| WBM185 | 48% | 35 / 40 / 70% | 0.01% |
| WBM232 | 40% | 35 / 40 / 45% | 0.011% |

GC distributions are broad with no sharp single mode, and **every k-mer above the noise floor was
identified as a library artifact, not an organism** — poly-G from 2-colour chemistry (confirmed
R2-specific by running WBM185 R2 as a control), and Illumina adapter read-through, which is what
drives WBM156's outlier profile and is itself diagnostic of degraded / low-input DNA.

Conclusion: **no dominant unknown organism is hiding in any sample.** And the honest limit,
recorded at the time:

> This probe reduces but does not eliminate the novel-agent risk — it would not catch an engineered
> organism present at **<0.1% of the unclassified fraction**.

That number is the starting sensitivity of a tier-3 method, and it is a defensible thing to put in a
proposal.

### 3.3.3 Four tiers, with confidence falling sharply

| Tier | Method | Confidence | Honest caveat |
|---|---|---|---|
| **1** | **Known-part screening** — vector backbones, origins of replication, common promoters, selection markers, epitope tags — against reads or contigs | **Good specificity; the only tier fit for routine reporting** | Finds only *known* parts. Fires on ordinary lab plasmid contamination exactly as readily as on engineering — **uninterpretable without negative controls** |
| **2** | **Junction / synteny anomaly** — assemble, then detect host-foreign junctions and markers in unexpected genomic context | Medium | Needs contigs long enough to span a junction; short-read assembly of a complex metagenome frequently is not. Long reads change this materially |
| **3** | **Compositional anomaly** — GC, k-mer and codon-usage deviation across the unclassified bin | **Lead generation only** | Prototyped (§3.3.2). Cannot distinguish engineered from novel-natural. Produces work for an analyst, not verdicts |
| **4** | **"Signature of design"** — inferring synthesis, optimisation or intent from sequence | **Not defensible** at metagenomic read depth | Should not be promised. If in scope, frame as research with an explicit null result as an acceptable outcome |

**Recommendation:** commit to tiers 1 and 2 against defined reference part databases; offer tier 3
as an analyst-facing exploratory flag with its <0.1% limit stated; exclude tier 4 or reframe it.

### 3.3.4 What it costs — this is a change of shape, not a feature

Tiers 1–3 all require an **assembly step**. The scale difference is worth being explicit about:

| | Today's triage component | An assembly node |
|---|---|---|
| Compute | **1 CPU / 2 GB** | Tens of GB RAM |
| Runtime | **0.54 s** per batch | Tens of minutes per sample |
| Dependencies | Python standard library only, no network | MEGAHIT/SPAdes, abricate, reference databases |

It is a separate pipeline node with its own compute budget and its own failure modes, not an
extension of the current one. Costing it as an increment to the existing component will understate
it by orders of magnitude.

### 3.3.5 One sensitivity correction that affects every depth calculation here

Library duplication in the HTX samples is high — only **27–36% of reads are unique**. Effective
library complexity is therefore about **one third of nominal depth**, and true molecular sensitivity
is roughly **3× worse than read counts suggest**. Every depth figure in this document, including the
~90 M raw reads in §3.1.3, should be read with that factor applied.

---

## 3.4 Consolidated position

| Capability | Today | Achievable confidence | Ceiling set by | Highest-value unlock |
|---|---|---|---|---|
| Virulence — defined marker panel | **Implemented, validated** | **High**, quantified as a depth requirement per agent | VFDB coverage; marker size vs genome size | Deeper sequencing on escalated samples |
| Virulence — open survey | Partial | **Low** | VFDB is bacterial; coverage uncertifiable | Assembly + VFanalyzer |
| AMR — acquired gene presence | **Implemented, validated** | **Medium–high** above the breadth floor | Read-level calling; no genomic context | Negative extraction control |
| AMR — organism attribution | Evidence layer only | **Not achievable from sequence** — measured, not assumed | No joining field; assembly recovered nothing | Culture + AST |
| AMR — point mutations | None | **Zero** | Only gene presence is reported | Variant calling at depth |
| AMR — mobility (plasmid/chromosome) | None | **Zero** | No genomic context reported | Long reads + replicon typing |
| Engineered — known parts | None | **Good specificity** once built | Reference part database completeness | Assembly node + negative controls |
| Engineered — junction anomaly | None | **Medium** | Contig length | Long reads |
| Engineered — compositional anomaly | Prototyped | **Lead generation**, limit <0.1% of the unclassified fraction | Cannot separate engineered from novel-natural | Deeper unclassified-bin sampling |
| Engineered — signature of design | None | **Not defensible** | Read depth and information content | — |

---

## 3.5 Questions to put to PFI

1. Does PFIDB v5.1+ expose **sub-threshold taxon data**? The reporting floor is 10 species-specific
   reads with nothing below it surfaced, which sets the trace-detection limit independently of
   anything we do.
2. Can the report carry any **gene-to-taxon association**, even a weak one (contig co-assembly,
   binning, read-pair linkage)? The whole attribution limit hangs on this one absent field.
3. Is **variant calling** available or planned for the AMR module? Point-mutation resistance is the
   single largest blind spot and cannot be closed downstream.
4. Is any **unclassified-fraction output** available — the reads themselves, or a k-mer/assembly
   summary? Tiers 1–3 of §3.3 need access to it.
5. What is PFI's own **validated limit of detection**, per organism class, at a stated library depth
   and input mass? Our figures come from one mock community and five swabs.
6. Are **RNA libraries** supported end-to-end, and does AMR/VF calling run on them or DNA only?
   (See point 2.)
