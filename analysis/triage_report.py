"""Self-contained HTML evidence report for analysis/triage.py.

    python3 analysis/triage.py --html                 # all five HTX samples
    python3 analysis/triage.py --html WBM185 WBM232   # a subset
    -> analysis/triage_report.html

One file, one sample switcher, four tabs per sample. No external requests: CSS, SVG icons and
JavaScript are inlined, so it opens from disk and survives being emailed.

What it is for: every verdict the engine reaches is shown next to the PFI evidence that produced
it, carrying the accession you would search for in `<sample>_en.html` to check it yourself. The
report is a lens on the PFI report, never a replacement for it.

Two honesty constraints are wired into the rendering, not left to the reader:

  * VFDB rows carry a `Pathogen` field, so virulence evidence is attached to a species - but that
    is a match against the reference protein's source strain, not read-level linkage, and the
    report says so on every card.
  * MEGARes carries NO organism column. Host associations come from `amr_host_hints` in the rule
    file: literature expectation, shown only when a candidate host is independently present in the
    same sample, always rendered as INFERRED, and never an input to any verdict. Assembly could
    not attribute these genes (docs/biothreat_assessment.md 2.5) and the report repeats it.
"""
import collections
import datetime
import html
import json
import math
import os

import sample_registry as SR
import triage

ROOT = triage.ROOT
OUT = os.path.join(ROOT, 'analysis', 'triage_report.html')

# Palette lifted from analysis/build_deck.py so deck and report read as one document.
# grey and amber are nudged off their original values to clear WCAG AA. #6D6D6D measured
# 3.98:1 as body text on the #EDF2F8 ground and #AD6400 measured 4.12:1 under the white chip
# label - both below the 4.5 floor, both used report-wide. The shifts are imperceptible and
# the ladder's hue relationships are unchanged.
C = {'blue': '#00539B', 'light': '#EDF2F8', 'ink': '#333333', 'red': '#C02A2A',
     'amber': '#AD6400', 'green': '#1E7A3C', 'grey': '#6D6D6D'}

# Severity ladder, highest first. NOT_TESTED is deliberately absent - it is not a severity, it is
# the absence of a test, and it gets its own band below the ladder.
ORDER = ['ESCALATE', 'CONFIRM', 'MONITOR', 'NO_ACTION']

# Rows shown in a taxon's candidate-host table. The list is tier-sorted, so a low cap truncates
# the NO_ACTION end - which is exactly where the interpretable regulators live: mecI with no mecA,
# blaI/blaR with blaZ. Cutting those threw away the evidence a reader most needs.
SHOW_HOSTS = 20

VERDICT = {
    'ESCALATE':   (C['red'],   'Threat-list agent with its confirmatory marker present'),
    'CONFIRM':    (C['amber'], 'Real and actionable - culture with AST. Terminal tier for any AMR gene'),
    'MONITOR':    (C['blue'],  'Real, not acutely actionable'),
    'NOT_TESTED': (C['grey'],  'This assay structurally cannot see it. NOT a negative result'),
    'NO_ACTION':  (C['grey'],  'Below threshold, kitome, artifact, intrinsic gene, or marker absent'),
}

# The banner at the top of every sample answers a different question from the row tiers above, in a
# different vocabulary - REVIEW exists here and nowhere else. Legending only the row tiers left
# a reader looking up the word they had just read and not finding it. Three levels (2026-10-26):
# file it, have someone look at it, send a team. The old MONITOR / INVESTIGATE split both ended in
# "a microbiologist reads this" and carried no distinct action.
SAMPLE_VERDICT = {
    'ESCALATE':    (C['red'],   'A threat-list agent with its confirmatory marker present. '
                                'The only verdict that asserts a biological threat.'),
    'REVIEW':      (C['amber'], 'A microbiologist reads this swab: a listed organism at CONFIRM, '
                                'a high-consequence acquired gene (mecA, CTX-M) at CONFIRM, or a '
                                'listed organism enriched at this site. The reasons say which.'),
    'NO ACTION':   (C['green'], 'Nothing above. Community-context organisms never contribute.'),
}
SV_ORDER = ['ESCALATE', 'REVIEW', 'NO ACTION']


def _sv_col(v):
    v = triage.LEGACY_VERDICTS.get(v, v)
    return SAMPLE_VERDICT.get(v, (C['grey'],))[0]

# Inline SVG glyphs, 16x16, currentColor. Same semantic roles as the deck's verdict chips.
ICON = {
    'ESCALATE':   '<path d="M8 1.2 15 14H1z" fill="currentColor"/>'
                  '<path d="M8 6v4M8 11.6v.9" stroke="#fff" stroke-width="1.6" stroke-linecap="round"/>',
    'CONFIRM':    '<path d="M8 1.2 14.8 8 8 14.8 1.2 8z" fill="currentColor"/>'
                  '<path d="M8 5v3.4M8 10.4v.9" stroke="#fff" stroke-width="1.6" stroke-linecap="round"/>',
    'MONITOR':    '<circle cx="8" cy="8" r="6.6" fill="currentColor"/>'
                  '<circle cx="8" cy="8" r="2.3" fill="#fff"/>',
    'NOT_TESTED': '<circle cx="8" cy="8" r="6.4" fill="none" stroke="currentColor" '
                  'stroke-width="1.8" stroke-dasharray="2.6 2.2"/>'
                  '<path d="M4.6 11.4 11.4 4.6" stroke="currentColor" stroke-width="1.8"/>',
    'NO_ACTION':  '<circle cx="8" cy="8" r="6.6" fill="currentColor"/>'
                  '<path d="M4.8 8.2 7 10.4l4.2-4.4" stroke="#fff" stroke-width="1.8" '
                  'fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
}

E = lambda s: html.escape(str(s if s is not None else ''))


# Both fingerprints a page is stamped with, from the engine's own functions rather than from a
# hash recomputed here. This used to be one inline sha256 over rules+engine, written out twice and
# labelled `rules` - which is the rule file's hash under --version and a different number here, so
# the identifier the README says to record with your results did not match the page in front of
# you. A named pair, computed once: `rules` answers "which thresholds", `build` answers "which
# thresholds on which code", and neither can drift into the other's label.
Fingerprints = collections.namedtuple('Fingerprints', 'rules build')


def fingerprints():
    return Fingerprints(triage.rules_fingerprint(), triage.build_fingerprint())


def icon(v):
    return (f'<svg class="ic" viewBox="0 0 16 16" width="15" height="15" aria-hidden="true">'
            f'{ICON.get(v, "")}</svg>')


def chip(v):
    col = VERDICT.get(v, (C['grey'], ''))[0]
    return f'<span class="chip" style="background:{col}">{icon(v)}{E(v.replace("_", " "))}</span>'


# ---------------------------------------------------------------- evidence assembly

def vf_for_taxon(vf_rows, taxon):
    """VFDB hits whose reference strain belongs to this species, collapsed to one row per factor.

    VFDB's `Pathogen` is strain-level ("Staphylococcus epidermidis RP62A"), so the first two tokens
    are the binomial. This is a REFERENCE match: the read matched a protein whose source genome is
    that strain. It does not prove the gene sits in this sample's copy of the organism.

    VFDB stores one reference protein per strain, so a single conserved gene recruits reads onto
    every strain's copy - exactly the redundancy that makes one real gene produce several MEG_ rows
    in MEGARes. WBM232 raw: 326 rows for A. baumannii, but only 121 distinct factors across 15
    reference strains, with plc1 alone appearing 8 times. Counting rows would overstate the
    evidence roughly threefold, so collapse by factor and keep the best-covered representative.
    """
    key = ' '.join(taxon.split()[:2]).lower()
    hit = [r for r in vf_rows if ' '.join(str(r.get('Pathogen', '')).split()[:2]).lower() == key]
    num = lambda r: (float(str(r.get('Coverage(%)', '0')).rstrip('%') or 0),
                     float(str(r.get('Depth', 0)) or 0))
    by_factor = {}
    for r in hit:
        f = r.get('Virulence Factor')
        by_factor.setdefault(f, []).append(r)
    out = []
    for f, rows in by_factor.items():
        best = dict(max(rows, key=num))
        best['_strains'] = len(rows)
        out.append(best)
    return sorted(out, key=lambda r: -num(r)[1]), len(hit)


# ---------------------------------------------------------------- flagged-species layer
#
# A cover sheet over the evidence report, never a replacement for it. The report below is
# ~53,000 words and 59% of it is MONITOR rows; exactly one taxon in the five-swab batch reaches
# CONFIRM. Ranking is the whole job here - nothing is deleted, every row still links down to its
# full evidence card.
#
# Three questions, answered in this order, because that is the order an analyst asks them:
#   1. Which resistance classes would raise THIS organism, and what was co-detected?
#   2. Which virulence determinants are present, and do they matter?
#   3. Which criteria did the cascade actually tick, and what is the verdict resting on?
#
# Block 3 is a criteria ledger written in this project's own scheme, BEC v1 - Biosurveillance
# Evidence Criteria. The 12 gates already behave as an evidence-code system: each contributes a
# named, directional, measured piece of evidence, and fixed rules combine them. They simply never
# published the tick-list. THE GATES STILL DECIDE. Nothing below recomputes a verdict; every line
# reads a field the cascade already wrote.
#
# WHY NOT ACMG'S CODES. An earlier draft reused PVS1/PS1/PM1/PP1/BS1 verbatim. That was a mistake.
# Those labels carry Tavtigian's calibrated odds of pathogenicity - PVS1 is ~350:1 under a
# published Bayesian model, for germline variant classification. Nothing in this pipeline has been
# calibrated against an outcome, so borrowing the namespace would import a quantitative claim it
# cannot support, and would invite a clinical reader to combine our codes with ACMG's combining
# rules. BEC keeps the useful idea - named, directional, strength-tiered criteria combined by
# fixed rules - and defines its own strengths as ORDINAL LABELS OF HOW FAR THE CASCADE LETS A
# CRITERION MOVE A VERDICT. They are not likelihood ratios and must not be read as any.
#
# A code is <strength><direction><serial>:
#   D  decisive    settles the row by itself. Two criteria reach this: the confirmatory marker
#                  on a threat-list agent (the only route to ESCALATE) and the read floor
#                  (below it the cascade stops - `continue` at gate 1 - and nothing later runs).
#   S  strong      sets or removes a ceiling, or moves the tier where it fires.
#   M  moderate    contributes and can tip a row, but never alone.
#   P  supporting  corroborates. Cannot tip anything by itself.
#   R  raises concern / L lowers it.
#   U<serial>      NOT ASSESSABLE: the gate could not run. No strength and no direction, by
#                  construction. This is the deliberate departure from any scheme with only a
#                  for/against axis - an unexamined agent is neither, and folding U into "against"
#                  is the exact error this report exists to prevent.
#
# The strength is a property of the CODE. Whether it fired is the state, kept separate:
#   met    the criterion was tested and is satisfied
#   unmet  it was tested and is not satisfied
#   na     it could not be tested (U codes only)

# strength letter -> (sort rank, label, filled pips out of 4)
BEC = {'D': (0, 'Decisive', 4), 'S': (1, 'Strong', 3), 'M': (2, 'Moderate', 2),
       'P': (3, 'Supporting', 1), 'U': (4, 'Not assessable', 0)}

STATE = {'met': ('&#10003;', 'met'), 'unmet': ('&#9675;', 'unmet'), 'na': ('&#9675;', 'unmet')}
ORDER_STATE = ['met', 'unmet', 'na']


def pip_key(letter):
    """Legend entry: the pip meter alone. Strength is what the legend explains; the hue rule is
    stated in prose beside it, because a hue swatch with no code on it means nothing."""
    _r, label, fill = BEC[letter]
    return (f'<span class="pipkey">{"&#9679;" * fill}{"&#9675;" * (4 - fill)}</span> '
            f'{letter} {label}')


def strongest(lg, dirn='R'):
    """(code, state) of the strongest criterion that FIRED in one direction, or None.

    Never a count. Counting met lines would let three supporting criteria outweigh one decisive
    one, which is exactly the arithmetic BEC declines to do - the cascade combines criteria by
    fixed rules, not by score, and the summary must not imply otherwise.
    """
    c = [x for x in lg if x['state'] == 'met' and x['code'][0] != 'U' and x['code'][1] == dirn]
    return (min(c, key=lambda x: BEC[x['code'][0]][0])['code'], 'met') if c else None


def bec_badge(code, state='met'):
    """Strength badge. THREE channels, never colour alone: hue is the direction (red raises,
    green lowers, grey not assessable), the pip meter is the strength, and the left rail thickens
    with it. A reader with any colour vision reads the pips; a fast scan reads the hue.
    """
    _rank, label, fill = BEC[code[0]]
    dirn = 'U' if code[0] == 'U' else code[1]
    pips = '&#9679;' * fill + '&#9675;' * (4 - fill)
    tail = '' if dirn == 'U' else (', lowers concern' if dirn == 'L' else ', raises concern')
    off = '' if state == 'met' else ' off'   # tested and not satisfied, or never testable
    return (f'<span class="bec d{dirn} s{fill}{off}" title="{label}{tail}">'
            f'<span class="pips" aria-hidden="true">{pips}</span>{E(code)}</span>')

FULL_LENGTH = 'gene_breadth_confident'   # >= this breadth is a full-length call, below it partial


def binomial(name):
    return ' '.join(str(name).split()[:2])


def core_vf(t):
    """Core determinants for this taxon: [(match, role, best_row_or_None)], or None if uncurated.

    Absence of a curated set is not absence of virulence - it means nobody has decided yet which
    of this organism's factors are informative, so the report must say so rather than rank 121
    factors by depth and let the reader infer that the deepest one matters most.
    """
    spec = triage.RULES.get('vf_core', {}).get(binomial(t['taxon']))
    if not spec:
        return None
    dep = lambda r: float(str(r.get('Depth', 0)) or 0)
    out = []
    for f in spec['factors']:
        hit = [r for r in t['vf'] if f['match'].lower() in str(r.get('Virulence Factor', '')).lower()]
        out.append((f['match'], f['role'], max(hit, key=dep) if hit else None))
    return out


def escalating_rows(t, genes):
    """[(class, [gene, ...])] for the classes that would raise THIS organism, or None.

    The class list is fixed per organism in clinical_watchlist[...].escalating_classes - decided
    before the run, not chosen after seeing the data, which is what makes it evidence rather than
    a post-hoc story. Co-detection is a fact about the SAMPLE: MEGARes carries no organism column,
    so nothing in this table is attributed to this taxon.
    """
    w = triage.RULES['clinical_watchlist'].get(binomial(t['taxon']))
    if not w:
        return None
    rows = []
    for cls in w['escalating_classes']:
        hits = [g for g in genes if g.get('drug_class') == cls and g.get('class') == 'acquired'
                and g['verdict'] in ('CONFIRM', 'MONITOR')]
        rows.append((cls, sorted(hits, key=lambda g: -g['depth'])))
    return rows


