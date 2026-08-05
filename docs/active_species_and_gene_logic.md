# "Active" species, and what AMR / virulence genes actually decide

Answers three questions: (1) WBM179 — does `blaZ` + `mecI` without `mecA` make *S. aureus*
"active"? (2) WBM174 — does absence of BoNT drive the *C. botulinum* call, and is `bont` an AMR
gene? (3) Can the 27,827-row PFIDB be annotated with what makes a species "active"?

---

## 0. The premise has to be corrected first

**"Active" is a specific, separate section of the PFI report, and it is empty in all five
samples.** It is not derived from AMR genes, virulence genes, or abundance.

In `globalData` each report carries `speciesActivity → {specie, subspecie}`, backed by
`Active.Species.xlsx` / `Active.SubSpecies.xlsx`. Measured across all five:

| Sample | `showDNA` | `showRNA` | Active species rows | `Active.Species.xlsx` on disk |
|---|---|---|---|---|
| WBM156 | True | **False** | 0 | absent |
| WBM174 | True | **False** | 0 | absent |
| WBM179 | True | **False** | 0 | absent |
| WBM185 | True | **False** | 0 | absent |
| WBM232 | True | **False** | 0 | absent |

Activity means **transcriptional** activity — the organism was detected in the RNA library, so it
was alive and expressing at sampling. There is no RNA library here, so `showRNA=False`, every
Active table is empty, and the download links in the HTML are dead (the files were never
generated).

**DNA cannot establish that anything is active.** A swab of a dry surface yields DNA from live
cells, dead cells, spores and free extracellular DNA identically. No gene — resistance,
virulence, or otherwise — changes that. So neither `blaZ`/`mecI` in WBM179 nor anything in WBM174
makes an organism "active"; nothing in this dataset can.

What genes *do* decide is whether a detection is **actionable**, which is a different judgment and
is made in §1–2 of the assessment, not by the report software.

---

## 1. WBM179 — `blaZ` present, `mecI` present, `mecA` absent

### What is actually in the sample

*S. aureus* is present but minor: **1,699 real reads, 0.20% abundance — the 8th most abundant
staphylococcus**. The staphylococcal population is dominated by coagulase-negative skin flora:

| Species | Real reads | Abundance |
|---|---:|---:|
| *S. epidermidis* | 65,238 | 3.37% |
| *S. hominis* | 34,036 | 1.58% |
| *S. capitis* | 23,679 | 1.12% |
| *S. haemolyticus* | 7,055 | 0.38% |
| **_S. aureus_** | **1,699** | **0.20%** |

### What the beta-lactam rows say

| Group | Accession | Breadth | Depth | Role |
|---|---|---:|---:|---|
| BLAZ | MEG_1331 | 58.82% | 6.04× | penicillinase (structural) |
| BLAZ | MEG_1330 | 74.91% | 2.49× | same gene, other allele |
| BLAZ | MEG_1356 | 53.14% | 3.20× | same gene, other allele |
| BLAR | MEG_1300 | 87.48% | 11.26× | *blaR1* sensor-transducer |
| BLAR | MEG_1299 | 75.18% | 10.29× | allele |
| BLAI | MEG_1287 | 98.16% | 3.94× | *blaI* repressor |
| MECI | MEG_3804 | 74.93% | **1.62×** | *mecI* repressor |
| MECA | — | — | — | **not detected** |

### Why `mecI` without `mecA` is not a resistance finding

**1. `mecI` is the repressor of `mecA`.** Its only function is to switch `mecA` off. With no
`mecA` there is nothing for it to regulate — the call is biologically incoherent as evidence of
methicillin resistance. Even in a genuine SCCmec, intact `mecI` *reduces* `mecA` expression.

**2. `mecI` and `blaI` are homologues, and MEGARes files them under the same mechanism.** Both
MECI and BLAI carry `Mechanism = "Penicillin binding protein regulator"`, as do all three BLAR
rows. `mecI`/`mecR1` and `blaI`/`blaR1` are the same two-component repressor–sensor architecture
and cross-map at short read length. Given a well-supported *bla* operon (`blaI` at 98.16% breadth,
`blaR1` at 11.26× depth) and `mecI` at **1.62× — the second-lowest depth in the whole 72-row
table** — the parsimonious reading is that MECI is spillover from `blaI`, not a separate element.

