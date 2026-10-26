#!/usr/bin/env python3
"""Export triage_rules.json as a human reference: Markdown + Excel.

    python3 analysis/export_rules.py

Writes docs/reference_rules.md and analysis/triage_rules.xlsx. Both are generated
artefacts — edit triage_rules.json, never these. The PFIDB column is an exact-string
check against PFI_DB/PFIDB_v5_0.xlsx, because triage.py matches taxon names with
dict.get(): a name that differs by one character never fires.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = json.load(open(os.path.join(ROOT, 'analysis', 'triage_rules.json')))
PFIDB = os.path.join(ROOT, 'PFI_DB', 'PFIDB_v5_0.xlsx')


def pfidb_names():
    """Species names in PFIDB v5, or an empty set if the workbook is not present."""
    try:
        import openpyxl
    except ImportError:
        return set()
    if not os.path.exists(PFIDB):
        return set()
    ws = openpyxl.load_workbook(PFIDB, read_only=True).active
    return {str(r[0]).strip() for r in ws.iter_rows(values_only=True) if r[0]}


def entries(section):
    return {k: v for k, v in RULES[section].items() if k != '_comment' and isinstance(v, dict)}


def rows():
    """Every export table, as (sheet_name, header, list-of-rows). One definition, two writers."""
    db = pfidb_names()
    hit = (lambda n: ('yes' if n in db else 'NO - name mismatch')) if db else (lambda n: 'not checked')

    thr = [[n, v.get('taxid', ''), v['tier'], v['genome'],
            ', '.join(v['markers']) or '-',
            ', '.join(v.get('supporting_markers', [])) or '-',
            'two-way' if v['markers'] else ('one-way' if v.get('supporting_markers') else 'none'),
            v.get('subspecies_required', ''),
            ', '.join(v['near_neighbours']) or '-',
            hit(n)]
           for n, v in sorted(entries('threat_list').items(), key=lambda x: (x[1]['tier'], x[0]))]

    watch = [[n, v.get('taxid', ''), v['priority'], ', '.join(v['escalating_classes']),
              v['note'], hit(n)]
             for n, v in sorted(entries('clinical_watchlist').items())]

    users = {}
    for n, v in entries('threat_list').items():
        for m in v['markers']:
            users.setdefault(m, []).append(n + ' (two-way)')
        for m in v.get('supporting_markers', []):
            users.setdefault(m, []).append(n + ' (one-way)')
    mark = [[m, pat, ', '.join(users.get(m, [])) or '- unused -']
            for m, pat in sorted(RULES['marker_patterns'].items())]

    amr = [[g, v.get('class', ''), v.get('drug', ''), v.get('requires', ''), v.get('why', '')]
           for g, v in sorted(RULES['amr_classes'].items()) if isinstance(v, dict)]

    mech = [[k] + k.split('|') + [v] for k, v in sorted(RULES['mechanism_classes'].items())
            if isinstance(v, str) and '|' in k]

    hints = [[g, ', '.join(v.get('taxa', [])), v.get('basis', '')]
             for g, v in sorted(RULES['amr_host_hints'].items()) if isinstance(v, dict)]

    # The decision table: one row per rule, in the order the gates run, with the live threshold
    # values pulled from the JSON so this view can never drift from what the engine applies.
    # The JSON remains the compiled, loaded form; this is the version a microbiologist argues with.
    # ponytail: generated view, not the source. Inverting that (table -> JSON compiler) is the
    # next step once the thresholds stop moving.
    T = RULES['thresholds']
    ct = RULES['class_thresholds'].get('acquired', {})
    table = [
        ['QC.FLOOR', 'every swab', 'Classified_Read', f'< {T["qc_classified_floor"]:,}',
         'flag QC-LIMITED (never a verdict)', 'a negative from a thin swab carries no weight', 'independent review 2026-10-26'],
        ['QC.RNA', 'every swab', 'showRNA', 'false',
         'flag NOT-TESTED; one standing row for all RNA agents', 'absence of a test is not absence', 'assay design'],
        ['GENE.ONE_PER_GROUP', 'every MEGARes row', 'Group', 'collapse alleles',
         'keep the allele best on breadth AND depth', 'one gene recruits reads onto several accessions', 'gate 3'],
        ['GENE.BREADTH_FLOOR', 'every gene', 'Coverage(%)', f'< {T["gene_breadth_floor"]}',
         'NO_ACTION', 'a fragment is not a gene', 'gate 4'],
        ['GENE.INTRINSIC', 'rRNA / efflux / intrinsic / environmental class', 'amr_classes, mechanism_classes',
         'class in suppressed set', 'NO_ACTION', 'presence is the default state', 'gate 5'],
        ['GENE.ACQUIRED', 'class = acquired, short reads', 'Coverage(%), Depth',
         f'>= {ct.get("breadth", T["gene_breadth_confident"])} and >= {ct.get("depth", T["gene_depth_confident"])} -> full; '
         f'>= {ct.get("partial_breadth", "-")} and >= {ct.get("partial_depth", "-")} -> partial',
         'CONFIRM (ceiling for any gene)', 'breadth separates a gene from a conserved fragment', 'class_thresholds.acquired'],
        ['TAX.RNA', 'threat-list agent, genome = RNA, DNA library', 'threat_list.genome', 'RNA',
         'NOT_TESTED', 'structurally undetectable', 'gate 2'],
        ['TAX.READ_FLOOR', 'every species row', 'Real Read', f'< {T["min_real_reads"]}',
         'listed -> NO_ACTION with the count; unlisted -> drop', 'below this a call is cross-mapping or background', 'gate 1'],
        ['TAX.INFLATION', 'every species row', 'Estimate Read / Real Read', f'> {T["bracken_inflation_ratio"]}',
         'judge on Real Read only; note it', 'Bracken redistribution inflates estimates', 'gate 7'],
        ['TAX.COMPARATORS', 'every swab', 'site_id prior runs', f'>= {T["site_history_min_runs"]} runs at this site',
         'compare against own history; else every other sample', 'is it new HERE, not new anywhere', 'gate 8, 2026-10-26'],
        ['TAX.ENRICHED', 'listed or unlisted taxon, comparators present', 'reads per million vs max comparator',
         f'>= {T["enrichment_fold"]}x', 'candidate (unlisted -> MONITOR; listed -> may escalate)',
         'site-specific, not batch background', 'gate 8'],
        ['TAX.GENUS_RATIO', 'listed taxon, comparators present', 'species share of its genus here / best elsewhere',
         'reported always; gates only if genus_ratio_min is set' + (f' ({T["genus_ratio_min"]})' if T.get('genus_ratio_min') is not None else ''),
         'batch-robust second opinion on TAX.ENRICHED', 'a kit artefact moves the whole genus together', 'gate 8, 2026-10-26'],
        ['TAX.NO_COMPARATORS', 'watchlist taxon, no comparators', 'Abundance', f'>= {T["watchlist_min_abundance_no_comparators"]}%',
         'counts as enriched', 'the only criterion measurable inside one sample', 'gate 8 fallback'],
        ['TAX.KITOME', 'unlisted taxon, no comparators', 'genus', 'in kitome_genera', 'drop',
         'reagent contaminants never enrich', 'gate 8 fallback'],
        ['TAX.NEAR_NEIGHBOUR', 'threat-list agent', 'near-neighbour reads', '>= this taxon',
         'CONFIRM -> NO_ACTION', 'cross-mapping cannot be excluded', 'gate 9'],
        ['TAX.MARKER', 'threat-list agent with markers', 'VFDB Virulence Factor, Coverage(%)',
         f'pattern match at >= {T["marker_breadth_floor"]}% breadth', 'present -> ESCALATE; absent -> NO_ACTION',
         'the marker is what makes the agent a threat', 'gate 10a'],
        ['TAX.MARKER_POWER', 'threat-list agent with markers', 'P(a read lands on the marker)',
         f'< {T["marker_power_min"]}', 'absent -> NOT_TESTED instead of NO_ACTION', 'a test with no power is not evidence', 'gate 10a'],
        ['TAX.SUPPORTING', 'threat-list agent with supporting markers', 'VFDB rows of this species', 'present',
         'ESCALATE; absent changes nothing', 'one-way: VFDB coverage cannot be certified', 'gate 10b'],
        ['TAX.SUBSPECIES', 'threat-list agent with subspecies_required at CONFIRM', 'subspeciesData',
         f'notifiable serovar named, Real Read >= {T["min_real_reads"]}', 'keep CONFIRM; else MONITOR',
         'the threat is defined below species rank', 'gate 10c, 2026-10-26'],
        ['TAX.WATCHLIST_ESC', 'watchlist taxon, enriched', 'co-located acquired gene class, host share',
         f'class in escalating_classes and share >= {T["escalation_host_share"]} or tops pool',
         'CONFIRM (culture with AST)', 'co-location, not co-attribution', 'gate 1b'],
        ['TAX.WATCHLIST_MARKER', 'watchlist taxon with markers', 'VFDB rows of this species', 'present',
         'CONFIRM; absent changes nothing', 'one-way; C. diphtheriae tox', 'gate 1b, 2026-10-26'],
        ['SAMPLE.VERDICT', 'every swab', 'row verdicts', 'ESCALATE row -> ESCALATE; CONFIRM row, high-consequence gene, '
         'site-enriched listed taxon, or listed taxon topping a CONFIRM gene -> REVIEW; else NO ACTION',
         'NO ACTION / REVIEW / ESCALATE', 'three responses: file, look, send a team', 'sample_verdict, 2026-10-26'],
    ]

    thresh = [[k, str(v)] for k, v in sorted(RULES['thresholds'].items())]
    for sect in ('class_thresholds', 'group_thresholds', 'long_read_thresholds'):
        for k, v in sorted(RULES[sect].items()):
            if isinstance(v, dict):
                thresh.append([f'{sect}.{k}', json.dumps({a: b for a, b in v.items()
                                                          if not a.startswith('_') and a != 'why'})])

    return [
        ('decision_table', ['id', 'when', 'input', 'test', 'then', 'why', 'source'], table),
        ('threat_list', ['Species', 'Taxid', 'CDC tier', 'Genome', 'Confirmatory markers (two-way)',
                         'Supporting markers (one-way)', 'Gate 10 mode', 'Subspecies required',
                         'Near neighbours', 'In PFIDB v5'], thr),
        ('clinical_watchlist', ['Species', 'Taxid', 'Priority', 'Escalating AMR classes',
                                'Note', 'In PFIDB v5'], watch),
        ('marker_patterns', ['Marker', 'Regex', 'Used by'], mark),
        ('amr_classes', ['MEGARes group', 'Class', 'Drug', 'Requires', 'Why'], amr),
        ('mechanism_classes', ['Key', 'Type', 'Mechanism', 'Class'], mech),
        ('amr_host_hints', ['MEGARes group', 'Expected host genera', 'Basis'], hints),
        ('kitome_genera', ['Genus'], [[x] for x in sorted(RULES['kitome_genera'])]),
        ('taxonomy_notes', ['Species', 'Note'], sorted(RULES['taxonomy_notes'].items())),
        ('thresholds', ['Setting', 'Value'], thresh),
    ]


def write_markdown(tables, path):
    esc = lambda c: str(c).replace('|', r'\|').replace('\n', ' ')
    out = ['# Rule-file reference — species, markers and thresholds', '',
           'Generated by `analysis/export_rules.py` from `analysis/triage_rules.json`.',
           '**Do not edit this file** — edit the JSON and re-run the exporter.', '',
           'The *In PFIDB v5* column is an exact-string check against `PFI_DB/PFIDB_v5_0.xlsx`.',
           'Since the taxid keying change this is advisory, not fatal: `triage.py` matches on',
           '`Taxid` first and falls back to the name. A `NO - name mismatch` row still fires,',
           'but only for reports that carry a taxid column.', '',
           'The first table is the **decision table**: every rule the engine applies, one row',
           'each, in the order the gates run, with the live threshold values. Read it top to',
           'bottom and you have read the engine. The tables after it are the lists those rules',
           'look things up in.', '']
    for name, header, data in tables:
        out += [f'## {name} — {len(data)} entries', '',
                '| ' + ' | '.join(header) + ' |',
                '|' + '|'.join('---' for _ in header) + '|']
        out += ['| ' + ' | '.join(esc(c) for c in r) + ' |' for r in data]
        out += ['']
    open(path, 'w').write('\n'.join(out))


def write_excel(tables, path):
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment
    except ImportError:
        return None
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, header, data in tables:
        ws = wb.create_sheet(name[:31])
        ws.append(header)
        for c in ws[1]:
            c.font = Font(bold=True)
            c.alignment = Alignment(vertical='top', wrap_text=True)
        for r in data:
            ws.append([str(c) for c in r])
        for i, h in enumerate(header, 1):
            width = max([len(h)] + [len(str(r[i - 1])) for r in data if i <= len(r)])
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = min(60, width + 2)
        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = ws.dimensions
    wb.save(path)
    return path


if __name__ == '__main__':
    tables = rows()
    md = os.path.join(ROOT, 'docs', 'reference_rules.md')
    xl = os.path.join(ROOT, 'analysis', 'triage_rules.xlsx')
    write_markdown(tables, md)
    got = write_excel(tables, xl)
    for name, _h, data in tables:
        print(f'  {name:20} {len(data):4} rows')
    print(f'\n{os.path.relpath(md, ROOT)}  ({os.path.getsize(md)/1024:.0f} KB)')
    print(f'{os.path.relpath(xl, ROOT)}' if got else 'openpyxl not installed - Excel skipped')