def ledger(d, t):
    """Named criteria the cascade evaluated for this taxon, each with the value it measured.

    Read-only over the taxon row. If a field the cascade writes is absent, the criterion is
    omitted rather than guessed - a ledger that invents a line is worse than a short ledger.
    """
    TH, out = triage.TH, []
    add = lambda c, s, txt, meas, gate: out.append(
        {'code': c, 'state': s, 'text': txt, 'measured': meas, 'gate': gate})
    tier = t.get('tier') or '-'
    cdc = tier not in ('-', 'W')

    # --- gate 2: the only criterion that overrides everything below it.
    if t['verdict'] == 'NOT_TESTED' and not t.get('real'):
        add('U1', 'na', 'Assay structurally cannot see this agent',
            'RNA genome screened against a DNA library - the test did not run', '2')
    if t['verdict'] == 'NOT_TESTED' and t.get('real'):
        mp = t.get('marker_power')
        add('U2', 'na', 'Confirmatory marker not assessable at this coverage',
            (f'marker power {mp:.0%} &lt; {TH["marker_power_min"]:.0%} floor - its absence is the '
             f'expected outcome either way' if isinstance(mp, float) else
             'below the power floor - its absence carries no information'), '10a')

    # --- gates 10a/10b: the markers. The only route to ESCALATE.
    if t.get('markers_required'):
        found = [x for x in (t.get('markers_found') or [])]
        if found:
            add('DR1', 'met', 'Threat-list agent with its confirmatory marker present',
                'found: ' + ', '.join(found), '10a')
        elif t['verdict'] != 'NOT_TESTED':
            add('SL1', 'met', 'Confirmatory marker absent where the two-way gate ran',
                'required: ' + ' / '.join(t['markers_required']), '10a')
    if t.get('supporting_required'):
        sup = t.get('supporting_found') or []
        if sup:
            add('SR1', 'met', 'Supporting marker present &mdash; one-way gate',
                'found: ' + ', '.join(sup), '10b')
        else:
            add('U3', 'na', 'Supporting marker not found &mdash; one-way gate, so NOT an exclusion',
                'VFDB coverage for this agent cannot be certified from the report', '10b')
    if not t.get('markers_required') and not t.get('supporting_required'):
        add('U4', 'na', 'No confirmatory or supporting marker defined for this agent',
            'gate 10 did not run - this is not an absence of evidence', '10')

    # --- gate 1b: list membership, and the ceiling it implies.
    if tier == 'W':
        add('SR2', 'met', 'Organism on the clinical watchlist',
            E(t.get('watch_priority') or 'clinical watchlist'), '1b')
    elif cdc:
        add('SR3', 'met', 'Organism on the CDC threat list', f'Category {E(tier)}', '1b')
    if not cdc and not t.get('markers_found'):
        add('DR1', 'unmet', 'CDC threat-list agent with its confirmatory marker',
            'not a CDC agent - <b>ceiling is CONFIRM</b>' if tier == 'W' else 'not a listed agent',
            '1b')

    # --- gates 3-5 + the watchlist escalation test: acquired resistance in an escalating class.
    esc = escalating_rows(t, d['genes']) or []
    conf = [(c, [g for g in gs if g['verdict'] == 'CONFIRM']) for c, gs in esc]
    hit = [(c, gs) for c, gs in conf if gs]
    if hit:
        full = [g for _, gs in hit for g in gs if g['breadth'] >= TH[FULL_LENGTH]]
        code, note = ('SR4', 'full-length') if full else ('MR1', 'partial')
        add(code, 'met', f'Acquired resistance in an escalating class - {note} call',
            f'{len(hit)} of {len(esc)} classes &mdash; ' + ', '.join(c for c, _ in hit), '3&ndash;5')

    # --- gate 8, host-share half: is naming THIS organism better than arbitrary?
    # Only the genes the escalation test actually weighed. Scoring rank over every
    # host-hinted gene in the sample would let this taxon lead on an irrelevant gene while
    # a congener outranks it 4x on the one that triggered the class hit.
    esc_groups = {g['group'] for _, gs in conf for g in gs}
    ctx = [x for x in (t.get('amr_context') or []) if x.get('group') in esc_groups]
    if ctx:
        lead = [x for x in ctx if x.get('self_rank') == 1]
        if lead:
            add('MR2', 'met',
                'Most abundant documented host, for a gene in an escalating class',
                f'rank 1 of {lead[0].get("n_hosts", "?")} candidate hosts of '
                f'{E(lead[0]["group"])}', '8')
        else:
            top = min(ctx, key=lambda x: x.get('self_rank') or 99)
            rival = next((n for n, _ in top.get('candidates', []) if n != t['taxon']), None)
            add('MR2', 'unmet',
                'Most abundant documented host, or &ge;'
                f'{TH["escalation_host_share"]:.0%} of the host pool',
                (f'not met on {E(top["group"])} &mdash; <i>{E(rival)}</i> outranks it'
                 if rival else f'not met on {E(top["group"])}'), '8')

    # --- gate 8, site-signal half. Two different criteria depending on what is available:
    # with comparators the test is enrichment, without them the engine falls back to raw
    # abundance. Naming only the enrichment route left the ledger silent on the criterion
    # that actually fired in a single-sample run.
    fold = t.get('fold')
    if isinstance(fold, float) and fold != float('inf'):
        st = 'met' if fold >= TH['enrichment_fold'] else 'unmet'
        add('MR3', st, 'Cross-sample enrichment above threshold',
            f'{fold:.1f}x vs other samples (floor {TH["enrichment_fold"]:.1f}x)', '8')
    elif not d.get('comparators') and t.get('abundance'):
        ab = float(str(t['abundance']).rstrip('%') or 0)
        flr = TH['watchlist_min_abundance_no_comparators']
        st = 'met' if ab >= flr else 'unmet'
        add('PR1', st, 'Abundance above the no-comparator floor',
            f'{ab:.2f}% (floor {flr:.1f}%) &mdash; <b>no comparator samples, so enrichment '
            f'is untestable</b> and abundance stands in for it', '8')

    # --- gate 1: the read floor.
    # Decisive on the way down: gate 1 does `continue` below the floor, so nothing after it
    # runs. Above the floor it is only supporting - clearing a floor is not evidence of a threat.
    if t.get('real'):
        ok = t['real'] >= TH['min_real_reads']
        add('PR2' if ok else 'DL1', 'met',
            'Real reads above the floor' if ok else 'Below the read floor &mdash; cascade stopped',
            f'{t["real"]:,} reads (floor {TH["min_real_reads"]:,})', '1')

    # --- gate 7: Bracken redistribution. A downgrade, so it counts against.
    if t.get('real') and t.get('est') and t['est'] / t['real'] > TH['bracken_inflation_ratio']:
        add('ML1', 'met', 'Bracken estimate inflated over real reads &mdash; judged on real',
            f'{t["est"]:,} est / {t["real"]:,} real = {t["est"]/t["real"]:.0f}x '
            f'(floor {TH["bracken_inflation_ratio"]}x)', '7')
    return out


def ledger_html(d, t):
    """Criteria ledger as a two-column grid: badge, then criterion and the value it measured.

    No preamble. The BEC legend is written once, in the method section, not once per organism.
    """
    lg = sorted(ledger(d, t), key=lambda c: (ORDER_STATE.index(c['state']), BEC[c['code'][0]][0]))
    rows = ''.join(
        f'<div class="lgb">{bec_badge(c["code"], c["state"])}</div>'
        f'<div class="lgt {STATE[c["state"]][1]}">{STATE[c["state"]][0]} {c["text"]}'
        f'<span class="lgm">{c["measured"]} <span class="gate">gate {c["gate"]}</span></span></div>'
        for c in lg)

    # Summarise by the STRONGEST criterion that fired in each direction, not by a count. Counting
    # met lines would let three supporting criteria outweigh one decisive one, which is precisely
    # the arithmetic BEC refuses to do.
    up, dn = strongest(lg, 'R'), strongest(lg, 'L')
    part = []
    for lbl, x in (('raising', up), ('lowering', dn)):
        if x:
            part.append(f'strongest {lbl} {bec_badge(*x)}')
    na = sum(1 for c in lg if c['state'] != 'met')
    part.append(f'{na} unmet or not assessable')
    verdict = (f'<div class="verdictline">{" &middot; ".join(part)} &rarr; {chip(t["verdict"])}</div>')

    return (f'<div class="xpan"><h4>Criteria ledger <span class="src">BEC v1 &middot; gates '
            f'decide, this list reports</span></h4>'
            f'<div class="lgrid">{rows}</div>{verdict}</div>')


def host_rank_cell(t, g):
    """Where THIS taxon sits among the documented hosts of gene `g` that are present in the sample.

    The whole point of the column. MEGARes has no organism column, so a co-detected gene is a fact
    about the swab; `amr_host_hints` says which genera are documented to carry it, and the species
    table says which of those are actually here and how deep. The rank is the only thing in the
    table that argues for or against attributing the gene to this row rather than to a congener,
    and it is not decorative: `triage.sample_verdict` promotes a swab only when a LISTED organism
    is the rank-1 host of a CONFIRM gene (triage.py, gate 8) - otherwise the resistome is read as
    commensal carriage. So rank 1 is a criterion for upgrading; rank 7 of 12 is the reason not to.
    """
    c = next((x for x in (t.get('amr_context') or []) if x['group'] == g['group']), None)
    if not c:
        return ('<td class="unmet tiny">no host hint indexed for this genus</td>')
    r, n = c.get('self_rank'), c.get('n_hosts') or 0
    if r == 1:
        return (f'<td class="met"><b>1 of {n}</b> <span class="tiny">most abundant '
                f'documented host present</span></td>')
    if not r:
        return f'<td class="unmet tiny">not among the {n} hosts present</td>'
    lead = c.get('top_host')
    ratio = c.get('ratio')
    return (f'<td class="unmet"><b>{r} of {n}</b> <span class="tiny">&mdash; '
            f'<i>{E(lead)}</i> leads'
            + (f' by {ratio:.0f}&times;' if ratio and ratio >= 1.5 else '') + '</span></td>')


def classes_html(d, t):
    esc = escalating_rows(t, d['genes'])
    if not esc:
        return ''
    TH, rows, short = triage.TH, [], []
    for cls, hits in esc:
        conf = [g for g in hits if g['verdict'] == 'CONFIRM']
        badge = ('<span class="tag hit">DETECTED</span>' if conf else
                 '<span class="tag none">NONE</span>')
        if not hits:
            rows.append(f'<tr><td class="unmet">{E(cls)}</td><td>{badge}</td>'
                        f'<td class="acc unmet" colspan="5">no acquired gene of this class detected</td></tr>')
            short.append(f'<tr><td class="unmet">{E(cls)}</td><td class="unmet" colspan="2">none detected</td></tr>')
            continue
        for g in hits:
            call = 'full length' if g['breadth'] >= TH[FULL_LENGTH] else 'partial'
            rows.append(f'<tr><td class="met">{E(cls)}</td><td>{badge}</td>'
                        f'<td class="acc">{E(g["group"])} ({E(g["allele"])})</td>'
                        f'<td class="num">{g["breadth"]:.1f}%</td><td class="num">{g["depth"]:.2f}x</td>'
                        f'<td>{chip(g["verdict"])} <span class="tiny">{call}</span></td>'
                        f'{host_rank_cell(t, g)}</tr>')
            short.append(f'<tr><td class="met">{E(cls)}</td><td><span class="acc">{E(g["group"])}</span> '
                         f'{g["breadth"]:.0f}% / {g["depth"]:.1f}&times; {chip(g["verdict"])}</td>'
                         f'{host_rank_cell(t, g)}</tr>')
    n_hit = sum(1 for _, hits in esc if any(g['verdict'] == 'CONFIRM' for g in hits))
    head = ('<tr><th>Class</th><th>Status</th><th>Gene co-detected</th>'
            '<th class="num">Breadth</th><th class="num">Depth</th><th>Gene verdict</th>'
            '<th>Host rank in this swab</th></tr>')
    # Three rows in view, in a three-column form that fits a third of the width (classes are
    # ordered by the rule file, hits by depth); the full seven-column table sits behind a toggle.
    tbl = (f'<table class="ev short"><tr><th>Class</th><th>Gene</th><th>Host rank</th></tr>'
           f'{"".join(short[:3])}</table>'
           f'<details class="fold"><summary>Full table &mdash; {len(esc)} classes, {len(rows)} row'
           f'{"s" if len(rows) != 1 else ""}</summary><table class="ev wide">{head}{"".join(rows)}'
           f'</table></details>')
    return (f'<div class="xpan"><h4>Co-detected resistance <span class="src">{n_hit} of '
            f'{len(esc)} escalating classes</span></h4><p class="dots">{class_dots(d, t)}</p>{tbl}'
            f'<p class="tiny">Classes fixed per organism before the run. MEGARes has no organism '
            f'column: each gene is co-detected in the swab, attributed to nothing. Host rank 1 on a '
            f'CONFIRM gene {bec_badge("MR2")} promotes the swab verdict at gate 8; a lower rank '
            f'reads as commensal carriage. Rank is evidence about attribution, never proof.</p></div>')


def vf_rows_html(t):
    """Every distinct VFDB factor for this species, behind a toggle. Nothing is dropped."""
    if not t['vf']:
        return ''
    rows = ''.join(
        f'<tr><td><b>{E(r.get("Virulence Factor"))}</b></td>'
        f'<td>{E(r.get("Pathogen"))}'
        + (f' <span class="tiny">+{r["_strains"]-1} more strain'
           f'{"s" if r["_strains"] > 2 else ""}</span>' if r['_strains'] > 1 else '')
        + f'</td><td class="acc">{E(r.get("VF Protein"))}</td>'
        f'<td class="num">{E(r.get("Coverage(%)"))}</td>'
        f'<td class="num">{E(r.get("Depth"))}x</td></tr>' for r in t['vf'])
    red = ''
    if t['vf_rows'] > len(t['vf']):
        red = (f' {t["vf_rows"]} raw rows collapse to {len(t["vf"])} factors: VFDB stores one '
               f'protein per strain, so one gene recruits reads onto every strain\'s copy; the '
               f'best-covered representative is shown.')
    return (f'<details class="fold"><summary>All {len(t["vf"])} VFDB factors '
            f'<span class="src">virulence.DNA</span></summary>'
            f'<p class="tiny">Reference match on the protein\'s source strain, not read-level '
            f'linkage to this sample\'s organism. Search the accession in the PFI report.{red}</p>'
            f'<table class="ev"><tr><th>Factor</th><th>Reference strain</th><th>VFDB accession</th>'
            f'<th class="num">Coverage</th><th class="num">Depth</th></tr>{rows}</table></details>')


def vf_html(t):
    core = core_vf(t)
    if core is None:
        n = len(t['vf'])
        return (f'<div class="xpan"><h4>Virulence <span class="src">{n} factor'
                f'{"s" if n != 1 else ""}</span></h4>'
                f'<p class="tiny">{n} distinct factor{"s" if n != 1 else ""} detected, and no '
                f'core-determinant set is curated for this organism, so this report does not say '
                f'whether they make it virulent. Depth measures sequencing, not importance.</p>'
                f'{vf_rows_html(t)}</div>') if t['vf'] else ''
    floor = triage.TH['gene_breadth_floor']
    cov = lambda r: float(str(r.get('Coverage(%)', '0')).rstrip('%') or 0)
    solid = [x for x in core if x[2] is not None and cov(x[2]) >= floor]
    trace = [x for x in core if x[2] is not None and cov(x[2]) < floor]
    def cell(b):
        if b is None:
            return ('<td><span class="tag none">no VFDB hit</span></td>'
                    '<td class="num">&mdash;</td><td class="num">&mdash;</td>')
        tag = ('<span class="tag hit">ABOVE FLOOR</span>' if cov(b) >= floor
               else '<span class="tag none">trace</span>')
        return (f'<td>{tag}</td><td class="num">{E(b.get("Coverage(%)"))}</td>'
                f'<td class="num">{E(b.get("Depth"))}x</td>')
    rows = ''.join(
        f'<tr><td class="acc {"met" if (b is not None and cov(b) >= floor) else "unmet"}">{E(m)}</td>'
        f'<td>{E(role)}</td>{cell(b)}</tr>' for m, role, b in core)
    return (f'<div class="xpan"><h4>Virulence <span class="src">{len(t["vf"])} factors</span></h4>'
            f'<p class="tiny"><b>{len(solid)} of {len(core)} core determinants above the breadth '
            f'floor</b>' + (f', {len(trace)} at trace level' if trace else '') + '.</p>'
            f'<details class="fold"><summary>Core determinants ({len(core)})</summary>'
            f'<table class="ev wide"><tr><th>Core determinant</th><th>Role</th><th>Status</th>'
            f'<th class="num">Coverage</th><th class="num">Depth</th></tr>{rows}</table>'
            f'<p class="tiny">VFDB rows carry no verdict and this pipeline defines no VFDB '
            f'threshold: the {floor:.0f}% split is borrowed from the AMR fragment floor, a '
            f'reporting convention. No gate consults <code>vf_core</code>.</p></details>'
            f'{vf_rows_html(t)}</div>')


# ---------------------------------------------------------------- visual summary
#
# Two figures, both part-to-whole, both with a table twin. They are CSS flex bars, not SVG:
# a stacked bar needs no coordinate math, and flex keeps the segments honest when the font
# or container changes.
#
# COLOUR IS NEVER THE ONLY ENCODING HERE, and that is a measurement rather than a
# preference. Running the palette validator over the tier ladder:
#
#   [FAIL] Normal-vision floor  worst adjacent #AD6400 (CONFIRM) <-> #C02A2A (ESCALATE)
#          dE 12.1 -- below the 15 floor, hard to tell apart even with full colour vision
#
# A search over every amber that keeps white label text at 4.5:1 and sits dE >= 15 from
# this red returned ZERO candidates: the ladder is a deliberate warm severity gradient, and
# separating its top two rungs by colour would cost the gradient its meaning. So the two
# most consequential tiers are separated structurally instead - a 2px surface gap between
# every segment, a direct count inside any segment wide enough to hold one, an icon and a
# word in the legend, and a table twin carrying every value. Nothing is reachable by colour
# or by hover alone.

BAR_H = 24          # the mark-thickness cap and the pointer-target floor are the same number
LABEL_MIN = 34      # a segment narrower than this cannot hold its count legibly


def _seg(k, n, tot, wide):
    """One segment of a tier bar. NOT_TESTED is hatched because it is not a severity."""
    hatch = k == 'NOT_TESTED'
    fill = (f'background:repeating-linear-gradient(45deg,#fff 0 4px,{C["grey"]} 4px 5px);'
            f'border:1px solid {C["grey"]}' if hatch else f'background:{VERDICT[k][0]}')
    ink = C['ink'] if hatch else '#fff'
    txt = (f'<span class="tsl{" onhatch" if hatch else ""}">{n:,}</span>') if wide else ''
    return (f'<span class="tseg" style="flex:{n};{fill};color:{ink}" '
            f'title="{E(k.replace("_", " "))} &mdash; {n:,} of {tot:,}">{txt}</span>')