**3. `blaZ` is ordinary.** Penicillinase is carried by the majority of staphylococci, including
the coagulase-negative species that dominate this sample. It confers penicillin resistance, which
has been near-universal in staphylococci since the 1950s, and says nothing about methicillin.

**4. Host is unattributed anyway.** As established in §2.5, the AMR table never links a gene to an
organism, and assembly could not close that gap. With *S. aureus* at 0.20% and *S. epidermidis* at
3.37%, `blaZ` is more likely *epidermidis*'.

**Conclusion for WBM179: no methicillin-resistance finding, and nothing that elevates
*S. aureus*.** `blaZ` + `blaI` + `blaR1` is a complete, unremarkable penicillinase operon most
plausibly belonging to the coagulase-negative majority. The single `mecI` row is a homology
artifact. This is *weaker* than WBM185, where `mecA` itself was detected at 90.89% breadth /
10.51× — and even that finding was withdrawn for lack of a host.

---

## 2. WBM174 — BoNT is not an AMR gene, and its absence does not "cause" the call

**`bont` is a virulence factor, not a resistance gene.** It is screened against VFDB
(`virulence` block), not MEGARes (`drugResistance`). It encodes botulinum neurotoxin — it makes
the organism dangerous, not drug-resistant. Nothing about it belongs in the AMR table.

**The *C. botulinum* call comes from taxonomy alone**, and is trace:

| WBM174 *Clostridium* | Real reads | Abundance |
|---|---:|---:|
| *C. perfringens* | 84 | 0.00% |
| *Clostridioides difficile* | 21 | 0.06% |
| *C. paraputrificum* | 13 | 0.00% |
| ***C. botulinum*** | **11** | **0.00%** |

11 reads, collapsing to **1 unique molecule** after deduplication — an amplification artifact, not
an organism.

**BoNT is absent everywhere.** Zero `bont`/neurotoxin hits across all five VF tables
(252 / 468 / 414 / 657 / 654 rows).

So the logic runs the other way round from the question. Absence of `bont` does not cause or
create the *C. botulinum* detection — the detection came from 11 taxonomy reads. What the absence
does is **remove the only thing that could have made it actionable**. Since the *bont* cluster is
mobile (chromosome, plasmid or prophage), species identity never implied toxigenicity in the first
place; conversely a *bont* hit without *C. botulinum* would have been the more alarming result.
Neither occurred.

---

## 3. Can the 27,827-row PFIDB be annotated with "what makes a species active"?

**No — not for "active", and the reason is structural, not effort.**

**"Active" is a measurement, not a property.** It is per-sample and RNA-derived: this organism was
transcribing in *this* swab. The same species is active in one sample and inert in the next. There
is no value you could write into a species row that would be true in general, so the column cannot
be precomputed for any species, let alone 27,827.

**Reframed as "actionable", it is still per-sample.** Actionability in this project depends on
depth-normalised load, enrichment relative to the other four samples, unique-read fraction, the
site, and co-occurring genes — none of which are properties of a species.

**What genuinely can be precomputed is a decision-rule table.** Static, species-level annotation
that turns each detection into a defined next step:

| Column | Example for *B. anthracis* |
|---|---|
| Risk tier | CDC Category A |
| Genome type | dsDNA → **detectable by this assay** |
| Near-neighbour ambiguity | *B. cereus*, *B. thuringiensis*, *B. mycoides* at same rank |
| Confirmatory marker required | pXO1 / pXO2 plasmid genes |
| Known kitome organism | No |
| Action if marker absent | Downgrade — near-neighbour cross-mapping |

This is buildable and would be worth having. Two things to size it correctly:

- **Only ~5% of the database is relevant.** 1,463 distinct species (plus 370 subspecies) were
  observed across all five samples, out of 27,827 in the DB. The remaining 26,000 are taxa that
  have never appeared.
- **The high-value subset is far smaller still** — the ~50 CDC A/B/C agents (`pfidb_cdc_coverage.md`)
  plus the ~46 kitome taxa already identified in §3, which is where nearly every real decision is
  made.

Recommendation: build the rule table for the ~1,463 observed taxa, seeded from the CDC list and the
kitome list, rather than attempting all 27,827. It should carry **no "active" column** — that
column can only ever be filled by an RNA library.
