# PFI database coverage of CDC Category A / B / C agents

Source: `PFIDB_v5_0.xlsx`, sheet `PFI.all.taxonomy_V5.0` — 27,827 taxon names, one column of names
plus a flag column. **Every row carries `Y`** (27,827/27,827), so the "Human Infection: Y" flag in
the sample reports carries no information: it is a property of being in the database at all, not
of the organism. This confirms item 3 of "Reading the data — four things that will mislead you" in
the README, from the database side.

Composition: 8,749 of 27,827 entries (31%) are viruses or phages.

**Version caveat:** this file is v5.0; the sample reports were generated against **DB v5.1.1**
(software v5.1.2). Coverage below is a lower bound for the database actually used.

---

## Summary

| | Agents checked | In database | Absent |
|---|---|---|---|
| Category A | 21 | 21 | 0 |
| Category B | 17 | 16 | 1 (ricin / *Ricinus communis*) |
| Category C | 12 | 11 | 1 (prions / vCJD) |

**Every CDC agent that has a genome is present.** The two absences are not gaps in curation —
they are agents with no nucleic acid to sequence:

- **Ricin** is a protein toxin from the castor bean. *Ricinus communis* is a plant and is not in a
  pathogen taxonomy. No metagenomic DNA assay can detect ricin.
- **Prions** have no genome at all. Structurally undetectable by sequencing.

Two Category B entries are *toxins* whose producing organisms are present and were screened:
epsilon toxin (*C. perfringens* ✓) and staphylococcal enterotoxin B (*S. aureus* ✓). Presence of
the organism is not presence of the toxin gene — the same distinction made for *bont* in §1.2 of
the assessment.

## Category A — all present

| Agent | Database entry |
|---|---|
| *Bacillus anthracis* | `Bacillus anthracis` (plus *cereus*, *thuringiensis*, *mycoides*) |
| *Clostridium botulinum* | `Clostridium botulinum` (plus *baratii*, *butyricum*, *tetani*) |
| *Yersinia pestis* | `Yersinia pestis` |
| *Francisella tularensis* | `Francisella tularensis` (+13 other *Francisella*) |
| Variola virus | `Variola virus` (plus Monkeypox, Cowpox, Vaccinia, Pseudocowpox) |
| Ebolavirus | 6 entries incl. `Zaire`, `Sudan`, `Bundibugyo`, `Reston`, `Bombali` |
| Marburgvirus | `Marburg marburgvirus` |
| Lassa | `Lassa mammarenavirus` |
| **Junín** | **`Argentinian mammarenavirus`** |
| **Sabiá** | **`Brazilian mammarenavirus`** |
| Machupo / Guanarito / Chapare / Lujo | present under those names + `mammarenavirus` |
| LCMV | `Lymphocytic choriomeningitis mammarenavirus` |
| CCHF | `Crimean-Congo hemorrhagic fever orthonairovirus` |
| Rift Valley fever | `Rift Valley fever phlebovirus` |
| Hantaviruses | 36 orthohantavirus entries |
| Yellow fever / Omsk HF / Kyasanur Forest | all present |

> **Naming trap.** A keyword search for "Junin" or "Sabia" returns **nothing** — those agents are
> filed under current ICTV species names (`Argentinian`/`Brazilian mammarenavirus`). A naive
> string screen of this database would report two Category A agents as uncovered when they are
> not. 45 arenavirus entries in total.

## Category B — 16/17

Present: *Brucella* (17 spp.), *B. mallei*, *B. pseudomallei*, *C. psittaci*, *C. burnetii*,
*C. perfringens*, *S. aureus*, *R. prowazekii*, *Salmonella* (2 spp. + 9 `sp.`), *E. coli*,
*Shigella* (4 spp.), *V. cholerae*, *Cryptosporidium parvum*, VEE, EEE, WEE.
Absent: **ricin / *Ricinus communis***.

## Category C — 11/12

Present: Nipah, Hendra, hantaviruses, SARS-related coronavirus, MERS-related coronavirus,
Influenza A, tick-borne encephalitis virus, rabies/lyssaviruses (17), *M. tuberculosis*,
yellow fever, chikungunya. Absent: **prions / vCJD**.

---

## The two limits that matter more than coverage

### 1. The database is strictly species-level

Only **1 of 27,827** entries contains `subsp.`, `serovar` or `str.`. Consequences for threat
calling:

- **No *E. coli* O157:H7.** The database has `Escherichia coli` and nothing below it. A pathogenic
  STEC serotype cannot be distinguished from commensal *E. coli* by classification alone.
- **No *F. tularensis* subsp. *tularensis* (Type A) vs *holarctica* (Type B)** — the virulence
  distinction that matters operationally.
- **No *Salmonella* serovar Typhi / Typhimurium.**
- ***B. anthracis* sits alongside *B. cereus*, *B. thuringiensis* and *B. mycoides*** at the same
  rank, with no plasmid-level entries. This is precisely why the pXO1/pXO2 marker check in §1.1
  of the assessment was necessary and could not be replaced by a taxonomy lookup.

Category-B/C coverage at *species* level is therefore stronger than coverage at the level the
threat is actually defined.

### 2. Database coverage is not assay coverage

This is a **DNA-only library**. Everything below is in the database and still structurally
undetectable in these five samples:

- **All Category A viral haemorrhagic fevers** — filoviruses, arenaviruses, bunyaviruses,
  flaviviruses are all RNA. 15 of the 21 Category A entries above.
- **All Category B viral encephalitides** — VEE, EEE, WEE are RNA alphaviruses.
- **10 of 12 Category C agents** — Nipah, Hendra, hantavirus, SARS, MERS, influenza, TBE, rabies,
  yellow fever, chikungunya are all RNA.

**Actually screenable by this assay:**

| Category | Screenable | Of |
|---|---|---|
| A | 5 (*B. anthracis*, *C. botulinum*, *Y. pestis*, *F. tularensis*, Variola) | 21 |
| B | 14 (all bacterial + *Cryptosporidium*) | 17 |
| C | 1 (*M. tuberculosis*) | 12 |

Conclusion: **the database is not the limiting factor.** Its Category A/B/C coverage is complete
for every agent with a genome. The limits on this screen are the missing RNA library and the
absence of sub-species resolution — both already recorded in §5 of `biothreat_assessment.md` and
in the README. A "no Category A agent detected" statement remains valid only for the five DNA
agents listed above.
