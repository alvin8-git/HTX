# Triage prototype — results against all five samples

Built: `analysis/triage_rules.json` (rule table, no code) + `analysis/triage.py` (evaluator).
Run: `python3 analysis/triage.py` → `analysis/triage_<sample>.tsv` ×5.
Self-check: `python3 analysis/triage.py --selftest` — passes.

**Input: `WBM<id>_en.html`, one file per sample — not the xlsx.** The evaluator brace-matches the
`globalData` object literal out of the Vue SPA, which carries QC (`basicSummary.readsQc`),
taxonomy (`indentification_DNA.speciesData`), AMR (`drugResistance.DNA`) and virulence
(`virulence.DNA`) in a single parse. The per-sample xlsx files hold the same tables but would need
four reads and an `openpyxl` dependency. The extracted FASTQs under `WBM<id>/ExtractRead_DNA/` are
touched only under `--with-fastq`, only for the unique-read fraction, and only for taxa that
survive the earlier gates. This run predates that flag, so the numbers below include gate 6; the
default output no longer does, and the three rows that differ are listed in
[`reference_triage.md`](reference_triage.md#measured-cost-of-the-html-only-default).

Deterministic, stdlib only, no LLM and no ML. Every verdict carries the rule and the numbers that
produced it.

---

## Where it agrees with the human report

| Human conclusion | Engine | Evidence it used |
|---|---|---|
| No CDC Category A agent in any sample | ✅ | Only Cat A hit anywhere is *C. botulinum* in WBM174 |
| *C. botulinum* is an artifact | ✅ `NO_ACTION` | 11 reads < min 50; `bont` absent — either alone suffices. (Unique fraction 9% adds a third, under `--with-fastq`.) |
| *mecA* = MEG_3778, not MEG_3770/3780 | ✅ | Collapsed 3 alleles, picked max(breadth, depth) — same allele |
| CTX-M = MEG_2430 over MEG_2435 (WBM185) | ✅ | Same collapsing rule, 82.88%/7.25× |
| *mecA* host unresolved → not MRSA | ✅ `CONFIRM`, never `ESCALATE` | Cap rule: acquired gene with no attributed host |
| WBM179 *mecI* is not resistance | ✅ suppressed | Regulator with no MECA in sample |
| WBM232 LpxA is not colistin resistance | ✅ suppressed | `core_essential` |
| WBM232 AdeJ is intrinsic | ✅ suppressed | `intrinsic` |
| *E. coli*, *V. cholerae*, *C. perfringens* not actionable | ✅ | Confirmatory markers absent |
| Bracken estimates inflated | ✅ flagged | e.g. WBM185 *E. coli* 115× over 105 real reads |
| RNA agents untested, not absent | ✅ `NOT_TESTED` | `showRNA=False` |
| rRNA / efflux / point-mutation rows are noise | ✅ | 11–32 rows suppressed per sample |

Suppression is where most of the value is. WBM179's 72 AMR rows reduce to **2** `CONFIRM` calls;
32 rows are dismissed as conserved rRNA, ubiquitous efflux, point-mutation-dependent, or orphan
regulators.

## Where it disagrees — and the human is right

**1. ~~WBM232 CTX-M scored `MONITOR`~~ — FIXED with per-class gating.**

Originally CTX-M's 60.56% breadth fell under a single global 80% gate despite 11.69× depth, and
WBM232 — the sample carrying the project's headline finding — produced **no `CONFIRM` at all**.

The mistake was treating breadth and depth as one axis. **PFI reports depth over *covered* bases**,
so the two are decoupled: a gene can sit at 11.69× across 60% of the reference allele. That is not
a weak hit. It is a real, well-sequenced gene fragment — what is uncertain is *which allele*, not
*whether it is there*. Low breadth at low depth means something different from low breadth at high
depth, and one threshold cannot express that.

Fix: two routes to a call, resolved group → class → global (`class_thresholds` /
`group_thresholds` in the rules file).

| Route | Condition (acquired default) | Reported as |
|---|---|---|
| Full length | breadth ≥ 80% **and** depth ≥ 5× | `acquired, full length` |
| Fragment | breadth ≥ 55% **and** depth ≥ 10× | `acquired, PARTIAL — family established, allele not` |

Group overrides carry their reason in a `why` field, so a threshold can be argued with rather than
merely obeyed:

- **`CTX`, `MECA`** — fragment depth relaxed to 8×. Both are clinically decisive; missing a real
  ESBL or a real *mecA* costs more than over-calling one, and a partial hit still warrants culture.
- **`BLAZ`** — raised to 85%/8× with the **fragment route disabled**. Staphylococcal penicillinase
  is near-universal background and must not crowd out real findings.

Result: **WBM232 CTX-M (MEG_2378) is now `CONFIRM`, reported as partial**, and WBM232 yields 5
`CONFIRM` calls — CTX-M plus `ant(3'')-IIa`, `aac(6')`, `aph(3'')` and `erm(X)`, which is the
integron-borne cassette picture the manual analysis described.

**The cost, stated plainly:** `CONFIRM` calls rose from 20 to 31 across the five samples
(WBM174 +4, WBM179 +2, WBM232 +5; WBM156 and WBM185 unchanged). This trades precision for recall,
which is the right direction for a *triage* front-end whose terminal state is "culture this" — but
it is a real increase in what a human must read. The `BLAZ` override pushes in the other
direction, and correctly demoted WBM185's *blaZ* (70.65%/8.17×) and WBM179's (74.91%/2.49×) out of
`CONFIRM`, matching the manual reading that both are unremarkable background.

**Not yet calibrated.** These numbers are reasoned, not fitted — there is no culture-confirmed set
to fit them against. That remains the top prerequisite for operational use.

**2. ~~Rule coverage is incomplete~~ — RESOLVED, then resolved properly.**

| Sample | Originally | After hand-annotation | Now (mechanism map) |
|---|---|---|---|
| WBM156 | 17/24 | 24/24 | **24/24** |
| WBM174 | 31/48 | 48/48 | **48/48** |
| WBM179 | 47/47 | 47/47 | **47/47** |
| WBM185 | 30/52 | 52/52 | **52/52** |
| WBM232 | 22/47 | 47/47 | **47/47** |

The first pass added 55 hand-written group entries, reaching 108/108 on the HTX samples. **That
number did not survive contact with a deeper library** — the Zymo standards surface 315–318 groups
and left 287 unannotated. The durable fix classifies by MEGARes `Type`/`Mechanism` instead of by
group name: **115 (Type, Mechanism) pairs span all 397 distinct groups**, with hand-written group
entries kept as authoritative overrides and a keyword fallback behind both. See
[`zymo_validation.md`](zymo_validation.md) §D3 and
[`reference_triage.md`](reference_triage.md#rule-file--analysistriage_rulesjson).

A new `environmental` class covers metal and biocide resistance (copper, mercury, arsenic,
cadmium, silver, `qacG`) — real, but not clinically actionable, so suppressed. The *Acinetobacter*
efflux family (`ADEG/H/L/T1/T2`, `ABAF`, `ABAQ`, `ABUO`, `AMVA`) is `intrinsic`: WBM232's
suppressed-intrinsic count went from 2 to 12.

### What the new annotations surfaced

**`mupA` in WBM185 — 90.18% breadth / 11.70× depth, `CONFIRM`. This is a new finding.** *mupA* is
a second, plasmid-borne isoleucyl-tRNA synthetase conferring **high-level mupirocin resistance**.
Mupirocin is the standard nasal decolonisation agent for MRSA carriage, so *mupA* predicts
decolonisation failure. It sits on the same check-in-kiosk touchscreen as the *mecA* signal
(90.89%/10.51×) and it is absent from the manual report entirely. Host is unattributed, as ever —
so `CONFIRM`, not `ESCALATE` — but it belongs in any follow-up culture request.

**A new rule class for repressors whose loss-of-function *is* the mechanism.** Where such a
regulator appears with its pump present, it now surfaces as `MONITOR` instead of being suppressed
with the intrinsic pumps:

| Sample | Gene | Breadth / depth | Why it matters |
|---|---|---|---|
| WBM232 | **`adeN`** (MEG_702) | 85.76% / 8.85× | Repressor of AdeIJK. LOF de-represses the pump — the exact mechanism §2.1 said DNA could not assess. Presence doesn't prove overexpression; it names the gene worth sequencing deeper. |
| WBM232 | `mexT` (MEG_3934) | 79.47% / 15.77× | Activator of MexEF-OprN. |
| WBM232 | `adeL` (MEG_700) | 52.52% / 3.55× | Regulator of AdeFGH. |
| WBM185 | `adeS` (MEG_704) | 50.51% / 1.94× | AdeRS sensor kinase. Weak — near the breadth floor. |

The intrinsic pumps themselves stay suppressed. That is the intended split: *"intrinsic pump,
ignore"* versus *"here is the testable one"*.

**Two further `CONFIRM` calls that did not exist before:** `aph(6)-Id` in WBM174
(80.14%/14.64×) and `erm(F)` in WBM156 (83.38%/7.12× — WBM156's only `CONFIRM`).

**Integron markers are now readable.** `qacEΔ1` is annotated as the 3'-conserved segment of class 1
integrons rather than as a biocide gene, and `ant(3'')-Ia`/`sul2` as the cassettes that ride with
it. WBM232 carries `ant(3'')-Ia` at 20.94× depth and `sul2`, which is the expected signature of a
mobilised resistance platform.

**3. Enrichment is not actionability.** Non-threat taxa enriched ≥5× produce 17–96 hits per
sample — WBM156's 57 are one oral-flora community on a tap, not 57 findings. Output caps the list
at 8 and reports the remainder as a community shift; the full list goes to the TSV. A real fix
needs a clinical-relevance annotation per taxon, which does not exist for 1,463 species.

**3b. ~~The threat list is CDC-only, so a clinically serious organism cannot exceed MONITOR~~ —
FIXED.** Found by comparing the HTML report against the briefing deck: the deck called WBM232
`ESCALATE`, the report showed *A. baumannii* at `MONITOR`, and the reason was structural rather
than evidential. `threat_list` is exclusively CDC Category A/B/C, so *A. baumannii* took the
non-threat path, whose only outcomes are `NO_ACTION` and `MONITOR`. Measured across all five
samples before the fix: **257 `MONITOR`, 3 `NO_ACTION`, and not one non-threat taxon above
`MONITOR` in any sample.** The engine had no way to say *"clinically serious, not a bioweapon"*.

A `clinical_watchlist` (24 organisms, WHO priority list + ESKAPE) now carries those, with a
ceiling of `CONFIRM` — `ESCALATE` stays reserved for a CDC agent with its confirmatory marker.
WBM232's *A. baumannii* reaches `CONFIRM` on evidence that was already in the data: 6× enriched,
27% unique, 121 distinct virulence factors, and co-located acquired resistance. See
[`reference_triage.md`](reference_triage.md#clinical_watchlist--24-organisms).

**3c. Sample-level verdict added.** The deck carried one verdict per swab and the row tiers had no
equivalent, so a reader comparing the two saw an apparent downgrade that was really a change of
subject. `sample_verdict()` rolls the rows up:

| Sample | Deck (human) | Engine (at the time) | Engine (current) |
|---|---|---|---|
| WBM156 | NO ACTION | **MONITOR** | MONITOR |
| WBM174 | MONITOR | MONITOR | **NO ACTION** |
| WBM179 | MONITOR | MONITOR | **NO ACTION** |
| WBM185 | INVESTIGATE | INVESTIGATE | INVESTIGATE |
| WBM232 | ESCALATE | **INVESTIGATE** | INVESTIGATE |

The third column is the 2026-08-12 rule change: `MONITOR` now needs a positive driver — a
site-enriched listed organism, or one topping the host pool of an acquired `CONFIRM` gene. WBM174
and WBM179 have neither. See
[`reference_triage.md`](reference_triage.md#sample-verdict).

Three of five identical against the deck at the time. WBM156 differs because the engine reports watchlist organisms
(*S. maltophilia*, *P. aeruginosa*, *Providencia*) that a human read as ordinary water flora on a
restroom tap. WBM232 differs by design: a watchlist organism cannot drive a sample past
`INVESTIGATE`.

**4. Marker logic conflates the bioweapon with the organism.** *S. aureus* is `NO_ACTION` in all
five samples because `seb` is absent — correct for *"staphylococcal enterotoxin B as a Category B
agent"*, wrong as a summary of *S. aureus* in WBM185, where it co-occurs with *mecA* at
90.89%/10.51×. The engine has **no rule linking a taxon to a gene** — which is the host-attribution
gap, restated. It cannot be closed by better rules; §2.5 showed assembly cannot close it either.

## Verdict

The prototype reproduces the routine determinations and, on WBM232's *adeN*, found something the
manual analysis did not. It fails on exactly one substantive call (WBM232 CTX-M), for a
diagnosable and fixable reason.

Judgement: **usable as a triage front-end that filters noise and ranks what a human should read
first — not as an autonomous classifier.** Before operational use it needs (a) per-class gene
thresholds — **implemented, not yet calibrated**; the values are reasoned, and fitting them needs
culture-confirmed samples, ~~(b) the remaining MEGARes groups annotated~~ — **done via the
mechanism map, 0 unannotated at any depth tested**, (c) a negative extraction control to set the
contamination floor empirically.

Since this was written the engine has been measured against a certified standard
([`zymo_validation.md`](zymo_validation.md)): sensitivity 10/10, zero false escalations,
quantitation MAE 1.01 pp — and nine false-positive AMR `CONFIRM` calls that no rule can fix,
because they are the host-attribution gap in a different costume.

With the annotations complete it has now produced **two things the manual analysis did not**:
*mupA* in WBM185, and *adeN* in WBM232. Both need culture to act on, and neither changes the
headline result — but both belong in the follow-up request.
