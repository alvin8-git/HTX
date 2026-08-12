# Biothreat screen — 5 surface swabs (WBM156/174/179/185/232)
### v4 — verified against raw sample folders, with assembly-based AMR attribution and a rule-engine cross-check

> **Scope: this document is deliberately outside the triage engine's input contract.**
> `analysis/triage.py` reads one PFI HTML report and nothing else. This assessment went further —
> raw FASTQs, unique-read fractions, observed-vs-expected genome GC, a *megahit* assembly with
> *abricate*, and per-taxon read mapping — because the question of the batch was "what can be
> established at all", not "what can be established from the report". It is kept intact as the
> record of that work, and it is the best evidence available for what the extra data buys:
> §2.5 is the measurement showing that even assembly could **not** resolve the *mecA* / CTX-M host.
> Do not port conclusions from this document into the engine, the report or the deck without
> checking that the report alone supports them. The standing list of what the report cannot carry
> lives in [`reference_triage.md`](reference_triage.md#what-the-report-cannot-carry).

**Changed in v4 (2026-08-05):** every finding below was re-derived independently by
`analysis/triage.py`, a deterministic rule engine with no access to this document. It agreed on
the Category A negatives, the *C. botulinum* artifact, the *mecI*/*lpxA*/*adeJ* dismissals and the
WBM232 ESBL, and it surfaced **two genes this report had not called out**: *mupA* in WBM185
(§2.2) and *adeN* in WBM232 (§2.1). The engine was then measured against a certified ZymoBIOMICS
standard — 10/10 sensitivity, zero false escalations, quantitation MAE 1.01 pp, and nine
false-positive AMR calls that restate §2.5's host-attribution gap. Nothing in §§1–5 was retracted.

**Changed in v3 (2026-07-31):** §2.5 added — assembly of WBM185 and WBM232 with host attribution
of the AMR genes. The result is a negative that matters: **neither *mecA* nor CTX-M assembles, so
the "MRSA" label on WBM185 is withdrawn** (§2.2 rewritten). §2.1 revised to separate the one
*acquired* resistance gene in WBM232 from the intrinsic *adeJ* and the essential-gene *lpxA* hit,
with the XDR definition spelled out. Recommendations 2 and 6 updated.

**Sources now used:** `WBM*_en.html` (`globalData` JSON), `Classify.DNA.Species.xlsx`,
`Resistance.DNA.xlsx`, `Virulence.DNA.xlsx`, the per-species extracted FASTQs in
`WBM*/ExtractRead_DNA/Species/`, and the host-depleted reads `WBM*/removehost.DNA_[12].fq.gz`.
**Scripts:** `analysis/` — `extract.py`, `analyze.py`, `verify_reads.py`, `dedup.py`,
`probe_unclassified.py`, `check_fastq_integrity.py`, `annotate_contigs.py`, `build_deck.py`,
`triage.py`, `validate_zymo.py`.
**Derived data:** `analysis/species_all.tsv`, `amr.tsv`, `vf.tsv`, `triage_*.tsv`;
`assembly/*.contigs.fa`, `assembly/*.<db>.tsv`, `assembly/*.amr_attribution.tsv`.
**Companion documents:** `docs/zymo_validation.md` (measured accuracy),
`docs/triage_prototype_results.md` (agreement and disagreement with this report),
`docs/pfidb_cdc_coverage.md` (what the classifier database can and cannot see).

| Sample | Site | Raw reads | Host % | Clean | Unclassified | Classified |
|---|---|---|---|---|---|---|
| WBM156 | Ferry terminal, arrival restroom tap | 45.2M | **91.28%** | 3.29M (7.3%) | 81.1% | 622,642 |
| WBM174 | Changi T3 arrival, passport scanner | 26.1M | 18.8% | 20.9M (80.2%) | 88.2% | 2,465,508 |
| WBM179 | Changi T3 departure, fingerprint scanner | 53.2M | 77.2% | 11.4M (21.4%) | 72.8% | 3,110,882 |
| WBM185 | Changi T3 departure, check-in kiosk touchscreen | 22.0M | 6.3% | 20.4M (92.7%) | 90.2% | 2,006,566 |
| WBM232 | Changi T4 departure, trolley handles rows 5&6 | 32.8M | 22.3% | 25.2M (76.7%) | 89.7% | 2,590,665 |

DNA-only run (`showDNA: true`, `showRNA: false`). PFI v5.1.2, DB v5.1.1.

---

## 0. Verification of the v1 findings

| Check | Result |
|---|---|
| Species table completeness | Extracted-read directory count == reported species count in all 5 (373 / 929 / 693 / 967 / 737). |
| Per-species read counts | Counted reads in all 3,698 `*_1.fq.gz` files: **3,678 exact matches**; the 20 "mismatches" are name-normalisation only (`[Candida] haemuloni`, `[Ruminococcus] gnavus`, `Deinococcus soli ... Cha et al. 2016`). **Zero numerical discrepancies.** |
| AMR tables | `Resistance.DNA.xlsx` matches HTML row-for-row (WBM185 n=90, WBM232 n=66, WBM156 n=33), incl. mecA 90.89%/10.51× and CTX 82.88%/7.25×. |
| Virulence tables | `Virulence.DNA.xlsx` matches HTML (WBM156 n=252, WBM174 n=468, WBM179 n=414, WBM185 n=657, WBM232 n=654). |

**All v1 conclusions hold.** The raw data additionally let me do two things the HTML could not:
read-level deduplication QC, and a contaminant (kitome) analysis. Both are below, and both
*change the interpretation of several trace calls*.

### New QC metric: unique-read fraction
The libraries are heavily duplicated (low-biomass, over-amplified). Baseline unique-read
fraction is remarkably flat at every depth from 10 reads to 1.1M reads:

| Sample | median unique fraction (all species, all bins) |
|---|---|
| WBM156 | 0.36 | 
| WBM174 | 0.35 |
| WBM179 | 0.33 |
| WBM185 | 0.35 |
| WBM232 | **0.27** |

So ~35% is "normal". A taxon well **below** its sample's baseline is a handful of molecules
amplified many times — not an organism. A taxon **at or above** baseline has genuinely diverse
DNA behind it. Combined with observed vs expected genome GC, this cleanly separates real trace
detections from classifier artifacts.

### Data integrity problem found

Two WBM232 FASTQs arrived corrupt. **Both were re-copied on 2026-07-31 and are now verified
intact — all FASTQs across all five samples pass.**

| File | Size | Status |
|---|---|---|
| `WBM232/unclassify.DNA_1.fq.gz` | 669 MB | ✅ re-copied — 100% readable, 7.80 GB decompressed, 22,579,161 reads |
| `WBM232/removehost.DNA_1.fq.gz` | 765 MB | ✅ re-copied — 100% readable, 8.70 GB decompressed, 25,169,826 reads |

A full sweep of all 20 delivered FASTQs (`analysis/check_fastq_integrity.py`) now returns
**20/20 intact**, with every R1/R2 pair reporting identical decompressed size.

Both re-copies validate against independently reported figures and against each other:

| Check | Result |
|---|---|
| `removehost` R1 read count | 25,169,826 = reported **`Clean_Read`** exactly |
| `unclassify` R1 read count | 22,579,161 = reported **`Unclassified_Read`** exactly |
| Internal arithmetic | 22,579,161 unclassified + 2,590,665 classified = **25,169,826 clean** ✓ |
| Pairing (both files) | identical read counts and identical first/last read IDs vs R2 |

**The two failures had different signatures, and the second is the one worth remembering.**
`unclassify.DNA_1.fq.gz` was truncated — 506 MB vs the correct 669 MB, bad gzip header at byte 0,
0% recoverable. `removehost.DNA_1.fq.gz` was **byte-identical in size (765.4 MB) before and after
re-copy** but failed at 67.7% with `invalid distance code`: silent in-place corruption during
transfer, not truncation. **A size check would have passed it.** Verify FASTQ deliveries by
full decompression, not by file size — and note that `gzip -t` exited 0 on both of these while
printing an error, so it is unreliable in scripts.

---

## 1. CDC Category A agents — the requested report

**Verdict: no CDC Category A agent is present in any of the five samples.**

| Cat A agent | Detected? | Evidence |
|---|---|---|
| **Bacillus anthracis** (anthrax) | **NO** | Not present at species or subspecies level in any sample — no table row, no extracted-read directory. See §1.1 for the near-neighbour analysis, which is the part that actually matters. |
| **Clostridium botulinum** (botulism) | **NO** | WBM174 only, 11 reads — but **all 11 reads are duplicates of ONE unique sequence** (9% unique vs 35% baseline). A single molecule. No *bont* gene in any VF table. §1.2. |
| **Yersinia pestis** (plague) | **NO** | Absent at every level in all 5. No *Yersinia* species at all. No *pla*, *caf1*, *lcrV*, or *ymt*. §1.3. |
| **Variola major / Orthopoxvirus** (smallpox) | **NO** | Absent. Only 2–5 viral species called per sample: HERV-K, human mastadenovirus C, *Alphabaculovirus spliturae*. **This is the one Cat A agent the DNA-only design can genuinely assess** — see §1.4. |
| **Francisella tularensis** (tularemia) | **NO** | No *Francisella* at any taxonomic level in any sample. Nothing in the VF tables. |
| **Viral haemorrhagic fevers** (Ebola, Marburg, Lassa, Junín, Machupo, Guanarito, Sabiá, Lujo, Chapare) | **NOT ASSESSABLE** | All are RNA viruses. No RNA library was run. Their absence from this dataset carries **zero** evidential weight. §1.5. |

Verified by direct pattern search over all 3,698 species + 711 subspecies directories and all
2,445 virulence-factor rows.

### 1.1 Anthrax — the near-neighbour question, resolved

This was the weakest point of v1. The raw data settles it.

*B. cereus* group members **are** genuinely present at trace level:

| | reads | unique | unique % | GC% | expected GC |
|---|---|---|---|---|---|
| WBM174 *B. cereus* | 22 | 9 | **41%** | 33.9 | ~35 |
| WBM185 *B. cereus* | 43 | 18 | **42%** | 37.4 | ~35 |
| WBM185 *B. thuringiensis* | 30 | 12 | **40%** | 33.0 | ~35 |

All three are *above* the 35% baseline with correct GC — this is real, diverse, trace
*B. cereus*-group DNA. Which is exactly what you expect: the group is ubiquitous in soil and
dust, and *B. thuringiensis* is a commercial biopesticide.

The discriminating question is whether any of it is *anthracis*. VFDB gives a direct answer:

| Sample | VF hit | Attributed strain | Coverage | Depth | What it actually is |
|---|---|---|---|---|---|
| WBM174 | `isdC` | *B. anthracis* str. Ames Ancestor | 40.67% | 6.51× | **Chromosomal** haem-uptake gene, conserved across the entire *B. cereus* group |
| WBM185 | `GBAA_RS23245` | *B. anthracis* str. Ames Ancestor | 29.50% | 0.31× | **Chromosomal**, group-conserved |
| WBM185 | `dhbE`, `inhA`, `fliG/M/Y`, `flhF`, `BCE_RS*` | *B. cereus* ATCC 10987 / AH187 | 11–27% | 0.2–1.7× | Siderophore + flagellar + protease, group-conserved |

**Zero pXO1 markers** (`pagA`/protective antigen, `lef`/lethal factor, `cya`/edema factor, `atxA`).
**Zero pXO2 markers** (`capA`–`capE`, `acpA`). The two capsule/toxin plasmids are what *define*
*B. anthracis* — a strain lacking them is not virulent anthrax. Nothing anywhere in the dataset
touches them.

*(Note: the `capA` hit in WBM185 at 42.28% is `capA` from* Staphylococcus aureus *MW2 — the
staphylococcal capsule locus, an unrelated gene of the same name.)*

**Anthrax: negative, and now positively excluded at the plasmid-marker level, not just by
taxonomic absence.**

### 1.2 Botulism

WBM174's 11 *C. botulinum* reads collapse to **1 unique sequence**. That is one DNA fragment
amplified 11 times. No *bont* gene of any serotype in any VF table.

A related organism *is* genuinely present: *Clostridium argentinense* (WBM185, 82 reads, 27
unique = 33% ≈ baseline, GC 28.7% vs expected ~28%). *C. argentinense* is the BoNT/G species,
but the vast majority of environmental isolates are the non-toxigenic *C. subterminale*-like
form, and **no BoNT gene was detected**. Soil clostridium, no toxin.

**Botulism: negative.**

### 1.3 Plague

No *Yersinia* species in any sample. The two Yersinia-attributed VF hits in WBM174 —
`ybtT` (33.5%, 1.49×) and `irp2` (2.49%, 0.10×) — are **yersiniabactin** siderophore genes,
which sit on the widely mobile ICE*Kp*/HPI element and are carried by *K. pneumoniae* and
*E. coli*, both present in WBM174. No *pla*, *caf1* (F1 capsule), *lcrV*, or *ymt*.

**Plague: negative.**

### 1.4 Smallpox / Orthopoxvirus — the informative viral negative

Unlike the VHFs, poxviruses are large dsDNA viruses and **would** have been sequenced by this
DNA library. No *Orthopoxvirus*, *Variola*, *Vaccinia*, *Cowpox*, or *Monkeypox* appears at any
level in any sample. Only 2–5 viral species were called per sample, all benign.

Caveat on sensitivity: a 186 kb poxvirus genome yields ~27× fewer reads per genome copy than a
5 Mb bacterium, so the effective copy-number floor for a poxvirus is ~27× higher than for a
bacterium at the same 10-read reporting threshold. A very low-level poxvirus deposit could
still fall below it. But this is a real negative, not a structural blind spot.

**Smallpox/Orthopoxvirus: negative, with a genome-size sensitivity caveat.**

### 1.5 Viral haemorrhagic fevers — cannot be answered by this dataset

Filoviruses, arenaviruses, and bunyaviruses are all RNA viruses. A DNA-only library cannot
detect them at any abundance. **This is not a negative result — it is a missing test.**
If VHF agents are in scope for this surveillance programme, an RNA library is mandatory.

### 1.6 Category B agents, for completeness

Screened the same way; all negative or artifactual:

| Agent | Finding |
|---|---|
| *Vibrio cholerae* | WBM179, 11 reads, **1 unique sequence** (9%). No *ctxA/ctxB/tcpA/zot/ace*. Single-molecule artifact. |
| *Burkholderia mallei / pseudomallei* | Absent. Only environmental *B. cepacia* complex (13–16 reads, 50–62% unique — real but harmless soil/water organisms). |
| *Brucella* (true zoonotic) | *B. melitensis/abortus/suis* all absent. What is reported as "*Brucella anthropi*" is **Ochrobactrum anthropi**, reclassified into *Brucella* in 2020 — see §3. |
| *Coxiella burnetii* | Absent. |
| *Rickettsia prowazekii* | Absent. *R. felis*/*R. massiliae* present at 53–151 reads, 29–40% unique — plausible trace environmental DNA, but no vector plausible on a touchscreen. |
| *Salmonella*, *Shigella*, *E. coli* O157 | *Salmonella* and *Shigella* absent entirely. *E. coli* present at 25–52 rpm with no *stx*/*eae*. |
| *C. perfringens* epsilon toxin | *C. perfringens* genuinely present (WBM174/185/232, 21–29% unique, GC 27–32% = correct). **No *etx*, *cpe*, *cpa*, *pfoA*, or *netB*.** |
| *Chlamydia psittaci* | Absent. |
| Staph enterotoxin B | No *sea*/*seb*/*sec*/*tst*/*pvl* in any sample despite genuine *S. aureus*. |

The only genes in the entire VF dataset matching a classic toxin-gene pattern are
*Acinetobacter baumannii* phospholipase C (`plc1`/`plc2`/`plcD`) — highest in WBM232 at
54.77% coverage / 9.77× depth, consistent with the genuine *A. baumannii* load there.

---

## 2. What IS real — confirmed and strengthened

### 2.1 WBM232 (T4 trolley handles) — *Acinetobacter baumannii*, confirmed and sample-specific
- 4.72% abundance, **6,496 species-specific reads / 1,733 unique (27% = exactly the WBM232
  baseline)**, GC 35.9%. Genuinely diverse DNA, not an amplification artifact.
- Depth-normalised load **2,507 reads per million classified vs 58–417 rpm in the other four
  samples — a 6–43× enrichment.** This is a sample-specific signal, not flat reagent background,
  which is the key discriminator against the kitome explanation (*Acinetobacter* is otherwise a
  classic kit contaminant genus).
- 268 VF hits across six *A. baumannii* reference strains (ACICU 65, AB0057 55, ATCC 17978 49,
  BJAB0715 43, D1279779 37, 1656-2 22), including phospholipase C at 9.77× depth.
- **CTX-group class A β-lactamase** (MEG_2378), 60.56% coverage, 11.69× depth (ESBL). This is the
  only genuinely *acquired* resistance gene of the three below.
- **AdeJ** (MEG_692), 53.72% coverage, 5.38× depth — inner-membrane transporter of the AdeIJK RND
  efflux pump. AdeIJK is **chromosomal and intrinsic to essentially every *A. baumannii***;
  resistance arises from *overexpression*, usually via an *adeN* repressor mutation, and DNA
  cannot measure expression. The whole family is present (AdeH 88.56%/19.82×, AdeN 85.76%/8.85×,
  AdeT2, AdeG, AdeL, AdeT1, AdeI), which is better evidence that *A. baumannii* is genuinely here
  than that it is resistant.
  **Added in v4 — *adeN* is the gene to sequence, and it is well covered.** v3 named *adeN* only as
  the mechanism DNA cannot assess. At **85.76% breadth / 8.85× depth** it is far better covered
  than *adeJ* itself, and it is the *repressor*: loss of function in *adeN* de-represses AdeIJK and
  **is** the resistance. Presence at this coverage still does not prove overexpression — that needs
  variant calling, and ~0.25× genome-average coverage cannot support it — but it identifies the
  precise target for a follow-up assay. The same logic applies to *adeL* (AdeFGH) and *mexT*
  (MexEF-OprN), both also present. This is the one place where the rule engine found a better
  question than the manual pass did.
- **LpxA** (MEG_3626), 51.65% coverage, 1.90× depth — first enzyme of lipid A biosynthesis.
  Loss-of-function in *lpxA/lpxC/lpxD* abolishes LPS, and because colistin binds lipid A, an
  LPS-null *A. baumannii* is fully colistin-resistant. **But *lpxA* is a core essential gene in
  every Gram-negative — presence is the default state, not a finding**, and MEGARes files this as
  a "colistin-resistant *mutant*" entry that requires the resistance variant to be confirmed. At
  1.90× depth no variant can be called at all. Do not read this as colistin resistance.
- Co-detected: *K. pneumoniae* 0.92% (311 reads, 18 VF hits), *S. aureus* 0.98% (3,654 reads).

**Why partial coverage is the limiting factor here.** 6,496 species-specific reads × 150 bp is
≈0.97 Mb against a ~3.9 Mb *A. baumannii* genome — about **0.25× genome-average coverage**. At
2–5× on a single gene you cannot call the point mutations that *lpxA*/*gyrA*/*parC* resistance
actually depends on; you cannot distinguish chromosome from plasmid from a different organism,
because reads carry no linkage information; and a sequencing error is indistinguishable from a
real SNP.

**On "XDR".** Magiorakos *et al.* 2012 (ECDC/CDC): MDR = non-susceptible to ≥1 agent in ≥3 drug
categories; **XDR = non-susceptible in all but ≤2 categories**; PDR = all. *If* a single isolate
carried all of the above — CTX-M removing extended-spectrum cephalosporins, aac(6′) removing
aminoglycosides, AdeIJK overexpression removing tetracyclines/tigecycline/fluoroquinolones, and
*lpxA* loss removing polymyxins — that would be XDR with colistin, the last-line agent for
carbapenem-resistant *A. baumannii*, gone. **These genes were called independently off reads in a
mixed community and are not shown to be in the same cell.** This is a hypothesis to test by
culture, not a confirmed XDR organism.

**This remains the single most notable result in the set.** An ESBL-carrying, MDR-associated
nosocomial organism at high and site-specific load on a shared high-touch public surface.

### 2.2 WBM185 (T3 check-in kiosk touchscreen) — methicillin-resistance marker, host unresolved

**How to read the MEGARes rows.** A `MEG_` accession is **one reference allele**, not a gene.
MEGARes is organised Type > Class > Mechanism > **Group** > accession and stores many
near-identical alleles per gene, so a single real gene recruits reads onto several accessions at
once. The report's three MECA rows and two CTX rows are therefore **not** three *mecA* genes and
two *bla*<sub>CTX-M</sub> genes — they are one *mecA* read pool and one CTX-M read pool, split
across alleles:

| Group | Accession | Coverage | Depth | Reading |
|---|---|---|---|---|
| MECA | **MEG_3778** | **90.89%** | **10.51×** | Best allele — highest breadth *and* highest depth. The representative call. |
| MECA | MEG_3780 | 59.77% | 2.83× | Partial cross-mapping of the same read pool onto a homologous allele |
| MECA | MEG_3770 | 58.52% | 6.68× | Same — not an additional *mecA* gene |
| MECI | MEG_3803 | 65.50% | 5.66× | *mecI* is the repressor of the *mec* operon; co-occurrence supports a genuine SCC*mec* element (*mecR1* not detected) |
| CTX | **MEG_2430** | **82.88%** | **7.25×** | Best allele of the *bla*<sub>CTX-M</sub> family — the representative ESBL call |
| CTX | MEG_2435 | 54.14% | 2.71× | Partial cross-mapping onto a second CTX-M allele |
| BLAZ | MEG_1330 / MEG_1331 | 70.65% / 64.73% | 8.17× / 4.24× | Staphylococcal penicillinase — ordinary carriage, and the one gene that *did* assemble (§2.5) |

- **mecA at 90.89% gene coverage, 10.51× depth** — *breadth*, not depth, is what separates a real
  gene from a conserved fragment, and 90.89% of the ~2 kb *mecA* reference carrying read support
  is a near-complete gene. This is the strongest AMR call in the batch **at read level**.
- 2,300 *S. aureus* species-specific reads (678 unique, 29% ≈ baseline, GC 32.4%).
- **CTX-group ESBL** (MEG_2430) at 82.88% coverage, 7.25× depth.

**The "MRSA" label is not supported.** Read-level calling carries no linkage information, so
*mecA* is tied to no organism — and *S. aureus* and coagulase-negative staphylococci
(*S. hominis* 11.22%, *S. epidermidis* 4.08%, *S. haemolyticus* 1.81%) are all abundant here.
Methicillin-resistant *S. epidermidis* is an ordinary skin organism; MRSA on a check-in kiosk is a
different conversation. **Assembly was run specifically to settle this and could not — see §2.5.**
- Richest AMR profile: 90 genes / 21 classes — mupirocin, trimethoprim, fosfomycin, phenicol,
  and ICR colistin phosphoethanolamine transferase at 91.77% coverage / 14.26× depth.
- Full ESKAPE-adjacent panel at low but consistent load.

**Added in v4 — *mupA* at 90.18% coverage / 11.70× depth.** Surfaced by the rule engine, not
called out in v3. *mupA* is a second, plasmid-borne isoleucyl-tRNA synthetase conferring
**high-level mupirocin resistance**. It matters operationally because mupirocin is the standard
nasal decolonisation agent for staphylococcal carriage, so *mupA* predicts decolonisation failure —
on the same touchscreen that carries the *mecA* signal. Breadth and depth are comparable to *mecA*
itself. **Host is equally unattributed**, so this does not upgrade the finding; it belongs in the
culture request alongside *mecA*, not in a separate conversation.

### 2.3 Cross-sample AMR gradient
ICR (colistin PEtN transferase) in WBM174/179/185 at 5.5–23.3× depth; blaZ/blaR/blaI in
174/179/185; CAP16S in 174/179/185/232. WBM156 is cleanest (33 genes, no mecA, no CTX).
Burden: **WBM185 (90) > WBM174 (80) > WBM179 (72) > WBM232 (66) > WBM156 (33)**.

### 2.4 Incidental: *Candida haemulonii* complex
WBM185 carries `[Candida] haemuloni` at 977 reads (329 unique) and `C. duobushaemulonis` at 32;
WBM179 has `C. duobushaemulonis` at 10. These are the *C. auris* sister clade — intrinsically
fluconazole-resistant and frequently misidentified as *C. auris* by conventional lab methods.
***C. auris* itself is absent from all five samples.** Worth noting for any downstream lab that
receives these isolates.

### 2.5 Assembly-based AMR attribution — attempted, and the result is a negative

**Method.** megahit (v1.2.9) on the host-depleted reads of the two flagged samples
(`-t 64 -m 0.5 --min-contig-len 500`, k = 21…141), then abricate against **five** databases —
megares (the same DB the PFI report used, so results are comparable), card, resfinder, ncbi and
plasmidfinder. Driver: `analysis/annotate_contigs.py`; contigs are checked in under `assembly/`.

| | WBM185 | WBM232 |
|---|---|---|
| Contigs (≥500 bp) | 57,627 | 10,837 |
| Total assembly | 54.9 Mb | 15.9 Mb |
| N50 | **849 bp** | 26,611 bp |
| Longest contig | 1.11 Mb | 1.11 Mb |
| Contigs ≥10 kb | 90 | 84 |

WBM185's N50 of 849 bp is the expected consequence of an even, diverse community with no dominant
organism; WBM232 assembles far better because *C. acnes* at 57.41% supplies deep uniform coverage.

**What was recovered**

- **WBM185** — the staphylococcal penicillinase operon **blaZ + blaR1 + blaI**, full length at
  97–99% identity on a 22× k-mer-coverage contig of **GC 25.3%**, plus *msrA*, *mphC*, *lnuA*,
  *fusB*, *aph(3′)-Ia*, *ant(4′)-Ia*, *ermX* and the *qacA/C/J/R* biocide-efflux set. Plasmidfinder
  placed these on **12 staphylococcal replicons** (rep7a/pSTE1, rep10/pNE131, rep7a/repC,
  repUS46, rep21/pWBG754, rep20/p11819p97, rep39, rep24c, Col440II, Col(pHAD28)).
- **WBM232** — only *blaI*, *ermX*, *ant(3″)-IIa*, *mgrA*, and **no plasmid replicons at all**.

**What was NOT recovered — the finding**

> **Neither *mecA* nor CTX-M appears on any contig, in any of the five databases, in either
> sample. Nor do *lpxA* or *adeJ* in WBM232.**

This is informative rather than a failed run, because the assembly demonstrably works: *blaZ* came
out at full length and near-perfect identity, and *is* attributable — it sits on a staphylococcal
plasmid. The likeliest explanation for *mecA* is that its read pool is split across divergent
alleles from several different staphylococcal species, so no single consensus is ever reached —
exactly what the multi-allele MEGARes pattern in §2.2 predicts.

We also tested the read-attribution step directly: mapping the per-taxon extracted read sets
(`ExtractRead_DNA/Species/*/`) onto the assembled AMR contigs returns **zero reads at MAPQ ≥ 20
for every taxon**, including all five abundant staphylococci — while 62 reads per 2M pairs map
from the unfiltered clean reads. **The classifier never assigned these mobile elements to any
species in the first place**, which is the structural reason attribution fails: plasmid backbones
are shared across species and poorly represented in the taxonomy database.

**Conclusion.** Gene presence is well supported at read level. **Host attribution is not
resolvable from this dataset.** Culture with AST is now the only way to determine whether WBM185
carries MRSA or methicillin-resistant coagulase-negative staphylococci, and whether the WBM232
CTX-M sits on the *A. baumannii* or on the co-detected *K. pneumoniae*.

---

## 3. The kitome — which detections are reagent background

216 species appear in all five samples despite five different sites. 50 of those belong to genera
on the standard reagent-contaminant lists (Salter 2014 / Eisenhofer 2019). 46 core taxa show
relative abundance *negatively* tracking sequencing depth — the classic contaminant signature,
where a fixed reagent input dilutes as real biomass increases.

**Confidently kitome / reagent background — do not report as findings:**

| Taxon | Evidence |
|---|---|
| ***Brucella anthropi*** (= *Ochrobactrum anthropi*) | All 5 samples, GC 55.5–57.7% (correct for *Ochrobactrum*), the single most-cited reagent contaminant. Its "Human Infection: Y" flag is a **taxonomy-rename artifact** — it is not zoonotic *Brucella*. Same for *B. tritici*, *B. pseudogrignonensis*. |
| *Pseudomonas putida* | ρ(abundance, depth) = **−1.00** across all 5 |
| *Pseudomonas aeruginosa* | ρ = −0.70; flat 87–378 rpm across all 5 — no site enrichment |
| *Stenotrophomonas maltophilia* | ρ = −0.70; flat 169–1,042 rpm |
| *Sphingobium yanoikuyae* | ρ = −0.89 |
| *Caulobacter* sp. FWC26 | ρ = −0.76 |
| *Acinetobacter bereziniae*, *A. johnsonii* | ρ = −0.77 / −0.40 (note: *A. baumannii* behaves **oppositely** — see §2.1) |
| *Paracoccus* sp. Arc7-R13 | ρ = −0.60 |
| *Cutibacterium acnes*, *C. granulosum* | Both skin flora **and** reagent contaminant; ρ = +0.80 here, so mostly genuine skin |

**Distinguishing rule applied throughout:** a taxon is treated as a real site-specific finding
only if its depth-normalised load is enriched in one sample relative to the others. *A. baumannii*
in WBM232 (6–43× enrichment) passes. *P. aeruginosa* and *S. maltophilia* (flat across all five)
do not.

---

## 4. Trace calls now positively refuted by read-level QC

v1 called these "probably noise". They are now demonstrably artifacts:

| Call | reads | unique | unique % | GC% | expected GC | Verdict |
|---|---|---|---|---|---|---|
| *C. botulinum* WBM174 | 11 | **1** | 9% | 32.0 | ~28 | 1 molecule |
| *V. cholerae* WBM179 | 11 | **1** | 9% | 43.3 | ~47 | 1 molecule |
| *L. pneumophila* WBM232 | 25 | **2** | 8% | 40.4 | ~38 | 2 molecules |
| *C. tetani* WBM232 | 28 | 3 | 11% | **56.8** | **~28.6** | 2× wrong GC — grossly misassigned |
| *N. meningitidis* WBM232 | 13 | 2 | 15% | **36.1** | **~51.5** | wrong GC |
| *C. butyricum* WBM232 | 10 | 2 | 20% | 36.8 | ~28.6 | wrong GC |

*Corynebacterium diphtheriae* is the one that does **not** refute cleanly: WBM179 has 1,553
reads / 497 unique (32% ≈ baseline) at GC 55.9%. Expected *C. diphtheriae* GC is ~53.5%, but the
co-dominant *C. segmentosum* (13.87% of that sample) sits at ~59%, so this is consistent with
either. **No *tox* gene and no *dtxR* was found in any sample.** Non-toxigenic corynebacteria are
normal skin flora; toxigenic diphtheria is not supported. If certainty is required, run
*tox*-targeted PCR on WBM179.

---

## 5. False-negative risk — updated

1. **DNA-only. No RNA library.** Influenza, SARS-CoV-2, noro-, entero-, measles, and **all Cat A
   viral haemorrhagic fevers** are structurally undetectable. The largest single gap.
2. **Reporting floor = 10 species-specific reads**, with no sub-threshold data exposed. At
   WBM179's 3.1M classified reads that is 0.0003%; at WBM156's 622k it is 0.0016% — a 5× worse
   floor for that sample.
3. **Library duplication is high** (only ~27–36% of reads unique). Effective library complexity
   is ~1/3 of nominal depth, so the true molecular sensitivity is ~3× worse than read counts
   suggest. This is what makes 10–30-read calls unreliable, and it now has a number attached.
4. **Host depletion.** WBM156 lost 91.3% to host, retaining 622k classified reads — 5× less
   microbial data than WBM179. Its shorter hit list is a depth artifact, not a cleaner tap.
5. **72–90% of clean reads are unclassified — probed, all 5 samples on R1, no dominant unknown.**
   300k reads sampled per sample:

   | Sample | read | unique | GC modes | top 25-mer |
   |---|---|---|---|---|
   | WBM156 | R1 | 79% | 45 / 40 / 50% | 0.26% |
   | WBM174 | R1 | 49% | 35 / 40 / 45% | 0.01% |
   | WBM179 | R1 | 44% | 35 / 40 / 45% | 0.02% |
   | WBM185 | R1 | 48% | 35 / 40 / 70% | 0.01% |
   | **WBM232** | **R1** | **40%** | **35 / 40 / 45%** | **0.011%** |
   | WBM232 (pre-recopy) | R2 | 40% | 35 / 40 / 45% | 0.011% |
   | WBM185 (control) | R2 | 48% | 35 / 40 / 70% | 0.011% |

   WBM232 was initially probed via its R2 mate while R1 was corrupt; after the R1 re-copy (§0)
   the probe was repeated on the real R1 and reproduced the R2 result exactly — same unique
   fraction, same GC modes, same 0.011% top k-mer, with the poly-G artifact absent as expected.

   GC distributions are broad with no sharp single mode, and the most frequent 25-mer occupies
   ~0.01–0.02% of reads. **No dominant unknown organism is hiding in any sample**, WBM232
   included — the unclassified fraction is diffuse unassignable/host-derived sequence.

   *Every k-mer above the noise floor is a library artifact, not an organism.* Inspecting the
   top 4 k-mers per sample rather than the top 1 identifies all of them:

   - **poly-G** (`GGGG…`, 383–417 reads, 0.13–0.14%) — in **both** R2 files, the standard
     2-colour-chemistry no-signal artifact. WBM185 R2 was run as a control and shows the
     identical spike where its R1 does not, confirming it is R2-specific. Excluding it,
     WBM232's next k-mer is 34 reads = 0.011%, in line with every other sample.
   - **Illumina adapter read-through** (`AGATCGGAAGAGCACACGTCTGAAC` and its frame shifts) —
     this is what drives WBM156's outlier profile (79% unique, top k-mer 0.26%, ~13× the
     others). Adapter read-through means short insert sizes, i.e. degraded / low-input DNA,
     which is exactly consistent with WBM156 being the 91%-host, 622k-classified-read sample.
     WBM179 shows the same adapter at 0.02%. **Not** human repeat DNA, and not microbial.

   With both artifacts accounted for, no sample has a genuine sequence over-represented above
   ~0.011% of its unclassified fraction.

   This probe reduces but does not eliminate the novel-agent risk — it would not catch an
   engineered organism present at <0.1% of the unclassified fraction.
