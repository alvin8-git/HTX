"""Running registry of analysed samples, and the sidecar that carries where each swab came from.

    analysis/sample_registry.json     written by the pipeline, never by hand
    analysis/sample_metadata.tsv      written by hand, never by the pipeline

WHY THIS EXISTS. Gate 8 asks whether an organism is unusually abundant *here*, which is
meaningless without a "compared to what". Run five swabs in one command and they compare
against each other; run one swab alone and there is nothing to compare against, and the
difference is not cosmetic. Measured on this batch:

    WBM156 sample verdict     MONITOR (4 comparators)  ->  NO ACTION (none)
    WBM232 taxon rows             84 (4 comparators)   ->  370 (none)

So the cohort decides a verdict AND decides what is worth printing - without comparators the
engine cannot discard background flora and the report inflates 4.4x. A per-sample report is
therefore NOT the batch report filtered to one sample. This registry is what lets a sample
analysed today still be judged against every sample analysed before it.

WHAT IS STORED. Only what gate 8 consumes: real reads per taxon, plus the classified total
that normalises them. Everything else in the file is provenance - what the sample was judged
against, and when.

WHAT IS NOT STORED. No read data, no sequences, no PFI report content. The registry is a
few KB per sample and is safe to commit.

REPORTS ARE SNAPSHOTS. A report records the cohort it was built against and a fingerprint of
it. Adding a new sample can change an older sample's verdict - WBM156 is MONITOR partly
because Providencia rettgeri was seen only in it, and the day another swab carries that
organism the reason evaporates. Old reports are not rewritten behind your back; the
fingerprint is how a stale one is spotted.
"""
import collections
import datetime
import hashlib
import json
import os

import triage

REGISTRY = os.path.join(triage.ROOT, 'analysis', 'sample_registry.json')


def registry_path(name=None):
    """Registry file for one cohort. `name` is a bare label, not a path.

    ONE REGISTRY PER COHORT, and the caller must say which. Gate 8 measures a swab's enrichment
    against every other sample in its registry, so the registry IS the definition of "normal" for
    that swab. Pooling the airport swabs with the ZymoBIOMICS standards would have gate 8 ask
    whether Acinetobacter is enriched in a terminal-4 trolley handle relative to a mock community
    of eight bacteria at 12% each - a question with an answer, and no meaning. The long-read stool
    run is a third population and a different assay chemistry again.
    """
    if not name:
        return REGISTRY
    assert '/' not in name and '\\' not in name and name.strip(), f'cohort label, not a path: {name!r}'
    return os.path.join(triage.ROOT, 'analysis', f'sample_registry_{name}.json')
METADATA = os.path.join(triage.ROOT, 'analysis', 'sample_metadata.tsv')
META_COLS = ['sample_id', 'site_id', 'site_label', 'collected_at', 'run_id']


def load(path=None):
    path = path or REGISTRY
    if not os.path.exists(path):
        return {'version': 1, 'samples': {}, 'path': path}
    with open(path, encoding='utf-8') as fh:
        reg = json.load(fh)
    reg['path'] = path                 # so save() cannot write a cohort back to the wrong file
    return reg


def save(reg):
    path = reg.get('path') or REGISTRY
    reg['samples'] = dict(sorted(reg['samples'].items()))
    out = {k: v for k, v in reg.items() if k != 'path'}
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False, sort_keys=False)
        fh.write('\n')
    os.replace(tmp, path)              # atomic: a crash mid-write must not truncate the registry


def metadata():
    """Sample metadata from the hand-maintained sidecar. Absent is absent, never inferred.

    A missing row, a missing file and a blank cell all mean the same thing and all render as
    "not captured". Nothing here is ever guessed from a filename or a run note, because a
    guessed site silently joins two swabs that were never in the same place.
    """
    if not os.path.exists(METADATA):
        return {}
    out = {}
    with open(METADATA, encoding='utf-8') as fh:
        rows = [ln.rstrip('\n').split('\t') for ln in fh if ln.strip() and not ln.startswith('#')]
    if not rows:
        return {}
    head = rows[0]
    for r in rows[1:]:
        rec = {k: (r[i].strip() if i < len(r) else '') for i, k in enumerate(head)}
        sid = rec.get('sample_id')
        if sid:
            out[sid] = {k: v for k, v in rec.items() if k != 'sample_id' and v}
    return out