def tier_bars(data):
    """Taxon tiers per sample, bar width proportional to that sample's total taxon count.

    Absolute widths, not percentages: WBM185 carries 134 rows and WBM179 carries 54, and a
    row-normalised bar would draw those as the same length and invite the reader to compare
    proportions that rest on very different denominators.
    """
    order = [v for v in ORDER if v != 'ESCALATE'] + ['NOT_TESTED']
    order = ['ESCALATE'] + order
    counts = [(d, {v: sum(1 for t in d['taxa'] if t['verdict'] == v) for v in order})
              for d in data]
    tots = {d['id']: sum(c.values()) for d, c in counts}
    top = max(tots.values()) or 1

    rows = ''
    for d, c in counts:
        tot = tots[d['id']]
        # px estimate only decides whether a count fits inside its own segment
        px = lambda n: (n / top) * 620
        segs = ''.join(_seg(k, c[k], tot, px(c[k]) >= LABEL_MIN) for k in order if c[k])
        rows += (f'<div class="tbar"><span class="tbl">{E(d["sample"])}</span>'
                 f'<span class="ttrack" style="width:{tot / top:.1%}">{segs}</span>'
                 f'<span class="ttot">{tot:,}</span></div>')

    legend = ''.join(
        f'<span class="tlg">{_swatch(k)}{icon(k)}{E(k.replace("_", " "))}</span>'
        for k in order if any(c[k] for _, c in counts))

    head = ''.join(f'<th class="num">{E(k.replace("_", " "))}</th>' for k in order)
    body = ''.join(
        f'<tr><td><b>{E(d["sample"])}</b></td>'
        + ''.join(f'<td class="num">{c[k]:,}</td>' for k in order)
        + f'<td class="num"><b>{tots[d["id"]]:,}</b></td></tr>' for d, c in counts)
    tfoot = ''.join(f'<td class="num"><b>{sum(c[k] for _, c in counts):,}</b></td>'
                    for k in order)

    return (f'<div class="fig"><div class="fighd"><b>Taxon tiers per swab</b>'
            f'<span class="tiny">Bar length is that swab\'s total taxon count, so the rows '
            f'compare in absolute rows rather than percentages. Hatched = never assessed.</span>'
            f'</div><div class="tbars">{rows}</div><div class="tlgs">{legend}</div>'
            f'<details class="fold"><summary>Table view &mdash; taxon tiers per swab</summary>'
            f'<table class="ev"><tr><th>Swab</th>{head}<th class="num">Total</th></tr>{body}'
            f'<tr><td><b>Batch</b></td>{tfoot}'
            f'<td class="num"><b>{sum(tots.values()):,}</b></td></tr></table></details></div>')


def _swatch(k):
    if k == 'NOT_TESTED':
        return (f'<span class="tsw" style="background:repeating-linear-gradient(45deg,'
                f'#fff 0 3px,{C["grey"]} 3px 4px);border:1px solid {C["grey"]}"></span>')
    return f'<span class="tsw" style="background:{VERDICT[k][0]}"></span>'


def coverage_fig(data):
    """What the assay could and could not answer, before any chart of what it found.

    Computed from threat_list's own `genome` field against the library that was run, NOT from
    the taxon rows. The engine only emits a row for an agent it saw or explicitly screened, so
    counting rows answers "how many agents appeared" and calls it coverage - which reported
    5 of 30 for a batch whose real coverage is 21 of 46.

    A report that renders "no CDC agent detected" as a clean result is lying by omission when
    more than half the panel was never testable, so this sits above every other figure.
    """
    panel = {k: v for k, v in triage.RULES['threat_list'].items()
             if not k.startswith('_') and isinstance(v, dict)}
    if not panel:
        return ''
    rna = sum(1 for v in panel.values() if v.get('genome') == 'RNA')
    # showRNA is per sample; an agent is assessable if ANY library in the batch could see it.
    any_rna = any(d.get('showRNA') for d in data)
    ok = len(panel) if any_rna else len(panel) - rna
    gap = len(panel) - ok
    pct = ok / len(panel)
    tail = (f'&mdash; the other <b>{gap}</b> have RNA genomes and the library was DNA. '
            f'<b>Not negative: never tested.</b>' if gap else
            '&mdash; an RNA library was sequenced, so the whole panel was in scope.')
    return (f'<div class="fig"><div class="fighd"><b>Assay coverage on this run</b>'
            f'<span class="tiny">Which listed agents this library could answer at all, from '
            f'each agent\'s genome type &mdash; not from what happened to be found.</span>'
            f'</div><div class="covrow"><span class="covbar2">'
            f'<span class="covok" style="flex:{ok}"></span>'
            + (f'<span class="covgap" style="flex:{gap}"></span>' if gap else '') +
            f'</span><span class="covtx"><b>{ok} of {len(panel)}</b> CDC-listed agents '
            f'assessable ({pct:.0%}) {tail}</span></div></div>')



def anchor(d, t):
    """Stable id for a taxon's evidence card, so a cover-sheet row can link straight to it."""
    key = t.get('taxid') or binomial(t['taxon']).replace(' ', '-')
    return f'c-{d["id"]}-{key}'


def class_dots(d, t):
    """Compact per-class indicator for the collapsed row: one square per escalating class."""
    esc = escalating_rows(t, d['genes'])
    if not esc:
        return '<span class="tiny">&mdash;</span>'
    dots = ''.join(
        f'<span class="cdot{"" if any(g["verdict"] == "CONFIRM" for g in hits) else " off"}" '
        f'title="{E(cls)}"></span>' for cls, hits in esc)
    n = sum(1 for _, hits in esc if any(g['verdict'] == 'CONFIRM' for g in hits))
    return (f'<span class="cdots">{dots}</span> '
            f'<span class="cn">{n} of {len(esc)}</span>')


def first_sentence(why):
    """The engine's `why` is a semicolon-joined chain of clauses; the first one is the headline."""
    s = str(why or '')
    for sep in ('; ', '. '):
        if sep in s:
            s = s.split(sep, 1)[0]
    return s.rstrip('.;') + ('.' if s else '')


def deepest_class(d, t):
    """The escalating class with the deepest CONFIRM gene, else the deepest acquired CONFIRM gene
    whose documented host range includes this genus. (name, depth) or None."""
    best = None
    for cls, hits in (escalating_rows(t, d['genes']) or []):
        for g in hits:
            if g['verdict'] == 'CONFIRM' and (best is None or g['depth'] > best[1]):
                best = (cls, g['depth'])
    if best is None:
        for x in (t.get('amr_context') or []):
            if x.get('verdict') == 'CONFIRM' and x.get('class') == 'acquired':
                cls = x.get('drug_class') or x['group']
                if best is None or x['depth'] > best[1]:
                    best = (cls, x['depth'])
    return best


def _priority(t):
    tier = t.get('tier') or '-'
    if tier == 'W':
        return E(t.get('watch_priority') or 'clinical watchlist')
    return f'CDC Cat. {E(tier)}' if tier != '-' else 'community'


def taxon_detail(d, t):
    """The expansion under a taxon row. Three panels side by side, one sentence of the engine's
    reasoning, and everything the old evidence card carried behind toggles. Nothing is dropped."""
    why = t.get('why') or ''
    head = first_sentence(why)
    full = ''
    if len(head) < len(why.strip()):
        full = (f'<details class="fold"><summary>Full reasoning</summary>'
                f'<p class="why">{E(why)}</p></details>')
    extra = ''
    if t.get('watch_note'):
        extra += (f'<details class="fold"><summary>Why it is on the clinical watchlist</summary>'
                  f'<p class="tiny">{E(t["watch_note"])} Not a CDC bioterrorism agent, so its '
                  f'ceiling is CONFIRM; ESCALATE stays reserved for a threat-list agent with its '
                  f'confirmatory marker.</p></details>')
    if t.get('markers_required'):
        found = [x for x in (t.get('markers_found') or []) if x not in (t.get('supporting_found') or [])]
        extra += (f'<details class="fold"><summary>Confirmatory markers (two-way)</summary><p class="tiny">'
                  f'Required: <b>{E(" / ".join(t["markers_required"]))}</b>. '
                  + (f'Found: <b>{E(", ".join(found))}</b>, which raises the verdict to ESCALATE.'
                     if found else 'None detected, so the agent is downgraded. This is the gate '
                     'that separates a threat-list organism from the threat itself.')
                  + '</p></details>')
    if t.get('supporting_required'):
        sup = t.get('supporting_found') or []
        extra += (f'<details class="fold"><summary>Supporting markers (one-way)</summary><p class="tiny">'
                  f'Searched: <b>{E(" / ".join(t["supporting_required"]))}</b>, restricted to VFDB '
                  f'rows whose reference strain is a <i>{E(t["taxon"].split(" ")[0])}</i>. '
                  + (f'Found: <b>{E(", ".join(sup))}</b>, which raises the verdict to ESCALATE.'
                     if sup else '<b>None found, and that is not an exclusion.</b> VFDB coverage for '
                     'this agent cannot be certified from the report, so a miss is no information, '
                     'not a clear. The verdict is unchanged by this gate.')
                  + '</p></details>')
    if t.get('amr_context'):
        def hosts(x):
            out = []
            for n, c in x['candidates']:
                if n == t['taxon']:
                    rank = (f' &mdash; rank {x["self_rank"]} of {x["n_hosts"]}'
                            if x.get('self_rank') else '')
                    out.append(f'<span class="self">{E(n)} {c:,}{rank}</span>')
                else:
                    out.append(f'<span>{E(n)} {c:,}</span>')
            return ' &middot; '.join(out) or '&mdash;'
        rows = ''.join(
            f'<tr><td><b>{E(x["group"])}</b></td><td class="acc">{E(x["allele"])}</td>'
            f'<td class="num">{x["breadth"]:.2f}%</td><td class="num">{x["depth"]:.2f}x</td>'
            f'<td>{chip(x["verdict"])}</td><td class="basis">{hosts(x)}</td>'
            f'<td class="basis">{E(x["basis"])}</td></tr>'
            for x in t['amr_context'][:SHOW_HOSTS])
        n_more = max(0, len(t['amr_context']) - SHOW_HOSTS)
        more = f'<p class="tiny">+ {n_more} more in the resistance-genes section.</p>' if n_more else ''
        extra += (f'<details class="fold inferred"><summary>{icon("NOT_TESTED")} '
                  f'{min(len(t["amr_context"]), SHOW_HOSTS)} resistance genes whose known host '
                  f'range includes this genus &mdash; INFERRED, NOT MEASURED</summary>'
                  f'<p class="tiny"><b>MEGARes carries no organism column.</b> These genes were '
                  f'detected in this sample and this genus is a documented host for them; nothing '
                  f'shows the gene is in <i>this</i> organism, and no field in the PFI report can. '
                  f'Culture with AST is the only way to close this. <b>Do not report these as this '
                  f'organism\'s resistance profile.</b> Candidate hosts are every documented host '
                  f'of the gene present in this sample, most abundant first, with '
                  f'<span class="self">this taxon highlighted</span>.</p>'
                  f'<table class="ev wide"><tr><th>Group</th><th>Allele</th><th>Breadth</th>'
                  f'<th>Depth</th><th>Gene verdict</th><th>Candidate hosts present (reads)</th>'
                  f'<th>Why this genus is a candidate</th></tr>{rows}</table>{more}</details>')
    meta = []
    if t.get('est'):
        meta.append(f'{t["est"]:,} Bracken estimate')
    if t.get('unique') is not None:
        meta.append(f'{t["unique"]:.0%} unique')
    if t.get('taxid'):
        meta.append(f'taxid {E(t["taxid"])}')
    return (f'<p class="xwhy"><b>Why:</b> {E(head)}'
            + (f' <span class="tiny">{" &middot; ".join(meta)}</span>' if meta else '') + '</p>'
            f'<div class="xp">{ledger_html(d, t)}{classes_html(d, t)}{vf_html(t)}</div>'
            f'{full}{extra}')


def taxon_row(d, t, band='', also=(), show_sample=False, with_id=True):
    """One organism: a <tbody> holding the summary row and its hidden expansion, so sorting moves
    them together and a deep link can open the pair."""
    v = t['verdict']
    sub = _priority(t)
    if also:
        sub += f' &middot; also in {E(", ".join(sorted(also)))}'
    fold = t.get('fold')
    fv = ('&mdash;' if fold is None else 'only here' if fold == float('inf') else f'{fold:.1f}&times;')
    fnum = '' if fold is None else ('1e9' if fold == float('inf') else f'{fold:.3f}')
    gr = t.get('genus_ratio')
    ab = float(str(t.get('abundance') or '0').rstrip('%') or 0)
    dc = deepest_class(d, t)
    rid = f' id="{anchor(d, t)}"' if with_id else ''
    return (f'<tbody class="org {band}"{rid}>'
            f'<tr class="xr"><td><button type="button" class="xb" aria-expanded="false" '
            f'onclick="toggleRow(this)" aria-label="Show evidence for {E(t["taxon"])}">'
            f'<span class="ftri" aria-hidden="true">&#9654;</span></button></td>'
            f'<td class="org-n"><i>{E(t["taxon"])}</i><span class="fsub">{sub}</span></td>'
            f'<td data-v="{ORDER.index(v) if v in ORDER else 9}">{chip(v)}</td>'
            + (f'<td class="smp">{E(d["sample"])}</td>' if show_sample else '')
            + f'<td class="num" data-v="{t.get("real") or 0}">{(t.get("real") or 0):,}</td>'
            f'<td class="num" data-v="{ab}">{E(t.get("abundance") or "&mdash;")}</td>'
            f'<td class="num" data-v="{fnum}">{fv}</td>'
            f'<td class="num" data-v="{gr if gr is not None else ""}">'
            f'{f"{gr:.1f}&times;" if gr is not None else "&mdash;"}</td>'
            f'<td class="cks-c">{checklist(d, t, compact=True)}</td>'
            f'<td data-v="{dc[1] if dc else ""}">'
            + (f'{E(dc[0])} <span class="tiny">{dc[1]:.1f}&times;</span>' if dc else '&mdash;')
            + '</td></tr>'
            f'<tr class="xd" hidden><td colspan="{10 if show_sample else 9}">'
            f'{taxon_detail(d, t)}</td></tr></tbody>')


def species_table(bodies, show_sample=False, caption=''):
    """Sortable table shell. Every <th> is a button; aria-sort tracks the live column."""
    cols = [('', ''), ('Organism', 'txt'), ('Verdict', 'num')] + \
           ([('Sample', 'txt')] if show_sample else []) + \
           [('Reads', 'num'), ('Abundance', 'num'), ('Fold', 'num'),
            ('Genus ratio', 'num'), ('Criteria met', ''), ('Deepest class', 'num')]
    ths = ''.join(
        (f'<th scope="col" aria-sort="none"><button type="button" onclick="sortBy(this.parentNode)">'
         f'{lbl}</button></th>') if lbl else '<th scope="col"><span class="vh">Expand</span></th>'
        for lbl, _k in cols)
    return (f'<div class="tw"><table class="sp">'
            + (f'<caption class="vh">{caption}</caption>' if caption else '')
            + f'<thead><tr>{ths}</tr></thead>{"".join(bodies)}</table></div>')


def flagged_section(data):
    """The cover sheet. Three bands, because the three states mean genuinely different things.

    Band 2 is the one the evidence report cannot express at the top level: an organism that is
    PRESENT, often abundantly, whose marker gate had too little power to mean anything. It shares
    the NOT_TESTED tier with an RNA agent at zero reads and shares nothing else. S. aureus at
    3,654 reads is the most abundant CDC-listed organism in the batch and the honest answer is
    that the run could not resolve it - which belongs above the fold, not in a band below the
    ladder.
    """
    rank = {'ESCALATE': 0, 'CONFIRM': 1}
    hot = sorted([(d, t) for d in data for t in d['taxa'] if t['verdict'] in rank],
                 key=lambda p: (rank[p[1]['verdict']], -(p[1].get('real') or 0)))
    unpowered = sorted([(d, t) for d in data for t in d['taxa']
                        if t['verdict'] == 'NOT_TESTED' and t.get('real')],
                       key=lambda p: -(p[1].get('real') or 0))
    watch = sorted([(d, t) for d in data for t in d['taxa'] if t['verdict'] == 'MONITOR'
                    and (t.get('tier') or '-') != '-'], key=lambda p: -(p[1].get('real') or 0))

    def dedupe(pairs):
        """Worst instance per organism, with the other samples it appears in noted on it."""
        best, extra = {}, {}
        for d, t in pairs:
            k = binomial(t['taxon'])
            if k not in best:
                best[k] = (d, t)
            else:
                extra.setdefault(k, []).append(d['sample'])
        return [(d, t, extra.get(binomial(t['taxon']), [])) for d, t in best.values()]

    # Distinct agents, not rows: the same 25 RNA agents are screened in every sample, so
    # summing rows reports 125 for a five-swab batch and overstates the gap fivefold.
    n_absent = len({binomial(t['taxon']) for d in data for t in d['taxa']
                    if t['verdict'] == 'NOT_TESTED' and not t.get('real')})
    multi = len(data) > 1
    bands = [('hot', dedupe(hot)), ('nt', dedupe(unpowered)), ('mon', dedupe(watch))]
    bodies = [taxon_row(d, t, cls, also, show_sample=multi, with_id=False)
              for cls, pairs in bands for d, t, also in pairs]
    if bodies:
        table = species_table(bodies, show_sample=multi,
                              caption='Flagged species, worst first; sortable by any column')
    else:
        table = ('<div class="flrest">No taxon reached CONFIRM in this batch. That is not a clean '
                 'result on its own &mdash; read the coverage line above it.</div>')
    legend = ''.join(
        f'<span class="bk {cls}"><b>{n}</b> {lbl}</span>' for cls, lbl, n in [
            ('hot', 'flagged, needs an analyst (CONFIRM or above)', len(bands[0][1])),
            ('nt', 'present, marker gate could not run', len(bands[1][1])),
            ('mon', 'watchlist, below every escalation criterion', len(bands[2][1]))])

    tot = sum(len(d['taxa']) for d in data)
    return (f'<section class="flagged"><div class="flwrap">'
            f'<div class="flmast"><h2>Flagged species</h2>'
            f'<span class="tiny">{len(data)} sample{"s" if len(data) != 1 else ""} &middot; '
            f'{tot:,} taxon rows &middot; {n_absent} agent{"s" if n_absent != 1 else ""} the assay '
            f'could not see</span></div>'
            f'{coverage_fig(data)}{tier_bars(data)}'
            f'<div class="bkey">{legend}</div>{table}</div></section>')


