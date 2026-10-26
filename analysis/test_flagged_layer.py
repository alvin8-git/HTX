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
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sample_registry as SR
import triage
import triage_report as R

SAMPLES = ['WBM156', 'WBM174', 'WBM179', 'WBM185', 'WBM232']


def bec_scheme(codes):
    """BEC v1: distinct from ACMG by construction, and legible without colour."""
    acmg = re.compile(r'^(PVS|PS|PM|PP|BA|BS|BM|BP)\d')
    assert codes, 'no criteria fired anywhere in the batch'
    bad = [c for c in codes if acmg.match(c)]
    assert not bad, f'BEC must not reuse ACMG codes; found {bad}'
    for c in codes:
        assert R.BEC[c[0]], c
        if c[0] == 'U':
            assert re.match(r'^U\d+$', c), f'{c}: U codes carry no direction'
        else:
            assert re.match(r'^[DSMP][RL]\d+$', c), f'{c}: <strength><direction><serial>'
    # every strength must be readable from the pip meter alone, not from the hue
    fills = {k: R.BEC[k][2] for k in 'DSMPU'}
    assert sorted(fills.values()) == [0, 1, 2, 3, 4], fills
    for c in sorted(codes):
        b = R.bec_badge(c)
        assert b.count('&#9679;') == R.BEC[c[0]][2], f'{c}: pip count must equal strength'
        assert b.count('&#9679;') + b.count('&#9675;') == 4, f'{c}: meter is always 4 wide'
    # the two decisive criteria, and only those
    dec = sorted(c for c in codes if c[0] == 'D')
    assert dec == ['DL1', 'DR1'], f'expected exactly the marker and read-floor gates, got {dec}'
    print(f'  BEC v1: {len(codes)} codes fired, none ACMG, pip meter matches strength')


