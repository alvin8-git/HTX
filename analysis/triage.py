"""Deterministic triage of a PFI metagenomic report. No LLM, no ML.

Reads WBM<id>_en.html (the embedded `globalData` object) and applies the gate cascade in
docs/automated_triage_design.md. Every verdict carries the rule that produced it.

    python3 analysis/triage.py                 # all five samples
    python3 analysis/triage.py WBM232          # one sample
    python3 analysis/triage.py --with-fastq    # additionally run the FASTQ-only gates
    python3 analysis/triage.py --selftest      # rule checks, no data needed

Output: analysis/triage_<sample>.tsv per sample, plus a summary on stdout.

INPUT CONTRACT: the HTML report is the whole input. This is auto-interpretation of the document
the microbiologist is already sent - so every verdict must be checkable against that same page,
and the engine must run wherever the page does. Anything needing the raw reads is an OPTIONAL
EXTENSION behind --with-fastq, off by default, never part of the baseline interpretation. The
extension exists because starting from FASTQ is a plausible future input; it is not one today.

Design constraints, deliberate:
  * Tiers, never diagnoses. The terminal state for a real finding is CONFIRM (culture + AST).
  * NOT_TESTED never collapses into NO_ACTION. An RNA agent against a DNA library is untested.
  * An AMR gene with no attributed host caps at CONFIRM. Host attribution is unsolved here
    (docs/biothreat_assessment.md 2.5) and no rule fixes a missing measurement.
  * The rules are expected to change. They encode what is decidable from today's report shape;
    an RNA library, a new database version or more sample data changes that, and the change
    belongs in triage_rules.json rather than in this file.
"""
import collections
import glob
import gzip
import math
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = json.load(open(os.path.join(ROOT, 'analysis', 'triage_rules.json')))
TH = RULES['thresholds']
SAMPLES = ['WBM156', 'WBM174', 'WBM179', 'WBM185', 'WBM232']
VERSION = '1.0.0'


def rules_fingerprint():
    """Short hash of the rule file. Printed by --version so a workflow run records WHICH rules
    produced its verdicts - the engine is stable, the rules are the part that moves."""
    import hashlib
    with open(os.path.join(ROOT, 'analysis', 'triage_rules.json'), 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:12]

# The optional-extension switch, set by --with-fastq. False is the contract: the HTML report is the
# whole input, and an importer that never touches this flag gets a pure report-only interpretation.
WITH_FASTQ = False

# Tier ordering, lowest to highest. NOT_TESTED sits outside the ladder: it is an absence of
# evidence, not a weak positive, so it must never be compared against or downgraded to NO_ACTION.
TIERS = ['NO_ACTION', 'MONITOR', 'CONFIRM', 'ESCALATE']


# OUTDIR is where TSVs land. Default is the repo layout; a workflow engine sets it, because
# WDL/Cromwell localises inputs into a generated directory and expects outputs beside them.
OUTDIR = os.path.join(ROOT, 'analysis')


def report_path(sample):
    """Resolve a sample argument to a report file.

    A bare stem (`WBM232`) resolves under the repo root, which is how this has always been driven
    by hand. Anything that already looks like a path or a file is taken as given - that is the
    case a workflow engine needs, since Cromwell localises an input to a directory generated at
    run time that the container cannot predict or hard-code.
    """
    if sample.endswith(('.html', '.htm')) or os.path.isabs(sample) or os.sep in sample:
        if os.path.exists(sample):
            return sample
        if os.path.exists(sample + '_en.html'):
            return sample + '_en.html'
        # Give up as the caller wrote it. Stapling _en.html onto a path that already ends in
        # .html only produces 'missing_en.html_en.html' in the error, which hides the real cause.
        return sample
    return os.path.join(ROOT, f'{sample}_en.html')


def sample_id(sample):
    """Display and filename stem for a sample argument, path or bare stem alike."""
    b = os.path.basename(sample)
    for suf in ('_en.html', '_en.htm', '.html', '.htm'):
        if b.endswith(suf):
            return b[:-len(suf)]
    return sample.replace('/', '_')


def load_report(sample):
    """Pull the globalData object literal out of the Vue SPA by brace matching."""
    path = report_path(sample)
    if not os.path.exists(path):
        # Name the path actually tried. The old failure surfaced as the bare OSError for
        # '/data/WBM*_en.html_en.html' - the _en.html fallback stapled onto an unexpanded glob -
        # which reads as an engine bug rather than a shell one.
        if any(c in sample for c in '*?['):
            # We glob these ourselves, so an unexpanded pattern arriving here matched nothing -
            # in a container, nearly always the mount, not the pattern.
            d = os.path.dirname(sample) or '.'
            raise SystemExit(f'{sample}: matched no file. Is {d} mounted, and are the reports '
                             f'directly in it? -v "$PWD/Reports:/data" puts them at /data/, '
                             f'not /data/Reports/.')
        raise SystemExit(f'{sample}: no such report (tried {path})')
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
    # FASTQ checks belong to the optional extension, not the baseline. Silence here is the correct
    # default: a report arriving without its reads is the normal case this engine is built for, and
    # saying so on every run would train the reader to skip the integrity list.
    if WITH_FASTQ:
        paths = [os.path.join(ROOT, sample, f'{kind}.DNA_{mate}.fq.gz')
                 for mate in (1, 2) for kind in ('unclassify', 'removehost')]
        if not any(os.path.exists(p) for p in paths):
            problems.append('--with-fastq requested but no FASTQs found - the FASTQ-only gates did '
                            'not run; verdicts rest on the report tables alone')
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
# OPTIONAL EXTENSION - the only gate that reads outside the HTML report, and the only one that is
# off by default. The PFI report gives read counts, never molecule counts: one fragment amplified
# 10,000x and 10,000 distinct fragments produce an identical row, so nothing in the document can
# separate them. Measured cost of running without it, across the five HTX samples: three rows move
# NO_ACTION -> MONITOR (S. inopinata, Hyphomicrobium sp. MC1, A. methanolica) and no threat-list,
# watchlist or sample verdict changes at all. It is a removal gate, so its absence can only leave
# noise in - never take a real finding out. That is the right direction for a screen to fail in,
# which is what makes HTML-only the safe default rather than a compromise.

def unique_fraction(sample, taxon):
    """Fraction of distinct sequences in a taxon's extracted reads. Computed lazily - only for
    taxa that survive the earlier gates, so the cost stays trivial. Returns (None, None) unless
    --with-fastq was given AND the reads are on disk."""
    if not WITH_FASTQ:
        return None, None
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

