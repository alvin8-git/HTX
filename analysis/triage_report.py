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
import hashlib
import html
import json
import os

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
# different vocabulary - INVESTIGATE exists here and nowhere else. Legending only the row tiers left
# a reader looking up the word they had just read and not finding it.
SAMPLE_VERDICT = {
    'ESCALATE':    (C['red'],   'A threat-list agent with its confirmatory marker present. '
                                'The only verdict that asserts a biological threat.'),
    'INVESTIGATE': (C['red'],   'A threat-list or clinical-watchlist organism at CONFIRM, or a '
                                'high-consequence acquired gene (mecA, CTX-M) at CONFIRM. '
                                'Something here needs a laboratory, not a decision.'),
    'MONITOR':     (C['amber'], 'A flagged organism at MONITOR, or ordinary acquired resistance '
                                'at CONFIRM. Worth knowing, not worth acting on today.'),
    'NO ACTION':   (C['green'], 'Nothing above. Community-context organisms never contribute.'),
}

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
# Block 3 is an ACMG-style criteria ledger. The 12 gates already behave as an evidence-code
# system - each contributes a named, signed, measured piece of evidence and fixed rules combine
# them - they simply never published the tick-list. THE GATES STILL DECIDE. Nothing below
# recomputes a verdict; every line reads a field the cascade already wrote. The one deliberate
# departure from ACMG is the NA axis: ACMG has pathogenic and benign directions only, and here an
# unexamined agent is neither. Collapsing NA into "benign" is the exact error this report exists
# to prevent.

# state -> (glyph, css class). 'met' counts toward concern, 'against' counts away from it,
# 'na' means the gate could not run, 'unmet' means it ran and the criterion was not satisfied.
STATE = {'met': ('&#10003;', 'met'), 'against': ('&#10007;', 'met'),
         'na': ('&#9675;', 'unmet'), 'unmet': ('&#9675;', 'unmet')}
