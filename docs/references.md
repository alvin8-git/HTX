# References

All records verified against Europe PMC (2026-08-05); DOIs and page ranges checked, not recalled.

## Unclassified fraction in environmental surface metagenomes

**Afshinnekoo E, Meydan C, Chowdhury S, et al. (2015)** Geospatial resolution of human and
bacterial diversity with city-scale metagenomics. *Cell Systems* 1(1):72–87.
doi:10.1016/j.cels.2015.01.001 — PMID 26594662.
> "Nearly half of the DNA (48%) does not match any known organism."

The NYC subway (PathoMap) study: 1,457 surface swabs of turnstiles, handrails, kiosks and
benches. Directly comparable sample type to this project. **Note the published correction**
(*Cell Systems* 1(1):97–97.e3, doi:10.1016/j.cels.2015.07.006, PMID 27135689): the original
*B. anthracis* and *Y. pestis* calls did not survive re-analysis. Cite it for the unclassified
fraction; it is also the standard cautionary example for trace pathogen calls on transit
surfaces, which is the exact failure mode §4 of the assessment guards against.

**Danko D, Bezdan D, Afshin EE, et al. (2021)** A global metagenomic map of urban microbiomes and
antimicrobial resistance. *Cell* 184(13):3376–3393.e17. doi:10.1016/j.cell.2021.05.002 —
PMID 34043940.
> "…including 10,928 viruses, 1,302 bacteria, 2 archaea, and 838,532 CRISPR arrays **not found in
> reference databases**."

MetaSUB: 4,728 mass-transit samples, 60 cities, 3 years. Establishes that unreferenced sequence
in transit-surface metagenomes is the rule, not a sign of a failed run. The abstract quantifies
novel taxa rather than an unclassified percentage — do not attribute a "% unclassified" figure to
this paper.

## Classification rate as a function of database scope

**Nasko DJ, Koren S, Phillippy AM, Treangen TJ (2018)** RefSeq database growth influences the
accuracy of k-mer-based lowest common ancestor species identification. *Genome Biology* 19:165.
doi:10.1186/s13059-018-1554-6 — PMID 30373669.
> "…more reads are classified with newer database versions, but fewer are classified at the
> species level."

The citable basis for the "against a clinical database" half of the claim: what fraction is
classified is a property of the reference set, not of the sample.

**Breitwieser FP, Lu J, Salzberg SL (2019)** A review of methods and databases for metagenomic
classification and assembly. *Briefings in Bioinformatics* 20(4):1125–1136.
doi:10.1093/bib/bbx120 — PMID 29028872.

**Gu W, Miller S, Chiu CY (2019)** Clinical metagenomic next-generation sequencing for pathogen
detection. *Annual Review of Pathology* 14:319–338.
doi:10.1146/annurev-pathmechdis-012418-012751 — PMID 30355154.

Both for the framing that a clinical mNGS database is curated toward human pathogens and is
narrower than a RefSeq-complete build.

## Low-biomass contamination (already cited in §3)

**Salter SJ, Cox MJ, Turek EM, et al. (2014)** Reagent and laboratory contamination can critically
impact sequence-based microbiome analyses. *BMC Biology* 12:87. doi:10.1186/s12915-014-0087-z —
PMID 25387460.

**Eisenhofer R, Minich JJ, Marotz C, et al. (2019)** Contamination in low microbial biomass
microbiome studies: issues and recommendations. *Trends in Microbiology* 27(2):105–117.
doi:10.1016/j.tim.2018.11.003 — PMID 30497919.

---

## Note on the deck's QC-caveats wording

`analysis/build_deck.py:341` currently reads:

> "Unclassified fractions of 72–90% are normal for environmental swabs against a clinical
> database."

**No publication states this.** The 72–90% range is measured from these five samples; "normal" is
an inference. Citable replacement:

> "A large unclassified fraction is expected for transit-surface swabs — the NYC subway survey
> left 48% of reads unmatched against a comprehensive database (Afshinnekoo 2015), and MetaSUB
> catalogued >12,000 taxa absent from reference databases across 60 cities (Danko 2021). The
> fraction is also set by the reference set, not only the sample: a clinical pathogen database is
> narrower than RefSeq-complete (Nasko 2018). The 72–90% seen here is consistent with both, and
> was probed directly rather than assumed (§5.5)."