def marker_power(reads, entry, read_len):
    """Probability that at least one read would land on this agent's confirmatory-marker target,
    given how much of its genome was actually sequenced. Returns None when the rule file carries no
    genome/marker size for the agent, in which case the caller must not use the power test.

    Gate 10a is two-way: marker present escalates, marker absent downgrades. The downgrade arm is
    only honest if the marker COULD have been seen. WBM179 carried 11 reads of V. cholerae - 0.0004x
    genome coverage - so the chance of a read touching ctxA/ctxB was 0.3%, and 'ctxA/ctxB absent'
    was the expected outcome whether or not the organism was toxigenic. The engine reported that
    non-result as an exclusion.

    Poisson over uniform coverage. A read overlaps the target if it STARTS anywhere in the
    marker_bp + read_len window, so E[reads on target] = reads * (marker_bp + read_len) / genome_bp
    and P(>=1) = 1 - exp(-E). Read length belongs in the numerator and it matters, though less
    than raw length suggests: the per-read gain is (marker + long) / (marker + short), so a 6.7 kb
    read beats a 150 bp read by ~6x on a 1.2 kb marker - not the 45x the length ratio implies -
    and the advantage grows as the target shrinks. Uniform coverage is an idealisation - real coverage is patchier, which
    makes true power slightly WORSE than this, so the estimate is the optimistic bound. It also
    assumes the strain carries the marker at all; seb sits in a minority of S. aureus and ctxAB only
    in toxigenic V. cholerae, so a genuine absence is common - it just is not demonstrated here.
    """
    gs, mb = entry.get('genome_size_bp'), entry.get('marker_bp')
    if not gs or not mb or not reads:
        return None
    return 1.0 - math.exp(-reads * (mb + read_len) / gs)


def read_length(g):
    """Mean read length from the QC block, whichever key this platform's report uses. 150 is the
    short-read default and only applies when the report carries neither key."""
    try:
        q = g['basicSummary']['readsQc']['data'][0]
    except (KeyError, IndexError, TypeError):
        return 150.0
    for k in ('Mean_read_length', 'Read_Length'):
        try:
            v = float(str(q.get(k, '')).replace(',', ''))
            if v > 0:
                return v
        except (TypeError, ValueError):
            pass
    return 150.0


def marker_present(g, marker, taxon=None):
    """Search the VFDB table for a marker's pattern. Returns (found, evidence).

    `taxon` restricts the search to rows whose VFDB reference strain shares the taxon's genus, and
    it matters more than it looks. VFDB names Type VI secretion components `icmF/tssM`,
    `dotU/tssL`, `vasK/icmF` — homologues of the Coxiella Dot/Icm T4BSS carried by ordinary
    Pseudomonas and Acinetobacter. Unrestricted, a Coxiella marker would have fired on three of the
    five HTX swabs, on genes belonging to organisms that are not Coxiella.
    """
    pat = re.compile(RULES['marker_patterns'].get(marker, re.escape(marker)), re.I)
    genus = taxon.split(' ')[0].lower() if taxon else None
    vf = g.get('virulence', {}).get('DNA', {})
    rows = vf.get('data', []) if isinstance(vf, dict) else []
    for r in rows:
        if genus and str(r.get('Pathogen', '')).split(' ')[0].lower() != genus:
            continue
        if pat.search(json.dumps(r)):
            return True, str(r.get('Virulence Factor') or r.get('Gene') or '?')[:40]
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


def detect_platform(g):
    """'long' or 'short', from the mean read length the report already carries.

    Not cosmetic: breadth and depth mean different things per platform. A 7 kb read spans a 1 kb
    gene end to end, so breadth saturates at 100% and stops discriminating, while one unit of depth
    is one whole molecule rather than a thin pileup of fragments.
    """
    q = (g.get('basicSummary', {}).get('readsQc', {}).get('data') or [{}])[0]
    for k in ('Mean_read_length', 'Read_Length'):
        try:
            if float(str(q.get(k, '')).replace(',', '')) >= TH['long_read_length_bp']:
                return 'long'
        except (TypeError, ValueError):
            continue
    return 'short'


def gene_thresholds(group, cls, platform='short'):
    """Resolve thresholds: group override -> platform override -> class default -> global default."""
    t = dict(RULES['class_thresholds'].get('_default', {}))
    t.update(RULES['class_thresholds'].get(cls, {}))
    if platform == 'long':
        t.update({k: v for k, v in RULES['long_read_thresholds'].get(cls, {}).items()
                  if k not in ('why', '_comment')})
    t.update({k: v for k, v in RULES['group_thresholds'].get(group, {}).items()
              if k not in ('why', '_comment')})
    return t


def triage_genes(g, platform=None):
    """Collapse MEGARes alleles to one call per Group, then classify. Returns list of dicts."""
    platform = platform or detect_platform(g)
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
            verdict, why = 'NO_ACTION', f'breadth {breadth:.2f}% below floor'
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
                why = (f'repressor of {need or "its operon"}, present at {breadth:.2f}%/{depth:.2f}x - '
                       'loss-of-function here is the resistance mechanism; target for variant calling')
            else:
                verdict, why = 'NO_ACTION', f'regulator; partner {need} present'
        elif cls == 'acquired':
            t = gene_thresholds(grp, cls, platform)
            # Host is never attributable from this data, so an acquired gene caps at CONFIRM.
            if breadth >= t['breadth'] and depth >= t['depth']:
                verdict = 'CONFIRM'
                why = f'acquired, full length: breadth {breadth:.2f}% depth {depth:.2f}x'
            elif depth >= t.get('partial_depth', 1e9) and breadth >= t.get('partial_breadth', 1e9):
                # Depth is reported over covered bases, so high depth on a fragment means the gene
                # is really there and well sequenced - only the allele is uncertain.
                verdict = 'CONFIRM'
                why = (f'acquired, PARTIAL: {breadth:.2f}% of the reference allele at {depth:.2f}x '
                       f'- gene family established, specific allele not')
            else:
                verdict = 'MONITOR'
                why = (f'acquired, breadth {breadth:.2f}% depth {depth:.2f}x - below '
                       f'{t["breadth"]:.0f}%/{t["depth"]:.0f}x and the partial route')
        else:
            verdict, why = 'MONITOR', 'unannotated group - needs a rule'

        out.append({'group': grp, 'allele': best['Gene'], 'alleles_collapsed': len(alleles),
                    'breadth': breadth, 'depth': depth, 'class': cls, 'platform': platform,
                    'drug_class': best.get('Class', ''), 'mechanism': best.get('Mechanism', ''),
                    'high_consequence': bool(ann.get('high_consequence')),
                    'verdict': verdict, 'why': why, 'note': ann['note']})
    return sorted(out, key=lambda r: (-TIERS.index(r['verdict']), -r['breadth']))


# ---------------------------------------------------------------- gates 1,2,7,9,10,11: taxa

def watchlist_escalation(name, w, genes, present=None):
    """Does a watchlist organism have supporting resistance context in the same sample?

    Returns (gene, basis) or None. This is CO-LOCATION, NOT CO-ATTRIBUTION: the gene is in the
    sample, this genus is a documented host for it, and MEGARes cannot say whose it is. The verdict
    it raises is CONFIRM — "culture with AST" — which is the right action whether or not the gene
    turns out to belong to this organism. It can never raise ESCALATE.
    """
    hints = RULES.get('amr_host_hints', {})
    genus = name.split()[0]
    for x in genes:
        if x['verdict'] != 'CONFIRM' or x['class'] != 'acquired':
            continue
        if x.get('drug_class') not in w['escalating_classes']:
            continue
        h = hints.get(x['group'])
        if not (h and any(genus.startswith(t) or t.startswith(genus) for t in h['taxa'])):
            continue
        # Being A documented host is not enough. If 77 organisms in this sample could carry the
        # gene and this one holds 1.3% of their reads, naming it is arbitrary - the co-location is
        # real and the attribution is noise. Require it to lead the pool, or hold a real share.
        if present:
            cands = [(n, c) for n, c in present.items()
                     if any(n.startswith(t + ' ') or n == t for t in h['taxa']) and c]
            tot = sum(c for _, c in cands)
            mine = present.get(name, 0)
            if tot and not (mine >= max(c for _, c in cands)
                            or mine / tot >= TH['escalation_host_share']):
                continue
            if tot:
                return x, (f"{h['basis']} This organism holds {mine/tot:.0%} of the reads of the "
                           f"{len(cands)} documented hosts of {x['group']} in this sample.")
        return x, h['basis']
    return None


