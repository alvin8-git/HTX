"""Deterministic triage of a PFI metagenomic report. No LLM, no ML.

Reads WBM<id>_en.html (the embedded `globalData` object) and applies the gate cascade in
docs/automated_triage_design.md. Every verdict carries the rule that produced it.

    python3 analysis/triage.py                 # all five samples
    python3 analysis/triage.py WBM232          # one sample
    python3 analysis/triage.py --selftest      # rule checks, no data needed

Output: analysis/triage_<sample>.tsv per sample, plus a summary on stdout.

Design constraints, deliberate:
  * Tiers, never diagnoses. The terminal state for a real finding is CONFIRM (culture + AST).
  * NOT_TESTED never collapses into NO_ACTION. An RNA agent against a DNA library is untested.
  * An AMR gene with no attributed host caps at CONFIRM. Host attribution is unsolved here
    (docs/biothreat_assessment.md 2.5) and no rule fixes a missing measurement.
"""
import collections
import gzip
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = json.load(open(os.path.join(ROOT, 'analysis', 'triage_rules.json')))
TH = RULES['thresholds']
SAMPLES = ['WBM156', 'WBM174', 'WBM179', 'WBM185', 'WBM232']

# Tier ordering, lowest to highest. NOT_TESTED sits outside the ladder: it is an absence of
# evidence, not a weak positive, so it must never be compared against or downgraded to NO_ACTION.
TIERS = ['NO_ACTION', 'MONITOR', 'CONFIRM', 'ESCALATE']


def load_report(sample):
    """Pull the globalData object literal out of the Vue SPA by brace matching."""
    path = os.path.join(ROOT, f'{sample}_en.html')
    html = open(path, encoding='utf-8', errors='replace').read()
    i = html.find('globalData:')
    if i < 0:
        raise ValueError(f'{sample}: no globalData in report')
    j = html.find('{', i)
    depth = 0
    for k in range(j, len(html)):
        if html[k] == '{':
            depth += 1
        elif html[k] == '}':
            depth -= 1
            if depth == 0:
                return json.loads(html[j:k + 1])
    raise ValueError(f'{sample}: unbalanced globalData')


# ---------------------------------------------------------------- gate 12: input integrity

def gate_integrity(sample, g):
    """Cheap, real checks. Returns list of problems; a non-empty list means do not trust the run."""
    problems = []
    stat = g['basicSummary']['readsQc']['data'][0]
    num = lambda s: int(str(s).split(' ')[0].replace(',', ''))
    clean, unclass, clas = num(stat['Clean_Read']), num(stat['Unclassified_Read']), num(stat['Classified_Read'])
    if unclass + clas != clean:
        problems.append(f'read partition does not sum: {unclass}+{clas} != {clean}')
    # Distinguish "not delivered" from "delivered broken". A report supplied without its FASTQs is
    # a normal delivery, not a corrupt one, and must not read as four failures.
    paths = [os.path.join(ROOT, sample, f'{kind}.DNA_{mate}.fq.gz')
             for mate in (1, 2) for kind in ('unclassify', 'removehost')]
    if not any(os.path.exists(p) for p in paths):
        problems.append('NOTE: no FASTQs delivered alongside this report - integrity and '
                        'unique-read gates cannot run; verdicts rest on the report tables alone')
    else:
        for p in paths:
            if not os.path.exists(p):
                problems.append(f'missing {os.path.basename(p)}')
            elif os.path.getsize(p) == 0:
                problems.append(f'empty {os.path.basename(p)}')
    if not g.get('showRNA'):
        problems.append('NOTE: DNA-only run - RNA agents are untested, and no species can be '
                        'called active (speciesActivity is empty by construction)')
    return problems, clas


# ---------------------------------------------------------------- gate 6: amplification

def unique_fraction(sample, taxon):
    """Fraction of distinct sequences in a taxon's extracted reads. Computed lazily - only for
    taxa that survive the earlier gates, so the cost stays trivial."""
    d = taxon.replace(' ', '_').replace('/', '_')
    path = os.path.join(ROOT, sample, 'ExtractRead_DNA', 'Species', d, f'{d}_1.fq.gz')
    if not os.path.exists(path):
        return None, None
    seen, n = set(), 0
    with gzip.open(path, 'rt') as fh:
        for i, line in enumerate(fh):
            if i % 4 != 1:
                continue
            n += 1
            if n > TH['unique_probe_reads']:
                break
            seen.add(line.strip())
    return (len(seen) / n if n else None), n