def collect(samples, comparators=None, cohort=None, cohort_name=None, control=None):
    """`cohort` is {taxon: {sample_id: load}} from the registry, merged into this run's loads.

    Same shape and normalisation as triage.loads_by_taxon, so triage.enrichment cannot tell a
    stored sample from one loaded off disk. That is what lets a single swab be judged against
    every swab analysed before it instead of against nothing. Gate 8's comparator set and the
    QC flags come from triage.batch_context / triage.qc_flags - the TSV and this page share them.
    """
    reports = {s: triage.load_report(s) for s in samples}
    classified, integrity = {}, {}
    for s, g in reports.items():
        integrity[s], classified[s] = triage.gate_integrity(s, g)
    # `cohort` None means "no registry" here (the batch page compares the batch against itself,
    # as it always has); batch_context reads None as "go and fetch the registry", which is the
    # TSV path's default. Pass {} to keep the two behaviours where they were.
    loads, names, pools, comparators, _ = triage.batch_context(
        samples, reports, classified, comparators, cohort_name,
        cohort if cohort is not None else {})
    meta = SR.metadata()
    ctrl = triage.run_control(control) if control else None

    out = []
    for s in samples:
        g = reports[s]
        genes = triage.triage_genes(g)
        pool, basis = pools[s]
        taxa = triage.triage_taxa(s, g, loads, genes, comparators, pool=pool, names=names)
        vfd = g.get('virulence', {}).get('DNA', {})
        vf_rows = vfd.get('data', []) if isinstance(vfd, dict) else []

        for t in taxa:
            t['vf'], t['vf_rows'] = vf_for_taxon(vf_rows, t['taxon'])

        sid = triage.sample_id(s)
        d = {
            # sample_id strips a localised path down to the stem: under WDL `s` is
            # /cromwell-executions/.../WBM185_en.html, which is not a sample name.
            'sample': sid, 'id': sid, 'site': meta.get(sid, {}),
            'platform': 'long read' if triage.detect_platform(g) == 'long' else 'short read',
            'qc': g['basicSummary']['readsQc']['data'][0],
            'idsum': (g['basicSummary'].get('idSummary', {}).get('data') or [{}])[0],
            'integrity': integrity[s], 'classified': classified[s],
            'taxa': taxa, 'genes': genes, 'comparators': comparators, 'n_samples': len(samples),
            'verdict': triage.sample_verdict(taxa, genes),
            'flags': triage.qc_flags(g, classified[s]), 'basis': basis, 'control': ctrl,
            'n_vf': len(vf_rows), 'n_amr': len(g.get('drugResistance', {}).get('DNA', {}).get('data', [])),
            'n_species': len(g['indentification_DNA']['speciesData']['data']),
            'showRNA': bool(g.get('showRNA')),
        }
        # Depth-normalised loads for the card taxa only: this swab against its comparator set,
        # which is what the dot strip draws and the sparkline extends into the site's history.
        rows = []
        for t in card_pick(d)[0]:
            key = str(t.get('taxid') or '').strip() or 'name:' + t['taxon']
            per = loads.get(key, {})
            others = sorted((triage.sample_id(k), v) for k, v in per.items()
                            if k != s and (pool is None or k in pool))
            rows.append((t['taxon'], key, per.get(s, 0.0), others))
        d['loadrows'] = rows
        out.append(d)
    return out


# ---------------------------------------------------------------- rendering

def qc_tab(d):
    q, i = d['qc'], d['idsum']
    pair = lambda v: (str(v).split(' ')[0], str(v).split('(')[1].rstrip(')') if '(' in str(v) else '')
    rows = []
    # Short-read and long-read PFI reports name these differently, and a key that is absent must
    # read as absent rather than as a silent blank.
    for label, keys in [('Raw reads', {'Raw_Read': ''}), ('Raw bases', {'Raw_Base': ''}),
                        ('Read length', {'Read_Length': '', 'Mean_read_length': ' (mean)'}),
                        ('Read quality', {'Mean_read_quality': ' (mean)'}),
                        ('Raw GC', {'Raw_GC': ''}),
                        # The quality bins differ by platform, so the label must name the bin that
                        # actually supplied the number - "Q20: 87%" would be a different claim.
                        ('Q', {'Raw_Q20': '20', 'Q10': '10'}),
                        ('Q', {'Raw_Q30': '30', 'Q7': '7'})]:
        k = next((k for k in keys if q.get(k) not in (None, '', '-')), None)
        if k is None:
            continue
        v = q[k]
        v = f'{int(v):,}' if str(v).isdigit() and k in ('Raw_Read', 'Raw_Base') else v
        rows.append(f'<tr><th>{label}{keys[k]}</th><td class="num">{E(v)}</td><td></td></tr>')
    rows.append(f'<tr><th>Platform</th><td class="num">{E(d["platform"])}</td><td></td></tr>')
    for label, key in [('Low quality', 'Lowquality_Read'), ('Host', 'Host_Read'), ('rRNA', 'rRNA_Read'),
                       ('Clean', 'Clean_Read'), ('Unclassified', 'Unclassified_Read'),
                       ('Classified', 'Classified_Read')]:
        n, pc = pair(q.get(key, ''))
        n = f'{int(n):,}' if n.isdigit() else n
        strong = ' class="hl"' if key == 'Classified_Read' else ''
        rows.append(f'<tr{strong}><th>{label}</th><td class="num">{E(n)}</td><td class="pc">{E(pc)}</td></tr>')

    king = ''
    if i:
        cells = ''.join(f'<tr><th>{E(k)}</th><td class="num">{int(v):,}</td></tr>'
                        for k, v in i.items()
                        if k in ('Bacteria', 'Fungi', 'Viruses', 'Archaea', 'Protozoa', 'Metazoa_Parasite')
                        and str(v).isdigit())
        disc = ''
        if str(i.get('Classified_Read', '')).isdigit():
            a, b = d['classified'], int(i['Classified_Read'])
            if a != b:
                disc = (f'<p class="note"><b>Two classified-read figures exist and both are correct.</b> '
                        f'The QC module reports <b>{a:,}</b>; this identification summary reports '
                        f'<b>{b:,}</b>, a difference of {a-b:,}. Both partition the same clean reads. '
                        f'The QC figure is the denominator quoted throughout; the summary drops reads '
                        f'assigned above species level.</p>')
        king = (f'<h3>Kingdom breakdown <span class="src">idSummary / Classify.stat.xlsx</span></h3>'
                f'<table class="kv">{cells}</table>{disc}')

    integ = ''.join(f'<li>{E(p)}</li>' for p in d['integrity']) or '<li>No problems reported.</li>'
    return (f'<div class="grid2"><div><h3>Read QC <span class="src">basicSummary.readsQc / '
            f'Basic.stat.xlsx</span></h3><table class="kv">{"".join(rows)}</table></div>'
            f'<div>{king}<h3>Integrity gate</h3><ul class="plain">{integ}</ul>'
            f'<h3>Library scope</h3><table class="kv">'
            f'<tr><th>Species called</th><td class="num">{d["n_species"]:,}</td></tr>'
            f'<tr><th>MEGARes rows</th><td class="num">{d["n_amr"]:,}</td></tr>'
            f'<tr><th>VFDB rows</th><td class="num">{d["n_vf"]:,}</td></tr>'
            f'<tr><th>RNA library</th><td class="num">{"yes" if d["showRNA"] else "no"}</td></tr>'
            f'</table></div></div>')


def species_tab(d):
    """Every taxon row, restructured: one sortable table for the flaggable species (anything on a
    list), the community-context taxa in one collapsed table, and the absent agents as a line.
    Nothing the old cards carried is gone; it sits under each row's expansion."""
    listed = [t for t in d['taxa'] if (t.get('tier') or '-') != '-'
              and not (t['verdict'] == 'NOT_TESTED' and not t.get('real'))]
    other = [t for t in d['taxa'] if (t.get('tier') or '-') == '-']
    absent = [t for t in d['taxa'] if t['verdict'] == 'NOT_TESTED' and not t.get('real')]
    rank = {'ESCALATE': 0, 'CONFIRM': 1, 'NOT_TESTED': 2, 'MONITOR': 3, 'NO_ACTION': 4}
    listed.sort(key=lambda t: (rank.get(t['verdict'], 9), -(t.get('real') or 0)))
    other.sort(key=lambda t: (rank.get(t['verdict'], 9), -(t.get('real') or 0)))
    band = lambda t: {'ESCALATE': 'hot', 'CONFIRM': 'hot', 'NOT_TESTED': 'nt',
                      'MONITOR': 'mon'}.get(t['verdict'], '')
    counts = collections.Counter(t['verdict'] for t in listed)
    head = ' &middot; '.join(f'{chip(v)} {counts[v]}' for v in ORDER + ['NOT_TESTED'] if counts[v])

    out = (f'<h3>Flaggable species <span class="ct">{len(listed)}</span>'
           f'<span class="src">on the CDC threat list or the clinical watchlist</span></h3>'
           f'<p class="blurb">{head or "none detected"}. Sort any column; expand a row for the '
           f'criteria ledger, co-detected resistance and virulence evidence.</p>')
    out += (species_table([taxon_row(d, t, band(t)) for t in listed],
                          caption='Flaggable species in this swab') if listed
            else '<p class="blurb">No listed organism was detected above the read floor.</p>')

    if other:
        oc = collections.Counter(t['verdict'] for t in other)
        oh = ' &middot; '.join(f'{oc[v]} {v.replace("_", " ")}' for v in ORDER if oc[v])
        out += (f'<details class="fold big"><summary>Community context &mdash; {len(other)} taxa '
                f'on no list ({oh}). Never contribute to the sample verdict.</summary>'
                + species_table([taxon_row(d, t) for t in other],
                                caption='Community-context taxa') + '</details>')

    if absent:
        names = ''.join(f'<li><i>{E(t["taxon"])}</i> <span class="tiny">CDC Category '
                        f'{E(t["tier"])}</span></li>' for t in absent)
        out += (f'<div class="band nt"><p class="blurb"><b>{icon("NOT_TESTED")} {len(absent)} '
                f'listed agent{"s" if len(absent) != 1 else ""} the assay cannot see:</b> RNA '
                f'genomes screened against a DNA library. The test did not run; not a negative '
                f'result, and never read as absent.</p>'
                f'<details class="fold"><summary>Names</summary><ul class="plain cols">{names}'
                f'</ul></details></div>')
    if listed and any(t['verdict'] == 'NOT_TESTED' for t in listed):
        out += (f'<p class="tiny">NOT TESTED with reads present: the organism is in the sample, '
                f'but at this depth the chance of a read landing on its confirmatory marker was '
                f'below {int(triage.TH["marker_power_min"] * 100)}%, so the marker\'s absence '
                f'carries no information. Targeted PCR or culture answers it.</p>')
    return out


def amr_tab(d):
    shown = [x for x in d['genes'] if x['verdict'] != 'NO_ACTION']
    supp = len(d['genes']) - len(shown)
    unann = sum(1 for x in d['genes'] if x['class'] == 'unannotated')
    shown.sort(key=lambda x: (ORDER.index(x['verdict']) if x['verdict'] in ORDER else 9,
                              -x['depth']))
    classes = collections.Counter(x.get('drug_class') or 'unclassified' for x in shown)
    rows = ''.join(
        f'<tr data-c="{E(x.get("drug_class") or "unclassified")}">'
        f'<td data-v="{ORDER.index(x["verdict"]) if x["verdict"] in ORDER else 9}">{chip(x["verdict"])}</td>'
        f'<td><b>{E(x["group"])}</b> <span class="acc">{E(x["allele"])}</span></td>'
        f'<td>{E(x.get("drug_class") or "unclassified")}</td>'
        f'<td class="num" data-v="{x["breadth"]:.3f}">{x["breadth"]:.1f}%</td>'
        f'<td class="num" data-v="{x["depth"]:.3f}">{x["depth"]:.2f}&times;</td>'
        f'<td class="num" data-v="{x["alleles_collapsed"]}">{x["alleles_collapsed"]}</td>'
        f'<td>{E(x["class"])}</td>'
        f'<td class="basis"><details class="fold"><summary>Why</summary>{E(x["why"])}'
        + (f'<p class="tiny">{E(x["note"])}</p>' if x.get('note') else '') + '</details></td></tr>'
        for x in shown)
    ths = ''.join(
        f'<th scope="col" aria-sort="none"><button type="button" onclick="sortBy(this.parentNode)">'
        f'{lbl}</button></th>' for lbl in ['Verdict', 'Gene', 'Drug class', 'Breadth', 'Depth',
                                            'Alleles', 'Kind']) + '<th scope="col">Reasoning</th>'
    filt = (f'<button type="button" aria-pressed="true" onclick="amrFilter(this,\'\')">All '
            f'<span class="ct">{len(shown)}</span></button>'
            + ''.join(f'<button type="button" aria-pressed="false" onclick="amrFilter(this,\'{E(c)}\')">'
                      f'{E(c)} <span class="ct">{n}</span></button>'
                      for c, n in sorted(classes.items(), key=lambda kv: (-kv[1], kv[0]))))
    return (f'<div class="warn"><b>No gene on this page is attributed to an organism.</b> MEGARes '
            f'has no organism column and assembly could not close the gap. <b>CONFIRM means "ask a '
            f'laboratory about this gene", not "the sample is resistant"</b>; on a certified-clean '
            f'ZymoBIOMICS standard the same logic yields nine false-positive CONFIRM calls.</div>'
            f'<p class="blurb">{len(shown)} gene groups at MONITOR or above, one call per MEGARes '
            f'group (the allele highest on breadth and depth). {supp} groups suppressed as rRNA, '
            f'efflux, point-mutation, intrinsic, environmental or orphan regulators. Rules cover '
            f'{len(d["genes"]) - unann}/{len(d["genes"])} groups.</p>'
            f'<div class="amrw"><div class="fltr" role="group" aria-label="Filter by drug class">'
            f'{filt}</div><div class="tw sticky"><table class="sp amr">'
            f'<caption class="vh">Resistance genes at MONITOR or above</caption>'
            f'<thead><tr>{ths}</tr></thead><tbody>{rows}</tbody></table></div></div>')