def genus_amr_context(name, genes, present):
    """Resistance genes in this sample whose documented host range covers THIS taxon's genus,
    each with the competing candidate hosts in the same sample ranked by read count.

    This is the honest half of a question the assay cannot answer. MEGARes has no organism
    column, so `blaZ` is a fact about the sample, not about *Staphylococcus aureus*. What the
    rule file does know is which genera carry the gene (`amr_host_hints`); what the species
    table knows is which of those genera are actually here and how abundant each is. Setting
    the two side by side is what lets a human see that in WBM179 the blaZ sits in a sample
    where *S. epidermidis* outnumbers *S. aureus* 38x — evidence about attribution, without
    ever asserting one.

    Returns a list of dicts, most-confident gene first. NEVER changes a verdict: a gene that
    probably belongs to a congener is not evidence for or against this taxon's own call.
    """
    hints = {k: v for k, v in RULES.get('amr_host_hints', {}).items() if k != '_comment'}
    genus = name.split()[0]
    mine = present.get(name, 0)
    out = []
    for x in genes:
        h = hints.get(x['group'])
        if not h or not any(genus.startswith(t) or t.startswith(genus) for t in h['taxa']):
            continue
        cands = sorted(((n, c) for n, c in present.items()
                        if any(n.startswith(t + ' ') for t in h['taxa']) and c),
                       key=lambda kv: -kv[1])
        top, top_reads = cands[0] if cands else (name, mine)
        rank = next((i + 1 for i, (n, _c) in enumerate(cands) if n == name), None)
        # Truncating the list would hide the sharpest fact when this taxon ranks low: in WBM179
        # S. aureus is 7th of 12 staphylococci. Always carry this taxon into the shown set.
        shown = cands[:5]
        if rank and rank > len(shown):
            shown = shown + [(name, mine)]
        out.append({'group': x['group'], 'allele': x['allele'], 'verdict': x['verdict'],
                    'class': x['class'], 'breadth': x['breadth'], 'depth': x['depth'],
                    'gene_why': x['why'], 'basis': h['basis'], 'candidates': shown,
                    'self_rank': rank, 'n_hosts': len(cands),
                    'top_host': top, 'top_reads': top_reads,
                    'ratio': (top_reads / mine) if mine and top != name else None})
    return sorted(out, key=lambda r: (-TIERS.index(r['verdict']), -r['breadth']))


def context_line(name, ctx, present, kind='', entry=None):
    """One `why` line summarising genus_amr_context. Never None for a listed organism.

    Silence is the failure mode this whole project exists to avoid, so an organism with no
    matching gene says WHY there is none: viruses and fungi are outside what MEGARes indexes,
    and a bacterium whose genus is absent from `amr_host_hints` is a coverage limit of the rule
    file, which is a different statement from "this organism carries no resistance".
    """
    genus = name.split()[0]
    if not ctx:
        hints = {k: v for k, v in RULES.get('amr_host_hints', {}).items() if k != '_comment'}
        n_genera = len({t for v in hints.values() for t in v['taxa']})
        if str(kind).lower().startswith('vir'):
            return ('AMR CONTEXT: not applicable - MEGARes indexes bacterial resistance genes '
                    'and this agent is a virus')
        if str(kind).lower().startswith(('proto', 'metazoa', 'parasit')):
            return ('AMR CONTEXT: not applicable - MEGARes indexes bacterial resistance genes '
                    'and this agent is a eukaryotic parasite')
        if str(kind).lower().startswith('fung'):
            return ('AMR CONTEXT: not applicable - MEGARes carries no antifungal classes, so no '
                    'resistance evidence of any kind exists for this organism in this assay')
        exp = (entry or {}).get('amr_expectation')
        if exp:
            return f'AMR CONTEXT: none detected, and none expected - {exp}'
        known = [g for g, v in hints.items()
                 if any(genus.startswith(t) or t.startswith(genus) for t in v['taxa'])]
        if known:
            # The genus IS curated; nothing from its repertoire turned up here. That is a result.
            return (f'AMR CONTEXT: none. {len(known)} MEGARes group(s) are documented in {genus} '
                    f'({", ".join(sorted(known)[:8])}) and none of them was detected in this '
                    f'sample')
        return (f'AMR CONTEXT: none. No gene detected here has a documented host range covering '
                f'{genus}, and {genus} appears in none of the {len(hints)} curated groups '
                f'({n_genera} genera) - a coverage limit of the rule file, NOT evidence that '
                f'this organism carries no resistance')
    groups = ', '.join(x['group'] for x in ctx[:6]) + (' ...' if len(ctx) > 6 else '')
    best = max(ctx, key=lambda x: x['top_reads'])
    mine = present.get(name, 0)
    if best['top_host'] != name and mine:
        who = (f"the most abundant competing host in the sample is {best['top_host']} at "
               f"{best['top_reads']:,} reads ({best['top_reads']/mine:.0f}x this taxon), a "
               f"documented host of {best['group']}")
    else:
        who = 'this taxon is the most abundant documented host of any of them in this sample'
    return (f'AMR CONTEXT: {len(ctx)} gene(s) expected in {genus} co-detected in this sample '
            f'({groups}); {who} - MEGARes carries no organism column, so none of them is '
            f'attributed to any species and none of them changed this verdict')