def contrast():
    """Badge text must clear WCAG AA 4.5:1. Measured, never eyeballed."""
    def lum(h):
        v = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        v = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in v]
        return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]
    pairs = [('.bec.dR', '#C02A2A', '#FBEAEA'), ('.bec.dR.s4', '#FFFFFF', '#C02A2A'),
             ('.bec.dL', '#1E7A3C', '#EAF5EE'), ('.bec.dU', '#5C5C5C', '#F2F3F4'),
             # .off drops the tint, so the panel background becomes the backdrop
             ('.bec.dR.off', '#C02A2A', '#EDF2F8'), ('.bec.dL.off', '#1E7A3C', '#EDF2F8'),
             ('.bec.dU.off', '#5C5C5C', '#EDF2F8')]
    for name, fg, bg in pairs:
        a, b = sorted((lum(fg), lum(bg)), reverse=True)
        r = (a + 0.05) / (b + 0.05)
        assert r >= 4.5, f'{name}: {fg} on {bg} is {r:.2f}:1, below AA'
        assert f'color:{fg.lower()}' in R.CSS.lower() or fg == '#FFFFFF', name
        print(f'  {name:14s} {fg} on {bg}  {r:.2f}:1')
    # an unmet criterion keeps its strength but must not render as the loudest thing on screen
    assert '.bec.off{background:transparent' in R.CSS
    assert R.bec_badge('DR1', 'unmet').count('off') == 1 and 'off' not in R.bec_badge('DR1')


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
    assert lg['SR2']['state'] == 'met', 'A. baumannii is on the clinical watchlist'
    assert lg['MR3']['state'] == 'met', '6.0x enriched, floor 5.0x'
    assert lg['ML1']['state'] == 'met', 'Bracken inflated 19x - a downgrade, not support'
    assert lg['DR1']['state'] == 'unmet' and 'ceiling' in lg['DR1']['measured'], \
        'not a CDC agent, so the ceiling is CONFIRM and ESCALATE is unreachable'
    assert 'U4' in lg and lg['U4']['state'] == 'na', \
        'gate 10 did not run for this agent and must not read as a clear'
    # MR2 must be scored on a gene the escalation test actually weighed, and must name it.
    esc = {g['group'] for _, gs in (R.escalating_rows(ab, d['genes']) or [])
           for g in gs if g['verdict'] == 'CONFIRM'}
    assert any(g in lg['MR2']['measured'] for g in esc), \
        f'MR2 must name an escalating-class gene; said {lg["MR2"]["measured"]!r}'

    # --- BEC v1, over every criterion the whole batch can produce -----------------
    bec_scheme({c['code'] for dd in data for t in dd['taxa'] for c in R.ledger(dd, t)})
    contrast()

    # --- host rank: the attribution column, and the sample-verdict gate ------------
    esc_g = [g for _c, gs in R.escalating_rows(ab, d['genes']) for g in gs]
    cells = [R.host_rank_cell(ab, g) for g in esc_g]
    assert cells and any('of' in c for c in cells), 'no host rank rendered for WBM232'
    for g, c in zip(esc_g, cells):
        ctx = next((x for x in ab['amr_context'] if x['group'] == g['group']), None)
        if ctx is None:
            assert 'no host hint' in c, g['group']
        elif ctx['self_rank'] == 1:
            assert '<b>1 of' in c, g['group']
        else:
            assert 'leads' in c, f"{g['group']}: a non-leading rank must name the leader"
    tbl = R.classes_html(d, ab)
    assert 'Host rank in this swab' in tbl and 'promotes the swab verdict' in tbl, \
        'the rank column must say what it is FOR, not just print a number'
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
    assert 'MR3' not in lg1, 'enrichment is untestable with one sample and must not be claimed'
    assert lg1['PR1']['state'] == 'met' and 'untestable' in lg1['PR1']['measured'], \
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

    # --- per-sample report == cohort report ---------------------------------------
    # The whole per-sample design rests on this: a report built from stored counts must reach
    # the same answer as one built with every PFI report open at once. If it drifts, the
    # registry is silently a different analysis wearing the same name.
    reg = SR.load()
    assert set(reg['samples']) >= set(SAMPLES), 'run: python3 analysis/triage.py --per-sample'
    cids = SR.cohort_ids(reg, 'WBM232')
    assert cids == ['WBM156', 'WBM174', 'WBM179', 'WBM185'], cids
    assert 'WBM232' not in cids, 'a sample is never its own comparator'
    solo_reg = R.collect([os.path.join(triage.ROOT, 'WBM232_en.html')],
                         comparators=True, cohort=SR.cohort_loads(reg, 'WBM232'))[0]
    assert solo_reg['verdict'][0] == d['verdict'][0] == 'REVIEW', \
        f"registry cohort gave {solo_reg['verdict'][0]}, batch gave {d['verdict'][0]}"
    bt = {t['taxon']: t['verdict'] for t in d['taxa']}
    pt = {t['taxon']: t['verdict'] for t in solo_reg['taxa']}
    assert bt == pt, ('registry cohort disagrees with the batch on '
                      f'{len([k for k in set(bt) | set(pt) if bt.get(k) != pt.get(k)])} rows')
    # ...and it must beat the no-cohort case, or the registry buys nothing
    assert len(solo_reg['taxa']) == 85 and len(solo['taxa']) == 370, \
        f"cohort {len(solo_reg['taxa'])} rows vs none {len(solo['taxa'])} - the gap is the point"

    # --- metadata is never guessed -------------------------------------------------
    meta = SR.metadata()
    assert meta['WBM232']['site_label'].startswith('Changi T4')
    assert 'collected_at' not in meta['WBM232'], 'a blank cell must not become a value'
    line = R.site_line('WBM232', meta)
    assert 'collection date not captured' in line and 'run id not captured' in line
    assert R.site_line('WBM999', meta).count('not captured') == 3, \
        'an unknown sample states three gaps rather than rendering blanks'

    print(f'OK - {len(data)} samples, 1 flagged taxon, ledger {len(lg)} criteria, '
          f'vf 0/{len(core)} above floor, {n} agents unseen, registry {len(reg["samples"])}')


if __name__ == '__main__':
    main()