def method_tab(d, cmd, fp):
    enr = ('' if d['comparators'] else
           '<li><b>Whether a finding is site-specific.</b> The cross-sample enrichment gate is inert '
           'on this run: ' + ('there is only one sample' if d['n_samples'] == 1 else
           'the samples were declared independent, so a fold-change between them would measure who '
           'they came from, not where') + '.</li>')
    sec = lambda title, line, body: (f'<details class="ms"><summary><b>{title}</b>'
                                     f'<span class="tiny">{line}</span></summary>{body}</details>')
    return sec('Reproduce this page offline', 'one command, stdlib Python, no network', f'''
<pre>cd {E(ROOT)}
{E(cmd)}</pre>
<p class="blurb">Produced from <code>{E(d["sample"])}_en.html</code> alone. No network, no database,
no aligner.</p>
<table class="kv">
<tr><th>Engine</th><td>analysis/triage.py</td></tr>
<tr><th>Rules</th><td>analysis/triage_rules.json</td></tr>
<tr><th>Rules fingerprint</th><td class="acc">{E(fp.rules)}</td></tr>
<tr><th>Build fingerprint</th><td class="acc">{E(fp.build)} <span class="tiny">rules + engine</span></td></tr>
<tr><th>Also written</th><td>analysis/triage_{E(d["id"])}.tsv</td></tr>
</table>''') + sec('Verify a row against the PFI report', 'search the accession, taxid or name', f'''
<ol class="plain">
<li>Open <code>{E(d["sample"])}_en.html</code>.</li>
<li>For a virulence row, search the <b>VFDB accession</b> (e.g. <code>VFG004763</code>) in the
    virulence table.</li>
<li>For a resistance row, search the <b>MEG_ accession</b> in the drug-resistance table. Expect to
    find several near-identical alleles: that is the allele collapsing described above.</li>
<li>For a taxon, search the <b>taxid</b> or the scientific name in the identification table.</li>
</ol>
<p class="blurb">Every number on this page is copied from those tables unchanged. The one quantity
computed rather than copied is cross-sample enrichment, which is arithmetic on read counts that are
themselves in the reports; the row's <i>Why</i> line says so.</p>''') + \
        sec('How to read the sample verdict', 'ESCALATE, REVIEW, NO ACTION: one answer per swab', f'''
<p class="blurb">The banner at the top. One answer for the whole sample, rolled up from the rows;
a different question, and a different set of words, from the row tiers.</p>
<table class="kv v">{''.join(
    f'<tr><th><span class="chip" style="background:{SAMPLE_VERDICT[v][0]}">{E(v)}</span></th>'
    f'<td>{E(SAMPLE_VERDICT[v][1])}</td></tr>'
    for v in SV_ORDER)}</table>''') + \
        sec('How to read a row verdict', 'ESCALATE to NO ACTION, with NOT TESTED outside the ladder', f'''
<p class="blurb">On the species and resistance-gene sections. <b>CONFIRM is the ceiling for any AMR
gene</b>, and no row is ever labelled REVIEW; that word belongs to the sample.</p>
<table class="kv v">{''.join(f'<tr><th>{chip(v)}</th><td>{E(VERDICT[v][1])}</td></tr>'
                             for v in ['ESCALATE', 'CONFIRM', 'MONITOR', 'NOT_TESTED', 'NO_ACTION'])}</table>''') + \
        sec('How to read a criteria badge', 'BEC v1: strength by pips, direction by hue, never a score', f'''
<p class="blurb">Each ledger line is one gate of the cascade, named under <b>BEC v1</b> and given the
value it measured. The badge carries the criterion's <b>strength</b>:
{" &middot; ".join(pip_key(k) for k in BEC)}, and its direction: red raises concern, green lowers it,
grey could not be assessed. <b>The gates decide the verdict; the ledger only publishes the tick-list
they already produce.</b> Strengths are ordinal labels for how far the cascade lets a criterion move
a verdict. <b>They are not likelihood ratios</b>, nothing has been calibrated against an outcome, and
BEC codes must not be combined using any other scheme's rules. A criterion whose gate could not run
is marked <span class="unmet">&#9675;</span> and is never read as a clear.</p>''') + \
        sec('What this page cannot tell you', 'viability, gene host, contamination, site-specificity', f'''
<ul class="plain">
<li><b>Whether anything is alive.</b> DNA comes off a dry surface from live cells, dead cells and
    spores alike. The PFI "active species" table needs an RNA library and is empty in every DNA run.</li>
<li><b>Which organism carries a resistance gene.</b> See the banner on the resistance-genes section.</li>
<li><b>Whether a trace call is contamination.</b> No negative extraction control was run, so the
    contamination floor is asserted rather than measured.</li>
{enr}
</ul>''') + \
        sec('The input contract, and what a FASTQ input would add', 'one PFI HTML report in; six listed gaps', '''
<p class="blurb">This engine reads <b>one PFI HTML report</b> and nothing else. That is deliberate:
it is the document a microbiologist is actually sent, so every conclusion here can be checked
against the same page, and the engine runs wherever the report does. The cost is a specific, listed
set of questions the report cannot answer; these are limits of the <i>input</i>, not of the
rules, and each would be recoverable from the raw reads if the pipeline is ever pointed at them.</p>
<table class="kv v">
<tr><th>Molecule count</th><td>The report gives read counts. One fragment amplified 10,000&times;
    and 10,000 distinct fragments produce an identical row, so a trace call cannot be shown to be a
    PCR artifact. <i>From FASTQ:</i> the unique-read fraction, already implemented as gate&nbsp;6 and
    active whenever <code>ExtractRead_DNA/</code> is delivered.</td></tr>
<tr><th>Gene host</th><td>No field joins the resistance table to the species table. <i>From FASTQ:</i>
    assembly plus read mapping, which on this batch still failed to resolve it, so this one is
    not guaranteed even with the reads.</td></tr>
<tr><th>Unclassified reads</th><td>72&ndash;90% of reads in a surface swab match nothing in the PFI
    database, and the report says nothing about them. Any organism absent from that database is
    invisible to every row on this page. <i>From FASTQ:</i> direct k-mer and GC interrogation of that
    bin.</td></tr>
<tr><th>Resistance by mutation</th><td>Only gene presence is reported. Resistance conferred by point
    mutation (<i>gyrA</i>, <i>rpoB</i>, <i>lpxA</i>) is invisible, so its absence here is
    never evidence of susceptibility. <i>From FASTQ:</i> variant calling, given sufficient
    depth.</td></tr>
<tr><th>Genomic context</th><td>Whether a gene sits on a plasmid, a prophage or the chromosome, and
    what travels with it. <i>From FASTQ:</i> assembly and replicon typing.</td></tr>
<tr><th>Viability and RNA</th><td>Not recoverable from the DNA reads either; this needs an RNA
    library at the bench. When one exists, the report grows a <code>speciesActivity</code> table and
    the rules gain an activity axis they currently cannot use.</td></tr>
</table>
<p class="blurb">These rules are expected to change. They encode what is decidable from today's
report shape; a new library type, a new database version or more sample data changes what is
decidable, and the rule file, not the engine, is where that change belongs.</p>''') + \
        sec('Measured accuracy', 'ZymoBIOMICS standard: 10/10 organisms, zero false escalations', '''
<p class="blurb">Against the ZymoBIOMICS Microbial Community Standard (known composition, five
inputs): sensitivity 10/10 organisms in every sample, zero false escalations, quantitation mean
absolute error 1.01 percentage points, and nine false-positive AMR CONFIRM calls that restate the
host-attribution gap. Full results in <code>docs/zymo_validation.md</code>.</p>''')


CSS = """
*{box-sizing:border-box}
body{margin:0;font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;
     color:%(ink)s;background:#fff}
header{background:%(blue)s;color:#fff;padding:18px 26px}
header h1{margin:0;font-size:20px;font-weight:700;letter-spacing:.2px}
header .sub{opacity:.85;font-size:12.5px;margin-top:4px}
.bar{background:%(light)s;border-bottom:1px solid #cfdcea;padding:0 26px;display:flex;
     flex-wrap:wrap;gap:2px}
.bar button{background:none;border:0;border-bottom:3px solid transparent;padding:11px 15px;
     font:600 13.5px inherit;color:%(blue)s;cursor:pointer}
.bar button[aria-selected=true]{border-bottom-color:%(blue)s;background:#fff}
.tabs{padding:0 26px;display:flex;gap:2px;border-bottom:1px solid #e2e8f0;flex-wrap:wrap}
.tabs button{background:none;border:0;border-bottom:2px solid transparent;padding:10px 14px;
     font:600 13px inherit;color:%(grey)s;cursor:pointer}
.tabs button[aria-selected=true]{color:%(ink)s;border-bottom-color:%(amber)s}
main{padding:20px 26px 60px;max-width:1500px}
h3{font-size:14px;margin:22px 0 8px;padding-left:9px;border-left:4px solid %(blue)s;
   text-transform:uppercase;letter-spacing:.4px;display:flex;align-items:center;gap:7px}
h4{font-size:12.5px;margin:0 0 5px;color:%(blue)s;display:flex;align-items:center;gap:6px}
.src{font-weight:400;text-transform:none;letter-spacing:0;color:%(grey)s;font-size:11.5px}
.ct{background:%(light)s;color:%(blue)s;border-radius:9px;padding:0 8px;font-size:11.5px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:26px}
table{border-collapse:collapse;width:100%%}
table.kv th{text-align:left;font-weight:600;padding:4px 12px 4px 0;white-space:nowrap;
   border-bottom:1px solid #eef2f6;width:1%%}
table.kv td{padding:4px 0;border-bottom:1px solid #eef2f6}
table.kv tr.hl th,table.kv tr.hl td{background:%(light)s;font-weight:700}
table.kv.v th{padding-right:14px}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;padding-right:18px}
.pc{color:%(grey)s;font-variant-numeric:tabular-nums;text-align:right;min-width:72px;
   white-space:nowrap}
.chip{display:inline-flex;align-items:center;gap:5px;color:#fff;border-radius:3px;
   padding:2px 8px;font-size:11px;font-weight:700;letter-spacing:.3px;white-space:nowrap}
.ic{flex:none}
.card{border:1px solid #e2e8f0;border-left:4px solid %(grey)s;border-radius:4px;padding:12px 14px;
   margin:10px 0;background:#fff}
.card.ESCALATE{border-left-color:%(red)s;background:#fdf6f6}
.card.CONFIRM{border-left-color:%(amber)s;background:#fffaf3}
.card.MONITOR{border-left-color:%(blue)s}
.card .hd{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.card .tx{font-size:15px;font-weight:700;font-style:italic}
.meta{margin:7px 0 0;display:flex;gap:16px;flex-wrap:wrap;color:%(grey)s;font-size:12px}
.meta .tier{color:%(red)s;font-weight:700}
.why{margin:9px 0 0;font-size:13px}
.self{font-weight:700;background:#fff3cd;padding:0 3px;border-radius:3px}
.ev{margin-top:11px;padding:10px 12px;background:%(light)s;border-radius:3px;overflow-x:auto}
/* the evidence tables are wide by design; they scroll inside .ev, never the page */
.ev.inferred{background:#fbf7ef;border:1px dashed %(amber)s}
table.ev{margin-top:6px;font-size:12px}
table.ev th{text-align:left;font-weight:600;color:%(grey)s;border-bottom:1px solid #d6e0ea;
   padding:3px 10px 3px 0;font-size:11px;text-transform:uppercase;letter-spacing:.3px}
table.ev td{padding:3px 10px 3px 0;border-bottom:1px solid #e8eef4;vertical-align:top}
table.wide td:last-child,.basis{color:%(grey)s;font-size:11.5px;max-width:420px}
.acc{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;color:%(blue)s}
.tiny{font-size:11.5px;color:%(grey)s;margin:3px 0 0}
.blurb{font-size:12.5px;color:%(grey)s;margin:0 0 10px}
.warn{border:1px solid %(red)s;background:#fdf6f6;border-radius:4px;padding:12px 14px;
   font-size:12.5px;margin-bottom:14px}
.verdict{display:flex;gap:14px;align-items:flex-start;border:1px solid;border-left-width:5px;
   border-radius:4px;padding:12px 14px;margin:4px 0 14px;background:#fcfdfe;font-size:12.5px}
.vchip{color:#fff;font-weight:700;font-size:13px;letter-spacing:.5px;padding:5px 12px;
   border-radius:3px;white-space:nowrap;flex:none}
.verdict ul{margin:6px 0 0}
.note{border-left:3px solid %(amber)s;background:#fffaf3;padding:8px 11px;font-size:12px;
   margin:10px 0 0}
.band{margin-bottom:26px}
.band.nt{opacity:.85}
ul.plain,ol.plain{margin:6px 0;padding-left:18px;font-size:12.5px}
ul.plain.cols{columns:2;font-size:12px}
.fold{margin:8px 0}
.fold summary{cursor:pointer;font-size:12.5px;color:%(blue)s;padding:6px 0;font-weight:600}
pre{background:%(light)s;padding:10px 12px;border-radius:3px;font-size:12px;overflow-x:auto}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;background:%(light)s;
   padding:1px 4px;border-radius:2px}
footer{border-top:1px solid #e2e8f0;padding:16px 26px;color:%(grey)s;font-size:11.5px}
@media print{.bar,.tabs{display:none}.panel,.tabp{display:block!important}}

/* -- flagged-species cover sheet ----------------------------------------------
   Sits above the sample switcher and spans the whole batch. It ranks; it never
   replaces. Every row links down to the evidence card it summarises. */
.flagged{background:#fff;border-bottom:2px solid #EDF2F8;padding:22px 0 26px}
.flwrap{max-width:1180px;margin:0 auto;padding:0 26px}
.flmast{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin-bottom:16px}
.flmast h2{margin:0;font-size:17px;color:#00539B}
.flband + .flband{margin-top:20px}
.flhead{display:flex;align-items:baseline;gap:12px;margin-bottom:7px}
.flhead h3{margin:0;font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;
  color:#333333;border:0;padding:0}
.flhead .ct{background:#EDF2F8;border-radius:9px;padding:0 7px;font-size:11px}
.flhint{margin-left:auto;font-size:11.5px;color:#6D6D6D;text-align:right}
details.fl{border:1px solid #dde3ea;border-radius:7px;background:#fff;overflow:hidden}
details.fl + details.fl{margin-top:7px}
details.fl > summary{list-style:none;cursor:pointer;display:grid;align-items:stretch;gap:14px;
  grid-template-columns:132px minmax(150px,1.5fr) 92px 132px 132px 124px 14px;
  padding:11px 14px;min-height:44px}
details.fl > summary::-webkit-details-marker{display:none}
details.fl > summary:hover{background:#f7f9fb}
details.fl > summary:focus-visible{outline:2px solid #00539B;outline-offset:-2px}
details.fl.hot{border-left:4px solid #AD6400}
details.fl.nt{border-left:4px solid #6D6D6D}
details.fl.mon{border-left:4px solid #00539B}
.fn{font-weight:600;font-size:13.5px;line-height:1.25;align-self:center}
.fsub{display:block;font-weight:400;font-size:11px;color:#6D6D6D;margin-top:1px}
.fv,.fc{align-self:center;min-width:0}
.fl-l{display:block;font-size:10.5px;letter-spacing:.04em;text-transform:uppercase;
  color:#6D6D6D}
.fl-v{display:block;font-size:12px;color:#333333;margin-top:2px}
.ftri{align-self:center;color:#6D6D6D;font-size:10px}
details.fl[open] > summary{border-bottom:1px solid #EDF2F8;background:#f7f9fb}
details.fl[open] .ftri{transform:rotate(90deg)}
.flbody{padding:4px 16px 16px}
.flrest{padding:11px 14px;font-size:12px;color:#333333;border:1px solid #dde3ea;
  border-radius:7px;background:#fbfcfd;line-height:1.8}
.cdots{display:inline-flex;gap:3px;vertical-align:-1px}
.cn{font-size:11.5px}
.cdot{width:11px;height:11px;border-radius:3px;background:#AD6400}
.cdot.off{background:transparent;border:1px solid #c8cfd6;color:#6D6D6D}
td.code{white-space:nowrap}
/* BEC badge. Contrast is checked in test_flagged_layer.py, not eyeballed. */
.bec{display:inline-flex;align-items:center;gap:5px;font-weight:700;font-size:11px;
  letter-spacing:.03em;padding:2px 7px 2px 5px;border-radius:4px;white-space:nowrap;
  border-left:2px solid transparent}
.bec .pips,.pipkey{font-size:8px;letter-spacing:.5px;line-height:1;opacity:.85}
.pipkey{color:#333333}
.bec.dR{background:#FBEAEA;color:#C02A2A;border-left-color:#C02A2A}
.bec.dR.s4{background:#C02A2A;color:#fff;border-left-color:#7D1A1A}
.bec.dL{background:#EAF5EE;color:#1E7A3C;border-left-color:#1E7A3C}
.bec.dU{background:#F2F3F4;color:#5C5C5C;border-left-color:#8B8B8B}
.bec.s1{border-left-width:2px}.bec.s2{border-left-width:4px}
.bec.s3{border-left-width:6px}.bec.s4{border-left-width:8px}
/* .off = tested and not satisfied, or never testable. It keeps its strength (that is a
   property of the code) but must never out-shout a criterion that actually fired. */
.bec.off{background:transparent;box-shadow:inset 0 0 0 1px currentColor}
.bec.dR.s4.off{background:transparent;color:#C02A2A;border-left-color:#C02A2A}
.bec.off .pips{opacity:.55}
td.meas{font-size:12px}
td.gate{color:#6D6D6D;font-size:11px}
.met{color:#333333}
.unmet{color:#6D6D6D}
.tag{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.03em;padding:1px 6px;
  border-radius:3px}
.tag.hit{background:#AD6400;color:#fff}
.tag.none{border:1px solid #c8cfd6;color:#6D6D6D}
.verdictline{margin-top:10px;padding:8px 12px;border-radius:5px;background:#EDF2F8;
  font-size:12.5px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
a.deep{color:#00539B;display:inline-block;min-height:24px;line-height:24px}
@media (max-width:900px){
  details.fl > summary{grid-template-columns:1fr 14px}
  details.fl > summary .fc{display:none}
}

/* -- visual summary: two part-to-whole figures, each with a table twin -------- */
.fig{border:1px solid #dde3ea;border-radius:7px;background:#fff;padding:13px 15px 14px;
  margin-bottom:14px}
.fighd{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:11px}
.fighd b{font-size:12.5px}
.fighd .tiny{margin-left:auto;text-align:right;max-width:62ch}
.tbar{display:flex;align-items:center;gap:10px;min-height:26px}
.tbar + .tbar{margin-top:6px}
.tbl{width:74px;flex:none;font-size:11.5px;text-align:right;color:#6D6D6D;
  font-family:ui-monospace,Menlo,Consolas,monospace}
.ttrack{display:flex;gap:2px;height:24px;min-width:2px}
.tseg{display:flex;align-items:center;justify-content:center;min-width:3px;height:100%%;
  border-radius:2px;font-size:11px;font-weight:600;overflow:hidden;
  font-family:ui-monospace,Menlo,Consolas,monospace}
.tsl{line-height:1}
.tsl.onhatch{background:#fff;padding:1px 4px;border-radius:2px}
.ttrack .tseg:first-child{border-radius:4px 2px 2px 4px}
.ttrack .tseg:last-child{border-radius:2px 4px 4px 2px}
.ttot{font-size:11.5px;color:#333;font-family:ui-monospace,Menlo,Consolas,monospace}
.tlgs{display:flex;gap:16px;flex-wrap:wrap;margin-top:12px;padding-left:84px}
.tlg{display:inline-flex;align-items:center;gap:6px;font-size:11.5px;color:#333;
  min-height:24px}
.tlg .ic{color:#6D6D6D}
.tsw{width:11px;height:11px;border-radius:2px;flex:none;display:inline-block}
.covrow{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.covbar2{display:flex;gap:2px;width:210px;height:24px;flex:none}
.covok{background:#00539B;border-radius:4px 2px 2px 4px}
.covgap{border:1px solid #6D6D6D;border-radius:2px 4px 4px 2px;
  background:repeating-linear-gradient(45deg,#fff 0 4px,#6D6D6D 4px 5px)}
.covtx{font-size:12.5px;color:#333;flex:1;min-width:280px}
@media (max-width:900px){.tlgs{padding-left:0}.tbl{width:58px}}

/* -- per-sample report: the verdict is the headline ------------------------- */
.svhero{background:%(light)s;border-bottom:1px solid #dbe3ec;padding:20px 0 22px}
.svwrap{max-width:1180px;margin:0 auto;padding:0 26px}
.svmain{display:flex;gap:16px;align-items:flex-start}
.svchip{color:#fff;font-weight:700;font-size:15px;letter-spacing:.06em;padding:9px 16px;
  border-radius:6px;white-space:nowrap;flex:none}
.svtext{font-size:12.5px;color:%(ink)s;line-height:1.6}
.svtext ul{margin:7px 0 0;padding-left:17px}
.nc{color:%(grey)s;font-style:italic}
header .nc{color:#B9CCE0}
details.cohort{border:1px solid #dde3ea;border-radius:7px;background:#fbfcfd;margin:0 0 16px}
details.cohort > summary{cursor:pointer;padding:10px 14px;font-size:12.5px;min-height:44px;
  display:flex;align-items:center;gap:8px}
details.cohort > summary:focus-visible{outline:2px solid %(blue)s;outline-offset:-2px}
.cohortb{padding:0 14px 12px}
.cfp{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11px;color:%(grey)s}
.cid{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11.5px;color:%(ink)s}
.cohort.none{padding:11px 14px;font-size:12.5px;color:%(ink)s}
""" % C