def triage_taxa(sample, g, loads, genes, comparators=True):
    """comparators=False when there is nothing to compare against (a single novel sample, or a set
    of replicates of one community). Gate 8 is then inert, and non-threat taxa are reported on read
    count alone. Threat-list gating is unaffected — it never depended on cross-sample context."""
    results = []
    read_len = read_length(g)
    threat, notes = RULES['threat_list'], RULES['taxonomy_notes']
    watch = {k: v for k, v in RULES.get('clinical_watchlist', {}).items() if k != '_comment'}
    # Taxid is the primary key. A name string is re-spelled every time a genus moves and the
    # match is exact, so drift is a silent negative: Candida auris reaches this engine as
    # '[Candida] auris' from PFIDB v5 and 'Candidozyma auris' from current NCBI - three
    # spellings, one number (498019). Name lookup stays as the fallback for any report that
    # does not carry a Taxid column.
    threat_ids = {v['taxid']: v for v in threat.values()
                  if isinstance(v, dict) and v.get('taxid')}
    watch_ids = {v['taxid']: v for v in watch.values() if v.get('taxid')}
    genes = list(genes) if not isinstance(genes, set) else []
    present = {r['Scientific Name']: int(r['Real Read'])
               for r in g['indentification_DNA']['speciesData']['data']}

    for r in g['indentification_DNA']['speciesData']['data']:
        name, real = r['Scientific Name'], int(r['Real Read'])
        est = int(r['Estimate Read'])
        taxid = str(r.get('Taxid', '')).strip()
        t = threat_ids.get(taxid) or threat.get(name)
        w0 = (watch_ids.get(taxid) or watch.get(name)) if not t else None
        why = []
        # Carried on every exit path so the HTML report can show the evidence behind a verdict
        # without re-reading the PFI report. Unique fraction is filled in where a gate computed it.
        base = {'taxon': name, 'taxid': r.get('Taxid', ''), 'real': real, 'est': est,
                'abundance': str(r.get('Abundance', '')), 'unique': None, 'fold': None,
                'human_infection': r.get('Human Infection', ''), 'amr_context': []}

        # Sample-wide AMR evidence, pulled into the row of every organism it could plausibly
        # belong to. Evidence only - the line below is appended before any gate runs and no gate
        # reads it back, so it can inform a human without moving a verdict.
        if t or w0:
            base['amr_context'] = genus_amr_context(name, genes, present)
            why.append(context_line(name, base['amr_context'], present,
                                    r.get('Type', ''), t or w0))

        # gate 11: emit the reclassification note whatever else happens.
        if name in notes:
            why.append('TAXONOMY: ' + notes[name])

        # gate 7: Bracken redistribution can inflate an estimate far beyond the real reads.
        if real and est / real > TH['bracken_inflation_ratio']:
            why.append(f'estimate inflated {est/real:.0f}x over {real} real reads - judged on real')

        # gate 1b: clinically serious but not a CDC agent. Without this list the threat_list's
        # exclusive CDC A/B/C scope caps A. baumannii - the most operationally important organism
        # in this dataset - at MONITOR, because it is not a bioweapon.
        w = w0
        if w:
            if real < TH['min_real_reads']:
                continue
            uf, _n = unique_fraction(sample, name)
            fold = enrichment(loads, name, sample) if comparators else None
            base['unique'], base['fold'] = uf, fold
            why.append(f'{w["priority"]} priority pathogen')
            if uf is not None and uf < TH['unique_fraction_floor']:
                results.append({**base, 'tier': 'W', 'verdict': 'NO_ACTION',
                                'why': '; '.join(why + [f'unique fraction {uf:.0%} - amplification '
                                                        f'artifact'])})
                continue
            # With comparators, enrichment is the evidence that this organism belongs to this site.
            # Without them it cannot be measured, and defaulting the gate open escalated five
            # watchlist organisms in WBM232 on one shared aminoglycoside gene. Fall back to a
            # criterion that IS measurable inside a single sample: substantial abundance.
            if fold is not None:
                enriched = fold >= TH['enrichment_fold']
                bar = ''
            else:
                ab = float(str(base['abundance']).rstrip('%') or 0)
                enriched = ab >= TH['watchlist_min_abundance_no_comparators']
                bar = (f'no comparator samples, so escalation required abundance '
                       f'>= {TH["watchlist_min_abundance_no_comparators"]}% instead of enrichment '
                       f'(this taxon: {ab:.2f}%)')
            hit = watchlist_escalation(name, w, genes, present) if enriched else None
            if fold is None:
                enr = bar or 'no comparator samples, enrichment untestable'
            elif fold == float('inf'):
                enr = 'detected only in this sample'
            elif fold < 1:
                enr = (f'not enriched - {fold:.2f}x the load of the sample that carries most of it, '
                       f'so this is background for the batch')
            else:
                enr = f'{fold:.1f}x enriched vs other samples'
            if hit:
                gene, basis = hit
                verdict = 'CONFIRM'
                why.append(enr)
                why.append(f'acquired {gene["drug_class"]} resistance in the same sample '
                           f'({gene["group"]} {gene["allele"]}, {gene["breadth"]:.1f}%/'
                           f'{gene["depth"]:.2f}x) and this genus is a documented host - '
                           f'CO-LOCATION, NOT CO-ATTRIBUTION; culture with AST to establish linkage')
            else:
                verdict = 'MONITOR'
                why.append(enr)
                why.append('no co-located acquired resistance of a listed class'
                           if enriched else 'not enriched, so no escalation was attempted')
            if uf is not None:
                why.append(f'unique fraction {uf:.0%}')
            results.append({**base, 'tier': 'W', 'verdict': verdict,
                            'watch_priority': w['priority'], 'watch_note': w['note'],
                            'why': '; '.join(why)})
            continue

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
            base['unique'], base['fold'] = uf, fold
            if uf is not None and uf < TH['unique_fraction_floor']:
                results.append({**base, 'tier': '-', 'verdict': 'NO_ACTION',
                                'why': f'unique fraction {uf:.0%} of {n} reads - amplification artifact'})
                continue
            why.append('no comparator samples - reported on read count alone, NOT shown to be '
                       'site-specific' if fold is None else
                       (f'{fold:.0f}x enriched vs other samples' if fold != float('inf')
                        else 'detected only in this sample'))
            if uf is not None:
                why.append(f'unique fraction {uf:.0%}')
            results.append({**base, 'tier': '-', 'verdict': 'MONITOR', 'why': '; '.join(why)})
            continue

        # --- threat-list agent ---
        # gate 2 (assay detectability). Must be decided BEFORE read count: an RNA agent at zero
        # reads is untested, not absent, and must never fall through to NO_ACTION.
        if t['genome'] == 'RNA' and not g.get('showRNA'):
            results.append({**base, 'tier': t['tier'], 'verdict': 'NOT_TESTED',
                            'why': 'RNA genome, DNA-only library - structurally undetectable'})
            continue

        if real < TH['min_real_reads']:
            why.append(f'{real} reads, below min {TH["min_real_reads"]}')
            uf, n = unique_fraction(sample, name)
            base['unique'] = uf
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

        # gate 10a: confirmatory marker. Absent = downgrade, present = escalate. Only for agents
        # whose marker is unique to them and reliably in VFDB, so that a negative is a real negative.
        found = [f'{m}({ev})' for m in t['markers']
                 for ok, ev in [marker_present(g, m, name)] if ok]
        power = marker_power(real, t, read_len)
        base['marker_power'] = power
        if t['markers']:
            if found:
                why.append('MARKER PRESENT: ' + ', '.join(found))
                verdict = 'ESCALATE'
            elif (power is not None and power < TH['marker_power_min']
                    and real >= TH['min_real_reads']):
                # Only above the read floor. Below it, gate 1 has already answered - "too few reads
                # to call the organism at all" is a well-powered conclusion about the organism, and
                # the marker question is moot. V. cholerae at 11 reads stays NO_ACTION.
                # The marker could not have been seen at this coverage, so its absence is not a
                # result. Downgrading on it would report the expected outcome of a test with no
                # power as if it were evidence. NOT_TESTED is the tier that already means exactly
                # this, and it sits outside the ladder so it can never collapse into NO_ACTION.
                why.append(f'confirmatory marker(s) {"/".join(t["markers"])} NOT ASSESSABLE at this '
                           f'coverage - {real:,} reads over a {t["genome_size_bp"]/1e6:.2f} Mb '
                           f'genome gives a {power:.0%} chance of a read landing on the '
                           f'{t["marker_bp"]:,} bp target, so absence carries no information. The '
                           f'marker reverts to ONE-WAY: present would still escalate')
                verdict = 'NOT_TESTED' if verdict != 'ESCALATE' else verdict
            else:
                pc = f' (detectable at {power:.0%} power)' if power is not None else ''
                why.append(f'confirmatory marker(s) {"/".join(t["markers"])} ABSENT{pc} - downgraded')
                verdict = 'NO_ACTION' if verdict != 'ESCALATE' else verdict

        if t.get('subspecies_required') and verdict == 'CONFIRM':
            # The species-level call is not the finding: the threat is defined below species and
            # this database cannot go there. Found by the Zymo standard, where the certified
            # laboratory S. enterica strain scored CONFIRM at 12% abundance in all five samples.
            verdict = 'MONITOR'
            why.append(f'species-level identification only - needs {t["subspecies_required"]}')

        # gate 10b: supporting marker. ONE-WAY. Present escalates; absent changes nothing and says
        # so. The asymmetry is the point - for these agents VFDB coverage cannot be certified from
        # the report alone, so treating a miss as an exclusion would let the engine silently clear a
        # real Category A/B detection. A one-way gate can only ever add evidence.
        sup = [f'{m}({ev})' for m in t.get('supporting_markers', [])
               for ok, ev in [marker_present(g, m, name)] if ok]
        if t.get('supporting_markers') and verdict in ('CONFIRM', 'MONITOR'):
            if sup:
                why.append('SUPPORTING MARKER PRESENT: ' + ', '.join(sup)
                           + ' - in this genus, at this coverage')
                verdict = 'ESCALATE'
            else:
                why.append(f'supporting marker(s) {"/".join(t["supporting_markers"])} searched in '
                           f'{name.split(" ")[0]} VFDB rows and not found - these escalate when '
                           'present but absence does NOT exclude the agent, so the call stands')
        elif not t['markers'] and not t.get('supporting_markers') and verdict == 'CONFIRM':
            # Neither gate ran. Say so: a silent CONFIRM reads like a marker was checked and found.
            why.append('no confirmatory or supporting marker defined for this agent - gate 10 did '
                       'not run, so CONFIRM is the ceiling and the call rests on taxonomy alone')

        results.append({**base, 'tier': t['tier'], 'verdict': verdict,
                        'markers_found': found + sup, 'markers_required': t['markers'],
                        'supporting_found': sup,
                        'supporting_required': t.get('supporting_markers', []),
                        'why': '; '.join(why) or 'threat-list agent'})

    # An agent this assay cannot see is absent from the species table, so the loop above never
    # reaches it and the NOT_TESTED warning would reach nobody at all - the exact collapse into
    # silence the tier exists to prevent. Emit one row per untestable threat-list agent, derived
    # from the rule file rather than from the data, because the data is what is missing.
    if not g.get('showRNA'):
        seen = {r['taxon'] for r in results}
        for name, t in sorted(threat.items()):
            if t['genome'] == 'RNA' and name not in seen:
                results.append({'taxon': name, 'taxid': '', 'real': 0, 'est': 0, 'abundance': '',
                                'unique': None, 'fold': None, 'human_infection': '',
                                'tier': t['tier'], 'verdict': 'NOT_TESTED',
                                'why': 'RNA genome, DNA-only library - structurally undetectable. '
                                       'Not screened, therefore not excluded.'})

    return sorted(results, key=lambda r: (-TIERS.index(r['verdict']) if r['verdict'] in TIERS else 99,
                                          -r['real']))