def cohort_ids(reg, exclude):
    """Every sample in the registry except the one being analysed.

    D1: the baseline is the whole registry, not the current run. A single-sample run is then
    still a real analysis rather than a degraded one. The trade is that the pool mixes sites
    and sequencing runs, which is why the batch caveat ships on the panel.
    """
    return sorted(s for s in reg['samples'] if s != exclude)


def cohort_loads(reg, exclude):
    """{taxon: {sample_id: reads per million classified}} for the cohort, from stored counts.

    Same shape and same normalisation as triage.loads_by_taxon, so triage.enrichment cannot
    tell a registry sample from one loaded off disk - which is the point. Nothing here reopens
    a PFI report.
    """
    out = collections.defaultdict(dict)
    for sid in cohort_ids(reg, exclude):
        rec = reg['samples'][sid]
        tot = rec.get('classified') or 0
        if not tot:
            continue
        for taxon, reads in rec.get('loads', {}).items():
            out[taxon][sid] = reads / tot * 1e6
    return out


def fingerprint(reg, ids):
    """Short digest of the comparison set: which samples, and how deep each was sequenced.

    Depth is included because it changes the normalised loads, so two cohorts with the same
    members but a re-sequenced member are genuinely different baselines and must not collide.
    """
    if not ids:
        return 'none'
    parts = [f"{s}:{reg['samples'].get(s, {}).get('classified', 0)}" for s in sorted(ids)]
    return hashlib.sha256('|'.join(parts).encode()).hexdigest()[:6]


def record(reg, sample_id, classified, loads, verdict, rules_fp, cohort):
    """Write one sample's contribution to the baseline, plus what it was judged against."""
    reg['samples'][sample_id] = {
        'classified': int(classified),
        'verdict': verdict,
        'analysed_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'rules_fp': rules_fp,
        'cohort': list(cohort),
        'cohort_fp': fingerprint(reg, cohort),
        # real reads per taxon; zero-read taxa contribute nothing to an enrichment and are dropped
        'loads': {k: int(v) for k, v in sorted(loads.items()) if v},
    }
    return reg['samples'][sample_id]


def loads_from_report(g):
    """Real reads per taxon straight off the PFI species table."""
    return {r['Scientific Name']: int(r['Real Read'])
            for r in g['indentification_DNA']['speciesData']['data']}


def _selftest():
    reg = {'version': 1, 'samples': {}}
    record(reg, 'A', 1_000_000, {'Escherichia coli': 500, 'Absent sp.': 0}, 'NO ACTION', 'r1', [])
    record(reg, 'B', 2_000_000, {'Escherichia coli': 400}, 'MONITOR', 'r1', ['A'])
    assert 'Absent sp.' not in reg['samples']['A']['loads'], 'zero-read taxa are not baseline'
    assert cohort_ids(reg, 'B') == ['A'] and cohort_ids(reg, 'A') == ['B']
    cl = cohort_loads(reg, 'B')
    assert abs(cl['Escherichia coli']['A'] - 500.0) < 1e-9, 'reads per million classified'
    assert 'B' not in cl['Escherichia coli'], 'a sample is never its own comparator'
    # the fingerprint must move when sequencing depth moves, not only when membership does
    f1 = fingerprint(reg, ['A'])
    reg['samples']['A']['classified'] = 3_000_000
    assert fingerprint(reg, ['A']) != f1, 'depth changes the baseline, so it changes the id'
    assert fingerprint(reg, []) == 'none'
    print('sample_registry selftest OK')


if __name__ == '__main__':
    _selftest()
