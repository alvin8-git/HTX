"""Validate analysis/triage.py against the ZymoBIOMICS Microbial Community Standard.

Five reports, one known community. Ground truth from the Zymo data sheet (Cat. DS1706, D6300 /
D6305 / D6306): eight bacteria at 12% gDNA abundance each and two yeasts at 2% each.

This is the only ground truth available in this project, and it tests three things the HTX samples
cannot:
  * sensitivity  - are all ten expected organisms recovered?
  * quantitation - does observed abundance track the theoretical 12/12/12/12/12/12/12/12/2/2?
  * specificity  - the standard contains three organisms that are on the CDC Category B threat
                   list (S. aureus, E. coli, S. enterica) as NON-toxigenic laboratory strains.
                   The engine must detect them and must NOT escalate them. Any ESCALATE here is a
                   false positive on a certified-negative sample.

    python3 analysis/validate_zymo.py
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import triage  # noqa: E402

SAMPLES = ['Zymo/ZymoBac_3ng', 'Zymo/ZymoBac_6ng', 'Zymo/ZymoM_1', 'Zymo/ZymoM_10',
           'Zymo/Zymo_Std_R1']

# Zymo data sheet, "Defined Microbial Community". Aliases cover post-2020 renaming: Lactobacillus
# fermentum -> Limosilactobacillus fermentum, Cryptococcus neoformans -> Cryptococcus deneoformans
# in some builds. Matching stays name-based against the classifier's own namespace.
TRUTH = [
    ('Pseudomonas aeruginosa',  12.0, 66.2, []),
    ('Escherichia coli',        12.0, 56.8, []),
    ('Salmonella enterica',     12.0, 52.2, []),
    ('Lactobacillus fermentum', 12.0, 52.8, ['Limosilactobacillus fermentum']),
    ('Enterococcus faecalis',   12.0, 37.5, []),
    ('Staphylococcus aureus',   12.0, 32.7, []),
    ('Listeria monocytogenes',  12.0, 38.0, []),
    ('Bacillus subtilis',       12.0, 43.8, ['Bacillus spizizenii', 'Bacillus inaquosorum']),
    ('Saccharomyces cerevisiae', 2.0, 38.4, []),
    ('Cryptococcus neoformans',  2.0, 48.2, ['Cryptococcus deneoformans']),
]
EXPECTED = {n for n, _, _, al in TRUTH} | {a for _, _, _, al in TRUTH for a in al}
FP_READ_FLOOR = 1000       # a contaminant below this in a 19M-read library is not worth arguing about


def observed(g):
    """name -> (real reads, abundance %) for one report."""
    return {r['Scientific Name']: (int(r['Real Read']), float(str(r['Abundance']).rstrip('%')))
            for r in g['indentification_DNA']['speciesData']['data']}


def main():
    reports = {s: triage.load_report(s) for s in SAMPLES}
    obs = {s: observed(g) for s, g in reports.items()}
    short = [s.split('/')[1] for s in SAMPLES]

    # ---------------------------------------------------------------- sensitivity + quantitation
    print('=' * 108)
    print('1. SENSITIVITY AND QUANTITATION - observed abundance % (theoretical in brackets)')
    print('=' * 108)
    print(f"{'expected organism':<28}{'theo':>6}{'GC':>6}  " + ''.join(f'{n:>15}' for n in short))
    detected = collections.Counter()
    for name, theo, gc, aliases in TRUTH:
        cells = []
        for s in SAMPLES:
            hit = None
            for cand in [name] + aliases:
                if cand in obs[s]:
                    hit = obs[s][cand]
                    break
            if hit:
                detected[s] += 1
                cells.append(f'{hit[1]:>14.2f}%')
            else:
                cells.append(f'{"NOT FOUND":>15}')
        print(f'{name:<28}{theo:>5.0f}%{gc:>6.1f}  ' + ''.join(cells))
    print(f'\n{"detected / 10":<40}  ' + ''.join(f'{detected[s]:>14}/10' for s in SAMPLES))

    # ---------------------------------------------------------------- specificity
    print('\n' + '=' * 108)
    print(f'2. SPECIFICITY - taxa NOT in the standard, above {FP_READ_FLOOR} real reads')
    print('=' * 108)
    for s, n in zip(SAMPLES, short):
        fp = sorted(((v[0], k) for k, v in obs[s].items()
                     if k not in EXPECTED and v[0] >= FP_READ_FLOOR), reverse=True)
        tot = sum(v[0] for v in obs[s].values())
        fp_reads = sum(r for r, _ in fp)
        print(f'\n  {n}: {len(fp)} taxa, {fp_reads:,} reads = {fp_reads/tot*100:.2f}% of classified')
        for reads, k in fp[:6]:
            print(f'      {reads:>10,}  {reads/tot*100:>6.2f}%  {k}')
        if len(fp) > 6:
            print(f'      ... and {len(fp)-6} more')

    # ---------------------------------------------------------------- the engine's own verdicts
    print('\n' + '=' * 108)
    print('3. TRIAGE VERDICTS - three threat-list organisms are PRESENT AT 12% BY DESIGN')
    print('=' * 108)
    classified = {}
    for s, g in reports.items():
        _, classified[s] = triage.gate_integrity(s, g)
    loads = triage.loads_by_taxon(reports, classified)

    worst = collections.Counter()
    for s, n in zip(SAMPLES, short):
        g = reports[s]
        genes = triage.triage_genes(g)
        taxa = triage.triage_taxa(s, g, loads, genes)
        threat = [t for t in taxa if t['tier'] != '-']
        conf = [x for x in genes if x['verdict'] == 'CONFIRM']
        esc = [t for t in taxa if t['verdict'] == 'ESCALATE']
        worst[s] = len(esc)
        print(f'\n  {n}')
        for t in threat:
            print(f"      {t['verdict']:<10} [{t['tier']}] {t['taxon']:<26} {t['real']:>9,}  {t['why'][:80]}")
        print(f'      AMR: {len(conf)} CONFIRM of {len(genes)} groups')

    print('\n' + '=' * 108)
    print('VERDICT')
    print('=' * 108)
    ok_sens = all(detected[s] == 10 for s in SAMPLES)
    ok_spec = sum(worst.values()) == 0
    print(f'  sensitivity  10/10 organisms in every sample : {"PASS" if ok_sens else "FAIL"}')
    print(f'  specificity  zero ESCALATE on a clean standard: {"PASS" if ok_spec else "FAIL"} '
          f'({sum(worst.values())} escalations)')
    return 0 if (ok_sens and ok_spec) else 1


if __name__ == '__main__':
    sys.exit(main())