# ---------------------------------------------------------------- sample roll-up

# What to do about the swab, as opposed to about one row. The deck carried a verdict like this per
# sample and the row-level tiers had no equivalent, so a reader comparing the two saw an apparent
# downgrade that was really a change of subject.
SAMPLE_VERDICTS = ['NO ACTION', 'MONITOR', 'INVESTIGATE', 'ESCALATE']


def _headline(t):
    """The clause of a row's reasoning that actually justifies its verdict.

    Taking the first clause picks up the Bracken-inflation note, which is a caveat about a number,
    not the reason for the tier.
    """
    parts = [p.strip() for p in t['why'].split(';') if p.strip()]
    for want in ('CO-LOCATION', 'MARKER PRESENT', 'enriched', 'only in this sample', 'priority'):
        for p in parts:
            if want in p:
                return p
    return parts[0] if parts else t['why']


def sample_verdict(taxa, genes):
    """Roll row verdicts up to one verdict for the sample. Returns (verdict, [reasons])."""
    flagged = [t for t in taxa if t['tier'] != '-']          # threat-list or watchlist only
    conf = [x for x in genes if x['verdict'] == 'CONFIRM' and x['class'] == 'acquired']
    hi = [x for x in conf if x.get('high_consequence')]
    why = []

    esc = [t for t in flagged if t['verdict'] == 'ESCALATE']
    if esc:
        return 'ESCALATE', [f'{t["taxon"]}: threat-list agent with its confirmatory marker present'
                            for t in esc]

    cf = [t for t in flagged if t['verdict'] == 'CONFIRM']
    why += [f'{t["taxon"]}: {_headline(t)}' for t in cf]
    why += [f'{x["group"]} ({x["allele"]}) at {x["breadth"]:.1f}%/{x["depth"]:.2f}x - '
            f'high-consequence acquired resistance' for x in hi]
    if cf or hi:
        return 'INVESTIGATE', why

    # MONITOR needs a POSITIVE driver, not merely the existence of a listed organism somewhere in
    # the sample. Before 2026-08-12 any watchlist taxon at MONITOR returned MONITOR - and since a
    # surface swab carries a dozen WHO-priority organisms at background level as a matter of
    # course, that made MONITOR the floor rather than a finding, and drained the word of meaning.
    # A listed organism sitting at the same relative abundance as it does in every other swab is
    # what background looks like; it is not something to watch.
    site = [t for t in flagged if t['verdict'] == 'MONITOR'
            and (t.get('fold') or 0) >= TH['enrichment_fold']]
    # An acquired gene counts toward the sample verdict only when a LISTED organism is the most
    # abundant documented host of it. Otherwise it is the resistome of the commensal flora - blaZ
    # and tetK topping out in S. hominis on a hand-touched surface is normal skin carriage, and
    # reading it as a reason to watch the site mistakes the population for the place.
    led = [t for t in flagged
           if any(c.get('self_rank') == 1 and c.get('verdict') == 'CONFIRM'
                  for c in (t.get('amr_context') or []))]
    why = [f'{t["taxon"]}: {_headline(t)}' for t in site]
    why += [f'{t["taxon"]}: most abundant documented host of an acquired gene at CONFIRM'
            for t in led if t not in site]
    if not flagged and conf:
        why.append(f'{len(conf)} acquired resistance gene(s) at CONFIRM with no listed organism '
                   f'in this sample to attach them to')
        return 'MONITOR', why
    if site or led:
        return 'MONITOR', why
    n_bg = len([t for t in flagged if t['verdict'] == 'MONITOR'])
    return 'NO ACTION', [f'No listed organism is site-enriched and no acquired resistance gene '
                         f'reached CONFIRM.'
                         + (f' {n_bg} WHO/CDC-listed organism(s) are present at batch-background '
                            f'levels - expected on a public surface, and not a finding.'
                            if n_bg else '')]


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
        why = 'single sample' if len(samples) == 1 else 'samples declared independent (--independent)'
        print(f'  [gate 8] {why} - cross-sample enrichment is inert; non-threat taxa are '
              'reported on read count alone and are NOT shown to be site-specific.')

    for s in samples:
        g = reports[s]
        genes = triage_genes(g)
        taxa = triage_taxa(s, g, loads, genes, comparators)
        sv, sv_why = sample_verdict(taxa, genes)

        print(f'\n{"="*100}\n{sample_id(s)}   classified={classified[s]:,}\n{"="*100}')
        print(f'  SAMPLE VERDICT: {sv}')
        for r in sv_why[:4]:
            print(f'      - {r[:110]}')
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

        out = os.path.join(OUTDIR, f'triage_{sample_id(s)}.tsv')
        with open(out, 'w') as fh:
            fh.write('kind\tverdict\tcdc_tier\tname\tevidence\treason\tnote\n')
            # sample_id, not the raw argument: under WDL the argument is a localised path
            # like /cromwell-executions/.../WBM185_en.html, and writing that into the identifier
            # column makes the TSV unreadable outside the run that produced it.
            fh.write(f'sample\t{sv}\t\t{sample_id(s)}\t{classified[s]} classified reads\t'
                     f'{" | ".join(sv_why)}\t\n')
            for r in taxa:
                fh.write(f"taxon\t{r['verdict']}\t{r['tier']}\t{r['taxon']}\t{r['real']} reads\t{r['why']}\t\n")
            for r in genes:
                fh.write(f"amr\t{r['verdict']}\t\t{r['group']} ({r['allele']})\t"
                         f"{r['breadth']:.2f}% {r['depth']:.2f}x collapsed {r['alleles_collapsed']}\t"
                         f"{r['why']}\t{r['note']}\n")
        print(f'  -> {os.path.relpath(out, ROOT) if out.startswith(ROOT) else out}')


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

    # --- clinical watchlist -------------------------------------------------------------------
    wl = {k: v for k, v in RULES['clinical_watchlist'].items() if k != '_comment'}
    assert 'Acinetobacter baumannii' in wl                 # the organism that motivated the list
    assert not (set(wl) & set(tl)), 'watchlist and threat list must not overlap'

    # --- taxid keying -------------------------------------------------------------------------
    # Every listed organism must carry a taxid, and no two may share one: the taxid is what the
    # engine matches on, so a missing one silently demotes that organism to name matching and a
    # duplicated one would make two rules collide on the same report row.
    listed = {**{k: v for k, v in tl.items() if k != '_comment' and isinstance(v, dict)}, **wl}
    for k, v in listed.items():
        assert str(v.get('taxid', '')).isdigit(), f'{k} has no taxid - run resolve_taxids.py'
    ids = [v['taxid'] for v in listed.values()]
    assert len(ids) == len(set(ids)), 'two rules share a taxid'
    # A rename must not lose the organism. PFIDB v5 spells this '[Candida] auris', NCBI now says
    # 'Candidozyma auris', the rule file says 'Candida auris' - all three are taxid 498019.
    assert wl['Candida auris']['taxid'] == '498019'
    assert tl['Bacillus anthracis']['taxid'] == '1392'
    renamed = triage_taxa('selftest', {'indentification_DNA': {'speciesData': {'data': [
        {'Taxid': '498019', 'Scientific Name': '[Candida] auris', 'Real Read': '900',
         'Estimate Read': '900'}]}}}, [], {}, comparators=False)
    assert renamed and renamed[0]['verdict'] != 'NO_ACTION', renamed
    assert 'WHO critical' in renamed[0]['why'], renamed[0]['why']

    # --- sample-wide AMR evidence, pulled into a species row ------------------------------------
    # The gene is in the sample; the genus is a documented host; a congener is far more abundant.
    # All three facts belong in the organism's row, and none of them may move its verdict.
    sp = {'indentification_DNA': {'speciesData': {'data': [
        {'Taxid': '1280', 'Scientific Name': 'Staphylococcus aureus', 'Real Read': '1699',
         'Estimate Read': '6162'},
        {'Taxid': '1282', 'Scientific Name': 'Staphylococcus epidermidis', 'Real Read': '65238',
         'Estimate Read': '104545'}]}}}
    blaz = {'group': 'BLAZ', 'allele': 'MEG_1330', 'verdict': 'MONITOR', 'class': 'acquired',
            'breadth': 74.91, 'depth': 2.49, 'why': 'acquired', 'drug_class': 'betalactams'}
    ctx = genus_amr_context('Staphylococcus aureus', [blaz], {'Staphylococcus aureus': 1699,
                                                              'Staphylococcus epidermidis': 65238})
    assert len(ctx) == 1 and ctx[0]['top_host'] == 'Staphylococcus epidermidis'
    assert round(ctx[0]['ratio']) == 38, ctx[0]['ratio']
    assert ctx[0]['self_rank'] == 2 and ctx[0]['n_hosts'] == 2
    # ...and the verdict is still driven only by the marker gate.
    row = next(x for x in triage_taxa('selftest', sp, {}, [blaz], comparators=False)
               if x['taxon'] == 'Staphylococcus aureus')
    # 1,699 reads over a 2.82 Mb genome gives ~44% power on the 801 bp seb target, under the 90%
    # bar, so the marker is NOT ASSESSABLE and the row is NOT_TESTED rather than NO_ACTION.
    assert row['verdict'] == 'NOT_TESTED' and 'seb NOT ASSESSABLE' in row['why'], row
    assert 'AMR CONTEXT' in row['why'] and 'BLAZ' in row['why'], row['why']
    assert 'none of them changed this verdict' in row['why'], row['why']

    # --- gate 10a marker power -----------------------------------------------------------------
    vc = RULES['threat_list']['Vibrio cholerae']
    assert round(marker_power(11, vc, 150) * 100, 1) == 0.4, marker_power(11, vc, 150)
    # Depth fixes it in principle; the required depth is the point. ~10k reads clears 90%.
    assert marker_power(10000, vc, 150) > 0.90
    # A long read helps, but by (marker+long)/(marker+short) = ~6x on ctxAB, not by the 45x
    # length ratio. Guard the real figure so the docstring claim cannot drift back up.
    ratio = marker_power(11, vc, 6678) / marker_power(11, vc, 150)
    assert 5.5 < ratio < 6.5, ratio
    # No genome/marker size in the rule file -> no power test, and the caller must not downgrade.
    assert marker_power(1000, {'markers': ['x']}, 150) is None
    # Below the read floor gate 1 has already answered; the marker gate must not override it.
    sp_lo = {'indentification_DNA': {'speciesData': {'data': [
        {'Scientific Name': 'Vibrio cholerae', 'Taxid': '666', 'Real Read': '11',
         'Estimate Read': '11', 'Abundance': '0.00%', 'Type': 'Bacteria'}]}},
        'virulence': {'DNA': {'data': []}}, 'showRNA': False}
    lo = next(x for x in triage_taxa('selftest', sp_lo, {}, [], comparators=False)
              if x['taxon'] == 'Vibrio cholerae')
    assert lo['verdict'] == 'NO_ACTION' and 'below min' in lo['why'], lo['why']
    assert 'NOT ASSESSABLE' not in lo['why'], lo['why']
    ab = wl['Acinetobacter baumannii']
    # Escalation needs ALL of: acquired + CONFIRM + a listed drug class + this genus as a host.
    good = {'group': 'CTX', 'allele': 'MEG_2378', 'verdict': 'CONFIRM', 'class': 'acquired',
            'drug_class': 'betalactams', 'breadth': 60.6, 'depth': 11.7}
    assert watchlist_escalation('Acinetobacter baumannii', ab, [good]), 'should escalate'
    for bad in ({**good, 'verdict': 'MONITOR'},          # not confident enough
                {**good, 'class': 'intrinsic'},          # not acquired
                {**good, 'drug_class': 'Tetracyclines'}):  # not a listed class for this organism
        assert not watchlist_escalation('Acinetobacter baumannii', ab, [bad]), bad
    # A staphylococcal gene must not escalate an Acinetobacter, however strong it is.
    assert not watchlist_escalation('Acinetobacter baumannii', ab,
                                    [{**good, 'group': 'MECA', 'drug_class': 'betalactams'}])
    # Co-location is not enough: the organism must lead the gene's host pool or hold a real share.
    lead = {'Acinetobacter baumannii': 6000, 'Acinetobacter junii': 100}
    tail = {'Acinetobacter baumannii': 100, 'Acinetobacter junii': 6000, 'Acinetobacter ursingii': 4000}
    assert watchlist_escalation('Acinetobacter baumannii', ab, [good], lead), 'tops pool -> escalate'
    assert not watchlist_escalation('Acinetobacter baumannii', ab, [good], tail), \
        'holds 1% of the pool -> co-location is arbitrary, must not escalate'

    # --- sample roll-up -----------------------------------------------------------------------
    T = lambda tier, v, why='x', fold=None, ctx=None: {'tier': tier, 'verdict': v, 'why': why,
                                                       'taxon': 'T', 'fold': fold,
                                                       'amr_context': ctx or []}
    G = lambda v, hc=False: {'verdict': v, 'class': 'acquired', 'high_consequence': hc,
                             'group': 'G', 'allele': 'MEG_1', 'breadth': 90.0, 'depth': 9.0}
    assert sample_verdict([T('A', 'ESCALATE')], [])[0] == 'ESCALATE'
    assert sample_verdict([T('W', 'CONFIRM')], [])[0] == 'INVESTIGATE'
    assert sample_verdict([], [G('CONFIRM', hc=True)])[0] == 'INVESTIGATE'   # mecA / CTX-M alone
    assert sample_verdict([], [G('CONFIRM')])[0] == 'MONITOR'                # ordinary acquired gene
    # MONITOR needs a positive driver. A listed organism merely PRESENT at background level is
    # what a public surface looks like, and returning MONITOR for it made the tier the floor.
    assert sample_verdict([T('W', 'MONITOR', fold=9.0)], [])[0] == 'MONITOR'      # site-enriched
    assert sample_verdict([T('W', 'MONITOR', fold=1.2)], [])[0] == 'NO ACTION'    # background
    assert sample_verdict([T('W', 'MONITOR', fold=None)], [])[0] == 'NO ACTION'   # not comparable
    # A listed organism topping the host pool of an acquired CONFIRM gene is also a driver...
    assert sample_verdict([T('W', 'MONITOR', ctx=[{'self_rank': 1, 'verdict': 'CONFIRM'}])],
                          [G('CONFIRM')])[0] == 'MONITOR'
    # ...but the same gene led by a commensal is not: that is the flora's resistome, not the site's.
    assert sample_verdict([T('W', 'MONITOR', ctx=[{'self_rank': 4, 'verdict': 'CONFIRM'}])],
                          [G('CONFIRM')])[0] == 'NO ACTION'
    assert sample_verdict([T('-', 'MONITOR')], [])[0] == 'NO ACTION'         # community context only
    assert sample_verdict([], [])[0] == 'NO ACTION'
    # A watchlist organism can never drive the sample to ESCALATE.
    assert sample_verdict([T('W', 'CONFIRM')], [G('CONFIRM', hc=True)])[0] == 'INVESTIGATE'

    # --- platform calibration -----------------------------------------------------------------
    qc = lambda **kw: {'basicSummary': {'readsQc': {'data': [kw]}}}
    assert detect_platform(qc(Mean_read_length='6678.0')) == 'long'
    assert detect_platform(qc(Read_Length='150')) == 'short'
    assert detect_platform({}) == 'short'                    # absent field must not crash or lie
    st, lt = gene_thresholds('X', 'acquired', 'short'), gene_thresholds('X', 'acquired', 'long')
    # Long reads saturate breadth and each unit of depth is a whole molecule, so the gates move
    # in opposite directions. Anything else means the override was dropped or inverted.
    assert lt['breadth'] > st['breadth'] and lt['depth'] < st['depth'], (st, lt)
    # A group override still beats the platform override.
    assert gene_thresholds('CTX', 'acquired', 'long')['breadth'] == \
           gene_thresholds('CTX', 'acquired', 'short')['breadth']
    # A full-length gene at 2 spanning molecules is CONFIRM on long reads, MONITOR on short.
    gene = {'Group': 'ERMB', 'Gene': 'MEG_2793', 'Coverage(%)': '100.0', 'Depth': '2.4',
            'Type': 'Drugs', 'Class': 'MLS', 'Mechanism': 'Macrolide-resistant 23S ribosomal subunit'}
    rep = lambda ml: {'basicSummary': {'readsQc': {'data': [{'Mean_read_length': ml}]}},
                      'drugResistance': {'DNA': {'data': [dict(gene, Mechanism='MLS transferases')]}}}
    assert triage_genes(rep('7000'))[0]['verdict'] == 'CONFIRM'
    assert triage_genes(rep('150'))[0]['verdict'] == 'MONITOR'

    # --- gate 10 coverage and the one-way supporting gate -----------------------------------------
    for pat in RULES['marker_patterns'].values():
        re.compile(pat)                                    # a broken regex must fail here, not live
    fake = lambda name, n, vf=(): {
        'showRNA': False,
        'virulence': {'DNA': {'data': [{'Virulence Factor': f, 'Pathogen': p, 'VF Protein': 'VFG1'}
                                       for f, p in vf]}},
        'indentification_DNA': {'speciesData': {'data': [
            {'Scientific Name': name, 'Taxid': '1', 'Real Read': str(n),
             'Estimate Read': str(n), 'Abundance': '5%', 'Human Infection': 'Y'}]}}}
    row = lambda name, n, vf=(): next(
        r for r in triage_taxa('s', fake(name, n, vf), {name: {'s': 1.0}}, [], False)
        if r['taxon'] == name)

    # Two-way marker: absent means downgraded, and it must not claim gate 10 was skipped.
    assert 'ABSENT' in row('Bacillus anthracis', 5000)['why']
    assert row('Bacillus anthracis', 5000)['verdict'] == 'NO_ACTION'

    # Supporting marker, present -> ESCALATE. Absent -> unchanged, and the row must say a miss is
    # not an exclusion. This asymmetry is the whole point: a one-way gate cannot silently clear a
    # Category A/B detection the way a two-way gate with uncertain VFDB coverage would.
    cox = row('Coxiella burnetii', 5000)
    assert cox['verdict'] == 'CONFIRM' and 'does NOT exclude' in cox['why'], cox['why']
    cox2 = row('Coxiella burnetii', 5000, vf=[('dotA', 'Coxiella burnetii RSA 493')])
    assert cox2['verdict'] == 'ESCALATE', cox2['why']
    # Same gene name on another genus's reference strain must NOT confirm it. VFDB really does name
    # Type VI secretion components icmF/tssM and dotU/tssL, and Staphylococcus really does carry
    # esxA/esxB - unrestricted, those would escalate Coxiella and M. tuberculosis on clean samples.
    assert row('Coxiella burnetii', 5000, vf=[('dotA', 'Pseudomonas aeruginosa PAO1')])['verdict'] == 'CONFIRM'
    assert row('Mycobacterium tuberculosis', 5000,
               vf=[('esxA', 'Staphylococcus aureus MW2')])['verdict'] == 'CONFIRM'
    assert row('Mycobacterium tuberculosis', 5000,
               vf=[('esxA', 'Mycobacterium tuberculosis H37Rv')])['verdict'] == 'ESCALATE'
    # A supporting marker must be able to lift the subspecies cap - that is what it is for.
    sal = row('Salmonella enterica', 5000)
    assert sal['verdict'] == 'MONITOR' and 'needs serovar' in sal['why']
    assert row('Salmonella enterica', 5000,
               vf=[('tviB', 'Salmonella enterica serovar Typhi CT18')])['verdict'] == 'ESCALATE'
    # Gate 9 runs first: a near-neighbour at equal depth must block the lift, or esx would escalate
    # M. tuberculosis off an environmental NTM that carries the same operon.
    ntm = {'showRNA': False, 'virulence': {'DNA': {'data': [
               {'Virulence Factor': 'esxA', 'Pathogen': 'Mycobacterium tuberculosis H37Rv'}]}},
           'indentification_DNA': {'speciesData': {'data': [
               {'Scientific Name': n, 'Taxid': '1', 'Real Read': '5000', 'Estimate Read': '5000',
                'Abundance': '5%', 'Human Infection': 'Y'}
               for n in ('Mycobacterium tuberculosis', 'Mycobacterium avium')]}}}
    mtb = next(r for r in triage_taxa('s', ntm, {'Mycobacterium tuberculosis': {'s': 1.0}}, [], False)
               if r['taxon'] == 'Mycobacterium tuberculosis')
    assert mtb['verdict'] == 'NO_ACTION' and 'near-neighbour' in mtb['why'], mtb['why']

    # Only agents with genuinely unavailable markers may still have neither gate.
    neither = sorted(k for k, v in tl.items() if v['genome'] == 'DNA'
                     and not v.get('markers') and not v.get('supporting_markers'))
    assert neither == ['Chlamydia psittaci', 'Cryptosporidium parvum', 'Rickettsia prowazekii',
                       'Variola virus'], neither
    for k in neither:
        assert tl[k]['near_neighbours'], f'{k} has no marker, so it must at least name its look-alikes'

    # --- mechanism coverage for the groups long-read stool surfaced ------------------------------
    for mech, want in (('Tetracycline resistance ribosomal protection proteins', 'acquired'),
                       ('Tetracycline inactivation enzymes', 'acquired'),
                       ('VanG-type resistance protein', 'acquired'),
                       ('VanA-type resistance protein', 'acquired'),
                       ('Tunicamycin resistance protein', 'environmental')):
        assert annotate_group('ZZZ', 'Drugs', mech)['class'] == want, mech
    print('selftest: all rule checks pass')


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    # Expand globs ourselves. Inside a container the host shell cannot see /data, so
    # `-v "$PWD/Reports:/data" ... /data/*_en.html` reaches us as a literal pattern - and the host
    # shell may even expand it against the WRONG directory. Sorted, because glob order is the
    # filesystem's and sample order shows up in the outputs. A no-op when the shell did expand.
    args = [m for a in args
            for m in (sorted(glob.glob(a)) if any(c in a for c in '*?[') else [a])
            or [a]]
    # --with-fastq: opt in to the gates that read outside the HTML report (gate 6, FASTQ integrity).
    # Off by default so the baseline output is reproducible by anyone holding only the report.
    WITH_FASTQ = '--with-fastq' in sys.argv
    # --outdir: where TSVs land. A workflow engine runs the container with inputs and outputs in
    # directories it generates, so neither can be baked into the image.
    _od = next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith('--outdir=')), None)
    if _od:
        # Refuse a filename here. `--outdir=out/triage_report.html` otherwise makedirs a DIRECTORY
        # called triage_report.html and the report goes somewhere else entirely - inside a
        # container, to a path that dies with it. Silent, and the exit code is 0.
        if _od.endswith(('.html', '.htm', '.tsv')):
            raise SystemExit(f'--outdir={_od} looks like a file. --outdir takes a DIRECTORY '
                             f'(--outdir={os.path.dirname(_od) or "."}); to name the HTML report '
                             f'use --out={_od}')
        OUTDIR = os.path.abspath(_od)
        os.makedirs(OUTDIR, exist_ok=True)
    # --independent: the samples are not from one site (different donors, different facilities), so
    # a fold-change between them measures who they came from, not where. Turns gate 8 off.
    comparators = False if '--independent' in sys.argv else None
    out = next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith('--out=')), None)
    # --outdir governs the HTML report too. Without this, `--html --outdir=/data/out` wrote the
    # report to the image's own /opt/htx/analysis/ and lost it when the container exited, while
    # printing a success line.
    if out is None and _od:
        out = os.path.join(OUTDIR, 'triage_report.html')
    if '--version' in sys.argv:
        print(f'htx-triage {VERSION}  rules={rules_fingerprint()}')
        raise SystemExit(0)
    if '--selftest' in sys.argv:
        selftest()
    elif '--html' in sys.argv:
        import triage_report
        path, n = triage_report.build(args or SAMPLES, comparators=comparators,
                                      # abspath against the CWD, not ROOT. Run from the repo root
                                      # this is identical to the old behaviour; inside a container
                                      # ROOT is /opt/htx, which is not where outputs belong and is
                                      # not writable by the task user.
                                      **({'out': os.path.abspath(out)} if out else {}))
        # Plain path when the output is outside ROOT. relpath against ROOT renders a
        # container path as ../../data/out/... which reads as a mistake, not a location.
        shown = os.path.relpath(path, ROOT) if path.startswith(ROOT + os.sep) else path
        print(f'{shown}: {n} sample(s), '
              f'{os.path.getsize(path)/1024:.0f} KB, self-contained')
    else:
        run(args or SAMPLES, comparators)