ORDER_STATE = ['met', 'against', 'unmet', 'na']

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
        add('NA1', 'na', 'Assay structurally cannot see this agent',
            'RNA genome screened against a DNA library - the test did not run', '2')
    if t['verdict'] == 'NOT_TESTED' and t.get('real'):
        mp = t.get('marker_power')
        add('NA2', 'na', 'Confirmatory marker not assessable at this coverage',
            (f'marker power {mp:.0%} &lt; {TH["marker_power_min"]:.0%} floor - its absence is the '
             f'expected outcome either way' if isinstance(mp, float) else
             'below the power floor - its absence carries no information'), '10a')

    # --- gates 10a/10b: the markers. The only route to ESCALATE.
    if t.get('markers_required'):
        found = [x for x in (t.get('markers_found') or [])]
        if found:
            add('PVS1', 'met', 'Threat-list agent with its confirmatory marker present',
                'found: ' + ', '.join(found), '10a')
        elif t['verdict'] != 'NOT_TESTED':
            add('BS1', 'against', 'Confirmatory marker absent where the two-way gate ran',
                'required: ' + ' / '.join(t['markers_required']), '10a')
    if t.get('supporting_required'):
        sup = t.get('supporting_found') or []
        if sup:
            add('PS1', 'met', 'Supporting marker present - one-way gate',
                'found: ' + ', '.join(sup), '10b')
        else:
            add('NA4', 'na', 'Supporting marker not found - one-way gate, so NOT an exclusion',
                'VFDB coverage for this agent cannot be certified from the report', '10b')
    if not t.get('markers_required') and not t.get('supporting_required'):
        add('NA3', 'na', 'No confirmatory or supporting marker defined for this agent',
            'gate 10 did not run - this is not an absence of evidence', '10')

    # --- gate 1b: list membership, and the ceiling it implies.
    if tier == 'W':
        add('PM1', 'met', 'Organism on the clinical watchlist',
            E(t.get('watch_priority') or 'clinical watchlist'), '1b')
    elif cdc:
        add('PM1', 'met', 'Organism on the CDC threat list', f'Category {E(tier)}', '1b')
    if not cdc and not t.get('markers_found'):
        add('PVS1', 'unmet', 'CDC threat-list agent with its confirmatory marker',
            'not a CDC agent - <b>ceiling is CONFIRM</b>' if tier == 'W' else 'not a listed agent',
            '1b')

    # --- gates 3-5 + the watchlist escalation test: acquired resistance in an escalating class.
    esc = escalating_rows(t, d['genes']) or []
    conf = [(c, [g for g in gs if g['verdict'] == 'CONFIRM']) for c, gs in esc]
    hit = [(c, gs) for c, gs in conf if gs]
    if hit:
        full = [g for _, gs in hit for g in gs if g['breadth'] >= TH[FULL_LENGTH]]
        code, note = ('PS2', 'full-length') if full else ('PM2', 'partial')
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
            add('PS3', 'met',
                'Most abundant documented host, for a gene in an escalating class',
                f'rank 1 of {lead[0].get("n_hosts", "?")} candidate hosts of '
                f'{E(lead[0]["group"])}', '8')
        else:
            top = min(ctx, key=lambda x: x.get('self_rank') or 99)
            rival = next((n for n, _ in top.get('candidates', []) if n != t['taxon']), None)
            add('PS3', 'unmet',
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
        add('PP2', st, 'Cross-sample enrichment above threshold',
            f'{fold:.1f}x vs other samples (floor {TH["enrichment_fold"]:.1f}x)', '8')
    elif not d.get('comparators') and t.get('abundance'):
        ab = float(str(t['abundance']).rstrip('%') or 0)
        flr = TH['watchlist_min_abundance_no_comparators']
        st = 'met' if ab >= flr else 'unmet'
        add('PP3', st, 'Abundance above the no-comparator floor',
            f'{ab:.2f}% (floor {flr:.1f}%) &mdash; <b>no comparator samples, so enrichment '
            f'is untestable</b> and abundance stands in for it', '8')

    # --- gate 1: the read floor.
    if t.get('real'):
        s = 'met' if t['real'] >= TH['min_real_reads'] else 'against'
        add('PP1' if s == 'met' else 'BP1', s,
            'Real reads above the floor' if s == 'met' else 'Below the read floor',
            f'{t["real"]:,} reads (floor {TH["min_real_reads"]:,})', '1')

    # --- gate 7: Bracken redistribution. A downgrade, so it counts against.
    if t.get('real') and t.get('est') and t['est'] / t['real'] > TH['bracken_inflation_ratio']:
        add('BM1', 'against', 'Bracken estimate inflated over real reads &mdash; judged on real',
            f'{t["est"]:,} est / {t["real"]:,} real = {t["est"]/t["real"]:.0f}x '
            f'(floor {TH["bracken_inflation_ratio"]}x)', '7')
    return out


def ledger_html(d, t):
    lg = sorted(ledger(d, t), key=lambda c: ORDER_STATE.index(c['state']))
    rows = ''.join(
        f'<tr><td class="code {STATE[c["state"]][1]}">{STATE[c["state"]][0]} {E(c["code"])}</td>'
        f'<td class="{STATE[c["state"]][1]}">{c["text"]}</td>'
        f'<td class="meas">{c["measured"]}</td><td class="num gate">{c["gate"]}</td></tr>'
        for c in lg)
    tally = collections.Counter(c['state'] for c in lg)
    verdict = (f'<div class="verdictline"><b>{tally["met"]} met, {tally["against"]} against, '
               f'{tally["na"] + tally["unmet"]} not applicable</b> &rarr; {chip(t["verdict"])}</div>')
    return (f'<div class="ev"><h4>3 &middot; Criteria ledger &mdash; why this row is '
            f'{E(t["verdict"].replace("_", " "))}</h4>'
            f'<p class="tiny">Each line is one gate of the cascade, named and given the value it '
            f'measured. <b>The gates decide the verdict; this table only publishes the tick-list '
            f'they already produce.</b> A criterion whose gate could not run is marked '
            f'<span class="unmet">&#9675;</span> and is never read as a clear.</p>'
            f'<table class="ev"><tr><th>Code</th><th>Criterion</th><th>Measured</th>'
            f'<th class="num">Gate</th></tr>{rows}</table>{verdict}</div>')


def classes_html(d, t):
    esc = escalating_rows(t, d['genes'])
    if not esc:
        return ''
    TH, rows = triage.TH, ''
    for cls, hits in esc:
        conf = [g for g in hits if g['verdict'] == 'CONFIRM']
        badge = ('<span class="tag hit">DETECTED</span>' if conf else
                 '<span class="tag none">NONE</span>')
        if not hits:
            rows += (f'<tr><td class="unmet">{E(cls)}</td><td>{badge}</td>'
                     f'<td class="acc unmet" colspan="4">no acquired gene of this class detected</td></tr>')
            continue
        for k, g in enumerate(hits):
            call = 'full length' if g['breadth'] >= TH[FULL_LENGTH] else 'partial'
            rows += (f'<tr><td class="met">{E(cls) if k == 0 else ""}</td>'
                     f'<td>{badge if k == 0 else ""}</td>'
                     f'<td class="acc">{E(g["group"])} ({E(g["allele"])})</td>'
                     f'<td class="num">{g["breadth"]:.1f}%</td><td class="num">{g["depth"]:.2f}x</td>'
                     f'<td>{chip(g["verdict"])} <span class="tiny">{call}</span></td></tr>')
    return (f'<div class="ev"><h4>1 &middot; Which resistance classes would raise this organism</h4>'
            f'<p class="tiny">Fixed per organism in <code>clinical_watchlist</code>.'
            f'<code>escalating_classes</code> &mdash; decided before the run, not chosen after '
            f'seeing the data. <b>MEGARes carries no organism column</b>, so every gene below is '
            f'co-detected <i>in the sample</i> and attributed to nothing. A class with no gene is '
            f'as informative as one with: it is the agent still on the table.</p>'
            f'<table class="ev wide"><tr><th>Class</th><th>Status</th><th>Gene co-detected</th>'
            f'<th class="num">Breadth</th><th class="num">Depth</th><th>Gene verdict</th></tr>'
            f'{rows}</table></div>')


def vf_html(t):
    core = core_vf(t)
    if core is None:
        n = len(t['vf'])
        return (f'<div class="ev"><h4>2 &middot; Virulence factors present</h4>'
                f'<p class="tiny"><b>{n} distinct factor{"s" if n != 1 else ""} detected, and no '
                f'core-determinant set is curated for this organism</b> &mdash; so this report will '
                f'not tell you whether they make it virulent. Depth measures how much was '
                f'sequenced, not how much a gene matters, and ranking 121 factors by depth invites '
                f'exactly the wrong inference. The factors are listed in full on the evidence card '
                f'below. Curating <code>vf_core</code> for this organism is what turns that list '
                f'into an answer.</p></div>') if t['vf'] else ''
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
    rest = len(t['vf']) - len(solid) - len(trace)
    return (f'<div class="ev"><h4>2 &middot; Virulence factors present &mdash; and whether they '
            f'matter</h4>'
            f'<p class="tiny"><b>{len(solid)} of {len(core)} core determinants above the breadth '
            f'floor</b>'
            + (f', {len(trace)} more at trace level' if trace else '') + f'. '
            f'<b>VFDB rows carry no verdict and this pipeline defines no VFDB threshold</b>, so the '
            f'{floor:.0f}% split above is borrowed from the AMR fragment floor and is a reporting '
            f'convention, not a validated call. Read the coverage column, not the badge. '
            f'Attribution is VFDB\'s own: the read matched a protein whose reference genome is '
            f'that strain &mdash; a reference match, <b>not read-level linkage to this sample\'s '
            f'organism</b>. Nothing here changes a verdict; no gate consults '
            f'<code>vf_core</code>.</p>'
            f'<table class="ev wide"><tr><th>Core determinant</th><th>Role</th><th>Status</th>'
            f'<th class="num">Coverage</th><th class="num">Depth</th></tr>{rows}</table>'
            f'<p class="tiny">+ {rest} other VFDB factor{"s" if rest != 1 else ""} for this species, '
            f'listed in full on the evidence card below.</p></div>')


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


def flagged_row(d, t, band, also=()):
    """One disclosure row: the summary is the ranking, the body is the three evidence blocks."""
    lg = ledger(d, t)
    tally = collections.Counter(c['state'] for c in lg)
    sub = (E(t.get('watch_priority')) if t.get('tier') == 'W'
           else f'CDC Category {E(t["tier"])}' if (t.get('tier') or '-') != '-' else '')
    if also:
        sub += f' &middot; also in {E(", ".join(sorted(also)))}'
    abund = f'{t["real"]:,} rd' + (f' &middot; {E(t["abundance"])}' if t.get('abundance') else '')
    body = (classes_html(d, t) + vf_html(t) + ledger_html(d, t) +
            f'<p class="tiny"><a class="deep" href="#{anchor(d, t)}" '
            f'onclick="openCard(\'{E(d["id"])}\')">Full evidence card for '
            f'<i>{E(t["taxon"])}</i> in {E(d["sample"])} &mdash; every VFDB row, every candidate '
            f'host, the reproduce-offline command &rarr;</a></p>')
    return (f'<details class="fl {band}"><summary>'
            f'<span class="fv">{chip(t["verdict"])}</span>'
            f'<span class="fn"><i>{E(t["taxon"])}</i>'
            + (f'<span class="fsub">{sub}</span>' if sub else '') + '</span>'
            f'<span class="fc"><span class="fl-l">Sample</span>'
            f'<span class="fl-v">{E(d["sample"])}</span></span>'
            f'<span class="fc"><span class="fl-l">Abundance</span>'
            f'<span class="fl-v">{abund}</span></span>'
            f'<span class="fc"><span class="fl-l">Escalating classes</span>'
            f'<span class="fl-v">{class_dots(d, t)}</span></span>'
            f'<span class="fc"><span class="fl-l">Criteria</span>'
            f'<span class="fl-v">{tally["met"]} met &middot; {tally["against"]} against</span></span>'
            f'<span class="ftri">&#9654;</span></summary>'
            f'<div class="flbody">{body}</div></details>')


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

    def band(title, hint, pairs, cls, cap=None):
        if not pairs:
            return ''
        pairs = dedupe(pairs)
        shown = pairs if cap is None else pairs[:cap]
        rows = ''.join(flagged_row(d, t, cls, also) for d, t, also in shown)
        more = ''
        if cap is not None and len(pairs) > cap:
            rest = ' &middot; '.join(
                f'<i>{E(t["taxon"])}</i> <b>{t["real"]:,}</b>' for d, t, _ in pairs[cap:])
            more = (f'<div class="flrest">+ {len(pairs) - cap} more organism'
                    f'{"s" if len(pairs) - cap != 1 else ""}, all below every escalation '
                    f'criterion &mdash; peak reads across the batch: {rest}</div>')
        return (f'<div class="flband"><div class="flhead"><h3>{title} <span class="ct">'
                f'{len(pairs)}</span></h3><span class="flhint">{hint}</span></div>{rows}{more}</div>')

    # Distinct agents, not rows: the same 25 RNA agents are screened in every sample, so
    # summing rows reports 125 for a five-swab batch and overstates the gap fivefold.
    n_absent = len({binomial(t['taxon']) for d in data for t in d['taxa']
                    if t['verdict'] == 'NOT_TESTED' and not t.get('real')})
    body = (
        band('Flagged &mdash; needs an analyst',
             'CONFIRM or above, ranked by verdict then read count', hot, 'hot') or
        '<div class="flband"><div class="flhead"><h3>Flagged &mdash; needs an analyst '
        '<span class="ct">0</span></h3></div><div class="flrest">No taxon reached CONFIRM in this '
        'batch. That is not a clean result on its own &mdash; read the coverage line above it.'
        '</div></div>') + \
        band('Present, but the answer is unavailable',
             'detected above the read floor &middot; the marker gate could not run',
             unpowered, 'nt', cap=6) + \
        band('Watchlist organisms detected, no action',
             'on a list, below every escalation criterion', watch, 'mon', cap=4)

    tot = sum(len(d['taxa']) for d in data)
    return (f'<section class="flagged"><div class="flwrap">'
            f'<div class="flmast"><h2>Flagged species</h2>'
            f'<span class="tiny">{len(data)} sample{"s" if len(data) != 1 else ""} &middot; '
            f'{tot:,} taxon rows &middot; {n_absent} agent{"s" if n_absent != 1 else ""} the assay '
            f'could not see</span></div>{body}</div></section>')


def collect(samples, comparators=None):
    reports = {s: triage.load_report(s) for s in samples}
    classified, integrity = {}, {}
    for s, g in reports.items():
        integrity[s], classified[s] = triage.gate_integrity(s, g)
    loads = triage.loads_by_taxon(reports, classified)
    if comparators is None:
        comparators = len(samples) > 1

    out = []
    for s in samples:
        g = reports[s]
        genes = triage.triage_genes(g)
        taxa = triage.triage_taxa(s, g, loads, genes, comparators)
        vfd = g.get('virulence', {}).get('DNA', {})
        vf_rows = vfd.get('data', []) if isinstance(vfd, dict) else []

        for t in taxa:
            t['vf'], t['vf_rows'] = vf_for_taxon(vf_rows, t['taxon'])

        out.append({
            # sample_id strips a localised path down to the stem: under WDL `s` is
            # /cromwell-executions/.../WBM185_en.html, which is not a sample name.
            'sample': triage.sample_id(s), 'id': triage.sample_id(s),
            'platform': 'long read' if triage.detect_platform(g) == 'long' else 'short read',
            'qc': g['basicSummary']['readsQc']['data'][0],
            'idsum': (g['basicSummary'].get('idSummary', {}).get('data') or [{}])[0],
            'integrity': integrity[s], 'classified': classified[s],
            'taxa': taxa, 'genes': genes, 'comparators': comparators, 'n_samples': len(samples),
            'verdict': triage.sample_verdict(taxa, genes),
            'n_vf': len(vf_rows), 'n_amr': len(g.get('drugResistance', {}).get('DNA', {}).get('data', [])),
            'n_species': len(g['indentification_DNA']['speciesData']['data']),
            'showRNA': bool(g.get('showRNA')),
        })
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


def taxon_card(d, t):
    v = t['verdict']
    meta = [f'<span class="m"><b>{t["real"]:,}</b> real reads</span>']
    if t.get('est'):
        meta.append(f'<span class="m">{t["est"]:,} Bracken estimate</span>')
    if t.get('abundance'):
        meta.append(f'<span class="m">{E(t["abundance"])} abundance</span>')
    if t.get('unique') is not None:
        meta.append(f'<span class="m">{t["unique"]:.0%} unique</span>')
    if t.get('taxid'):
        meta.append(f'<span class="m">taxid {E(t["taxid"])}</span>')
    if t.get('tier') == 'W':
        meta.append(f'<span class="m tier">{E(t.get("watch_priority", "clinical watchlist"))}</span>')
    elif t.get('tier') and t['tier'] != '-':
        meta.append(f'<span class="m tier">CDC Category {E(t["tier"])}</span>')

    vf = ''
    if t['vf']:
        rows = ''.join(
            f'<tr><td><b>{E(r.get("Virulence Factor"))}</b></td>'
            f'<td>{E(r.get("Pathogen"))}'
            + (f' <span class="tiny">+{r["_strains"]-1} more strain'
               f'{"s" if r["_strains"] > 2 else ""}</span>' if r['_strains'] > 1 else '')
            + f'</td><td class="acc">{E(r.get("VF Protein"))}</td>'
            f'<td class="num">{E(r.get("Coverage(%)"))}</td>'
            f'<td class="num">{E(r.get("Depth"))}x</td></tr>' for r in t['vf'][:25])
        more = (f'<p class="tiny">Showing the 25 best-covered of {len(t["vf"])} factors. The rest '
                f'are in the PFI report\'s virulence table.</p>' if len(t['vf']) > 25 else '')
        red = ''
        if t['vf_rows'] > len(t['vf']):
            red = (f' <b>{t["vf_rows"]} raw VFDB rows collapse to {len(t["vf"])} distinct factors</b> '
                   f'&mdash; VFDB stores one reference protein per strain, so a single conserved gene '
                   f'recruits reads onto every strain\'s copy. Counting rows would overstate this '
                   f'evidence by {t["vf_rows"]/len(t["vf"]):.1f}x. Best-covered representative shown '
                   f'per factor, same collapsing rule as the MEG_ alleles.')
        vf = (f'<div class="ev"><h4>Virulence evidence attributed to this species '
              f'<span class="src">VFDB &mdash; virulence.DNA</span></h4>'
              f'<p class="tiny">Attribution is VFDB\'s own: the read matched a protein whose '
              f'reference genome is that strain. It is a reference match, <b>not read-level linkage '
              f'to this sample\'s organism</b>. Search the accession in the PFI report to verify.'
              f'{red}</p>'
              f'<table class="ev"><tr><th>Factor</th><th>Reference strain</th><th>VFDB accession</th>'
              f'<th>Coverage</th><th>Depth</th></tr>{rows}</table>{more}</div>')

    hints = ''
    if t.get('amr_context'):
        def hosts(x):
            """Every documented host of this gene that is actually in the sample, most abundant
            first. This is the column that lets a reader judge attribution: a gene sitting in a
            sample where a congener outnumbers this taxon 38x is weak evidence for this taxon."""
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
        more = f'<p class="tiny">+ {n_more} more in the AMR tab.</p>' if n_more else ''
        hints = (f'<div class="ev inferred"><h4>{icon("NOT_TESTED")} Resistance genes whose known host '
                 f'range includes this genus &mdash; INFERRED, NOT MEASURED</h4>'
                 f'<p class="tiny"><b>MEGARes carries no organism column.</b> These genes were '
                 f'detected in this sample and this genus is a documented host for them &mdash; that '
                 f'is all. Nothing here shows the gene is in <i>this</i> organism. Nothing in the '
                 f'PFI report can show it either: the resistance table has no organism column and '
                 f'the species table has no gene column, so no field joins them. Assembly from raw '
                 f'reads is the analysis that could settle it, and it is outside what this report '
                 f'sees. Culture with AST is the only way to close this. '
                 f'<b>Do not report these as this organism\'s '
                 f'resistance profile.</b> The <i>candidate hosts present</i> column lists every '
                 f'documented host of that gene found in this sample, most abundant first, with '
                 f'<span class="self">this taxon highlighted</span>. Where a congener outnumbers '
                 f'this organism, the gene is more likely that congener\'s &mdash; which is an '
                 f'argument, not a measurement.</p>'
                 f'<table class="ev wide"><tr><th>Group</th><th>Allele</th><th>Breadth</th>'
                 f'<th>Depth</th><th>Gene verdict</th><th>Candidate hosts present (reads)</th>'
                 f'<th>Why this genus is a candidate</th></tr>{rows}</table>{more}</div>')

    wn = ''
    if t.get('watch_note'):
        wn = (f'<div class="ev"><h4>Why this organism is on the clinical watchlist</h4>'
              f'<p class="tiny">{E(t["watch_note"])} It is <b>not</b> a CDC bioterrorism agent, so '
              f'its ceiling is CONFIRM &mdash; ESCALATE stays reserved for a threat-list agent with '
              f'its confirmatory marker.</p></div>')

    mk = ''
    if t.get('markers_required'):
        found = [x for x in (t.get('markers_found') or []) if x not in (t.get('supporting_found') or [])]
        mk = (f'<div class="ev"><h4>Confirmatory markers &mdash; two-way</h4><p class="tiny">'
              f'Required: <b>{E(" / ".join(t["markers_required"]))}</b>. '
              + (f'Found: <b>{E(", ".join(found))}</b> &mdash; this is what raises the verdict to '
                 f'ESCALATE.' if found else 'None detected, so the agent is downgraded. This is the '
                 'gate that separates a threat-list organism from the threat itself.')
              + '</p></div>')
    if t.get('supporting_required'):
        sup = t.get('supporting_found') or []
        mk += (f'<div class="ev"><h4>Supporting markers &mdash; one-way</h4><p class="tiny">'
               f'Searched: <b>{E(" / ".join(t["supporting_required"]))}</b>, restricted to VFDB rows '
               f'whose reference strain is a <i>{E(t["taxon"].split(" ")[0])}</i>. '
               + (f'Found: <b>{E(", ".join(sup))}</b> &mdash; this raises the verdict to ESCALATE.'
                  if sup else '<b>None found, and that is not an exclusion.</b> VFDB coverage for '
                  'this agent cannot be certified from the report, so a miss is treated as no '
                  'information rather than as a clear. The verdict is unchanged by this gate.')
               + '</p></div>')

    return (f'<div class="card {v}" id="{anchor(d, t)}"><div class="hd">{chip(v)}'
            f'<span class="tx">{E(t["taxon"])}</span></div>'
            f'<div class="meta">{"".join(meta)}</div>'
            f'<p class="why"><b>Why:</b> {E(t["why"])}</p>{wn}{mk}{vf}{hints}</div>')


def species_tab(d):
    banded, seen = [], 0
    for v in ORDER:
        grp = [t for t in d['taxa'] if t['verdict'] == v]
        if not grp:
            continue
        threat = [t for t in grp if t['tier'] != '-']
        other = [t for t in grp if t['tier'] == '-']
        col, blurb = VERDICT[v]
        body = ''.join(taxon_card(d, t) for t in threat)
        if other:
            body += (f'<details class="fold"><summary>{len(other)} non-threat taxa at this tier '
                     f'&mdash; community context, expand to read</summary>'
                     + ''.join(taxon_card(d, t) for t in other) + '</details>')
        seen += len(grp)
        banded.append(f'<div class="band"><h3 style="border-left-color:{col}">{icon(v)} {v.replace("_"," ")} '
                      f'<span class="ct">{len(grp)}</span></h3>'
                      f'<p class="blurb">{E(blurb)}</p>{body}</div>')

    # NOT_TESTED carries TWO distinct reasons and they need different renderings. Both mean "the
    # test did not run", which is why they share the tier - but one agent is absent from the sample
    # entirely (RNA genome, nothing to show) and the other is PRESENT and often abundant, with its
    # own evidence, and only its marker test failed. Collapsing the second into a bare name list
    # would hide S. aureus at 3,654 reads behind a blurb about RNA viruses.
    nt = [t for t in d['taxa'] if t['verdict'] == 'NOT_TESTED']
    absent = [t for t in nt if not t.get('real')]
    unpowered = [t for t in nt if t.get('real')]
    if unpowered:
        cards = ''.join(taxon_card(d, t) for t in unpowered)
        banded.append(
            f'<div class="band nt"><h3 style="border-left-color:{C["grey"]}">'
            f'{icon("NOT_TESTED")} NOT TESTED &mdash; marker not assessable at this coverage '
            f'<span class="ct">{len(unpowered)}</span></h3>'
            f'<p class="blurb"><b>Present, and the confirmatory-marker test had too little power to '
            f'mean anything.</b> These organisms ARE in the sample. Their threat-list status turns on '
            f'a toxin or virulence marker, and at this sequencing depth the chance of a read landing '
            f'on that marker was below {int(triage.TH["marker_power_min"] * 100)}%, so its absence is '
            f'the expected outcome either way and carries no information. Finding the marker would '
            f'still escalate; missing it changes nothing. <b>Do not read these as cleared</b> &mdash; '
            f'targeted PCR or culture is what answers the question.</p>{cards}</div>')
    if absent:
        rows = ''.join(f'<li><b>{E(t["taxon"])}</b> &mdash; CDC Category {E(t["tier"])}</li>'
                       for t in absent)
        banded.append(f'<div class="band nt"><h3 style="border-left-color:{C["grey"]}">'
                      f'{icon("NOT_TESTED")} NOT TESTED &mdash; assay cannot see this agent '
                      f'<span class="ct">{len(absent)}</span></h3>'
                      f'<p class="blurb"><b>Not a severity, and not a negative result.</b> These are '
                      f'threat-list agents with RNA genomes screened against a DNA-only library. The '
                      f'test did not run. They are listed below the ladder so they can never be read '
                      f'as "absent".</p><ul class="plain cols">{rows}</ul></div>')
    return ''.join(banded) or '<p class="blurb">No taxon reached a reportable verdict.</p>'


def amr_tab(d):
    shown = [x for x in d['genes'] if x['verdict'] != 'NO_ACTION']
    supp = len(d['genes']) - len(shown)
    unann = sum(1 for x in d['genes'] if x['class'] == 'unannotated')
    bands = []
    for v in ORDER:
        grp = [x for x in shown if x['verdict'] == v]
        if not grp:
            continue
        rows = ''.join(
            f'<tr><td>{chip(x["verdict"])}</td><td><b>{E(x["group"])}</b></td>'
            f'<td class="acc">{E(x["allele"])}</td><td class="num">{x["breadth"]:.2f}%</td>'
            f'<td class="num">{x["depth"]:.2f}x</td><td class="num">{x["alleles_collapsed"]}</td>'
            f'<td>{E(x["class"])}</td><td>{E(x["why"])}</td><td class="basis">{E(x["note"])}</td></tr>'
            for x in grp)
        bands.append(f'<h3 style="border-left-color:{VERDICT[v][0]}">{icon(v)} {v.replace("_"," ")} '
                     f'<span class="ct">{len(grp)}</span></h3>'
                     f'<table class="ev wide"><tr><th>Verdict</th><th>Group</th><th>Allele</th>'
                     f'<th>Breadth</th><th>Depth</th><th>Alleles</th><th>Class</th><th>Why</th>'
                     f'<th>What the gene is</th></tr>{rows}</table>')
    return (f'<div class="warn"><b>No gene on this page is attributed to an organism.</b> The '
            f'MEGARes table has no organism column, and assembly could not close the gap '
            f'(docs/biothreat_assessment.md &sect;2.5). <b>CONFIRM here means "ask a laboratory '
            f'about this gene", not "the sample is resistant".</b> On a certified-clean ZymoBIOMICS '
            f'standard this same logic produces nine false-positive CONFIRM calls, because genes '
            f'like <i>aac(6\')-Ii</i> and <i>fosA</i> are chromosomal in one organism and acquired '
            f'in another. Do not read the CONFIRM count as a resistance burden.</div>'
            f'<p class="blurb">Alleles are collapsed to one call per MEGARes group: one real gene '
            f'recruits reads onto several near-identical accessions, so the representative call is '
            f'the allele highest on both breadth and depth. {supp} groups were suppressed as '
            f'conserved rRNA, ubiquitous efflux, point-mutation-dependent, intrinsic, environmental '
            f'or orphan regulators. Rule coverage: {len(d["genes"]) - unann}/{len(d["genes"])} '
            f'groups annotated.</p>' + ''.join(bands))


def method_tab(d, cmd, fp):
    return f'''<div class="grid2"><div>
<h3>Reproduce this page offline</h3>
<p class="blurb">Everything below was produced from <code>{E(d["sample"])}_en.html</code> alone, by
the command shown. No network, no database, no aligner &mdash; Python 3 standard library only.</p>
<pre>cd {E(ROOT)}
{E(cmd)}</pre>
<table class="kv">
<tr><th>Engine</th><td>analysis/triage.py</td></tr>
<tr><th>Rules</th><td>analysis/triage_rules.json</td></tr>
<tr><th>Fingerprint</th><td class="acc">{E(fp)}</td></tr>
<tr><th>Also written</th><td>analysis/triage_{E(d["id"])}.tsv</td></tr>
</table>
<h3>Verify a row against the PFI report</h3>
<ol class="plain">
<li>Open <code>{E(d["sample"])}_en.html</code>.</li>
<li>For a virulence row, search the <b>VFDB accession</b> (e.g. <code>VFG004763</code>) in the
    virulence table.</li>
<li>For a resistance row, search the <b>MEG_ accession</b> in the drug-resistance table. Expect to
    find several near-identical alleles &mdash; that is the allele collapsing described above.</li>
<li>For a taxon, search the <b>taxid</b> or the scientific name in the identification table.</li>
</ol>
<p class="blurb">Every number on this page is copied from those tables unchanged. The one quantity
computed rather than copied is cross-sample enrichment, which is arithmetic on read counts that are
themselves in the reports; the card says so in its <i>Why</i> line.</p>
</div><div>
<h3>How to read the sample verdict</h3>
<p class="blurb">The banner at the top of every tab. One answer for the whole sample, rolled up from
the rows &mdash; a different question, and a different set of words, from the row tiers below.</p>
<table class="kv v">{''.join(
    f'<tr><th><span class="chip" style="background:{SAMPLE_VERDICT[v][0]}">{E(v)}</span></th>'
    f'<td>{E(SAMPLE_VERDICT[v][1])}</td></tr>'
    for v in ['ESCALATE', 'INVESTIGATE', 'MONITOR', 'NO ACTION'])}</table>
<h3>How to read a row verdict</h3>
<p class="blurb">On the species and resistance-gene tabs. <b>CONFIRM is the ceiling for any AMR
gene</b>, and no row is ever labelled INVESTIGATE &mdash; that word belongs to the sample.</p>
<table class="kv v">{''.join(f'<tr><th>{chip(v)}</th><td>{E(VERDICT[v][1])}</td></tr>'
                             for v in ['ESCALATE', 'CONFIRM', 'MONITOR', 'NOT_TESTED', 'NO_ACTION'])}</table>
<h3>What this page cannot tell you</h3>
<ul class="plain">
<li><b>Whether anything is alive.</b> DNA comes off a dry surface from live cells, dead cells and
    spores alike. The PFI "active species" table needs an RNA library and is empty in every DNA run.</li>
<li><b>Which organism carries a resistance gene.</b> See the banner on the AMR tab.</li>
<li><b>Whether a trace call is contamination.</b> No negative extraction control was run, so the
    contamination floor is asserted rather than measured.</li>
{'<li><b>Whether a finding is site-specific.</b> The cross-sample enrichment gate is inert on this '
 'run &mdash; ' + ('there is only one sample' if d['n_samples'] == 1 else
 'the samples were declared independent, so a fold-change between them would measure who they came '
 'from, not where') + '.</li>' if not d['comparators'] else ''}
</ul>
<h3>The input contract &mdash; and what a FASTQ input would add</h3>
<p class="blurb">This engine reads <b>one PFI HTML report</b> and nothing else. That is deliberate:
it is the document a microbiologist is actually sent, so every conclusion here can be checked
against the same page, and the engine runs wherever the report does. The cost is a specific, listed
set of questions the report cannot answer &mdash; these are limits of the <i>input</i>, not of the
rules, and each would be recoverable from the raw reads if the pipeline is ever pointed at them.</p>
<table class="kv v">
<tr><th>Molecule count</th><td>The report gives read counts. One fragment amplified 10,000&times;
    and 10,000 distinct fragments produce an identical row, so a trace call cannot be shown to be a
    PCR artifact. <i>From FASTQ:</i> the unique-read fraction, already implemented as gate&nbsp;6 and
    active whenever <code>ExtractRead_DNA/</code> is delivered.</td></tr>
<tr><th>Gene host</th><td>No field joins the resistance table to the species table. <i>From FASTQ:</i>
    assembly plus read mapping &mdash; which on this batch still failed to resolve it, so this one is
    not guaranteed even with the reads.</td></tr>
<tr><th>Unclassified reads</th><td>72&ndash;90% of reads in a surface swab match nothing in the PFI
    database, and the report says nothing about them. Any organism absent from that database is
    invisible to every row on this page. <i>From FASTQ:</i> direct k-mer and GC interrogation of that
    bin.</td></tr>
<tr><th>Resistance by mutation</th><td>Only gene presence is reported. Resistance conferred by point
    mutation &mdash; <i>gyrA</i>, <i>rpoB</i>, <i>lpxA</i> &mdash; is invisible, so its absence here is
    never evidence of susceptibility. <i>From FASTQ:</i> variant calling, given sufficient
    depth.</td></tr>
<tr><th>Genomic context</th><td>Whether a gene sits on a plasmid, a prophage or the chromosome, and
    what travels with it. <i>From FASTQ:</i> assembly and replicon typing.</td></tr>
<tr><th>Viability and RNA</th><td>Not recoverable from the DNA reads either &mdash; this needs an RNA
    library at the bench. When one exists, the report grows a <code>speciesActivity</code> table and
    the rules gain an activity axis they currently cannot use.</td></tr>
</table>
<p class="blurb">These rules are expected to change. They encode what is decidable from today's
report shape; a new library type, a new database version or more sample data changes what is
decidable, and the rule file &mdash; not the engine &mdash; is where that change belongs.</p>
<h3>Measured accuracy</h3>
<p class="blurb">Against the ZymoBIOMICS Microbial Community Standard (known composition, five
inputs): sensitivity 10/10 organisms in every sample, zero false escalations, quantitation mean
absolute error 1.01 percentage points, and nine false-positive AMR CONFIRM calls that restate the
host-attribution gap. Full results in <code>docs/zymo_validation.md</code>.</p>
</div></div>'''


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
.ev{margin-top:11px;padding:10px 12px;background:%(light)s;border-radius:3px}
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
td.code{font-weight:700;font-size:11px;white-space:nowrap;letter-spacing:.02em}
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
""" % C

JS = """
function pick(sel,attr,on){document.querySelectorAll(sel).forEach(function(b){
  b.setAttribute('aria-selected', String(b.dataset[attr]===on));});}
function showSample(id){pick('.bar button','s',id);
  document.querySelectorAll('.panel').forEach(function(p){p.hidden=(p.dataset.s!==id);});}
function showTab(s,t){pick('.panel[data-s="'+s+'"] .tabs button','t',t);
  document.querySelectorAll('.panel[data-s="'+s+'"] .tabp').forEach(function(p){
    p.hidden=(p.dataset.t!==t);});}
/* A cover-sheet link points at a card inside a hidden panel AND a hidden tab. Reveal both
   before the browser tries to scroll, or the jump silently lands nowhere. */
function openCard(s){showSample(s);showTab(s,'sp');}
"""


def build(samples, out=OUT, comparators=None):
    data = collect(samples, comparators)
    # sample_id, not the raw arguments. Under a workflow engine the arguments are localised
    # paths under a task container's _miniwdl_inputs/ that exist only inside that one container,
    # so printing them verbatim under "Reproduce this page offline" gives the reader a command
    # that cannot be run - the exact opposite of what the section promises.
    cmd = ('python3 analysis/triage.py --html ' + ' '.join(triage.sample_id(x) for x in samples) +
           ('' if comparators is not False or len(samples) < 2 else ' --independent') +
           # basename, not a relpath: out is absolute under a workflow engine and
           # relpath(out, ROOT) renders as ../../mnt/... which is noise, not a command.
           ('' if out == OUT else f' --out={os.path.basename(out)}'))
    fp = hashlib.sha256(
        open(os.path.join(ROOT, 'analysis', 'triage_rules.json'), 'rb').read() +
        open(os.path.join(ROOT, 'analysis', 'triage.py'), 'rb').read()).hexdigest()[:12]
    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

    bar = ''.join(f'<button data-s="{E(d["id"])}" onclick="showSample(\'{E(d["id"])}\')" '
                  f'aria-selected="{str(k == 0).lower()}">{E(d["sample"])}</button>'
                  for k, d in enumerate(data))

    panels = []
    for k, d in enumerate(data):
        tabs = [('qc', 'QC'), ('sp', 'Flaggable species'), ('amr', 'Resistance genes'),
                ('me', 'Method &amp; verification')]
        tb = ''.join(f'<button data-t="{t}" onclick="showTab(\'{E(d["id"])}\',\'{t}\')" '
                     f'aria-selected="{str(j == 0).lower()}">{lbl}</button>'
                     for j, (t, lbl) in enumerate(tabs))
        body = {'qc': qc_tab(d), 'sp': species_tab(d), 'amr': amr_tab(d),
                'me': method_tab(d, cmd, fp)}
        tp = ''.join(f'<section class="tabp" data-t="{t}"{"" if j == 0 else " hidden"}>{body[t]}</section>'
                     for j, (t, lbl) in enumerate(tabs))
        counts = {v: sum(1 for t in d['taxa'] if t['verdict'] == v) for v in VERDICT}
        head = ' &nbsp;·&nbsp; '.join(f'{chip(v)} {counts[v]}' for v in
                                      ['ESCALATE', 'CONFIRM', 'MONITOR', 'NOT_TESTED'] if counts[v])
        sv, sv_why = d['verdict']
        svcol = {'ESCALATE': C['red'], 'INVESTIGATE': C['red'], 'MONITOR': C['amber'],
                 'NO ACTION': C['green']}[sv]
        reasons = ''.join(f'<li>{E(r)}</li>' for r in sv_why[:5])
        banner = (f'<div class="verdict" style="border-color:{svcol}">'
                  f'<span class="vchip" style="background:{svcol}">{sv}</span>'
                  f'<div><b>What to do about this swab.</b> Rolled up from the rows below: a '
                  f'threat-list agent with its marker present gives ESCALATE; a threat-list or '
                  f'watchlist organism at CONFIRM, or a high-consequence acquired gene, gives '
                  f'INVESTIGATE.<ul class="plain">{reasons}</ul></div></div>')
        panels.append(f'<div class="panel" data-s="{E(d["id"])}"{"" if k == 0 else " hidden"}>'
                      f'<div class="tabs">{tb}</div><main>{banner}'
                      f'<p class="blurb">{d["classified"]:,} classified reads &nbsp;·&nbsp; '
                      f'{head or "no taxon above NO ACTION"}</p>{tp}</main></div>')

    doc = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Triage evidence report — {E(", ".join(d["sample"] for d in data))}</title>
<style>{CSS}</style></head><body>
<header><h1>Triage evidence report</h1>
<div class="sub">Deterministic gate cascade over PFI metagenomic reports &nbsp;·&nbsp;
{len(data)} sample{"s" if len(data) != 1 else ""} &nbsp;·&nbsp; generated {E(stamp)}
&nbsp;·&nbsp; rules {E(fp)}</div></header>
{flagged_section(data)}
<div class="bar">{bar}</div>
{''.join(panels)}
<footer>Generated by <code>analysis/triage_report.py</code> from
<code>&lt;sample&gt;_en.html</code> only. Every figure is traceable to the PFI report or to a rule
in <code>analysis/triage_rules.json</code>. Verdicts are tiers, never diagnoses: CONFIRM means
culture with AST. Reproduce with <code>{E(cmd)}</code>.</footer>
<script>{JS}</script></body></html>'''

    with open(out, 'w', encoding='utf-8') as fh:
        fh.write(doc)
    return out, len(data)