JS = """
function pick(sel,attr,on){document.querySelectorAll(sel).forEach(function(b){
  b.setAttribute('aria-selected', String(b.dataset[attr]===on));});}
function showSample(id){pick('.bar button','s',id);
  document.querySelectorAll('.panel').forEach(function(p){p.hidden=(p.dataset.s!==id);});}
function showTab(s,t){pick('.panel[data-s="'+s+'"] .tabs button','t',t);
  document.querySelectorAll('.panel[data-s="'+s+'"] .tabp').forEach(function(p){
    p.hidden=(p.dataset.t!==t);});}
/* A cover-sheet link points at a card inside a hidden panel, a closed appendix AND a hidden
   tab. Reveal all three before the browser tries to scroll, or the jump silently lands nowhere. */
function openCard(s){showSample(s);
  document.querySelectorAll('.panel[data-s="'+s+'"] details.appx').forEach(function(a){a.open=true;});
  showTab(s,'sp');
  /* the link's hash lands after onclick; expand the target row once it has */
  setTimeout(function(){var el=location.hash&&document.getElementById(location.hash.slice(1));
    if(el){expandRow(el);el.scrollIntoView();}},0);}
function toggleRow(b){var tb=b.closest('tbody');var open=tb.classList.toggle('open');
  b.setAttribute('aria-expanded',String(open));tb.rows[1].hidden=!open;}
function expandRow(el){var p=el;while((p=p.parentElement)){if(p.tagName==='DETAILS')p.open=true;}
  var tb=el.closest('tbody');if(tb&&!tb.classList.contains('open'))toggleRow(tb.querySelector('button.xb'));}
/* sort by <th>: numeric when the cell carries data-v, text otherwise; tbodies move as units */
function sortBy(th){var tb=th.closest('table'),i=[].indexOf.call(th.parentNode.children,th);
  var dir=th.getAttribute('aria-sort')==='ascending'?'descending':'ascending';
  tb.querySelectorAll('th[aria-sort]').forEach(function(h){h.setAttribute('aria-sort','none');});
  th.setAttribute('aria-sort',dir);
  var val=function(g){var c=g.rows[0].cells[i];if(c.dataset.v!==undefined){
    var n=parseFloat(c.dataset.v);return isNaN(n)?-Infinity:n;}
    return c.textContent.trim().toLowerCase();};
  var gs=[].slice.call(tb.tBodies);
  if(gs.length===1){var rs=[].slice.call(gs[0].rows);
    rs.sort(function(a,b){var x=a.cells[i],y=b.cells[i];var p=x.dataset.v!==undefined?
      (parseFloat(x.dataset.v)||0)-(parseFloat(y.dataset.v)||0):
      x.textContent.trim().toLowerCase().localeCompare(y.textContent.trim().toLowerCase());return p;});
    if(dir==='descending')rs.reverse();rs.forEach(function(r){gs[0].appendChild(r);});return;}
  gs.sort(function(a,b){var x=val(a),y=val(b);
    return typeof x==='number'?x-y:x.localeCompare(y);});
  if(dir==='descending')gs.reverse();gs.forEach(function(g){tb.appendChild(g);});}
function amrFilter(b,c){var w=b.closest('.amrw');
  w.querySelectorAll('.fltr button').forEach(function(x){x.setAttribute('aria-pressed',String(x===b));});
  w.querySelectorAll('tbody tr').forEach(function(r){r.hidden=!!c&&r.dataset.c!==c;});}
"""

# -- one-page layout (2026-10-26) ---------------------------------------------------------------
# Header · verdict strip · at most three flagged cards · panels · collapsed evidence appendix.
# Nothing the old tabs rendered is gone: it all sits behind one <details>, so the ~64k words of
# evidence stay reachable and stop being the first thing a reader meets. Charts are inline SVG,
# one hue per job (blue = this swab, grey outline = comparators, amber = CONFIRM), direct labels
# on at most a handful of marks, and every chart has a table twin in the appendix.
CSS += """
.pghead{display:flex;gap:18px;align-items:center;flex-wrap:wrap;padding:14px 26px;
  background:#fff;border-bottom:1px solid #e2e8f0;font-size:12.5px}
.pghead .site{font-weight:700;font-size:14px}
.gauge{display:inline-flex;align-items:center;gap:8px;font-size:12px}
.gl{font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:#6D6D6D}
.gtrack{width:110px;height:10px;border-radius:5px;background:#e8eef4;overflow:hidden;flex:none}
.gfill{display:block;height:100%;border-radius:5px}
.standing{margin-left:auto;font-size:11.5px;color:#6D6D6D;border:1px dashed #c8cfd6;
  border-radius:4px;padding:3px 9px}
.vstrip{display:flex;gap:14px;align-items:center;flex-wrap:wrap;padding:14px 26px;
  background:#EDF2F8;border-bottom:1px solid #dbe3ec}
.vstrip .svchip{font-size:14px;padding:7px 14px}
.vstrip .vreason{font-size:13px;flex:1;min-width:min(260px,100%)}
.flag{display:inline-block;font-size:10.5px;font-weight:700;letter-spacing:.05em;
  padding:3px 8px;border-radius:3px;border:1px solid;margin-left:4px}
.flag.qc-limited{color:#C02A2A;border-color:#C02A2A;background:#FBEAEA}
.flag.not-tested{color:#5C5C5C;border-color:#8B8B8B;background:#F2F3F4}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr));gap:14px;
  padding:16px 26px 4px}
.fcard{border:1px solid #dde3ea;border-left:5px solid #6D6D6D;border-radius:7px;padding:12px 14px;
  background:#fff;display:flex;flex-direction:column;gap:8px;min-width:0}
.fcard.ESCALATE{border-left-color:#C02A2A}.fcard.CONFIRM{border-left-color:#AD6400}
.fcard.MONITOR{border-left-color:#00539B}.fcard.NOT_TESTED{border-left-color:#8B8B8B}
.fchd{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.fchd i{font-weight:700;font-size:14px}
.fcm{font-size:12px;color:#333}
.cks{display:grid;grid-template-columns:1fr 1fr;gap:5px 10px}
.ck{display:flex;align-items:center;gap:6px;font-size:11.5px;color:#333;min-height:22px}
.ck b{font-weight:600;color:#6D6D6D;margin-left:auto;text-align:right;font-size:11px}
.ckb{width:15px;height:15px;border:1.5px solid #8B8B8B;border-radius:3px;flex:none;
  display:inline-flex;align-items:center;justify-content:center;font-size:11px;line-height:1}
.ck.on .ckb{background:#00539B;border-color:#00539B;color:#fff}
.ck.na .ckb{border-style:dashed;color:#8B8B8B}
.fact{font-size:12.5px;font-weight:600;border-top:1px solid #eef2f6;padding-top:7px}
.nocard{margin:16px 26px 4px;padding:12px 14px;border:1px solid #dde3ea;border-radius:7px;
  font-size:12.5px;background:#fbfcfd}
.panels{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(360px,100%),1fr));gap:14px;
  padding:12px 26px 10px}
.panel-fig{border:1px solid #dde3ea;border-radius:7px;background:#fff;padding:12px 14px;min-width:0}
.panel-fig b.t{font-size:12.5px;display:block;margin-bottom:2px}
.panel-fig .tiny{margin:0 0 8px}
.panel-fig svg{display:block;width:100%;max-width:520px;height:auto;overflow:visible}
details.appx{margin:10px 26px 30px;border:1px solid #dde3ea;border-radius:7px;background:#fbfcfd}
details.appx > summary{cursor:pointer;padding:11px 14px;font-size:13px;font-weight:600;
  color:#00539B;min-height:44px;display:flex;align-items:center}
details.appx > summary:focus-visible{outline:2px solid #00539B;outline-offset:-2px}
details.appx[open] > summary{border-bottom:1px solid #e2e8f0}
details.appx .flagged{border:0;padding:12px 0}
details.appx main{padding-top:10px}
.ctrl{font-size:11.5px;color:#333}
.ctrl.fail{color:#C02A2A;font-weight:700}
@media print{details.appx{display:none}}

/* -- evidence browser (appendix redesign) ------------------------------------
   One sortable table per section, one <tbody> per organism (summary row + hidden
   expansion), a left section nav with counts. Text is 13px minimum in tables;
   grey ink is #5C5C5C or darker on every light ground (>= 4.5:1). */
.vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.apgrid{display:grid;grid-template-columns:200px minmax(0,1fr);gap:0 22px;align-items:start}
.apnav{position:sticky;top:0;display:flex;flex-direction:column;gap:2px;padding:14px 0 14px 14px;
  border:0}
.apnav button{text-align:left;border:0;border-left:3px solid transparent;padding:9px 12px;
  font:600 13px/1.3 inherit;color:#333;background:none;cursor:pointer;border-radius:0 5px 5px 0;
  display:flex;justify-content:space-between;gap:8px;min-height:44px;align-items:center}
.apnav button:hover{background:#EDF2F8}
.apnav button[aria-selected=true]{border-left-color:#00539B;color:#00539B;background:#EDF2F8}
.apnav button:focus-visible{outline:2px solid #00539B;outline-offset:-2px}
.apnav .ct{font-weight:700}
.apgrid > main{padding:14px 18px 40px 0;min-width:0}
.apgrid .flwrap{padding:0;max-width:none}
@media (max-width:999px){
  .apgrid{display:block}
  .apnav{position:static;flex-direction:row;flex-wrap:wrap;padding:8px 14px;gap:4px;
    border-bottom:1px solid #e2e8f0}
  .apnav button{border-left:0;border-bottom:3px solid transparent;border-radius:0;padding:8px 10px}
  .apnav button[aria-selected=true]{border-bottom-color:#00539B;background:none}
  .apgrid > main{padding:12px 14px 30px}
}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid #dde3ea;border-radius:7px;
  background:#fff}
table.sp{font-size:13px;min-width:720px;width:100%}
table.sp td.org-n{min-width:150px}
table.sp th{text-align:left;font-weight:600;color:#5C5C5C;font-size:12px;letter-spacing:.02em;
  border-bottom:2px solid #d6e0ea;padding:0;background:#fff;white-space:nowrap}
table.sp th button{all:unset;display:block;padding:9px 10px;cursor:pointer;min-height:40px;
  box-sizing:border-box;width:100%}
table.sp th button:hover{color:#00539B}
table.sp th button:focus-visible{outline:2px solid #00539B;outline-offset:-2px}
table.sp th[aria-sort=ascending] button::after{content:" \\25B4";color:#00539B}
table.sp th[aria-sort=descending] button::after{content:" \\25BE";color:#00539B}
table.sp td{padding:7px 8px;border-bottom:1px solid #e8eef4;vertical-align:middle}
table.sp td.num{white-space:nowrap}
table.sp tbody.org{border-left:4px solid transparent}
table.sp tbody.hot{border-left-color:#AD6400}
table.sp tbody.nt{border-left-color:#8B8B8B}
table.sp tbody.mon{border-left-color:#00539B}
table.sp tbody.open > tr.xr > td{background:#f7f9fb;border-bottom-color:#f7f9fb}
.org-n i{font-weight:600}
.org-n .fsub{font-size:11.5px;color:#5C5C5C}
.xb{all:unset;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;
  width:32px;height:32px;border-radius:4px;color:#5C5C5C}
.xb:hover{background:#EDF2F8}
.xb:focus-visible{outline:2px solid #00539B}
.xb .ftri{transition:transform .15s ease-out;font-size:10px}
.xb[aria-expanded=true] .ftri{transform:rotate(90deg)}
@media (prefers-reduced-motion:reduce){.xb .ftri{transition:none}}
tr.xd > td{background:#fbfcfd;padding:12px 16px 16px;border-bottom:2px solid #d6e0ea}
.cks-c .cks{display:grid;grid-template-columns:auto auto;gap:2px 12px;white-space:nowrap;
  width:max-content}
.cks-c .ck{font-size:12px;min-height:18px;gap:4px}
.xp{grid-template-columns:repeat(auto-fit,minmax(min(280px,100%),1fr))}
table.ev.short{table-layout:auto}
table.ev.short td{font-size:12px}
table.ev.short td.tiny,table.ev.short .tiny{font-size:11.5px}
.xwhy{margin:0 0 10px;font-size:13px;max-width:90ch}
.xp{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;align-items:start}
.xpan{background:#fff;border:1px solid #dde3ea;border-radius:6px;padding:10px 12px;min-width:0;
  overflow-x:auto}
.xpan h4{margin:0 0 8px;font-size:12.5px}
.xpan .src{margin-left:auto}
.xpan .dots{margin:0 0 6px}
.lgrid{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:5px 10px;align-items:start;
  font-size:12.5px}
.lgt{line-height:1.4}
.lgm{display:block;color:#5C5C5C;font-size:12px}
.lgm .gate{font-size:11px;color:#5C5C5C}
.xpan .verdictline{margin-top:8px;padding:6px 10px;font-size:12px}
.xpan table.ev{font-size:12.5px}
.xpan .tiny,.tiny{color:#5C5C5C;font-size:12px}
.fold.inferred{border:1px dashed #AD6400;border-radius:5px;padding:0 10px 4px;background:#fbf7ef}
.fold.big > summary{font-size:13px;padding:10px 0}
.bkey{display:flex;gap:14px;flex-wrap:wrap;margin:14px 0 8px;font-size:12.5px;color:#333}
.bk{display:inline-flex;align-items:center;gap:6px;padding-left:10px;border-left:4px solid}
.bk.hot{border-color:#AD6400}.bk.nt{border-color:#8B8B8B}.bk.mon{border-color:#00539B}
.fltr{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 10px}
.fltr button{font:600 12.5px inherit;color:#333;background:#fff;border:1px solid #c8cfd6;
  border-radius:16px;padding:6px 12px;cursor:pointer;min-height:36px;display:inline-flex;
  align-items:center;gap:6px}
.fltr button[aria-pressed=true]{background:#00539B;border-color:#00539B;color:#fff}
.fltr button[aria-pressed=true] .ct{background:#fff}
.fltr button:focus-visible{outline:2px solid #00539B;outline-offset:2px}
.tw.sticky{overflow:visible}
.tw.sticky th{position:sticky;top:0;z-index:1;box-shadow:0 2px 0 #d6e0ea}
table.amr .fold{margin:0}
table.amr .fold summary{padding:2px 0;font-size:12px}
table.amr td.basis{max-width:360px;font-size:12px;color:#333}
@media (max-width:999px){.tw.sticky{overflow-x:auto}.tw.sticky th{position:static;box-shadow:none}}
details.ms{border:1px solid #dde3ea;border-radius:6px;background:#fff;margin:0 0 8px}
details.ms > summary{cursor:pointer;padding:10px 14px;min-height:44px;display:flex;gap:12px;
  align-items:baseline;flex-wrap:wrap;font-size:13px}
details.ms > summary:focus-visible{outline:2px solid #00539B;outline-offset:-2px}
details.ms > summary .tiny{margin:0}
details.ms > :not(summary){padding:0 14px}
details.ms[open] > summary{border-bottom:1px solid #e2e8f0;margin-bottom:8px}
.band.nt{opacity:1}
.apgrid h3{margin-top:4px}
"""