# ---------------------------------------------------------------- gate 8: cross-sample load

def loads_by_taxon(reports, classified):
    """Depth-normalised load: real reads per million classified reads, per taxon per sample.
    Normalising is what makes WBM156 (622k classified) comparable to WBM232 (2.59M)."""
    out = collections.defaultdict(dict)
    for s, g in reports.items():
        for r in g['indentification_DNA']['speciesData']['data']:
            out[r['Scientific Name']][s] = int(r['Real Read']) / classified[s] * 1e6
    return out


def enrichment(loads, taxon, sample):
    """Fold-enrichment of this sample's load over the highest of the others. inf = seen only here."""
    per = loads[taxon]
    others = [v for s, v in per.items() if s != sample and v > 0]
    if not others:
        return float('inf')
    return per.get(sample, 0.0) / max(others)


# ---------------------------------------------------------------- markers

def marker_present(g, marker):
    """Search the VFDB table for a marker's pattern. Returns (found, evidence)."""
    pat = re.compile(RULES['marker_patterns'].get(marker, re.escape(marker)), re.I)
    vf = g.get('virulence', {}).get('DNA', {})
    rows = vf.get('data', []) if isinstance(vf, dict) else []
    for r in rows:
        if pat.search(json.dumps(r)):
            return True, str(r.get('Gene', r))[:40]
    return False, ''


# ---------------------------------------------------------------- gates 3-5: AMR genes

# Keyword fallback for a (Type, Mechanism) pair never seen before. Ordered — first match wins.
# This is what stops a deeper library, or a newer MEGARes release, from producing 'unannotated'.
_MECH_FALLBACK = [
    (r'-resistant (mutation|mutant|dna topoisomerases|beta-subunit|isoleucyl)|\bmutant\b|'
     r'target mutation|resistant mprf', 'point_mutation'),
    (r'ribosomal subunit protein|rrna mutation', 'rrna_conserved'),
    (r'regulator|repressor', 'regulator'),
    (r'efflux', 'efflux_ubiquitous'),
    (r'lipid a modification|undecaprenyl', 'intrinsic'),
    (r'penicillin binding protein$|ef-tu|ribosomal zinc-binding', 'point_mutation'),
    (r'transferase|betalactamase|reductase|synthase', 'acquired'),
]


def annotate_group(group, type_, mechanism):
    """Resolve a MEGARes group to a class: group override -> mechanism map -> keyword fallback.

    Hand-written group entries stay authoritative — they encode host-specific knowledge the
    mechanism string cannot carry (adeJ is intrinsic only because its host is A. baumannii). The
    mechanism map covers the rest: 115 (Type, Mechanism) pairs span 397 distinct groups.
    """
    if group in RULES['amr_classes']:
        return RULES['amr_classes'][group]
    key = f'{type_}|{mechanism}'
    cls = RULES['mechanism_classes'].get(key)
    if cls:
        return {'class': cls, 'note': f'classified by mechanism: {mechanism} ({type_}). '
                                      f'No group-specific rule for {group}.'}
    ml = (mechanism or '').lower()
    if type_ in ('Metals', 'Biocides'):
        return {'class': 'environmental', 'note': f'{type_} resistance ({mechanism}) - not clinically actionable.'}
    for pat, c in _MECH_FALLBACK:
        if re.search(pat, ml):
            return {'class': c, 'note': f'keyword fallback on mechanism "{mechanism}" - '
                                        f'no rule for {group}, and this pair is new to the map.'}
    return {'class': 'unannotated', 'note': f'No rule for {group}, and mechanism "{mechanism}" '
                                            f'({type_}) matched nothing. Add it to the rule file.'}


def gene_thresholds(group, cls):
    """Resolve thresholds: group override -> class default -> global default."""
    t = dict(RULES['class_thresholds'].get('_default', {}))
    t.update(RULES['class_thresholds'].get(cls, {}))
    t.update({k: v for k, v in RULES['group_thresholds'].get(group, {}).items()
              if k not in ('why', '_comment')})
    return t