6. **Near-neighbour masking** — now largely resolved for anthrax and plague via plasmid-marker
   absence (§1.1, §1.3), and *not* an issue for *Francisella* (no congeners present at all).
7. **No blank / negative extraction control in this batch.** The kitome analysis in §3 is a
   statistical substitute, not a replacement. Trace calls below ~100 reads cannot be formally
   separated from reagent background without a blank.
8. **Presence ≠ viability.** Metagenomic DNA detects dead cells and free DNA equally well.

---

## 6. Recommendations

1. ~~Re-copy the corrupt WBM232 FASTQs.~~ **Done and verified 2026-07-31 (§0).** No data
   integrity issues remain, and the assembly work in recommendation 6 has since been completed.
2. **Culture + AST on WBM232** (*A. baumannii*, ESBL) and **WBM185** (*mecA*, host unknown).
   This is now the *only* remaining route: assembly-based attribution has been attempted and
   returned a definitive "not resolvable" (§2.5), and at 0.25× genome coverage the WBM232
   *lpxA*/*gyrA* point mutations cannot be called from sequence either. These are the only two
   findings that warrant operational follow-up.
3. **Add an RNA library** if viral agents — including Cat A VHFs — are in scope at all. Without
   it, this programme cannot answer the viral question.
4. **Add extraction blanks** to every batch, and set a floor of ≥2M classified reads per sample
   (WBM156 does not meet it).
5. **Report a duplication-aware read threshold**, not just raw reads — a 10-read call backed by
   1 unique sequence is not a detection, and the current report format does not distinguish them.
6. ~~Assembly-based AMR attribution.~~ **Done 2026-07-31 — and it did not resolve the question
   (§2.5).** *blaZ* was successfully placed on a staphylococcal plasmid, but neither *mecA* nor
   CTX-M assembled in either sample, and the classifier had never assigned the resistance-bearing
   mobile elements to a species. **The "MRSA" label is therefore not supported by this dataset and
   should not be used** — see the amended §2.2. Do not re-run assembly on these libraries; the
   limitation is coverage and allele diversity, not assembler choice.
   *Future batches:* collapse the multiple `MEG_` alleles of one gene into a single best-allele
   row in the standard report, and report gene **breadth** alongside depth — the current format
   invites double-counting one gene as three.
7. Optional given the negatives above: a targeted PCR panel (pagA/capB, pla/caf1, tox, ctxA)
   is now largely redundant — the plasmid-marker analysis already excludes anthrax and plague.
   Retain *tox* PCR for WBM179 only.