ACTION = {
    'ESCALATE':   'Notify now: a threat-list agent with its confirmatory marker.',
    'CONFIRM':    'Culture with AST, and resample this site.',
    'NOT_TESTED': 'Targeted PCR or culture: present, and the marker test had no power here.',
    'MONITOR':    'Read at the next weekly review.',
}


def card_pick(d):
    """At most three taxa, worst first: CONFIRM/ESCALATE, then present-but-unassessable, then
    a site-enriched listed organism. Community-context rows never make a card. Returns
    (cards, how many further candidates were left for the appendix)."""
    th = triage.TH['enrichment_fold']

    def rank(t):
        v = t['verdict']
        if v == 'ESCALATE':
            return 0
        if v == 'CONFIRM':
            return 1
        if v == 'NOT_TESTED' and t.get('real'):
            return 2
        if v == 'MONITOR' and (t.get('fold') or 0) >= th:
            return 3
        return 9
    cand = [t for t in d['taxa'] if (t.get('tier') or '-') != '-' and rank(t) < 9]
    cand.sort(key=lambda t: (rank(t), -(t.get('real') or 0)))
    return cand[:3], max(0, len(cand) - 3)


def _box(met, label, value, na=False, compact=False):
    cls = 'na' if na else ('on' if met else 'off')
    mark = '&ndash;' if na else ('&#10003;' if met else '')
    if compact:   # table row: box + label; the number lives in the row's own columns
        return (f'<span class="ck {cls}" title="{label}: {E(value)}"><span class="ckb">{mark}</span>'
                f'{label}</span>')
    return f'<span class="ck {cls}"><span class="ckb">{mark}</span>{label}<b>{E(value)}</b></span>'


def checklist(d, t, compact=False):
    """The four criteria as boxes with the measured number beside each. The ledger says the same
    thing in ~1,500 words; this is the version an operations officer reads."""
    why = t.get('why') or ''
    fold, th = t.get('fold'), triage.TH['enrichment_fold']
    enr = fold is not None and fold >= th
    fv = 'n/a' if fold is None else ('only here' if fold == float('inf') else f'{fold:.1f}×')
    gr = t.get('genus_ratio')
    if gr is not None and fold not in (None, float('inf')):
        fv += f' · genus {gr:.1f}×'
    co = 'CO-LOCATION' in why
    nconf = sum(1 for c in (t.get('amr_context') or [])
                if c.get('verdict') == 'CONFIRM' and c.get('class') == 'acquired')
    gv = (f'{nconf} at CONFIRM' + (', host documented' if co else ', host unresolved')
          if nconf else 'none')
    w = triage.RULES['clinical_watchlist'].get(binomial(t['taxon'])) or {}
    req = list(t.get('markers_required') or []) + list(w.get('markers') or [])
    found = list(t.get('markers_found') or [])
    if 'MARKER PRESENT: ' in why and not found:
        found = [why.split('MARKER PRESENT: ', 1)[1].split(';')[0].split(' - ')[0]]
    mv = (', '.join(found) if found else 'not assessable' if 'NOT ASSESSABLE' in why
          else 'absent' if req else 'none defined')
    qc_ok = not any(f == 'QC-LIMITED' for f, _ in d['flags'])
    return ('<div class="cks">' + _box(enr, 'enriched', fv, na=fold is None, compact=compact)
            + _box(co, 'acquired gene', gv, compact=compact)
            + _box(bool(found), 'marker', mv, na=not req and not found, compact=compact)
            + _box(qc_ok, 'QC ok', 'yes' if qc_ok else 'QC-LIMITED', compact=compact) + '</div>')


def card(d, t):
    v = t['verdict']
    sub = (E(t.get('watch_priority')) if t.get('tier') == 'W'
           else f'CDC Category {E(t["tier"])}')
    abund = f'<b>{t["real"]:,}</b> reads' + (f' &middot; {E(t["abundance"])}' if t.get('abundance') else '')
    return (f'<div class="fcard {v}"><div class="fchd">{chip(v)}<i>{E(t["taxon"])}</i>'
            f'<span class="tiny">{sub}</span></div>'
            f'<div class="fcm">{abund} &middot; comparators: {E(d["basis"].split(" (")[0])}</div>'
            f'{checklist(d, t)}<div class="fact">{E(ACTION.get(v, ""))}</div>'
            f'<a class="deep tiny" href="#{anchor(d, t)}" onclick="openCard(\'{E(d["id"])}\')">'
            f'Full evidence &rarr;</a></div>')


def _qcnum(q, key):
    v = str(q.get(key, '') or '').split(' ')[0].replace(',', '')
    return int(v) if v.isdigit() else 0


def page_head(d, meta):
    q, floor, clas = d['qc'], triage.TH['qc_classified_floor'], d['classified']
    host = str(q.get('Host_Read', ''))
    host = host.split('(')[1].rstrip(')') if '(' in host else '&mdash;'
    lim = clas < floor
    gauge = (f'<span class="gauge"><span class="gl">QC</span><span class="gtrack">'
             f'<span class="gfill" style="width:{min(clas / floor, 1.0):.0%};'
             f'background:{C["red"] if lim else C["green"]}"></span></span>'
             f'<span>{clas / 1e6:.2f}M classified <span class="tiny">/ {floor / 1e6:.0f}M floor'
             f'</span> &middot; host {host}</span></span>')
    standing = ('' if d['showRNA'] else
                '<span class="standing">DNA assay &rarr; RNA viruses NOT TESTED</span>')
    ctrl = ''
    if d.get('control'):
        c = d['control']
        ctrl = f'<span class="ctrl{"" if c["ok"] else " fail"}">run control: {E(c["line"])}</span>'
    return (f'<div class="pghead"><span class="site">{site_line(d["id"], meta)}</span>'
            f'{gauge}{ctrl}{standing}</div>')


def verdict_strip(d):
    sv, sv_why = d['verdict']
    reason = sv_why[0] if sv_why else 'Nothing above threshold.'
    flags = ''.join(f'<span class="flag {f.lower()}" title="{E(r)}">{E(f)}</span>'
                    for f, r in d['flags'])
    return (f'<div class="vstrip"><span class="svchip" style="background:{_sv_col(sv)}">{E(sv)}'
            f'</span><span class="vreason">{E(reason)}'
            + (f' <span class="tiny">+{len(sv_why) - 1} more in the appendix</span>'
               if len(sv_why) > 1 else '')
            + f'</span><span>{flags}</span></div>')


def cards_html(d):
    cards, more = card_pick(d)
    if not cards:
        return ('<div class="nocard"><b>No organism meets a card criterion.</b> Nothing reached '
                'CONFIRM, nothing listed is enriched at this site, and nothing present was left '
                'unassessable. Listed organisms at background level are in the appendix.</div>')
    tail = (f'<div class="nocard tiny">+ {more} further candidate{"s" if more != 1 else ""} '
            f'below these three &mdash; see the appendix.</div>' if more else '')
    return f'<div class="cards">{"".join(card(d, t) for t in cards)}</div>{tail}'


def dot_strip(d):
    """Site vs comparators, one row per card taxon, log x. Filled = this swab, open = comparators.
    A bar would imply a zero baseline a log ratio does not have."""
    rows = [r for r in d['loadrows'] if r[2] > 0 or any(v > 0 for _, v in r[3])]
    if not rows:
        return ''
    vals = [v for _, _, h, o in rows for v in [h] + [x for _, x in o] if v > 0]
    lo, hi = math.floor(math.log10(min(vals))), math.ceil(math.log10(max(vals)))
    if hi == lo:
        hi = lo + 1
    W, L, R, rh = 520, 190, 16, 26
    x = lambda v: L + (math.log10(max(v, 10 ** lo)) - lo) / (hi - lo) * (W - L - R)
    H = 16 + len(rows) * rh + 22
    s = [f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
         f'aria-label="reads per million classified, this swab against its comparators">']
    for p in range(lo, hi + 1):
        s.append(f'<line x1="{x(10 ** p):.1f}" x2="{x(10 ** p):.1f}" y1="8" y2="{H - 20}" '
                 f'stroke="#eef2f6"/><text x="{x(10 ** p):.1f}" y="{H - 6}" text-anchor="middle" '
                 f'font-size="10" fill="#6D6D6D">{10 ** p:,}</text>')
    for i, (taxon, _, here, others) in enumerate(rows):
        y = 18 + i * rh
        s.append(f'<text x="{L - 8}" y="{y + 4}" text-anchor="end" font-size="11" '
                 f'font-style="italic" fill="#333">{E(taxon[:30])}</text>')
        for sid, v in others:
            if v > 0:
                s.append(f'<circle cx="{x(v):.1f}" cy="{y}" r="4.5" fill="#fff" stroke="#6D6D6D" '
                         f'stroke-width="1.5"><title>{E(sid)}: {v:,.0f} reads/M</title></circle>')
        if here > 0:
            s.append(f'<circle cx="{x(here):.1f}" cy="{y}" r="5.5" fill="{C["blue"]}" stroke="#fff" '
                     f'stroke-width="2"><title>{E(d["sample"])}: {here:,.0f} reads/M</title></circle>')
    s.append('</svg>')
    return (f'<div class="panel-fig"><b class="t">This swab vs comparators</b><p class="tiny">'
            f'Reads per million classified, log scale. Filled = {E(d["sample"])}; open = '
            f'{E(d["basis"].split(" (")[0])} comparators.</p>{"".join(s)}</div>')


def amr_strip(data, cur):
    """Drug class x swab, shaded by the deepest acquired gene; amber ring = a CONFIRM in that
    class. rRNA and efflux classes are already out (gates 4-5). One hue, light to dark."""
    keep = lambda g: g.get('class') == 'acquired' and g['verdict'] in ('CONFIRM', 'MONITOR') and g.get('drug_class')
    classes = sorted({g['drug_class'] for d in data for g in d['genes'] if keep(g)})
    if not classes:
        return ''
    best = {(d['id'], g['drug_class']): max([x['depth'] for x in d['genes'] if keep(x)
                                              and x['drug_class'] == g['drug_class']] or [0])
            for d in data for g in d['genes'] if keep(g)}
    conf = {(d['id'], g['drug_class']) for d in data for g in d['genes']
            if keep(g) and g['verdict'] == 'CONFIRM'}
    top = max(best.values()) or 1
    cw, rh, L, T = 24, 24, 66, 78
    W, H = L + len(classes) * cw + 8, T + len(data) * rh + 6
    s = [f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
         f'aria-label="acquired resistance classes per swab">']
    for ci, cls in enumerate(classes):
        cx = L + ci * cw + cw / 2
        s.append(f'<text transform="translate({cx:.1f},{T - 6}) rotate(-55)" font-size="10" '
                 f'fill="#6D6D6D" text-anchor="start">{E(cls[:24])}</text>')
    for ri, d in enumerate(data):
        y = T + ri * rh
        s.append(f'<text x="{L - 6}" y="{y + rh / 2 + 4}" text-anchor="end" font-size="11" '
                 f'font-weight="{700 if d["id"] == cur else 400}" fill="#333">{E(d["sample"])}</text>')
        for ci, cls in enumerate(classes):
            v = best.get((d['id'], cls), 0)
            a = 0.12 + 0.88 * (math.log10(1 + v) / math.log10(1 + top)) if v else 0
            fill = f'rgba(0,83,155,{a:.2f})' if v else '#f4f6f9'
            ring = f' stroke="{C["amber"]}" stroke-width="2.5"' if (d['id'], cls) in conf else ''
            s.append(f'<rect x="{L + ci * cw + 1}" y="{y + 1}" width="{cw - 2}" height="{rh - 2}" '
                     f'rx="3" fill="{fill}"{ring}><title>{E(d["sample"])} &middot; {E(cls)}: '
                     f'{v:.1f}x deepest acquired gene{" (CONFIRM)" if (d["id"], cls) in conf else ""}'
                     f'</title></rect>')
    s.append('</svg>')
    return (f'<div class="panel-fig"><b class="t">Acquired resistance by drug class</b>'
            f'<p class="tiny">Shade = depth of the deepest acquired gene in the class; amber ring = '
            f'a gene at CONFIRM. Not attributed to any organism.</p>{"".join(s)}</div>')