def triage_genes(g):
    """Collapse MEGARes alleles to one call per Group, then classify. Returns list of dicts."""
    rows = g.get('drugResistance', {}).get('DNA', {}).get('data', [])
    by_group = collections.defaultdict(list)
    for r in rows:
        by_group[r['Group']].append(r)

    pct = lambda v: float(str(v).rstrip('%') or 0)
    out = []
    for grp, alleles in by_group.items():
        # gate 3: one real gene recruits reads onto several accessions. The representative call
        # is the allele with the highest breadth AND depth; the rest are partial cross-mapping.
        best = max(alleles, key=lambda r: (pct(r['Coverage(%)']), float(r['Depth'])))
        breadth, depth = pct(best['Coverage(%)']), float(best['Depth'])
        ann = annotate_group(grp, best.get('Type', ''), best.get('Mechanism', ''))
        cls = ann['class']

        # gate 4: breadth separates a real gene from a conserved fragment.
        if breadth < TH['gene_breadth_floor']:
            verdict, why = 'NO_ACTION', f'breadth {breadth:.1f}% below floor'
        elif cls in ('rrna_conserved', 'efflux_ubiquitous', 'point_mutation', 'core_essential',
                     'intrinsic', 'environmental'):
            verdict, why = 'NO_ACTION', f'{cls}: presence is the default state'
        elif cls == 'regulator':
            need = ann.get('requires')
            if need and need not in by_group:
                verdict, why = 'NO_ACTION', f'regulator with no {need} in this sample - incoherent as a resistance call'
            elif ann.get('actionable_when_partner'):
                # A repressor whose loss-of-function IS the resistance mechanism. Presence does not
                # prove overexpression - it names the gene worth sequencing deeper. Surfacing this
                # is the difference between "intrinsic pump, ignore" and "here is the testable one".
                verdict = 'MONITOR'
                why = (f'repressor of {need or "its operon"}, present at {breadth:.1f}%/{depth:.2f}x - '
                       'loss-of-function here is the resistance mechanism; target for variant calling')
            else:
                verdict, why = 'NO_ACTION', f'regulator; partner {need} present'
        elif cls == 'acquired':
            t = gene_thresholds(grp, cls)
            # Host is never attributable from this data, so an acquired gene caps at CONFIRM.
            if breadth >= t['breadth'] and depth >= t['depth']:
                verdict = 'CONFIRM'
                why = f'acquired, full length: breadth {breadth:.1f}% depth {depth:.2f}x'
            elif depth >= t.get('partial_depth', 1e9) and breadth >= t.get('partial_breadth', 1e9):
                # Depth is reported over covered bases, so high depth on a fragment means the gene
                # is really there and well sequenced - only the allele is uncertain.
                verdict = 'CONFIRM'
                why = (f'acquired, PARTIAL: {breadth:.1f}% of the reference allele at {depth:.2f}x '
                       f'- gene family established, specific allele not')
            else:
                verdict = 'MONITOR'
                why = (f'acquired, breadth {breadth:.1f}% depth {depth:.2f}x - below '
                       f'{t["breadth"]:.0f}%/{t["depth"]:.0f}x and the partial route')
        else:
            verdict, why = 'MONITOR', 'unannotated group - needs a rule'

        out.append({'group': grp, 'allele': best['Gene'], 'alleles_collapsed': len(alleles),
                    'breadth': breadth, 'depth': depth, 'class': cls,
                    'verdict': verdict, 'why': why, 'note': ann['note']})
    return sorted(out, key=lambda r: (-TIERS.index(r['verdict']), -r['breadth']))


# ---------------------------------------------------------------- gates 1,2,7,9,10,11: taxa

