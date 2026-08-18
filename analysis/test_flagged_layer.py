"""Self-check for the flagged-species cover sheet in triage_report.py.

    python3 analysis/test_flagged_layer.py

Runs the real gate cascade over the five HTX swabs and asserts the properties that would
silently rot. The one that matters most is the virulence floor: an earlier draft binarised
any VFDB row into "DETECTED" and reported "5 of 5 core determinants present" for
A. baumannii when the deepest of them covered 48% and the shallowest covered 8.75%. That is
the exact class of overclaim the rest of the pipeline is built to avoid, so it gets a test.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import triage
import triage_report as R

SAMPLES = ['WBM156', 'WBM174', 'WBM179', 'WBM185', 'WBM232']


def main():
    data = R.collect([triage.report_path(s) for s in SAMPLES]
                     if hasattr(triage, 'report_path') else SAMPLES)
    by = {d['id']: d for d in data}
    d = by['WBM232']
    ab = next(t for t in d['taxa'] if t['taxon'].startswith('Acinetobacter baumannii'))

    # --- the cover sheet ranks; it must not invent or drop rows -------------------
    hot = [(x, t) for x in data for t in x['taxa'] if t['verdict'] in ('ESCALATE', 'CONFIRM')]
    assert len(hot) == 1, f'expected 1 taxon at CONFIRM or above across the batch, got {len(hot)}'
    assert hot[0][1]['taxon'].startswith('Acinetobacter baumannii')

    # --- ledger: gates decide, the ledger only reports -----------------------------
    lg = {c['code']: c for c in R.ledger(d, ab)}
    assert lg['PM1']['state'] == 'met', 'A. baumannii is on the clinical watchlist'
    assert lg['PP2']['state'] == 'met', '6.0x enriched, floor 5.0x'
    assert lg['BM1']['state'] == 'against', 'Bracken inflated 19x - a downgrade, not support'
    assert lg['PVS1']['state'] == 'unmet' and 'ceiling' in lg['PVS1']['measured'], \
        'not a CDC agent, so the ceiling is CONFIRM and ESCALATE is unreachable'
    assert 'NA3' in lg and lg['NA3']['state'] == 'na', \
        'gate 10 did not run for this agent and must not read as a clear'
    # PS3 must be scored on a gene the escalation test actually weighed, and must name it.
    esc = {g['group'] for _, gs in (R.escalating_rows(ab, d['genes']) or [])
           for g in gs if g['verdict'] == 'CONFIRM'}
    assert any(g in lg['PS3']['measured'] for g in esc), \
        f'PS3 must name an escalating-class gene; said {lg["PS3"]["measured"]!r}'
    # A verdict is never recomputed here - the ledger reports whatever the cascade set.
    assert ab['verdict'] == 'CONFIRM'

    # --- coverage is a property of the panel and the library, not of what was found ---
    cov = R.coverage_fig(data)
    assert '21 of 46 </b>' not in cov  # guard against a stray space breaking the check below
    assert '<b>21 of 46</b>' in cov, \
        f'coverage must read 21 of 46 (threat_list: 21 DNA, 25 RNA vs a DNA library); got: ' \
        + re.sub(r'<[^>]+>', '', cov)[:160]
    assert '46%' in cov or '(46%)' in cov, 'percentage must follow the count'
    panel = {k: v for k, v in triage.RULES['threat_list'].items()
             if not k.startswith('_') and isinstance(v, dict)}
    assert len(panel) == 46 and sum(1 for v in panel.values() if v['genome'] == 'RNA') == 25

    # --- a single-sample run must name the criterion that actually fired ---------
    solo = R.collect(['WBM232_en.html'])[0]
    ab1 = next(t for t in solo['taxa'] if t['taxon'].startswith('Acinetobacter baumannii'))
    lg1 = {c['code']: c for c in R.ledger(solo, ab1)}
    assert 'PP2' not in lg1, 'enrichment is untestable with one sample and must not be claimed'
    assert lg1['PP3']['state'] == 'met' and 'untestable' in lg1['PP3']['measured'], \
        'the abundance fallback route must be named, not left silent'

    # --- the virulence floor: no trace-level hit may render as a positive ----------
    core = R.core_vf(ab)
    assert core and len(core) == 5, 'A. baumannii is the one curated vf_core organism'
    floor = triage.TH['gene_breadth_floor']
    cov = lambda r: float(str(r.get('Coverage(%)', '0')).rstrip('%') or 0)
    above = [m for m, _, b in core if b is not None and cov(b) >= floor]
    assert not above, (f'no A. baumannii core determinant clears the {floor}% floor in WBM232; '
                       f'these claimed to: {above}')
    html = R.vf_html(ab)
    assert 'ABOVE FLOOR' not in html, 'a trace-level hit rendered as a positive call'
    assert f'0 of {len(core)} core determinants above the breadth floor' in html
    assert 'no VFDB threshold' in html, 'the borrowed floor must be named as a convention'

    # --- an uncurated organism asserts nothing ------------------------------------
    pa = next(t for t in d['taxa'] if t['taxon'].startswith('Pseudomonas aeruginosa'))
    assert R.core_vf(pa) is None, 'P. aeruginosa is not curated yet'
    assert pa['vf'], 'this assertion needs an organism that actually has VFDB factors'
    out = R.vf_html(pa)
    assert 'no core-determinant set is curated for this organism' in out, \
        'an uncurated organism must say so rather than rank its factors by depth'
    assert 'DETECTED' not in out and 'ABOVE FLOOR' not in out, \
        'an uncurated organism must not assert any determinant is present'
    # An organism with no VFDB rows at all has nothing to report; silence is correct there.
    quiet = next((t for t in d['taxa'] if not t['vf'] and R.core_vf(t) is None), None)
    if quiet is not None:
        assert R.vf_html(quiet) == '', 'no factors means no block, not an empty block'

    # --- the escalating-class table is fixed by rule, not by what was found --------
    rows = R.escalating_rows(ab, d['genes'])
    assert [c for c, _ in rows] == triage.RULES['clinical_watchlist'][
        'Acinetobacter baumannii']['escalating_classes']
    hit = [c for c, gs in rows if any(g['verdict'] == 'CONFIRM' for g in gs)]
    assert hit == ['betalactams', 'Aminoglycosides'], hit
    assert not any(g['verdict'] == 'CONFIRM' for c, gs in rows
                   for g in gs if c == 'Lipopeptides'), 'no colistin resistance in WBM232'

    # The RNA panel is screened in every sample; the cover sheet must report distinct
    # agents, not rows, or a five-swab batch claims 125 unseen agents instead of 25.
    head = R.flagged_section(data).split('</div>')[0]
    n = int(re.search(r'(\d+) agents the assay could not see', head).group(1))
    distinct = len({R.binomial(t['taxon']) for x in data for t in x['taxa']
                    if t['verdict'] == 'NOT_TESTED' and not t.get('real')})
    assert n == distinct == 25, f'cover sheet says {n}, distinct agents are {distinct}'

    print(f'OK - {len(data)} samples, 1 flagged taxon, ledger {len(lg)} criteria, '
          f'vf 0/{len(core)} above floor, {n} agents unseen')


if __name__ == '__main__':
    main()