def qc_bars(data, cur):
    """Read partition per swab as one horizontal bar, absolute length = raw reads, with the
    classified floor marked. For WBM156 the partition IS the finding."""
    segs = [('Host_Read', 'host', '#b9c4d0'), ('Lowquality_Read', 'low quality', '#dfe5ec'),
            ('Unclassified_Read', 'unclassified', '#8fb3d9'), ('Classified_Read', 'classified', C['blue'])]
    floor = triage.TH['qc_classified_floor']
    raws = {d['id']: (_qcnum(d['qc'], 'Raw_Read') or sum(_qcnum(d['qc'], k) for k, _, _ in segs))
            for d in data}
    top = max(raws.values()) or 1
    L, R, rh, W = 66, 118, 22, 520
    H = 10 + len(data) * rh + 26
    s = [f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="read QC">']
    for ri, d in enumerate(data):
        y, x0 = 10 + ri * rh, L
        q, raw = d['qc'], raws[d['id']]
        bw = (W - L - R) * raw / top
        s.append(f'<text x="{L - 6}" y="{y + 15}" text-anchor="end" font-size="11" '
                 f'font-weight="{700 if d["id"] == cur else 400}" fill="#333">{E(d["sample"])}</text>')
        for key, label, col in segs:
            n = _qcnum(q, key)
            if not n:
                continue
            w = bw * n / raw
            s.append(f'<rect x="{x0:.1f}" y="{y + 2}" width="{max(w - 1, 0.5):.1f}" height="{rh - 6}" '
                     f'rx="2" fill="{col}"><title>{E(d["sample"])} {label}: {n:,} '
                     f'({n / raw:.1%})</title></rect>')
            if key == 'Classified_Read':
                fx = x0 + bw * min(floor, n) / raw
                s.append(f'<line x1="{fx:.1f}" x2="{fx:.1f}" y1="{y}" y2="{y + rh - 2}" '
                         f'stroke="{C["red"] if n < floor else C["green"]}" stroke-width="2" '
                         f'stroke-dasharray="3 2"><title>{floor:,} classified floor</title></line>')
                s.append(f'<text x="{x0 + bw + 6:.1f}" y="{y + 15}" font-size="10" '
                         f'fill="{C["red"] if n < floor else "#333"}">{n / 1e6:.2f}M classified</text>')
            x0 += w
    lx = L
    for key, label, col in segs:
        s.append(f'<rect x="{lx}" y="{H - 14}" width="10" height="10" rx="2" fill="{col}"/>'
                 f'<text x="{lx + 14}" y="{H - 5}" font-size="10" fill="#6D6D6D">{label}</text>')
        lx += 86
    s.append('</svg>')
    return (f'<div class="panel-fig"><b class="t">Read QC</b><p class="tiny">Bar length = raw '
            f'reads; dashed tick = the {floor / 1e6:.0f}M classified-read floor (red when under '
            f'it).</p>{"".join(s)}</div>')


def sparklines(d, reg):
    """Reads per million over this site's own runs, per card taxon. A placeholder line until
    the site has three runs is honest; a verdict about "new here" needs a history."""
    site = (d.get('site') or {}).get('site_id')
    sites = SR.site_ids(reg)
    runs = sorted(((rec.get('analysed_at', ''), sid, rec) for sid, rec in reg['samples'].items()
                   if site and sites.get(sid) == site and sid != d['id']), key=lambda r: r[:2])
    if not site:
        note = 'Site not captured in analysis/sample_metadata.tsv, so no history can accrue.'
    else:
        n = len(runs) + 1
        note = (f'{n} run{"s" if n != 1 else ""} at this site. History drives gate 8 from '
                f'{triage.TH["site_history_min_runs"]} runs.')
    rows = d['loadrows']
    W, rh, L = 520, 26, 190
    H = 14 + max(1, len(rows)) * rh
    s = [f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="site history">']
    for i, (taxon, key, here, _) in enumerate(rows):
        y = 18 + i * rh
        series = [(rec.get('loads', {}).get(key, 0) / rec['classified'] * 1e6) if rec.get('classified')
                  else 0 for _, _, rec in runs] + [here]
        top = max(series) or 1
        pts = [(L + j * (W - L - 16) / max(len(series) - 1, 1), y + 8 - 16 * v / top)
               for j, v in enumerate(series)]
        s.append(f'<text x="{L - 8}" y="{y + 4}" text-anchor="end" font-size="11" '
                 f'font-style="italic" fill="#333">{E(taxon[:30])}</text>')
        if len(pts) > 1:
            s.append('<polyline fill="none" stroke="#6D6D6D" stroke-width="1.5" points="'
                     + ' '.join(f'{px:.1f},{py:.1f}' for px, py in pts) + '"/>')
        else:
            s.append(f'<line x1="{L}" x2="{W - 16}" y1="{y + 8}" y2="{y + 8}" stroke="#dde3ea" '
                     f'stroke-dasharray="4 3"/>')
        px, py = pts[-1]
        s.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="{C["blue"]}" stroke="#fff" '
                 f'stroke-width="1.5"><title>{E(d["sample"])}: {here:,.0f} reads/M</title></circle>')
    if not rows:
        s.append(f'<text x="{L}" y="22" font-size="11" fill="#6D6D6D">no card taxa</text>')
    s.append('</svg>')
    return (f'<div class="panel-fig"><b class="t">Site history</b><p class="tiny">{E(note)}</p>'
            f'{"".join(s)}</div>')


def page_top(d, data, meta, reg):
    """The one page: head, verdict strip, cards, panels. The appendix is added by the caller."""
    return (page_head(d, meta) + verdict_strip(d) + cards_html(d)
            + f'<div class="panels">{dot_strip(d)}{amr_strip(data, d["id"])}'
              f'{qc_bars(data, d["id"])}{sparklines(d, reg)}</div>')


def appendix(inner):
    return (f'<details class="appx"><summary>Evidence appendix &mdash; every taxon row, every '
            f'resistance gene, the gates that fired, QC and the method</summary>{inner}</details>')


def section_counts(d):
    """What each nav entry counts: listed taxa, genes at MONITOR or above, QC notes."""
    listed = sum(1 for t in d['taxa'] if (t.get('tier') or '-') != '-'
                 and not (t['verdict'] == 'NOT_TESTED' and not t.get('real')))
    return {'fl': listed, 'sp': len(d['taxa']), 'amr': sum(1 for g in d['genes'] if g['verdict'] != 'NO_ACTION'),
            'qc': len(d['integrity']), 'me': None}


def appendix_grid(d, tabs, body, lead=''):
    """Left section nav (sticky on wide screens, a button row on phones) beside the sections.
    The nav keeps the `.tabs` class so showTab() drives it unchanged."""
    n = section_counts(d)
    nav = ''.join(
        f'<button data-t="{t}" onclick="showTab(\'{E(d["id"])}\',\'{t}\')" '
        f'aria-selected="{str(j == 0).lower()}"><span>{lbl}</span>'
        + (f'<span class="ct">{n[t]}</span>' if n.get(t) is not None else '') + '</button>'
        for j, (t, lbl) in enumerate(tabs))
    tp = ''.join(f'<section class="tabp" data-t="{t}"{"" if j == 0 else " hidden"}>{body[t]}</section>'
                 for j, (t, lbl) in enumerate(tabs))
    return (f'<div class="apgrid"><nav class="tabs apnav" aria-label="Appendix sections">{nav}'
            f'</nav><main>{lead}{tp}</main></div>')


# ---------------------------------------------------------------- per-sample report
#
# One file per swab, `<id>_report.html`, judged against a running registry of every sample
# analysed before it. See analysis/sample_registry.py for why the cohort is load-bearing
# rather than an optimisation.
#
# THE REPORT IS A SNAPSHOT. It records the cohort it was built against and a fingerprint of
# that cohort, next to the rules fingerprint the report already carried. Adding a sample later
# can change an older sample's verdict; nothing is rewritten behind your back, and the
# fingerprint is how a stale report is spotted.



def site_line(sid, meta):
    """Where and when the swab was taken. Absent fields say so; none of them is ever inferred."""
    m = meta.get(sid, {})
    bits = []
    bits.append(f'<b>{E(m["site_label"])}</b>' if m.get('site_label')
                else '<span class="nc">site not captured</span>')
    bits.append(f'collected {E(m["collected_at"])}' if m.get('collected_at')
                else '<span class="nc">collection date not captured</span>')
    bits.append(f'run {E(m["run_id"])}' if m.get('run_id')
                else '<span class="nc">run id not captured</span>')
    return ' &middot; '.join(bits)


# A per-sample report is INDEPENDENT: it answers "what about this swab", and nothing else.
# An earlier draft carried a verdict breakdown across every analysed swab in the hero. That is a
# programme-level statistic - it changes whenever any other sample is added, which would make this
# report's headline drift without a single figure about this swab changing. It belongs to the
# managing dashboard. What stays is `cohort_block`: the named comparator set, because gate 8
# genuinely computed this swab's enrichment against it and an unnamed baseline is not auditable.


def cohort_block(reg, cids, cfp, meta):
    """What this sample was compared against, named. An unnamed baseline is not auditable."""
    if not cids:
        return ('<div class="cohort none"><b>No comparator samples.</b> This is the first swab '
                'in the registry, so gate 8 could not test cross-sample enrichment and fell back '
                'to raw abundance. Every later swab will be compared against this one.</div>')
    rows = ' &middot; '.join(
        f'<span class="cid">{E(s)}</span>'
        + (f' <span class="tiny">{E(meta[s]["site_label"])}</span>'
           if meta.get(s, {}).get('site_label') else '')
        for s in cids)
    return (f'<details class="cohort"><summary><b>{len(cids)}</b> comparator sample'
            f'{"s" if len(cids) != 1 else ""} &nbsp;<span class="cfp">cohort {E(cfp)}</span>'
            f'</summary><div class="cohortb"><p class="tiny">Gate 8 measured this swab\'s '
            f'enrichment against these. <b>The comparison set changes the verdict</b> &mdash; on '
            f'this batch WBM156 is MONITOR against four siblings and NO ACTION against none, so a '
            f'report is only as reproducible as the cohort it names. This report is a snapshot: '
            f're-running it once more samples exist may reach a different answer, and the cohort '
            f'fingerprint above is how you notice.</p><p class="tiny">{rows}</p>'
            f'<p class="tiny"><b>These swabs were sequenced in separate batches</b>, so a raw '
            f'cross-sample fold change confounds site with processing run. Cross-site enrichment '
            f'claims that survive a batch-robust check are reported as such; those that do not are '
            f'labelled as read-count alone. Recording <code>run_id</code> in '
            f'<code>analysis/sample_metadata.tsv</code> is what makes that check possible.</p>'
            f'</div></details>')


def build_one(sample, reg, meta, fp, outdir=None, cohort_name=None, control=None):
    """Render one swab's report against the registry, and return (path, data, cohort ids)."""
    sid = triage.sample_id(sample)
    cids = SR.cohort_ids(reg, sid)
    cfp = SR.fingerprint(reg, cids)
    d = collect([sample], comparators=bool(cids), cohort=SR.cohort_loads(reg, sid),
                cohort_name=cohort_name, control=control)[0]

    cmd = f'python3 analysis/triage.py --per-sample {sid}'
    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    sv, sv_why = d['verdict']
    reasons = ''.join(f'<li>{E(r)}</li>' for r in sv_why[:5]) or '<li>Nothing above threshold.</li>'

    # One page, then the appendix. The appendix is the whole previous report - cover sheet and
    # four tabs - behind a single <details>, so the ~50k words of evidence remain reachable and
    # are not the first thing on the page.
    tabs = [('fl', 'Flagged species'), ('qc', 'QC &amp; depth'), ('sp', 'All taxa'),
            ('amr', 'Resistance genes'), ('me', 'Method &amp; verification')]
    body = {'fl': flagged_section([d]), 'qc': qc_tab(d), 'sp': species_tab(d),
            'amr': amr_tab(d), 'me': method_tab(d, cmd, fp)}
    counts = {v: sum(1 for t in d['taxa'] if t['verdict'] == v) for v in VERDICT}
    head = ' &nbsp;·&nbsp; '.join(f'{chip(v)} {counts[v]}' for v in
                                 ['ESCALATE', 'CONFIRM', 'MONITOR', 'NOT_TESTED'] if counts[v])
    inner = (f'<div class="verdict" style="border-color:{_sv_col(sv)}"><div><b>All reasons for '
             f'{E(sv)}.</b><ul class="plain">{reasons}</ul></div></div>'
             + appendix_grid(d, tabs, body, f'<p class="blurb">{d["classified"]:,} classified reads '
                             f'&nbsp;·&nbsp;{head or "no taxon above NO ACTION"}</p>'
                             f'{cohort_block(reg, cids, cfp, meta)}'))

    doc = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(sid)} — triage report</title>
<style>{CSS}</style></head><body>
<header><h1>{E(sid)}</h1>
<div class="sub">Deterministic gate cascade over the PFI metagenomic report &nbsp;·&nbsp;
analysed {E(stamp)} &nbsp;·&nbsp; rules {E(fp.rules)} &nbsp;·&nbsp; build {E(fp.build)}
&nbsp;·&nbsp; cohort {E(cfp)}
({len(cids)} comparator{"s" if len(cids) != 1 else ""})</div></header>
<div class="panel" data-s="{E(sid)}">
{page_top(d, [d], meta, reg)}
{appendix(inner)}</div>
<footer>Generated by <code>analysis/triage_report.py</code> from
<code>{E(sid)}_en.html</code> only. Every figure is traceable to the PFI report or to a rule in
<code>analysis/triage_rules.json</code>. Verdicts are tiers, never diagnoses: CONFIRM means
culture with AST. Reproduce with <code>{E(cmd)}</code> &mdash; note that the cohort will differ
if the registry has grown since {E(stamp)}.</footer>
<script>{JS}</script></body></html>'''

    base = os.path.join(outdir or os.path.join(ROOT, 'analysis'), sid)
    with open(base + '_report.html', 'w', encoding='utf-8') as fh:
        fh.write(doc)

    # The same evidence the HTML renders, in the shape the dashboard database will ingest. It is
    # written here rather than scraped back out of the HTML so that the report and the record can
    # never disagree, and so the ~50k words of detail can be condensed on screen without being
    # lost. Ledger codes are stored per taxon: a future longitudinal query wants "every swab where
    # DR1 fired", and recomputing that needs the whole cascade.
    rec = {'sample': sid, 'verdict': sv, 'reasons': sv_why, 'analysed_at': stamp,
           'classified': d['classified'], 'rules_fp': fp.rules, 'build_fp': fp.build,
           'cohort_fp': cfp, 'cohort': cids,
           'site': meta.get(sid, {}), 'bec_version': 1,
           'taxa': [dict(t, ledger=ledger(d, t)) for t in d['taxa']], 'genes': d['genes']}
    with open(base + '_report.json', 'w', encoding='utf-8') as fh:
        json.dump(rec, fh, indent=1, default=str)
    return base + '_report.html', d, cids


def build_per_sample(samples, outdir=None, cohort=None):
    """Two passes, so a batch of new swabs judges each member against all the others.

    Pass 1 ingests every requested sample's loads into the registry. Pass 2 renders each report
    against the registry minus itself. Without the split, the first swab of a run would be
    analysed against an empty baseline and the last against a full one - the same asymmetry the
    registry exists to remove.

    `cohort` selects the registry, and therefore what this swab is compared against. Default is
    the field-swab registry; see sample_registry.registry_path for why they must not be pooled.
    """
    fp = fingerprints()
    reg, meta = SR.load(SR.registry_path(cohort)), SR.metadata()

    seen = {}
    for s in samples:                                            # pass 1 - ingest
        sid = triage.sample_id(s)
        g = triage.load_report(s)
        _, classified = triage.gate_integrity(s, g)
        # cached: pass 2 needs the same counts, and a PFI report is ~7 MB to parse
        seen[sid] = (classified, SR.loads_from_report(g), triage.taxon_names(g))
        prior = reg['samples'].get(sid, {})
        SR.record(reg, sid, classified, seen[sid][1], prior.get('verdict'), fp.rules,
                  prior.get('cohort', []), names=seen[sid][2], build_fp=fp.build)
    SR.save(reg)

    out = []                                                     # pass 2 - render
    for s in samples:
        path, d, cids = build_one(s, reg, meta, fp, outdir, cohort_name=cohort)
        sv = d['verdict'][0]
        SR.record(reg, d['id'], seen[d['id']][0], seen[d['id']][1], sv, fp.rules, cids,
                  names=seen[d['id']][2], build_fp=fp.build)
        out.append((path, d['id'], sv, len(cids)))
    SR.save(reg)
    return out


def build(samples, out=OUT, comparators=None, control=None):
    data = collect(samples, comparators, control=control)
    reg, meta = SR.load(), SR.metadata()
    # sample_id, not the raw arguments. Under a workflow engine the arguments are localised
    # paths under a task container's _miniwdl_inputs/ that exist only inside that one container,
    # so printing them verbatim under "Reproduce this page offline" gives the reader a command
    # that cannot be run - the exact opposite of what the section promises.
    cmd = ('python3 analysis/triage.py --html ' + ' '.join(triage.sample_id(x) for x in samples) +
           ('' if comparators is not False or len(samples) < 2 else ' --independent') +
           # basename, not a relpath: out is absolute under a workflow engine and
           # relpath(out, ROOT) renders as ../../mnt/... which is noise, not a command.
           ('' if out == OUT else f' --out={os.path.basename(out)}'))
    fp = fingerprints()
    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

    panels = []
    for k, d in enumerate(data):
        tabs = [('sp', 'Flaggable species'), ('qc', 'QC'), ('amr', 'Resistance genes'),
                ('me', 'Method &amp; verification')]
        body = {'qc': qc_tab(d), 'sp': species_tab(d), 'amr': amr_tab(d),
                'me': method_tab(d, cmd, fp)}
        counts = {v: sum(1 for t in d['taxa'] if t['verdict'] == v) for v in VERDICT}
        head = ' &nbsp;·&nbsp; '.join(f'{chip(v)} {counts[v]}' for v in
                                      ['ESCALATE', 'CONFIRM', 'MONITOR', 'NOT_TESTED'] if counts[v])
        sv, sv_why = d['verdict']
        reasons = ''.join(f'<li>{E(r)}</li>' for r in sv_why[:5])
        banner = (f'<div class="verdict" style="border-color:{_sv_col(sv)}">'
                  f'<div><b>All reasons for {E(sv)}.</b><ul class="plain">{reasons}</ul></div></div>')
        inner = banner + appendix_grid(d, tabs, body, f'<p class="blurb">{d["classified"]:,} '
                                       f'classified reads &nbsp;·&nbsp; '
                                       f'{head or "no taxon above NO ACTION"}</p>')
        panels.append(f'<div class="panel" data-s="{E(d["id"])}"{"" if k == 0 else " hidden"}>'
                      f'{page_top(d, data, meta, reg)}{appendix(inner)}</div>')

    # Batch overview: the assay-coverage bar (which agents this library could answer at all)
    # and one verdict per swab. The old whole-batch cover sheet lives in the batch appendix.
    overview = ''.join(
        f'<button data-s="{E(d["id"])}" onclick="showSample(\'{E(d["id"])}\')" '
        f'aria-selected="{str(k == 0).lower()}">{E(d["sample"])} '
        f'<span class="svchip" style="background:{_sv_col(d["verdict"][0])};font-size:10.5px;'
        f'padding:2px 7px">{E(d["verdict"][0])}</span></button>' for k, d in enumerate(data))

    doc = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Triage report — {E(", ".join(d["sample"] for d in data))}</title>
<style>{CSS}</style></head><body>
<header><h1>Triage report</h1>
<div class="sub">Deterministic gate cascade over PFI metagenomic reports &nbsp;·&nbsp;
{len(data)} sample{"s" if len(data) != 1 else ""} &nbsp;·&nbsp; generated {E(stamp)}
&nbsp;·&nbsp; rules {E(fp.rules)} &nbsp;·&nbsp; build {E(fp.build)}</div></header>
<div class="flwrap" style="padding-top:14px">{coverage_fig(data)}</div>
<div class="bar">{overview}</div>
{''.join(panels)}
<details class="appx"><summary>Batch appendix &mdash; flagged species across all swabs, ranked</summary>
{flagged_section(data)}</details>
<footer>Generated by <code>analysis/triage_report.py</code> from
<code>&lt;sample&gt;_en.html</code> only. Every figure is traceable to the PFI report or to a rule
in <code>analysis/triage_rules.json</code>. Verdicts are tiers, never diagnoses: CONFIRM means
culture with AST. Reproduce with <code>{E(cmd)}</code>.</footer>
<script>{JS}</script></body></html>'''

    with open(out, 'w', encoding='utf-8') as fh:
        fh.write(doc)
    return out, len(data)