def triage_taxa(sample, g, loads, genes_by_group, comparators=True):
    """comparators=False when there is nothing to compare against (a single novel sample, or a set
    of replicates of one community). Gate 8 is then inert, and non-threat taxa are reported on read
    count alone. Threat-list gating is unaffected — it never depended on cross-sample context."""
    results = []
    threat, notes = RULES['threat_list'], RULES['taxonomy_notes']
    present = {r['Scientific Name']: int(r['Real Read'])
               for r in g['indentification_DNA']['speciesData']['data']}

    for r in g['indentification_DNA']['speciesData']['data']:
        name, real = r['Scientific Name'], int(r['Real Read'])
        est = int(r['Estimate Read'])
        t = threat.get(name)
        why = []

        # gate 11: emit the reclassification note whatever else happens.
        if name in notes:
            why.append('TAXONOMY: ' + notes[name])

        # gate 2: Bracken redistribution can inflate an estimate far beyond the real reads.
        if real and est / real > TH['bracken_inflation_ratio']:
            why.append(f'estimate inflated {est/real:.0f}x over {real} real reads - judged on real')

        if not t:
            # Non-threat taxa are only worth reporting when site-specific and substantial.
            if real < TH['min_real_reads']:
                continue
            fold = enrichment(loads, name, sample) if comparators else None
            genus = name.split(' ')[0]
            if fold is not None:
                if fold < TH['enrichment_fold']:
                    continue                      # includes the kitome genera, which never enrich
            elif genus in RULES['kitome_genera']:
                continue                          # no enrichment test available: fall back to the list
            uf, n = unique_fraction(sample, name)
            if uf is not None and uf < TH['unique_fraction_floor']:
                results.append({'taxon': name, 'tier': '-', 'real': real, 'verdict': 'NO_ACTION',
                                'why': f'unique fraction {uf:.0%} of {n} reads - amplification artifact'})
                continue
            why.append('no comparator samples - reported on read count alone, NOT shown to be '
                       'site-specific' if fold is None else
                       (f'{fold:.0f}x enriched vs other samples' if fold != float('inf')
                        else 'detected only in this sample'))
            if uf is not None:
                why.append(f'unique fraction {uf:.0%}')
            results.append({'taxon': name, 'tier': '-', 'real': real, 'verdict': 'MONITOR',
                            'why': '; '.join(why)})
            continue

        # --- threat-list agent ---
        # gate 2 (assay detectability). Must be decided BEFORE read count: an RNA agent at zero
        # reads is untested, not absent, and must never fall through to NO_ACTION.
        if t['genome'] == 'RNA' and not g.get('showRNA'):
            results.append({'taxon': name, 'tier': t['tier'], 'real': real, 'verdict': 'NOT_TESTED',
                            'why': 'RNA genome, DNA-only library - structurally undetectable'})
            continue

        if real < TH['min_real_reads']:
            why.append(f'{real} reads, below min {TH["min_real_reads"]}')
            uf, n = unique_fraction(sample, name)
            if uf is not None:
                why.append(f'unique fraction {uf:.0%} of {n} reads'
                           + (' - amplification artifact' if uf < TH['unique_fraction_floor'] else ''))
            verdict = 'NO_ACTION'
        else:
            verdict = 'CONFIRM'

        # gate 9: near-neighbour co-detection at comparable depth undermines the call.
        for nb in t['near_neighbours']:
            if present.get(nb, 0) >= real:
                why.append(f'near-neighbour {nb} at {present[nb]} reads >= this taxon - '
                           'cross-mapping cannot be excluded')
                verdict = 'NO_ACTION' if verdict == 'CONFIRM' else verdict

        # gate 10: confirmatory marker. Absent = downgrade, present = escalate.
        found = []
        for m in t['markers']:
            ok, ev = marker_present(g, m)
            if ok:
                found.append(f'{m}({ev})')
        if t['markers']:
            if found:
                why.append('MARKER PRESENT: ' + ', '.join(found))
                verdict = 'ESCALATE'
            else:
                why.append(f'confirmatory marker(s) {"/".join(t["markers"])} ABSENT - downgraded')
                verdict = 'NO_ACTION' if verdict != 'ESCALATE' else verdict
        elif t.get('subspecies_required') and verdict == 'CONFIRM':
            # The species-level call is not the finding: the threat is defined below species and
            # this database cannot go there. Found by the Zymo standard, where the certified
            # laboratory S. enterica strain scored CONFIRM at 12% abundance in all five samples.
            verdict = 'MONITOR'
            why.append(f'species-level identification only - needs {t["subspecies_required"]}')

        results.append({'taxon': name, 'tier': t['tier'], 'real': real,
                        'verdict': verdict, 'why': '; '.join(why) or 'threat-list agent'})

    return sorted(results, key=lambda r: (-TIERS.index(r['verdict']) if r['verdict'] in TIERS else 99,
                                          -r['real']))


# ---------------------------------------------------------------- driver

def run(samples, comparators=None):
    reports = {s: load_report(s) for s in samples}
    classified, integrity = {}, {}
    for s, g in reports.items():
        integrity[s], classified[s] = gate_integrity(s, g)
    loads = loads_by_taxon(reports, classified)
    if comparators is None:
        comparators = len(samples) > 1
    if not comparators:
        print('  [gate 8] single sample - cross-sample enrichment is inert; non-threat taxa are '
              'reported on read count alone and are NOT shown to be site-specific.')

    for s in samples:
        g = reports[s]
        genes = triage_genes(g)
        taxa = triage_taxa(s, g, loads, {x['group'] for x in genes}, comparators)

        print(f'\n{"="*100}\n{s}   classified={classified[s]:,}\n{"="*100}')
        for p in integrity[s]:
            print(f'  [integrity] {p}')

        print('\n  -- TAXA ' + '-'*90)
        shown = 0
        for r in taxa:
            if r['verdict'] == 'NO_ACTION' and r['tier'] == '-':
                continue
            # Enrichment alone is not actionability: a sample can carry a whole shifted community
            # (WBM156 is oral flora on a tap). Cap the non-threat list and report the remainder
            # rather than truncating silently. Everything lands in the TSV either way.
            if r['tier'] == '-':
                shown += 1
                if shown > 8:
                    continue
            print(f"  {r['verdict']:<10} {r['tier']:<2} {r['taxon'][:44]:<44} {r['real']:>8,}  {r['why'][:150]}")
        if shown > 8:
            word = 'enriched ' if comparators else ''
            print(f'  ... and {shown-8} further {word}non-threat taxa (see TSV) - a community '
                  f'shift, not {shown} separate findings')

        print('\n  -- AMR GENES ' + '-'*85)
        for r in genes:
            if r['verdict'] == 'NO_ACTION':
                continue
            print(f"  {r['verdict']:<10} {r['group']:<12} {r['allele']:<10} "
                  f"{r['breadth']:>6.2f}% {r['depth']:>7.2f}x  x{r['alleles_collapsed']}  {r['why'][:90]}")
        supp = collections.Counter(r['class'] for r in genes if r['verdict'] == 'NO_ACTION')
        unann = [r['group'] for r in genes if r['class'] == 'unannotated']
        print(f"  suppressed: {dict(supp)}")
        print(f"  rule coverage: {len(genes)-len(unann)}/{len(genes)} MEGARes groups annotated; "
              f"{len(unann)} need a rule: {' '.join(sorted(unann)[:14])}")

        out = os.path.join(ROOT, 'analysis', f'triage_{s.replace("/", "_")}.tsv')
        with open(out, 'w') as fh:
            fh.write('kind\tverdict\tcdc_tier\tname\tevidence\treason\tnote\n')
            for r in taxa:
                fh.write(f"taxon\t{r['verdict']}\t{r['tier']}\t{r['taxon']}\t{r['real']} reads\t{r['why']}\t\n")
            for r in genes:
                fh.write(f"amr\t{r['verdict']}\t\t{r['group']} ({r['allele']})\t"
                         f"{r['breadth']:.2f}% {r['depth']:.2f}x collapsed {r['alleles_collapsed']}\t"
                         f"{r['why']}\t{r['note']}\n")
        print(f'  -> {os.path.relpath(out, ROOT)}')


def selftest():
    """One runnable check per non-trivial rule. Fails loudly if the logic drifts."""
    r = RULES
    assert r['amr_classes']['MECI']['requires'] == 'MECA'
    assert r['amr_classes']['ADEJ']['class'] == 'intrinsic'
    assert r['amr_classes']['LPXA']['class'] == 'core_essential'
    assert r['amr_classes']['CTX']['class'] == 'acquired'
    # The naming trap: colloquial names must NOT be in the table, PFIDB names must be.
    assert 'Junin virus' not in r['threat_list']
    assert 'Argentinian mammarenavirus' in r['threat_list']
    assert 'Brazilian mammarenavirus' in r['threat_list']
    # NOT_TESTED must sit outside the tier ladder so it can never be compared into NO_ACTION.
    assert 'NOT_TESTED' not in TIERS
    # Allele collapsing picks the allele that is best on BOTH axes.
    fake = {'drugResistance': {'DNA': {'data': [
        {'Group': 'MECA', 'Gene': 'MEG_3778', 'Coverage(%)': '90.89%', 'Depth': '10.51'},
        {'Group': 'MECA', 'Gene': 'MEG_3770', 'Coverage(%)': '58.52%', 'Depth': '6.68'},
        {'Group': 'MECA', 'Gene': 'MEG_3780', 'Coverage(%)': '59.77%', 'Depth': '2.83'}]}}}
    got = triage_genes(fake)[0]
    assert got['allele'] == 'MEG_3778' and got['alleles_collapsed'] == 3, got
    assert got['verdict'] == 'CONFIRM', got            # never ESCALATE: host is unattributed
    # mecI without mecA must be dismissed, with mecA present it is merely uninformative.
    solo = triage_genes({'drugResistance': {'DNA': {'data': [
        {'Group': 'MECI', 'Gene': 'MEG_3804', 'Coverage(%)': '74.93%', 'Depth': '1.62'}]}}})[0]
    assert solo['verdict'] == 'NO_ACTION' and 'no MECA' in solo['why'], solo
    # A repressor whose loss-of-function is the mechanism must surface when its pump is present,
    # and stay silent when it is not. This is the adeN / AdeIJK case.
    aden = {'Group': 'ADEN', 'Gene': 'MEG_702', 'Coverage(%)': '85.76%', 'Depth': '8.85'}
    adej = {'Group': 'ADEJ', 'Gene': 'MEG_692', 'Coverage(%)': '53.72%', 'Depth': '5.30'}
    pair = {r['group']: r for r in triage_genes({'drugResistance': {'DNA': {'data': [aden, adej]}}})}
    assert pair['ADEN']['verdict'] == 'MONITOR', pair['ADEN']
    assert pair['ADEJ']['verdict'] == 'NO_ACTION', pair['ADEJ']   # intrinsic pump stays suppressed
    lone = triage_genes({'drugResistance': {'DNA': {'data': [aden]}}})[0]
    assert lone['verdict'] == 'NO_ACTION', lone
    # Metal/biocide resistance is real but not clinically actionable.
    merc = triage_genes({'drugResistance': {'DNA': {'data': [
        {'Group': 'MERT', 'Gene': 'MEG_3895', 'Coverage(%)': '88.51%', 'Depth': '2.03'}]}}})[0]
    assert merc['verdict'] == 'NO_ACTION' and merc['class'] == 'environmental', merc
    # Per-class gating: WBM232 CTX-M is a fragment at high depth and must reach CONFIRM...
    ctx = triage_genes({'drugResistance': {'DNA': {'data': [
        {'Group': 'CTX', 'Gene': 'MEG_2378', 'Coverage(%)': '60.56%', 'Depth': '11.69'}]}}})[0]
    assert ctx['verdict'] == 'CONFIRM' and 'PARTIAL' in ctx['why'], ctx
    # ...but a fragment at low depth must NOT. The route requires depth, not just breadth.
    weak = triage_genes({'drugResistance': {'DNA': {'data': [
        {'Group': 'CTX', 'Gene': 'MEG_2378', 'Coverage(%)': '60.56%', 'Depth': '3.00'}]}}})[0]
    assert weak['verdict'] == 'MONITOR', weak
    # blaZ has the fragment route disabled: near-universal background must not crowd out findings.
    bz = triage_genes({'drugResistance': {'DNA': {'data': [
        {'Group': 'BLAZ', 'Gene': 'MEG_1330', 'Coverage(%)': '74.91%', 'Depth': '12.00'}]}}})[0]
    assert bz['verdict'] == 'MONITOR', bz
    # A threat whose definition lives below species rank must not reach CONFIRM on a species hit;
    # one whose species identity IS the finding still must.
    tl = RULES['threat_list']
    assert 'subspecies_required' in tl['Salmonella enterica']
    for k in ('Variola virus', 'Burkholderia pseudomallei', 'Brucella melitensis',
              'Coxiella burnetii', 'Mycobacterium tuberculosis'):
        assert 'subspecies_required' not in tl[k], k
    print('selftest: all rule checks pass')


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if '--selftest' in sys.argv:
        selftest()
    else:
        run(args or SAMPLES)
